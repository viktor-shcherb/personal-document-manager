# Folder Exchange

Folder exchange is a generic local-filesystem transport. It contains no
iCloud-specific business logic, so the same commands work with a normal local
folder or a folder synchronized by iCloud Drive, Dropbox, Syncthing, or another
tool.

## Intake

Configure a profile and place files below its `Inbox`:

```bash
pdocs ingest folder --profile iphone
```

Supported defaults are PDF, JPEG, PNG, and HEIC. Intake:

- recursively discovers regular files
- ignores hidden, temporary, partial, empty, unsupported, symlinked, and
  offline-placeholder files
- verifies SHA-256 after copying
- preserves relative paths in a run-specific local inbox batch
- leaves the exchange folder unchanged
- records exact path/hash and content-hash identities in the shared ledger

Changing a file in place creates a new path/hash identity. Unchanged files are
skipped on later runs.

## Readable Views

Configure each destination independently from intake sources:

```toml
[views.local]
path = "~/Documents/Personal Documents"
prune = true

[views.icloud]
path = "~/Library/Mobile Documents/com~apple~CloudDocs/Personal Documents"
prune = true
```

Refresh every destination from the same committed Git `HEAD`:

```bash
pdocs view refresh
```

Each destination keeps frequently reused documents directly visible and moves
rare evidence into an archive:

```text
Russian passport.pdf
Swiss residence permit.pdf
Current curriculum vitae.pdf
EPFL employment contract.pdf
Archive/
  Employment/
    UNIL payslip 2024-03.pdf
  Home and Housing/
    Route d'Oron 5/
      Refrigerator defect photo.jpg
.metadata/
INDEX.json
```

The importing agent must choose both an explicit `--view-name` and
`--view-access frequent|archive`. Frequent records are always placed directly
at the view root and cannot have a folder. Archive records default to
`Archive/<domain>`. PDM never exposes the opaque original filename or silently
invents a readable name.

Use `frequent` narrowly for documents likely to be opened or supplied again:
current identity documents, reusable application material, current contracts
and policies, core active housing documents, and similar references. Use
`archive` for historical evidence, old statements, correspondence, expired
documents, completed cases, and material retained mainly just in case.

An issue date stays in metadata unless it is part of the document's identity,
such as a tax year or payslip month. Names must be unique within their
effective folder. Refresh reports duplicate names so the agent can choose a
better distinction instead of appending an automatic suffix.

Nested folders are supported only inside `Archive` when they materially improve
retrieval, for example `Archive/Home and Housing/Route d'Oron 5` or a named
legal case.

PDM records the source commit and managed files in
`.pdocs-folder-export.json`. Repeated runs skip destinations already at that
commit. Refresh copies changed files, prunes stale PDM-managed files when
configured, and preserves unrelated files.

An agent can persist a better downstream name or placement without changing
the original content or semantic record ID:

```bash
pdocs record organize employment/epfl/contract/2026-03-30 \
  --name "EPFL employment agreement" \
  --access frequent
git add records
git commit -m "Improve readable document organization"
pdocs view refresh
```

For archived records, `--clear-folder` returns to `Archive/<domain>`.
Presentation metadata is encrypted with the record. After commit, refresh
renames the managed files in every destination and removes their old paths.

Destinations must be outside the encrypted vault, inbox, state directory, and
each other. Refresh always reads Git `HEAD`, so uncommitted record changes are
not exposed.

## Automatic Refresh

On macOS, install a per-user LaunchAgent:

```bash
pdocs view auto install
pdocs view auto status
```

The agent runs at the configured interval, defaulting to five minutes. It does
no decryption or copying when every destination already records the current
commit. It refreshes after local commits, checkouts, or pulls change `HEAD`.
Remote commits cannot appear in a local view until this machine pulls them.

## iPhone And iCloud Drive Example

On the Mac, a profile may use:

```toml
[sources.folder.iphone]
root = "~/Library/Mobile Documents/com~apple~CloudDocs/PDM Exchange"
inbox = "Inbox"

[views.icloud]
path = "~/Library/Mobile Documents/com~apple~CloudDocs/Personal Documents"
prune = true
```

On iPhone, save scans or documents into `PDM Exchange/Inbox` through Files.
After iCloud has downloaded them on the Mac, run folder intake. Refreshed
committed records appear under `Personal Documents`.

Cloud synchronization is external to PDM. Wait for files to finish uploading
or downloading before a run, avoid editing during intake, and do not assume
that a cloud placeholder contains readable bytes.
