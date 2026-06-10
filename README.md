# Personal Document Manager

A small, agent-oriented toolkit for maintaining a private personal document
repository.

It is designed around five practical properties:

1. Secrets stay in a system secret store, outside version control.
2. Canonical records are encrypted before entering Git.
3. Git preserves previous issues of replaceable records.
4. A readable view of the latest commit is generated outside the repository.
5. Each push replaces a verified full-history backup in Google Drive.

The initial implementation supports:

- macOS Keychain for secrets
- GnuPG symmetric encryption
- Gmail read-only discovery and `.eml` export
- a local Git repository with a private GitHub remote
- Google Drive backup of complete Git history through GitHub Actions
- a generated plaintext view of current records
- a Codex-compatible skill for agent maintenance

The interfaces remain replaceable, but this project does not include unused
provider implementations.

## Scope

This project manages deliberate personal records such as identity documents,
permits, education records, employment records, insurance, taxes, household
records, and important correspondence.

It is not:

- a full mailbox backup
- a password manager
- a general filesystem organizer
- an application-data or game-save backup
- an enterprise document-management platform

## Repository Layout

```text
config/profile.example.toml       Example deployment profile
docs/interfaces.md                Extension boundaries
docs/setup.md                     User setup
docs/faq.md                       OAuth and operational troubleshooting
docs/storage-format.md            Encrypted record format
.github/actions/                  Reusable Google Drive backup action
skills/manage-personal-documents/ Agent workflow
src/pdocs/                        Local command-line tool
```

## Quick Start

Read [docs/setup.md](docs/setup.md). After setup, the routine workflow is:

```bash
pdocs check
pdocs gmail scan
pdocs gmail show MESSAGE_ID
pdocs gmail thread THREAD_ID
pdocs gmail export MESSAGE_ID
pdocs record add FILE --id employment/example/contract \
  --title "Employment contract" \
  --domain employment \
  --owner self \
  --lifecycle replaceable
git add records
git commit -m "Update employment contract"
git push
pdocs view build
```

The vault's push workflow creates and verifies a complete Git bundle, then
replaces one stable app-managed file in Google Drive. See
[docs/backups.md](docs/backups.md).

## Security Boundary

The encrypted Git repository is canonical. The inbox and readable view contain
plaintext and must remain outside that repository. Commands never print
encryption passphrases or OAuth refresh tokens.

## License

MIT
