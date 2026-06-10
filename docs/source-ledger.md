# Incremental Source Ledger

The source ledger gives recurring Gmail and folder imports shared memory across
agent sessions and devices. It is an encrypted, append-only event stream in the
private vault:

```text
.pdocs/state/source-ledger/events/
```

Each successful run records its source identity, query window, exact item
identities, content hashes, counts, and completion time. Failed runs write only
a local failure report and do not advance shared state.

## Configure Named Sources

```toml
[sources.gmail.personal-documents]
query = "-category:promotions -category:social"
initial_window = "30d"
overlap_window = "24h"

[sources.folder.iphone]
root = "~/Documents/PDM Exchange"
inbox = "Inbox"
views = "Views"
extensions = ["pdf", "jpg", "jpeg", "png", "heic"]
```

A named folder profile is the logical source identity, so its local root may
differ across devices. An ad hoc `--folder` path is included in its identity.

## Run Incrementally

Pull the vault first and avoid concurrent runs of the same profile:

```bash
git -C VAULT pull --ff-only
pdocs source run email --profile personal-documents
pdocs ingest folder --profile iphone
```

The first Gmail run starts at `initial_window`. Later runs resume from the last
successful source window and subtract `overlap_window` to catch delayed or
boundary items. Exact message IDs, relative-path/hash pairs, and content hashes
prevent duplicate staging.

Useful controls:

```bash
pdocs source run email --profile personal-documents --since 2026-01-01
pdocs source run email --profile personal-documents --overlap 72h
pdocs source run email --profile personal-documents --full
pdocs ingest folder --profile iphone --full
```

`--full` rescans the provider but retains content deduplication. Use an approved
reset when content must become eligible for import again.

## Commit The Checkpoint

After a successful run:

1. Review the printed inbox batch and its provenance manifest.
2. Add selected records with the printed source profile and source key.
3. Commit `records/` and `.pdocs/state/source-ledger/` together.
4. Push before running the same profile on another device.

Commit a successful no-item run too: its event advances the shared window.
Never commit plaintext inbox batches or local state.

## Inspect And Recover

```bash
pdocs source state list
pdocs source state show gmail --profile personal-documents
pdocs source state show folder --profile iphone
pdocs source state rebuild
```

`rebuild` recreates only the local derived index. Failure reports and locks are
under `STATE/source-runs/`. Remove a stale lock only after confirming its
recorded process is not active.

To deliberately re-import a logical source:

```bash
pdocs source state reset gmail --profile personal-documents
```

Reset appends an encrypted event; commit and push it. Do not edit, replace, or
delete existing ledger events.

## Multi-Device Rules

- Use the same profile name for the same logical source.
- Pull before each run and push its event before another device runs.
- Do not run the same profile concurrently on separate devices.
- Resolve Git conflicts before source execution.
- Treat the encrypted event stream as canonical; local indexes are disposable.
