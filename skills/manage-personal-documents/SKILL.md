---
name: manage-personal-documents
description: Maintain an encrypted, Git-versioned personal document repository. Use when an agent needs to run incremental Gmail or folder intake, apply remembered inclusion and organization preferences, resolve genuinely ambiguous records with minimal user interruption, export committed readable views, or commit and push document updates.
---

# Manage Personal Documents

Maintain deliberate personal records without turning the repository into a
mailbox or filesystem mirror.

## Start

1. Read the deployment configuration at `$PDOCS_CONFIG` or
   `~/.config/pdocs/config.toml`.
2. Run `pdocs check`.
3. Read [references/record-policy.md](references/record-policy.md).
4. Read [references/decision-preferences.md](references/decision-preferences.md)
   and run `pdocs preference list`.
5. Read [references/source-ledger.md](references/source-ledger.md) before
   running a recurring Gmail or folder source.
6. Keep the configured vault, inbox, readable views, and exchange folders
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

## Decide With Minimal Interruption

Apply remembered preferences before the general record policy. When a matching
inclusion rule says `add` or `skip`, follow it automatically without asking
again. Apply matching organization rules to domain, owner, lifecycle, record
ID hierarchy, and grouping.

When no rule matches, use common sense and the existing vault structure. Do not
ask about obvious durable records, obvious non-records, cosmetic naming, or
minor folder choices. Inspect neighboring record IDs and choose the least
surprising consistent organization.

Ask one concise question only when uncertainty is consequential, such as
whether a borderline document belongs in the managed scope, whether it is a
replaceable current document or a historical event, who owns it, or which of
two materially different recurring organizations the user prefers. State the
recommended default and why.

After the answer, immediately record a narrow reusable rule:

```bash
pdocs preference remember inclusion \
  --match "NARROW DOCUMENT KIND AND ISSUER" \
  --decision add \
  --instruction "USER'S REUSABLE GUIDANCE"

pdocs preference remember organization \
  --match "NARROW DOCUMENT KIND" \
  --domain DOMAIN \
  --owner OWNER \
  --lifecycle event \
  --id-prefix "domain/category" \
  --instruction "USER'S REUSABLE GROUPING GUIDANCE"
```

Tell the user what narrow rule was remembered. Future matching documents must
be handled automatically unless facts conflict, safety policy applies, or the
user says the answer was one-off. Never generalize one answer to unrelated
issuers, people, document kinds, or legal contexts.

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
  --view-name "Example employment contract" \
  --view-access frequent \
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

Choose `--view-name` and `--view-access frequent|archive` deliberately for every
record. Frequent means likely to be opened or supplied again, and places the
file directly at the readable root. Use it narrowly for current identity
documents, reusable application material, current contracts and policies, core
active housing documents, and similar references. Archive historical evidence,
old statements, correspondence, expired documents, completed cases, and
records retained mainly just in case.

Do not rely on the original filename. Put the issue date in `issued_at`; keep a
date or period in the view name only when it is part of the document's identity.
Readable names must be unique within their effective folder.

If inspection of the generated view reveals a better filename or flatter
placement, persist the improvement instead of manually renaming disposable
view files:

```bash
pdocs record organize RECORD_ID \
  --name "Descriptive filename" \
  --access archive \
  --folder "Descriptive folder"
```

Frequent records cannot have folders. For archived records, prefer the existing
domain folder; a custom nested folder is appropriate for a coherent property,
legal case, or similar dossier. Commit the changed encrypted record; the next
view refresh renames it in every destination and prunes the old managed path.

## Verify And Publish

After changes:

1. Run the compact `pdocs record list` and inspect changed records with
   `pdocs record show RECORD_ID`. Use `pdocs record list --json` only when
   complete metadata for every record is required.
2. Check that Git contains only encrypted records, encrypted source-ledger
   events, encrypted preference events, and non-secret policy files.
3. For a successful recurring source run, commit both `records/` and
   `.pdocs/state/source-ledger/`. Do this even when only the ledger changed.
4. Commit `.pdocs/state/preferences/` whenever user feedback created or retired
   a remembered rule.
5. Commit a concise description of the changed logical records, source
   checkpoint, or preference.
6. Push when the deployment policy enables automatic push.
7. Confirm the configured Google Drive backup workflow succeeds.
8. Run `pdocs view refresh` to materialize the newly committed `HEAD` to every
   configured view destination.

Read the commit identifier printed by `view refresh`. If it warns that
uncommitted record changes were ignored, do not describe the readable views as
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

Do not rewrite preference events manually. If the user changes a preference,
use `pdocs preference forget RULE_ID`, commit that encrypted event, then
remember the replacement. A current user instruction overrides an older
preference.

Do not edit or delete encrypted ledger events manually. The
`pdocs source state reset` command appends a shared reset event and requires
the same approval as a destructive re-import. `pdocs source state rebuild`
only regenerates the local derived index and is safe.
