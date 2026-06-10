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
- generic local folder intake for PDF, JPEG, PNG, and HEIC files

Possible later extensions include IMAP, scanners, or cloud drives. They should
produce the same inbox artifacts rather than bypassing record review.

## Source Ledger Interface

Recurring sources append encrypted completion and reset events under
`.pdocs/state/source-ledger/events/` in the vault. Replaying those events
derives the last successful source window and exact source/content identities.
Only a successful run writes an event.

The ledger is provider-neutral. Source adapters provide a stable source key,
source item identity, source time, and content checksum. Gmail uses message IDs
and internal timestamps. Folder intake uses profile-relative paths and content
hashes.

Locks, failure reports, and the rebuildable index are local state outside Git.
Agents pull before running a source and commit encrypted events with accepted
records so another device can replay the same progress.

## Secret Interface

A secret store must retrieve named values without printing them. Initial writes
must be create-only. Replacement must verify that the current value matches the
value previously read, so an unexpected or concurrent change fails instead of
being overwritten.

Implemented:

- macOS Keychain through Security.framework

Secrets include the repository encryption passphrase and Gmail OAuth token.
Secret files and recovery material never enter Git.

Repository encryption secrets are not replaceable in place. Keychain access
repair uses a verified temporary recovery item and removes it only after the
recreated original is verified.

Each deployment has a required UUID. The implementation derives fixed,
role-specific Keychain services and UUID-namespaced accounts, rather than
accepting arbitrary secret addresses from deployment configuration.

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
- folder export of the committed view with an app-owned manifest

Folder export updates only managed files. Deletion is opt-in through `--prune`
and never targets unrelated files.

## Backup Interface

A backup implementation has three responsibilities:

```text
snapshot(repository) -> complete repository artifact
verify_local(artifact) -> valid or error
replace_remote(artifact, repository identity) -> remote object reference
```

Implemented:

- a lossless Git bundle containing all fetched branches, tags, remote refs,
  and their reachable history
- Google Drive upload through a user OAuth grant limited to `drive.file`
- one stable Drive object per GitHub repository, replaced after every push
- resumable transfer followed by size and MD5 verification

The backup stores the encrypted repository, not the plaintext inbox or readable
view. Drive's own file-revision retention is not part of the recovery model;
the current bundle itself contains the Git history.

GitHub Actions is the current scheduler. The backup action is reusable, but
there are no unused implementations for other schedulers or storage providers.

## Policy Versus Mechanism

Configuration controls paths, providers, domains, scan queries, and approval
thresholds. Agent policy decides whether a candidate is a durable record, which
record it supersedes, who owns it, and whether correspondence has evidentiary
value.

Backup failure does not alter the Git push that triggered it. It must remain
visible as a failed GitHub Actions run and be retried before backup health is
considered current.
