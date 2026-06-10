# Source Ledger Runbook

The shared source ledger is the cross-session and cross-device memory for
recurring Gmail and folder intake. Its encrypted append-only events live at:

```text
VAULT/.pdocs/state/source-ledger/events/
```

Local locks, failure reports, and the derived index live under the configured
state directory and must not be committed.

## Before A Run

1. Read the named source profile from the deployment config.
2. Ensure the vault has no unresolved Git changes.
3. Pull the vault with `git pull --ff-only`.
4. Do not start if another agent or device is running the same profile.
5. Inspect prior state when needed:

   ```bash
   pdocs source state list
   pdocs source state show gmail --profile PROFILE
   pdocs source state show folder --profile PROFILE
   ```

## Run A Source

```bash
pdocs source run email --profile PROFILE
pdocs ingest folder --profile PROFILE
```

The first Gmail run uses the profile's `initial_window`. Later runs resume from
the last successful source window with the configured overlap. Use `--since`
for a deliberate historical start, `--overlap` for a one-run override, and
`--full` only to rescan the provider while retaining exact-content
deduplication.

The folder command is non-destructive. It copies supported files into a
run-specific inbox batch and leaves the source folder unchanged.

## After A Successful Run

1. Record the printed source key, run ID, counts, batch, and ledger event.
2. Review every staged candidate and its `source.json` or `manifest.json`.
3. Import durable records with the provided source profile and source key.
4. Verify records with `pdocs record list` and `pdocs record show`.
5. Commit `records/` and `.pdocs/state/source-ledger/` together, then push.
6. Report exported and duplicate counts and the committed checkpoint.

Never commit the plaintext batch. If no items were exported, commit the ledger
event by itself so the successful source window is shared.

## Failure And Recovery

A failed run writes no shared event. Inspect:

```text
STATE/source-runs/failures/
STATE/source-runs/locks/
```

Remove a stale lock only after confirming that its recorded process is no
longer active. Rerun after fixing the cause. Do not synthesize a ledger event.

Use `pdocs source state rebuild` to recreate the local derived index from
encrypted events.

Use `pdocs source state reset KIND --profile PROFILE` only after explicit
approval to make the source eligible for re-import. The reset is itself an
encrypted event and must be committed and pushed. Never rewrite old events.
