from __future__ import annotations

import argparse
import json
import secrets as secret_generator
import shutil
import subprocess
import sys
from pathlib import Path

from .config import AppConfig, load_config
from .crypto import GpgSymmetricCipher
from .gmail import GmailSource
from .keychain import KeychainError, MacOSKeychain
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
    cipher = GpgSymmetricCipher(config.security, keychain)
    return config, keychain, cipher


def _print_candidates(candidates) -> None:
    for candidate in candidates:
        attachment = " attachment" if candidate.has_attachments else ""
        print(
            f"{candidate.reference}\t{candidate.received_at}\t"
            f"{candidate.sender}\t{candidate.subject}{attachment}"
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
    try:
        keychain.get(
            config.security.keychain_service,
            config.security.repository_key_account,
        )
        secret_status = "available"
    except Exception:
        secret_status = "missing"
        errors.append("Repository encryption secret is missing")
    git_status = "not initialized"
    if (config.paths.vault / ".git").exists():
        result = subprocess.run(
            ["git", "status", "--short", "--branch"],
            cwd=config.paths.vault,
            text=True,
            capture_output=True,
        )
        git_status = result.stdout.splitlines()[0] if result.stdout else "initialized"
    print(f"config: {config.path}")
    print(f"vault: {config.paths.vault}")
    print(f"inbox: {config.paths.inbox}")
    print(f"readable: {config.paths.readable}")
    print(f"encryption secret: {secret_status}")
    print(f"git: {git_status}")
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pdocs")
    parser.add_argument("--config", help="Path to deployment configuration")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check")

    secrets_parser = commands.add_parser("secrets")
    secrets_commands = secrets_parser.add_subparsers(
        dest="secrets_command", required=True
    )
    init_secret = secrets_commands.add_parser("init")
    init_secret.add_argument("--force", action="store_true")
    secrets_commands.add_parser("status")

    record_parser = commands.add_parser("record")
    record_commands = record_parser.add_subparsers(dest="record_command", required=True)
    add = record_commands.add_parser("add")
    add.add_argument("path", type=Path)
    add.add_argument("--id", required=True)
    add.add_argument("--title", required=True)
    add.add_argument("--domain", required=True)
    add.add_argument("--owner", required=True)
    add.add_argument("--lifecycle", required=True, choices=["replaceable", "event"])
    add.add_argument("--issued-at")
    add.add_argument("--source-kind", default="local")
    add.add_argument("--source-ref")
    add.add_argument("--thread-ref")
    add.add_argument("--notes")
    record_commands.add_parser("list")
    show = record_commands.add_parser("show")
    show.add_argument("record_id")
    extract = record_commands.add_parser("extract")
    extract.add_argument("record_id")
    extract.add_argument("--output", type=Path, required=True)

    view_parser = commands.add_parser("view")
    view_commands = view_parser.add_subparsers(dest="view_command", required=True)
    view_commands.add_parser("build")

    gmail_parser = commands.add_parser("gmail")
    gmail_commands = gmail_parser.add_subparsers(dest="gmail_command", required=True)
    gmail_commands.add_parser("auth")
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
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        config, keychain, cipher = _runtime(args.config)
        if args.command == "check":
            cmd_check(config, keychain)
        elif args.command == "secrets":
            if args.secrets_command == "init":
                if not args.force:
                    try:
                        keychain.get(
                            config.security.keychain_service,
                            config.security.repository_key_account,
                        )
                    except KeychainError:
                        pass
                    else:
                        raise RuntimeError(
                            "Repository encryption secret already exists; "
                            "use --force to replace it"
                        )
                keychain.set(
                    config.security.keychain_service,
                    config.security.repository_key_account,
                    secret_generator.token_urlsafe(48),
                )
                print("Repository encryption secret stored in macOS Keychain")
            else:
                keychain.get(
                    config.security.keychain_service,
                    config.security.repository_key_account,
                )
                print("Repository encryption secret is available")
        elif args.command == "record":
            if args.record_command == "add":
                destination = add_record(
                    vault=config.paths.vault,
                    cipher=cipher,
                    source_path=args.path.expanduser().resolve(),
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
                print(destination)
            elif args.record_command == "list":
                print(
                    json.dumps(
                        list_records(config.paths.vault, cipher),
                        indent=2,
                        ensure_ascii=False,
                    )
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
                print(
                    extract_record(
                        config.paths.vault,
                        cipher,
                        args.record_id,
                        args.output.expanduser().resolve(),
                    )
                )
        elif args.command == "view":
            count = build_view_from_head(
                config.paths.vault,
                config.paths.readable,
                cipher,
            )
            print(f"Materialized {count} records into {config.paths.readable}")
        elif args.command == "gmail":
            gmail = GmailSource(config, keychain)
            state = ReviewState(config.paths.state)
            if args.gmail_command == "auth":
                gmail.authorize()
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
    except (KeyError, OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
