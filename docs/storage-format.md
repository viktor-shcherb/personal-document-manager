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
    "thread_reference": "gmail-thread-id"
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
