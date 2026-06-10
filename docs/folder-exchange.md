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

## Readable Export

Export the latest committed vault view:

```bash
pdocs view export folder --profile iphone
```

The export includes each original, its `metadata.json`, and `INDEX.json`.
Repeated runs copy only changed files. PDM tracks its files in
`.pdocs-folder-export.json` and preserves unrelated files.

Stale managed files remain by default. Remove them explicitly:

```bash
pdocs view export folder --profile iphone --prune
```

The destination must be outside the encrypted vault. Export always reads Git
`HEAD`, so uncommitted record changes are not exposed.

## iPhone And iCloud Drive Example

On the Mac, a profile may use:

```toml
[sources.folder.iphone]
root = "~/Library/Mobile Documents/com~apple~CloudDocs/PDM Exchange"
inbox = "Inbox"
views = "Views"
```

On iPhone, save scans or documents into `PDM Exchange/Inbox` through Files.
After iCloud has downloaded them on the Mac, run folder intake. Exported
committed records appear under `PDM Exchange/Views`.

Cloud synchronization is external to PDM. Wait for files to finish uploading
or downloading before a run, avoid editing during intake, and do not assume
that a cloud placeholder contains readable bytes.
