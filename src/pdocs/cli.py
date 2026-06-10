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
from .folder_exchange import export_view_to_folder, resolve_views_folder
from .gmail import GmailSource
from .keychain import MacOSKeychain
from .preferences import PreferenceStore
from .records import (
    add_record,
    extract_record,
    list_records,
    read_metadata,
    record_path,
)
from .state import ReviewState
from .source_ledger import SourceLedger, source_key
from .source_runs import (
    folder_profile,
    folder_source_identity,
    gmail_profile,
    gmail_source_identity,
    run_folder_source,
    run_gmail_source,
)
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


def _print_source_run(result) -> None:
    print(f"source key: {result.source_key}")
    print(f"run: {result.run_id}")
    if result.query:
        print(f"query: {result.query}")
    print(f"items seen: {result.items_seen}")
    print(f"items exported: {result.items_exported}")
    print(f"duplicates skipped: {result.items_skipped_duplicate}")
    if result.batch:
        print(f"inbox batch: {result.batch}")
    print(f"encrypted ledger event: {result.ledger_event}")
    print("next: review the inbox batch, import selected records, then commit")
    print("      records/ and .pdocs/state/source-ledger/")


def _paths_overlap(left: Path, right: Path) -> bool:
    left = left.resolve()
    right = right.resolve()
    return left == right or left in right.parents or right in left.parents


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
            if _paths_overlap(left, right):
                errors.append(
                    f"{left_name} and {right_name} paths must be separate and non-nested"
                )
    for name, profile in config.sources.folder.items():
        external_paths = {
            "inbox": profile.inbox_path(),
            "views": profile.views_path(),
        }
        if _paths_overlap(external_paths["inbox"], external_paths["views"]):
            errors.append(
                f"folder source {name!r} inbox and views must be separate "
                "and non-nested"
            )
        for role, external in external_paths.items():
            for local_role, local in configured_paths.items():
                if _paths_overlap(external, local):
                    errors.append(
                        f"folder source {name!r} {role} must not overlap "
                        f"the configured {local_role} path"
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
    add.add_argument("--source-profile", help="Configured source profile name.")
    add.add_argument("--source-key", help="Stable source ledger key.")
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

    preference_parser = commands.add_parser(
        "preference",
        help="Remember encrypted inclusion and organization decisions.",
    )
    preference_commands = preference_parser.add_subparsers(
        dest="preference_command",
        required=True,
    )
    preference_list = preference_commands.add_parser(
        "list",
        help="List effective remembered preferences.",
    )
    preference_list.add_argument(
        "--scope",
        choices=["inclusion", "organization"],
    )
    preference_list.add_argument("--json", action="store_true")
    preference_show = preference_commands.add_parser(
        "show",
        help="Show one remembered preference.",
    )
    preference_show.add_argument("rule_id")
    preference_remember = preference_commands.add_parser(
        "remember",
        help="Record a user decision as an encrypted reusable rule.",
    )
    preference_remember_commands = preference_remember.add_subparsers(
        dest="preference_scope",
        required=True,
    )
    preference_inclusion = preference_remember_commands.add_parser(
        "inclusion",
        help="Remember whether a narrowly described document kind is retained.",
    )
    preference_inclusion.add_argument("--match", required=True)
    preference_inclusion.add_argument(
        "--decision",
        required=True,
        choices=["add", "skip"],
    )
    preference_inclusion.add_argument("--instruction")
    preference_inclusion.add_argument("--source-kind")
    preference_inclusion.add_argument("--source-profile")
    preference_organization = preference_remember_commands.add_parser(
        "organization",
        help="Remember how a narrowly described document kind is organized.",
    )
    preference_organization.add_argument("--match", required=True)
    preference_organization.add_argument("--instruction")
    preference_organization.add_argument("--domain")
    preference_organization.add_argument("--owner")
    preference_organization.add_argument(
        "--lifecycle",
        choices=["replaceable", "event"],
    )
    preference_organization.add_argument("--id-prefix")
    preference_organization.add_argument("--source-kind")
    preference_organization.add_argument("--source-profile")
    preference_forget = preference_commands.add_parser(
        "forget",
        help="Append an encrypted event that retires a preference.",
    )
    preference_forget.add_argument("rule_id")

    view_parser = commands.add_parser(
        "view",
        help="Build the disposable plaintext view from committed records.",
    )
    view_commands = view_parser.add_subparsers(dest="view_command", required=True)
    view_commands.add_parser(
        "build",
        help="Replace the readable view with records from Git HEAD.",
    )
    view_export = view_commands.add_parser(
        "export",
        help="Export the committed readable view to an external transport.",
    )
    view_export_commands = view_export.add_subparsers(
        dest="view_export_command",
        required=True,
    )
    view_export_folder = view_export_commands.add_parser(
        "folder",
        help="Export the committed readable view to a local folder transport.",
    )
    view_export_folder.add_argument(
        "--profile",
        default="default",
        help="Configured folder source profile.",
    )
    view_export_folder.add_argument(
        "--folder",
        type=Path,
        help="Explicit destination path instead of the profile's views folder.",
    )
    view_export_folder.add_argument(
        "--prune",
        action="store_true",
        help="Delete stale files previously managed by PDM.",
    )

    source_parser = commands.add_parser(
        "source",
        help="Run recurring sources using the encrypted shared ledger.",
    )
    source_commands = source_parser.add_subparsers(
        dest="source_command",
        required=True,
    )
    source_run = source_commands.add_parser(
        "run",
        help="Run a configured source and append a successful ledger event.",
    )
    source_run_commands = source_run.add_subparsers(
        dest="source_run_kind",
        required=True,
    )
    source_email = source_run_commands.add_parser(
        "email",
        aliases=["gmail"],
        help="Run an incremental Gmail source profile.",
    )
    source_email.add_argument(
        "--profile",
        default="default",
        help="Configured Gmail source profile.",
    )
    email_window = source_email.add_mutually_exclusive_group()
    email_window.add_argument(
        "--full",
        action="store_true",
        help="Scan all matching history while retaining exact deduplication.",
    )
    email_window.add_argument(
        "--since",
        help="Override the start with YYYY-MM-DD or an ISO 8601 timestamp.",
    )
    source_email.add_argument(
        "--overlap",
        help="Override this run's overlap duration, such as 48h.",
    )
    source_email.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum Gmail messages to inspect; use 0 for all matches.",
    )
    source_folder = source_run_commands.add_parser(
        "folder",
        help="Run a ledger-backed local folder source.",
    )
    source_folder.add_argument(
        "--profile",
        default="default",
        help="Configured folder source profile.",
    )
    source_folder.add_argument(
        "--folder",
        type=Path,
        help="Explicit source path instead of the profile's inbox folder.",
    )
    source_folder.add_argument(
        "--full",
        action="store_true",
        help="Rescan all files while retaining exact content deduplication.",
    )

    source_state = source_commands.add_parser(
        "state",
        help="Inspect or manage effective state replayed from the ledger.",
    )
    source_state_commands = source_state.add_subparsers(
        dest="source_state_command",
        required=True,
    )
    source_state_commands.add_parser("list")
    source_state_show = source_state_commands.add_parser("show")
    source_state_show.add_argument("kind", choices=["email", "gmail", "folder"])
    source_state_show.add_argument("--profile", default="default")
    source_state_show.add_argument("--folder", type=Path)
    source_state_reset = source_state_commands.add_parser("reset")
    source_state_reset.add_argument("kind", choices=["email", "gmail", "folder"])
    source_state_reset.add_argument("--profile", default="default")
    source_state_reset.add_argument("--folder", type=Path)
    source_state_commands.add_parser("rebuild")

    ingest_parser = commands.add_parser(
        "ingest",
        help="Stage documents from external transports for review.",
    )
    ingest_commands = ingest_parser.add_subparsers(
        dest="ingest_command",
        required=True,
    )
    ingest_folder = ingest_commands.add_parser(
        "folder",
        help="Stage new files through a ledger-backed folder source.",
    )
    ingest_folder.add_argument(
        "--profile",
        default="default",
        help="Configured folder source profile.",
    )
    ingest_folder.add_argument(
        "--folder",
        type=Path,
        help="Explicit source path instead of the profile's inbox folder.",
    )
    ingest_folder.add_argument(
        "--full",
        action="store_true",
        help="Rescan all files while retaining exact content deduplication.",
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
                    source_profile=args.source_profile,
                    source_key=args.source_key,
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
        elif args.command == "preference":
            preferences = PreferenceStore(config.paths.vault, cipher)
            if args.preference_command == "list":
                rules = [
                    rule.as_dict()
                    for rule in preferences.rules().values()
                    if not args.scope or rule.scope == args.scope
                ]
                if args.json:
                    print(json.dumps(rules, indent=2, ensure_ascii=False))
                elif not rules:
                    print("No remembered preferences.")
                else:
                    print("ID\tSCOPE\tDECISION\tMATCH")
                    for rule in rules:
                        print(
                            f"{rule['id']}\t{rule['scope']}\t"
                            f"{rule.get('decision') or '-'}\t{rule['match']}"
                        )
            elif args.preference_command == "show":
                rule = preferences.rule(args.rule_id)
                if not rule:
                    raise RuntimeError(f"Preference not found: {args.rule_id}")
                print(json.dumps(rule.as_dict(), indent=2, ensure_ascii=False))
            elif args.preference_command == "remember":
                rule, destination = preferences.remember(
                    scope=args.preference_scope,
                    match=args.match,
                    instruction=args.instruction,
                    source_kind=args.source_kind,
                    source_profile=args.source_profile,
                    decision=getattr(args, "decision", None),
                    domain=getattr(args, "domain", None),
                    owner=getattr(args, "owner", None),
                    lifecycle=getattr(args, "lifecycle", None),
                    id_prefix=getattr(args, "id_prefix", None),
                )
                print(f"Remembered preference: {rule.rule_id}")
                print(f"encrypted preference event: {destination}")
                print("next: commit .pdocs/state/preferences/ to share this decision")
            elif args.preference_command == "forget":
                destination = preferences.forget(args.rule_id)
                print(f"Forgot preference with encrypted event: {destination}")
                print("next: commit .pdocs/state/preferences/ to share this change")
        elif args.command == "view":
            if args.view_command == "build":
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
                    print(
                        f"warning: ignored {len(changes)} uncommitted record change(s):"
                    )
                    for change in changes:
                        print(f"  {change}")
            elif args.view_command == "export":
                profile = (
                    config.sources.folder.get(args.profile) if not args.folder else None
                )
                destination = resolve_views_folder(profile, args.folder)
                for role, local in (
                    ("vault", config.paths.vault),
                    ("local inbox", config.paths.inbox),
                    ("readable view", config.paths.readable),
                ):
                    if _paths_overlap(destination, local):
                        raise ValueError(
                            f"Folder export must not overlap the configured "
                            f"{role}: {destination}"
                        )
                result = export_view_to_folder(
                    vault=config.paths.vault,
                    destination=destination,
                    cipher=cipher,
                    prune=args.prune,
                )
                print(
                    f"Exported {result['records']} record(s), "
                    f"{result['files']} managed file(s) -> {destination}"
                )
                print(f"changed: {result['changed']}; pruned: {result['pruned']}")
        elif args.command == "source":
            ledger = SourceLedger(config.paths.vault, cipher)
            if args.source_command == "run":
                if args.source_run_kind in {"email", "gmail"}:
                    result = run_gmail_source(
                        config=config,
                        cipher=cipher,
                        gmail=GmailSource(config, keychain),
                        profile_name=args.profile,
                        full=args.full,
                        since=args.since,
                        overlap=args.overlap,
                        limit=args.limit,
                    )
                else:
                    result = run_folder_source(
                        config=config,
                        cipher=cipher,
                        profile_name=args.profile,
                        folder_override=args.folder,
                        full=args.full,
                    )
                _print_source_run(result)
            elif args.source_command == "state":
                if args.source_state_command == "list":
                    states = [state.as_dict() for state in ledger.states().values()]
                    print(json.dumps(states, indent=2, ensure_ascii=False))
                elif args.source_state_command in {"show", "reset"}:
                    if args.kind in {"email", "gmail"}:
                        if args.folder:
                            raise ValueError("--folder is valid only for folder state")
                        profile = gmail_profile(config, args.profile)
                        identity = gmail_source_identity(config, profile)
                        kind = "gmail"
                    else:
                        profile = folder_profile(
                            config,
                            args.profile,
                            args.folder,
                        )
                        identity = folder_source_identity(profile, args.folder)
                        kind = "folder"
                    key = source_key(kind, profile.name, identity)
                    if args.source_state_command == "show":
                        state = ledger.state(key)
                        if not state:
                            raise RuntimeError(
                                f"No source state found for {kind}:{profile.name}"
                            )
                        print(
                            json.dumps(
                                state.as_dict(),
                                indent=2,
                                ensure_ascii=False,
                            )
                        )
                    else:
                        destination = ledger.reset(
                            key,
                            kind=kind,
                            profile=profile.name,
                        )
                        print(f"Reset source state with encrypted event: {destination}")
                        print(
                            "next: commit .pdocs/state/source-ledger/ "
                            "to share the reset"
                        )
                elif args.source_state_command == "rebuild":
                    destination = ledger.rebuild_local_index(config.paths.state)
                    print(f"Rebuilt local source index: {destination}")
        elif args.command == "ingest":
            if args.ingest_command == "folder":
                result = run_folder_source(
                    config=config,
                    cipher=cipher,
                    profile_name=args.profile,
                    folder_override=args.folder,
                    full=args.full,
                )
                _print_source_run(result)
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
