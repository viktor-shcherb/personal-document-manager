# Interfaces

The project has narrow extension boundaries. They exist to keep personal
document policy independent from current providers, not to turn the project
into a general storage framework.

## Record Model

A record is the unit stored in Git.

Two lifecycle types are supported:

- `replaceable`: a stable logical slot, such as `identity/passport` or
  `employment/acme/contract`. A new issue replaces the encrypted file at the
  same path. Git retains earlier issues.
- `event`: an immutable occurrence, such as an important email, decision,
  signed notice, or receipt. Its identifier must be unique.

Every record contains:

- a stable identifier
- title, domain, owner, and lifecycle
- issue and import dates when known
- source provenance
- original filename and media type
- SHA-256 checksum
- the original file bytes

## Source Interface

A source implementation must support three operations:

```text
discover(query) -> candidate summaries
inspect(source reference) -> content suitable for agent review
export(source reference, inbox) -> original artifact plus provenance
```

Implemented:

- local files
- Gmail through read-only OAuth

Possible later extensions include IMAP, scanners, or cloud drives. They should
produce the same inbox artifacts rather than bypassing record review.

## Secret Interface

A secret store must retrieve and update named values without printing them.

Implemented:

- macOS Keychain through `/usr/bin/security`

Secrets include the repository encryption passphrase and Gmail OAuth token.
Secret files and recovery material never enter Git.

## Cipher Interface

A cipher must seal and unseal a byte stream using a secret obtained from the
secret interface.

Implemented:

- GnuPG symmetric encryption

The encrypted `.pdoc` format does not depend on Gmail, GitHub, or the readable
view.

## Record Store Interface

The record store maps a record identifier to one encrypted `.pdoc` file.

Implemented:

- local filesystem under `records/`, versioned by Git

GitHub is a remote for the Git repository, not a record-store API. Agents use
ordinary Git commands for review, commit, and push.

## Readable View Interface

The view materializes encrypted records from the latest Git commit into a
plaintext directory outside Git. It never includes uncommitted changes. It is
derived, replaceable, and never canonical.

Implemented:

- local filesystem view with an `INDEX.json`

## Policy Versus Mechanism

Configuration controls paths, providers, domains, scan queries, and approval
thresholds. Agent policy decides whether a candidate is a durable record, which
record it supersedes, who owns it, and whether correspondence has evidentiary
value.

Backup is outside the current interface set and will be designed separately.
