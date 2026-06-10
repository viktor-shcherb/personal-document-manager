---
name: manage-personal-documents
description: Maintain an encrypted, Git-versioned personal document repository. Use when an agent needs to review local files or Gmail messages, decide which items are durable personal records, preserve important attachmentless correspondence, add or supersede records, generate the latest readable view, or commit and push document updates.
---

# Manage Personal Documents

Maintain deliberate personal records without turning the repository into a
mailbox or filesystem mirror.

## Start

1. Read the deployment configuration at `$PDOCS_CONFIG` or
   `~/.config/pdocs/config.toml`.
2. Run `pdocs check`.
3. Read [references/record-policy.md](references/record-policy.md).
4. Keep the configured vault, inbox, and readable view as separate paths.

Never retrieve or print a secret directly. Use `pdocs` commands, which access
the configured secret store internally.

## Review Intake

For local files, inspect the file and its surrounding context before importing.

For Gmail:

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

## Export Originals

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
  --thread-ref THREAD_ID
```

Store third-party records only when they are legitimately part of the user's
personal administration. Set ownership accurately and avoid broad sharing.

## Verify And Publish

After changes:

1. Run `pdocs record list` and inspect changed records with
   `pdocs record show RECORD_ID`.
2. Check that Git contains only encrypted `.pdoc` records and non-secret policy
   files.
3. Commit a concise description of the changed logical records.
4. Push when the deployment policy enables automatic push.
5. Confirm the configured Google Drive backup workflow succeeds.
6. Run `pdocs view build` to materialize the newly committed `HEAD`.

Never add inbox files, readable files, OAuth material, recovery codes, or
encryption keys to Git.

A backup failure does not roll back the push. Report it, diagnose the failed
workflow, and retry it before treating the repository as fully protected.

## Destructive Actions

Do not delete a record, rewrite ownership, or collapse ambiguous records
without the approval required by deployment policy. Surface factual conflicts
instead of silently choosing one version.
