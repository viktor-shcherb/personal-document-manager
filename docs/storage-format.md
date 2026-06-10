# Storage Format

Each `records/**/*.pdoc` file is a GnuPG-encrypted tar archive. GnuPG applies
lossless zlib compression before encryption. This substantially reduces text
and `.eml` records while safely leaving already-compressed PDFs and images with
little additional reduction.

After decryption, the archive contains:

```text
metadata.json
content/<original filename>
```

`metadata.json` uses schema version 1:

```json
{
  "schema": 1,
  "id": "employment/example/contract",
  "title": "Employment contract",
  "domain": "employment",
  "owner": "self",
  "lifecycle": "replaceable",
  "issued_at": "2026-05-15",
  "imported_at": "2026-06-10T12:00:00Z",
  "source": {
    "kind": "gmail",
    "reference": "gmail-message-id",
    "thread_reference": "gmail-thread-id",
    "profile": "personal-documents",
    "source_key": "gmail:personal-documents:..."
  },
  "content": {
    "filename": "contract.pdf",
    "media_type": "application/pdf",
    "sha256": "..."
  }
}
```

Unknown optional fields must be preserved by tools that rewrite a package.

## Repository Paths

A record identifier maps directly to its encrypted path:

```text
employment/example/contract
-> records/employment/example/contract.pdoc
```

Identifiers use lowercase ASCII letters, digits, `.`, `_`, and `-` in
slash-separated components. `.` and `..` components are forbidden.

## Replacement Semantics

Updating a `replaceable` record writes a new encrypted package to the same
path. Git history is the only historical store required inside the repository.

An `event` record cannot be overwritten by the normal add command.

## Original Preservation

The content file is stored byte-for-byte. Conversion, OCR, previews, and
readable views are derivatives and must not replace the original.

## Source Ledger

Recurring-source progress is stored as encrypted schema-1 JSON events:

```text
.pdocs/state/source-ledger/events/<timestamp>_<event-id>.pdoc
```

Events are append-only and use unique filenames so independently created
events can merge through Git. They contain source identity, run windows,
counts, exact source item identifiers, content checksums, and source times.
Resetting a source appends a reset event instead of rewriting history.

The event payload is encrypted with the repository cipher. Local locks,
failure reports, and the derived source index remain outside the vault.

## Decision Preferences

Reusable user feedback is stored as encrypted schema-1 events:

```text
.pdocs/state/preferences/events/<timestamp>_<event-id>.pdoc
```

A `remember` event contains a random rule ID, scope, narrow human-readable
match, optional source qualifiers, and either an inclusion decision or
organization defaults. A `forget` event retires a rule without deleting
history.

The effective preference set is derived by replaying events. Event filenames
contain no preference details. The encrypted payload may contain sensitive
issuer, household, or organization information and must be committed only in
encrypted form.
