from __future__ import annotations

import hashlib
import http.client
import json
import os
import re
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, urlopen


TOKEN_URL = "https://oauth2.googleapis.com/token"
FILES_URL = "https://www.googleapis.com/drive/v3/files"
UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files"
FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
BUNDLE_MIME_TYPE = "application/x-git-bundle"
CHUNK_SIZE = 8 * 1024 * 1024
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class DriveBackupError(RuntimeError):
    pass


def _required_env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise DriveBackupError(f"Required environment variable is missing: {name}")
    return value


def _error_detail(error: HTTPError) -> str:
    body = error.read(2048).decode("utf-8", errors="replace").strip()
    return body or str(error.reason)


def _json_request(
    method: str,
    url: str,
    *,
    token: str | None = None,
    body: dict | None = None,
    form: dict | None = None,
) -> tuple[dict, dict[str, str]]:
    headers = {"Accept": "application/json"}
    data = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=UTF-8"
    elif form is not None:
        data = urlencode(form).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=60) as response:
            payload = response.read()
            result = json.loads(payload) if payload else {}
            return result, dict(response.headers.items())
    except HTTPError as error:
        raise DriveBackupError(
            f"Google API request failed with HTTP {error.code}: {_error_detail(error)}"
        ) from error
    except URLError as error:
        raise DriveBackupError(f"Google API request failed: {error.reason}") from error


def _access_token() -> str:
    response, _ = _json_request(
        "POST",
        TOKEN_URL,
        form={
            "client_id": _required_env("PDOCS_GOOGLE_CLIENT_ID"),
            "client_secret": _required_env("PDOCS_GOOGLE_CLIENT_SECRET"),
            "refresh_token": _required_env("PDOCS_GOOGLE_REFRESH_TOKEN"),
            "grant_type": "refresh_token",
        },
    )
    token = response.get("access_token")
    if not token:
        raise DriveBackupError("Google token response did not contain an access token")
    return token


def _escape_query(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _list_files(token: str, query: str) -> list[dict]:
    files = []
    page_token = None
    while True:
        parameters = {
            "q": query,
            "spaces": "drive",
            "pageSize": "100",
            "fields": (
                "nextPageToken,files("
                "id,name,mimeType,trashed,size,md5Checksum,appProperties)"
            ),
        }
        if page_token:
            parameters["pageToken"] = page_token
        response, _ = _json_request(
            "GET",
            f"{FILES_URL}?{urlencode(parameters)}",
            token=token,
        )
        files.extend(response.get("files", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            return files


def _one_or_none(files: list[dict], kind: str) -> dict | None:
    if len(files) > 1:
        ids = ", ".join(item["id"] for item in files)
        raise DriveBackupError(f"Multiple {kind} objects found in Drive: {ids}")
    return files[0] if files else None


def _get_file(token: str, file_id: str) -> dict:
    fields = "id,name,mimeType,trashed,size,md5Checksum,appProperties"
    response, _ = _json_request(
        "GET",
        f"{FILES_URL}/{quote(file_id, safe='')}?{urlencode({'fields': fields})}",
        token=token,
    )
    return response


def _folder(token: str) -> dict:
    configured_id = os.environ.get("PDOCS_DRIVE_FOLDER_ID", "")
    if configured_id:
        folder = _get_file(token, configured_id)
        if folder.get("trashed") or folder.get("mimeType") != FOLDER_MIME_TYPE:
            raise DriveBackupError("Configured Drive folder is missing or invalid")
        return folder

    query = (
        f"mimeType = '{FOLDER_MIME_TYPE}' and trashed = false and "
        "appProperties has { key='pdocs_kind' and value='backup_folder' }"
    )
    folder = _one_or_none(_list_files(token, query), "backup folder")
    if folder:
        return folder

    folder_name = os.environ.get("PDOCS_DRIVE_FOLDER_NAME", "Personal Document Backups")
    folder, _ = _json_request(
        "POST",
        f"{FILES_URL}?{urlencode({'fields': 'id,name,mimeType,trashed'})}",
        token=token,
        body={
            "name": folder_name,
            "mimeType": FOLDER_MIME_TYPE,
            "parents": ["root"],
            "appProperties": {"pdocs_kind": "backup_folder"},
        },
    )
    return folder


def _existing_backup(token: str, repository: str) -> dict | None:
    repository = _escape_query(repository)
    query = (
        "trashed = false and "
        "appProperties has "
        f"{{ key='pdocs_repository' and value='{repository}' }}"
    )
    return _one_or_none(_list_files(token, query), "repository backup")


def _initiate_upload(
    token: str,
    *,
    existing: dict | None,
    folder_id: str,
    backup_name: str,
    bundle_size: int,
    repository: str,
    commit: str,
) -> str:
    metadata = {
        "name": backup_name,
        "mimeType": BUNDLE_MIME_TYPE,
        "description": (
            f"Complete Git bundle for {repository}; latest pushed commit {commit}."
        ),
        "appProperties": {
            "pdocs_kind": "git_bundle",
            "pdocs_repository": repository,
            "pdocs_commit": commit,
            "pdocs_run_id": os.environ.get("GITHUB_RUN_ID", ""),
        },
    }
    if existing:
        method = "PATCH"
        endpoint = f"{UPLOAD_URL}/{quote(existing['id'], safe='')}"
    else:
        method = "POST"
        endpoint = UPLOAD_URL
        metadata["parents"] = [folder_id]

    parameters = urlencode(
        {
            "uploadType": "resumable",
            "fields": "id,name,size,md5Checksum,modifiedTime,appProperties",
        }
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json; charset=UTF-8",
        "X-Upload-Content-Type": BUNDLE_MIME_TYPE,
        "X-Upload-Content-Length": str(bundle_size),
    }
    data = json.dumps(metadata).encode("utf-8")
    request = Request(
        f"{endpoint}?{parameters}",
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urlopen(request, timeout=60) as response:
            location = response.headers.get("Location")
    except HTTPError as error:
        raise DriveBackupError(
            f"Unable to start Drive upload: HTTP {error.code}: {_error_detail(error)}"
        ) from error
    except URLError as error:
        raise DriveBackupError(
            f"Unable to start Drive upload: {error.reason}"
        ) from error
    if not location:
        raise DriveBackupError("Drive did not return a resumable upload URL")
    return location


def _session_put(
    session_url: str,
    body: bytes,
    headers: dict[str, str],
) -> tuple[int, dict[str, str], bytes]:
    parsed = urlsplit(session_url)
    if parsed.scheme != "https":
        raise DriveBackupError("Drive returned a non-HTTPS upload URL")
    path = parsed.path
    if parsed.query:
        path += f"?{parsed.query}"
    connection = http.client.HTTPSConnection(parsed.hostname, parsed.port, timeout=120)
    try:
        connection.request("PUT", path, body=body, headers=headers)
        response = connection.getresponse()
        payload = response.read()
        return response.status, dict(response.getheaders()), payload
    finally:
        connection.close()


def _acknowledged_offset(headers: dict[str, str]) -> int:
    uploaded_range = headers.get("Range") or headers.get("range")
    if not uploaded_range:
        return 0
    match = re.fullmatch(r"bytes=0-(\d+)", uploaded_range)
    if not match:
        raise DriveBackupError(f"Unexpected Drive upload range: {uploaded_range}")
    return int(match.group(1)) + 1


def _query_upload(session_url: str, total: int) -> tuple[int, dict | None]:
    for attempt in range(5):
        try:
            status, headers, payload = _session_put(
                session_url,
                b"",
                {
                    "Content-Length": "0",
                    "Content-Range": f"bytes */{total}",
                },
            )
        except OSError as error:
            if attempt == 4:
                raise DriveBackupError(
                    f"Unable to query Drive upload status: {error}"
                ) from error
            time.sleep(2**attempt)
            continue
        if status == 308:
            return _acknowledged_offset(headers), None
        if status in (200, 201):
            return total, json.loads(payload)
        if status in RETRYABLE_STATUS:
            time.sleep(2**attempt)
            continue
        detail = payload.decode("utf-8", errors="replace")[:2048]
        raise DriveBackupError(
            f"Drive upload status query failed with HTTP {status}: {detail}"
        )
    raise DriveBackupError("Drive upload status remained unavailable")


def _upload(session_url: str, path: Path) -> dict:
    total = path.stat().st_size
    if total <= 0:
        raise DriveBackupError("Git bundle is empty")
    offset = 0
    with path.open("rb") as handle:
        while offset < total:
            handle.seek(offset)
            chunk = handle.read(min(CHUNK_SIZE, total - offset))
            end = offset + len(chunk) - 1
            try:
                status, headers, payload = _session_put(
                    session_url,
                    chunk,
                    {
                        "Content-Length": str(len(chunk)),
                        "Content-Type": BUNDLE_MIME_TYPE,
                        "Content-Range": f"bytes {offset}-{end}/{total}",
                    },
                )
            except OSError:
                time.sleep(1)
                offset, result = _query_upload(session_url, total)
                if result:
                    return result
                continue
            if status == 308:
                offset = _acknowledged_offset(headers)
                print(f"Uploaded {offset} of {total} bytes")
                continue
            if status in (200, 201):
                return json.loads(payload)
            if status in RETRYABLE_STATUS:
                time.sleep(1)
                offset, result = _query_upload(session_url, total)
                if result:
                    return result
                continue
            detail = payload.decode("utf-8", errors="replace")[:2048]
            raise DriveBackupError(f"Drive upload failed with HTTP {status}: {detail}")
    raise DriveBackupError("Drive upload ended without file metadata")


def _md5(path: Path) -> str:
    digest = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_output(name: str, value: str) -> None:
    output = os.environ.get("GITHUB_OUTPUT")
    if not output:
        return
    with Path(output).open("a", encoding="utf-8") as handle:
        handle.write(f"{name}={value}\n")


def main() -> None:
    bundle = Path(_required_env("PDOCS_BUNDLE_PATH"))
    if not bundle.is_file():
        raise DriveBackupError(f"Git bundle does not exist: {bundle}")
    repository = _required_env("GITHUB_REPOSITORY")
    commit = _required_env("GITHUB_SHA")
    backup_name = os.environ.get("PDOCS_BACKUP_NAME") or (
        repository.replace("/", "-") + ".bundle"
    )

    token = _access_token()
    folder = _folder(token)
    existing = _existing_backup(token, repository)
    upload_url = _initiate_upload(
        token,
        existing=existing,
        folder_id=folder["id"],
        backup_name=backup_name,
        bundle_size=bundle.stat().st_size,
        repository=repository,
        commit=commit,
    )
    uploaded = _upload(upload_url, bundle)

    expected_size = bundle.stat().st_size
    expected_md5 = _md5(bundle)
    if int(uploaded.get("size", -1)) != expected_size:
        raise DriveBackupError("Drive reported a different backup size")
    if uploaded.get("md5Checksum") != expected_md5:
        raise DriveBackupError("Drive reported a different backup checksum")

    _write_output("file-id", uploaded["id"])
    _write_output("folder-id", folder["id"])
    _write_output("md5", expected_md5)
    print(
        f"Verified Google Drive backup {uploaded['id']}: "
        f"{expected_size} bytes, md5 {expected_md5}"
    )


if __name__ == "__main__":
    try:
        main()
    except DriveBackupError as error:
        raise SystemExit(f"error: {error}") from error
