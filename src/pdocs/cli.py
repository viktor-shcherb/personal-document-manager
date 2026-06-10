from __future__ import annotations

import argparse
import json
import secrets as secret_generator
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

from .backup import GoogleDriveBackupAuth, install_backup_workflow
from .config import AppConfig, load_config, repository_secret_locator
from .crypto import GpgSymmetricCipher
from .gmail import GmailSource
from .keychain import MacOSKeychain
from .records import (
    add_record,
    extract_record,
    list_records,
    read_metadata,
    record_path,
)
from .state import ReviewState
from .view import build_view_from_head


def _runtime(config_path: str | None):
    config = load_config(config_path)
    keychain = MacOSKeychain()
    cipher = GpgSymmetricCipher(config, keychain)
    return config, keychain, cipher


def _print_candidates(candidates) -> None:
    for candidate in candidates:
        attachment = " attachment" if candidate.has_attachments else ""
        print(
            f"{candidate.reference}\t{candidate.received_at}\t"
            f"{candidate.sender}\t{candidate.subject}{attachment}"
        )


def _validate_record_input(config: AppConfig, args) -> None:
    domains = tuple(config.raw.get("taxonomy", {}).get("domains", ()))
    if domains and args.domain not in domains:
        allowed = ", ".join(domains)
        raise ValueError(
            f"Unknown domain {args.domain!r}; configured domains: {allowed}"
        )
    if args.issued_at:
        try:
            parsed = date.fromisoformat(args.issued_at)
        except ValueError as error:
            raise ValueError("Issue date must use YYYY-MM-DD") from error
        if parsed.isoformat() != args.issued_at:
            raise ValueError("Issue date must use YYYY-MM-DD")


def _repair_keychain_access(
    config: AppConfig,
    keychain: MacOSKeychain,
) -> None:
    locator = repository_secret_locator(config)
    keychain.repair_access(locator.service, locator.account)


def _initialize_repository_secret(
    config: AppConfig,
    keychain: MacOSKeychain,
) -> None:
    locator = repository_secret_locator(config)
    keychain.create(
        locator.service,
        locator.account,
        secret_generator.token_urlsafe(48),
    )


def cmd_check(config: AppConfig, keychain: MacOSKeychain) -> None:
    errors = []
    configured_paths = {
        "vault": config.paths.vault,
        "inbox": config.paths.inbox,
        "readable": config.paths.readable,
    }
    path_items = list(configured_paths.items())
    for index, (left_name, left) in enumerate(path_items):
        for right_name, right in path_items[index + 1 :]:
            if left == right or left in right.parents or right in left.parents:
                errors.append(
                    f"{left_name} and {right_name} paths must be separate and non-nested"
                )
    if not shutil.which(config.security.gpg_binary):
        errors.append(f"GnuPG binary not found: {config.security.gpg_binary}")
    locator = repository_secret_locator(config)
    try:
        keychain.get(locator.service, locator.account)
        secret_status = "available"
    except Exception:
        secret_status = "missing"
        errors.append("Repository encryption secret is missing")
    git_status = "not initialized"
    git_changes = []
    if (config.paths.vault / ".git").exists():
        result = subprocess.run(
            ["git", "status", "--short", "--branch", "--untracked-files=all"],
            cwd=config.paths.vault,
            text=True,
            capture_output=True,
        )
        lines = result.stdout.splitlines()
        git_status = lines[0] if lines else "initialized"
        git_changes = lines[1:]
    else:
        errors.append("Vault is not a Git repository")
    print(f"config: {config.path}")
    print(f"deployment: {config.deployment.id}")
    print(f"vault: {config.paths.vault}")
    print(f"inbox: {config.paths.inbox}")
    print(f"readable: {config.paths.readable}")
    print(f"encryption secret: {secret_status}")
    print(f"git: {git_status}")
    if git_changes:
        print(f"working tree: {len(git_changes)} change(s)")
        for change in git_changes:
            print(f"  {change}")
    else:
        print("working tree: clean")
    if errors:
        sys.stdout.flush()
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pdocs",
        description="Maintain an encrypted, Git-versioned personal document vault.",
    )
    parser.add_argument("--config", help="Path to deployment configuration")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "check",
        help="Validate configuration, encryption, paths, and Git state.",
    )

    secrets_parser = commands.add_parser(
        "secrets",
        help="Initialize or verify the vault encryption secret.",
    )
    secrets_commands = secrets_parser.add_subparsers(
        dest="secrets_command", required=True
    )
    secrets_commands.add_parser(
        "init",
        help="Generate and store a new vault encryption secret.",
    )
    secrets_commands.add_parser(
        "repair-access",
        help="Reset Keychain access control without changing the secret.",
    )
    secrets_commands.add_parser(
        "status",
        help="Verify that the vault encryption secret is available.",
    )

    record_parser = commands.add_parser(
        "record",
        help="Add, inspect, list, or extract encrypted records.",
    )
    record_commands = record_parser.add_subparsers(dest="record_command", required=True)
    add = record_commands.add_parser(
        "add",
        help="Encrypt a source file as a new or replacement record.",
    )
    add.add_argument("path", type=Path, help="Original file to preserve.")
    add.add_argument("--id", required=True, help="Stable slash-separated record ID.")
    add.add_argument("--title", required=True, help="Human-readable record title.")
    add.add_argument("--domain", required=True, help="Configured document domain.")
    add.add_argument("--owner", required=True, help="Record owner identifier.")
    add.add_argument(
        "--lifecycle",
        required=True,
        choices=["replaceable", "event"],
        help="Whether the stable slot may be replaced or is immutable.",
    )
    add.add_argument("--issued-at", help="Issue date, preferably YYYY-MM-DD.")
    add.add_argument(
        "--source-kind",
        default="local",
        help="Provenance type, such as local or gmail.",
    )
    add.add_argument("--source-ref", help="Source message or artifact reference.")
    add.add_argument("--thread-ref", help="Source thread reference.")
    add.add_argument("--notes", help="Short factual context.")
    list_command = record_commands.add_parser(
        "list",
        help="List current record slots.",
    )
    list_command.add_argument(
        "--json",
        action="store_true",
        help="Print complete record metadata as JSON.",
    )
    show = record_commands.add_parser(
        "show",
        help="Print complete metadata for one record.",
    )
    show.add_argument("record_id", help="Record ID to inspect.")
    extract = record_commands.add_parser(
        "extract",
        help="Decrypt one original file to an explicit output path.",
    )
    extract.add_argument("record_id", help="Record ID to extract.")
    extract.add_argument("--output", type=Path, required=True, help="Output path.")

    view_parser = commands.add_parser(
        "view",
        help="Build the disposable plaintext view from committed records.",
    )
    view_commands = view_parser.add_subparsers(dest="view_command", required=True)
    view_commands.add_parser(
        "build",
        help="Replace the readable view with records from Git HEAD.",
    )

    gmail_parser = commands.add_parser(
        "gmail",
        help="Discover, inspect, and export Gmail messages.",
    )
    gmail_commands = gmail_parser.add_subparsers(dest="gmail_command", required=True)
    gmail_auth = gmail_commands.add_parser("auth")
    gmail_auth.add_argument(
        "--replace-existing",
        action="store_true",
        help="Deliberately replace the token for the configured Gmail account.",
    )
    search = gmail_commands.add_parser("search")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=50)
    scan = gmail_commands.add_parser("scan")
    scan.add_argument("--query", action="append")
    scan.add_argument("--limit", type=int, default=50)
    show_mail = gmail_commands.add_parser("show")
    show_mail.add_argument("message_id")
    thread = gmail_commands.add_parser("thread")
    thread.add_argument("thread_id")
    export = gmail_commands.add_parser("export")
    export.add_argument("message_id")
    reviewed = gmail_commands.add_parser("reviewed")
    reviewed.add_argument("message_ids", nargs="+")

    backup_parser = commands.add_parser(
        "backup",
        help="Authorize and install Google Drive Git-history backups.",
    )
    backup_commands = backup_parser.add_subparsers(dest="backup_command", required=True)
    backup_auth = backup_commands.add_parser("auth")
    backup_auth.add_argument(
        "--replace-existing",
        action="store_true",
        help="Deliberately replace the token for the configured Drive account.",
    )
    backup_commands.add_parser("status")
    github_secrets = backup_commands.add_parser("github-secrets")
    github_secrets.add_argument("--repository", required=True)
    install_workflow = backup_commands.add_parser("install-workflow")
    install_workflow.add_argument("--action-ref", default="v1")
    install_workflow.add_argument("--force", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        config, keychain, cipher = _runtime(args.config)
        if args.command == "check":
            cmd_check(config, keychain)
        elif args.command == "secrets":
            if args.secrets_command == "init":
                _initialize_repository_secret(
                    config,
                    keychain,
                )
                print(
                    "Repository encryption secret stored in macOS Keychain "
                    "with access granted to this CLI runtime"
                )
            elif args.secrets_command == "status":
                locator = repository_secret_locator(config)
                keychain.get(locator.service, locator.account)
                print("Repository encryption secret is available")
            elif args.secrets_command == "repair-access":
                _repair_keychain_access(config, keychain)
                print(
                    "Keychain access repaired without changing the repository "
                    "encryption secret"
                )
        elif args.command == "record":
            if args.record_command == "add":
                _validate_record_input(config, args)
                source_path = args.path.expanduser().resolve()
                destination = record_path(config.paths.vault, args.id)
                existed = destination.exists()
                destination = add_record(
                    vault=config.paths.vault,
                    cipher=cipher,
                    source_path=source_path,
                    record_id=args.id,
                    title=args.title,
                    domain=args.domain,
                    owner=args.owner,
                    lifecycle=args.lifecycle,
                    issued_at=args.issued_at,
                    source_kind=args.source_kind,
                    source_reference=args.source_ref,
                    thread_reference=args.thread_ref,
                    notes=args.notes,
                )
                action = "Updated" if existed else "Added"
                print(f"{action} {args.lifecycle} record: {args.id}")
                print(f"source: {source_path}")
                print(f"stored: {destination}")
                if existed:
                    print(
                        "history: Git preserves the prior committed issue after "
                        "this change is committed"
                    )
            elif args.record_command == "list":
                records = list_records(config.paths.vault, cipher)
                if args.json:
                    print(
                        json.dumps(
                            records,
                            indent=2,
                            ensure_ascii=False,
                        )
                    )
                elif not records:
                    print("No records found.")
                else:
                    print("ID\tLIFECYCLE\tISSUED\tOWNER\tTITLE")
                    for record in records:
                        print(
                            f"{record['id']}\t{record['lifecycle']}\t"
                            f"{record.get('issued_at') or '-'}\t"
                            f"{record['owner']}\t{record['title']}"
                        )
            elif args.record_command == "show":
                print(
                    json.dumps(
                        read_metadata(
                            record_path(config.paths.vault, args.record_id),
                            cipher,
                        ),
                        indent=2,
                        ensure_ascii=False,
                    )
                )
            elif args.record_command == "extract":
                destination = extract_record(
                    config.paths.vault,
                    cipher,
                    args.record_id,
                    args.output.expanduser().resolve(),
                )
                print(f"Extracted record {args.record_id} to: {destination}")
        elif args.command == "view":
            changes = subprocess.run(
                [
                    "git",
                    "status",
                    "--short",
                    "--untracked-files=all",
                    "--",
                    "records",
                ],
                cwd=config.paths.vault,
                check=True,
                text=True,
                capture_output=True,
            ).stdout.splitlines()
            count = build_view_from_head(
                config.paths.vault,
                config.paths.readable,
                cipher,
            )
            commit = subprocess.run(
                ["git", "rev-parse", "--short=12", "HEAD"],
                cwd=config.paths.vault,
                check=True,
                text=True,
                capture_output=True,
            ).stdout.strip()
            print(
                f"Built readable view from commit {commit}: "
                f"{count} record(s) -> {config.paths.readable}"
            )
            if changes:
                print(f"warning: ignored {len(changes)} uncommitted record change(s):")
                for change in changes:
                    print(f"  {change}")
        elif args.command == "gmail":
            gmail = GmailSource(config, keychain)
            state = ReviewState(config.paths.state)
            if args.gmail_command == "auth":
                gmail.authorize(replace_existing=args.replace_existing)
                print("Gmail read-only OAuth token stored in macOS Keychain")
            elif args.gmail_command == "search":
                _print_candidates(gmail.search(args.query, args.limit))
            elif args.gmail_command == "scan":
                queries = args.query or list(config.gmail.scan_queries)
                candidates = []
                seen = set()
                for query in queries:
                    for candidate in gmail.search(query, args.limit):
                        if candidate.reference not in seen:
                            candidates.append(candidate)
                            seen.add(candidate.reference)
                pending = set(state.pending([item.reference for item in candidates]))
                _print_candidates(
                    [item for item in candidates if item.reference in pending]
                )
            elif args.gmail_command == "show":
                print(
                    json.dumps(
                        gmail.inspect(args.message_id),
                        indent=2,
                        ensure_ascii=False,
                    )
                )
            elif args.gmail_command == "thread":
                print(
                    json.dumps(
                        gmail.inspect_thread(args.thread_id),
                        indent=2,
                        ensure_ascii=False,
                    )
                )
            elif args.gmail_command == "export":
                print(gmail.export(args.message_id))
                state.mark([args.message_id])
            elif args.gmail_command == "reviewed":
                state.mark(args.message_ids)
                print(f"Marked {len(args.message_ids)} message(s) reviewed")
        elif args.command == "backup":
            backup = GoogleDriveBackupAuth(config, keychain)
            if args.backup_command == "auth":
                backup.authorize(replace_existing=args.replace_existing)
                print("Google Drive OAuth token stored in macOS Keychain")
            elif args.backup_command == "status":
                backup.token_data()
                print("Google Drive backup credentials are available")
            elif args.backup_command == "github-secrets":
                backup.configure_github(args.repository)
                print(f"Google Drive backup secrets configured for {args.repository}")
            elif args.backup_command == "install-workflow":
                destination = install_backup_workflow(
                    config.paths.vault,
                    action_ref=args.action_ref,
                    folder_name=config.backup.folder_name,
                    force=args.force,
                )
                print(f"Installed Google Drive backup workflow: {destination}")
                print("next: commit and push the workflow in the private vault")
    except (KeyError, OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
