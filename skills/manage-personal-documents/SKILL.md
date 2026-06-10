---
name: manage-personal-documents
description: Maintain an encrypted, Git-versioned personal document repository. Use when an agent needs to run incremental Gmail or folder intake through the shared source ledger, review local files or messages, preserve durable records, export committed readable views, or commit and push document updates.
---

# Manage Personal Documents

Maintain deliberate personal records without turning the repository into a
mailbox or filesystem mirror.

## Start

1. Read the deployment configuration at `$PDOCS_CONFIG` or
   `~/.config/pdocs/config.toml`.
2. Run `pdocs check`.
3. Read [references/record-policy.md](references/record-policy.md).
4. Read [references/source-ledger.md](references/source-ledger.md) before
   running a recurring Gmail or folder source.
5. Keep the configured vault, inbox, readable view, and exchange folders
   separate.

Never retrieve or print a secret directly. Use `pdocs` commands, which access
the configured secret store internally.

## Review Intake

For local files, inspect the file and its surrounding context before importing.

For one-off Gmail inspection:

```bash
pdocs gmail scan
pdocs gmail show MESSAGE_ID
pdocs gmail thread THREAD_ID
```

Inspect full threads when an individual message lacks context. An email does
not need an attachment to be a record. Preserve decisions, commitments,
offers, rejections, approvals, notices, disputes, and other correspondence
that establishes consequential facts.

Ignore newsletters, marketing, routine notifications, casual discussion, and
documents outside the configured managed scope.

## Run Recurring Intake

Recurring sources MUST use the encrypted shared ledger:

```bash
git -C VAULT pull --ff-only
pdocs source run email --profile PROFILE
pdocs ingest folder --profile PROFILE
```

Do not use raw `gmail scan` or `gmail export` as a replacement for a configured
recurring source. Those commands do not advance the shared ledger.

Run only one agent or device at a time for a given source profile. After a
successful run, review the printed batch before committing its ledger event.
The event advances the incremental window even when no items were exported.

## Export One-Off Originals

Export selected Gmail messages before adding them:

```bash
pdocs gmail export MESSAGE_ID
```

This preserves the original message as `.eml`, including headers, body, and
embedded attachments. Treat extracted attachments as separate records only
when they have an independent lifecycle, such as a contract or permit.

Do not convert an original into PDF merely for consistency.

## Choose Record Semantics

Use `replaceable` for a logical slot whose newest issue is current:

- passport
- current residence permit
- current insurance policy
- current employment contract for a role
- current official transcript

Use a stable identifier and overwrite the same `.pdoc` path. Git retains prior
issues.

Use `event` for immutable evidence:

- important email
- signed resignation
- administrative decision
- application submission
- dated certificate that remains historically meaningful

Give every event a unique identifier. Do not overwrite an existing event.

## Add A Record

Use lowercase slash-separated identifiers:

```bash
pdocs record add PATH \
  --id "employment/example/contract" \
  --title "Employment contract" \
  --domain employment \
  --owner self \
  --lifecycle replaceable \
  --issued-at 2026-05-15
```

Include Gmail provenance when applicable:

```bash
  --source-kind gmail \
  --source-ref MESSAGE_ID \
  --thread-ref THREAD_ID \
  --source-profile PROFILE \
  --source-key SOURCE_KEY
```

For recurring intake, copy `source_profile`, `source_key`, source references,
and checksums from the staged `source.json` or `manifest.json`. Do not invent
or shorten a source key.

Store third-party records only when they are legitimately part of the user's
personal administration. Set ownership accurately and avoid broad sharing.

## Verify And Publish

After changes:

1. Run the compact `pdocs record list` and inspect changed records with
   `pdocs record show RECORD_ID`. Use `pdocs record list --json` only when
   complete metadata for every record is required.
2. Check that Git contains only encrypted records, encrypted source-ledger
   events, and non-secret policy files.
3. For a successful recurring source run, commit both `records/` and
   `.pdocs/state/source-ledger/`. Do this even when only the ledger changed.
4. Commit a concise description of the changed logical records or source
   checkpoint.
5. Push when the deployment policy enables automatic push.
6. Confirm the configured Google Drive backup workflow succeeds.
7. Run `pdocs view build` to materialize the newly committed `HEAD`.

Read the commit identifier printed by `view build`. If it warns that
uncommitted record changes were ignored, do not describe the readable view as
containing those changes.

Never add inbox files, readable files, OAuth material, recovery codes, or
encryption keys to Git.

If a source run fails, do not create a checkpoint manually. Failed runs do not
advance the shared ledger. Inspect the local failure report under the
configured state directory, fix the cause, and rerun.

A backup failure does not roll back the push. Report it, diagnose the failed
workflow, and retry it before treating the repository as fully protected.

## Destructive Actions

Do not delete a record, rewrite ownership, or collapse ambiguous records
without the approval required by deployment policy. Surface factual conflicts
instead of silently choosing one version.

Do not edit or delete encrypted ledger events manually. The
`pdocs source state reset` command appends a shared reset event and requires
the same approval as a destructive re-import. `pdocs source state rebuild`
only regenerates the local derived index and is safe.
