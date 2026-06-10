# Personal Document Manager

An agent-maintained system for organizing important personal documents without
giving up privacy, history, or readable local access.

Give this repository to your coding agent. The agent can set up a private
document vault, organize existing files, review incoming email, preserve
important records, and keep the system backed up.

## What It Manages

The system is intended for deliberate, long-lived personal records:

- identity documents and residence permits
- education and professional qualifications
- employment contracts, offers, decisions, and correspondence
- insurance, tax, banking, and major-purchase records
- household and housing documents
- legal or administrative notices
- important emails, including messages without attachments

It distinguishes between documents where only the latest issue is normally
needed and events that should remain permanently recorded. Older issues remain
recoverable through version history.

It is not intended to archive application data, logs, game saves, software
packages, general downloads, or an entire mailbox.

## Integrations

- **Apple Keychain** keeps encryption credentials and Google authorization
  tokens outside the document repository. New items are create-only, and
  updates require collision checks against the value previously read.
- **Gmail** provides read-only discovery of potentially important messages and
  preserves selected emails in their original form. Recurring scans use an
  encrypted source ledger so sessions and devices share incremental progress.
- **Folder exchange** stages scans and files from local or synchronized folders
  and exports the latest committed readable view without deleting unrelated
  files.
- **Remembered preferences** let the user resolve an ambiguous document or
  organization once; encrypted rules guide future agents without repeated
  questions.
- **Git and private GitHub** store encrypted records and retain previous
  versions.
- **Google Drive** receives a verified backup of the complete repository
  history after each push.
- **Codex and compatible coding agents** perform setup, classification,
  maintenance, verification, and recovery workflows.

The current implementation is designed for macOS and Google accounts.
Each deployment has a required UUID that isolates its encryption, Gmail, and
Drive entries in Apple Keychain.

## Typical Use Cases

### Keep the current document without losing the old one

When a new passport, permit, policy, or contract is issued, your agent replaces
the current copy. The previous issue remains recoverable from history.

### Preserve consequential email

Your agent can review Gmail for offers, approvals, rejections, notices,
commitments, and disputes. Important messages can be retained even when they
have no attachment.

### Teach the agent once

When inclusion or organization is genuinely unclear, the agent recommends a
choice and asks one focused question. The answer is stored as a narrow
encrypted preference, so future documents of that kind are handled
automatically.

### Find the latest readable documents

Encrypted records remain canonical, while a separate local folder contains a
readable copy of the latest committed versions for normal use. That view can
also be exported to an iCloud Drive or other locally synchronized folder.

### Recover after loss

The private GitHub repository contains encrypted document history. Google Drive
holds an independently restorable copy of that complete history. Recovery still
requires the encryption secret or its offline recovery copy.

## Set It Up With An Agent

Start a coding agent on your Mac and give it this prompt:

```text
Set up Personal Document Manager for me from:
https://github.com/viktor-shcherb/personal-document-manager

Read the repository documentation and handle the setup end to end. Before
creating anything, ask me to confirm:
- where the encrypted vault, temporary inbox, and readable documents should live
- which document categories I want managed
- which Gmail account, private GitHub repository, and Google Drive account to use

Keep all secrets outside version control. Explain any browser authorization or
recovery step that requires my direct action. Test document import, replacement,
readable-view generation, GitHub synchronization, Google Drive backup, and
recovery using fake documents before importing my real files.
```

The agent should follow [the setup guide](docs/setup.md) and install the
included [document-management skill](skills/manage-personal-documents/SKILL.md).

## What Requires Your Attention

Most setup and maintenance can be handled by the agent. You still need to:

- approve Google and GitHub authorization in the browser
- confirm which documents and email categories are in scope
- answer occasional consequential inclusion or organization questions; the
  encrypted preference store prevents the agent from asking the same kind of
  question repeatedly
- keep one offline recovery copy of the encryption secret
- approve destructive or ownership-changing operations

Personal Google OAuth apps that have not completed Google's public
verification display a **Google hasn't verified this app** warning. This is
expected for a self-owned deployment. Continue through **Advanced** only after
confirming that the displayed developer is you and the requested permission is
the documented Gmail read-only or Drive app-file scope. See the
[OAuth FAQ](docs/faq.md#how-do-i-continue-past-the-unverified-app-warning).

The agent should never display or commit encryption keys, OAuth tokens,
recovery material, inbox contents, or readable copies.

## Privacy Model

Documents are encrypted before entering GitHub or Google Drive. The plaintext
inbox and readable view remain local and separate from the encrypted vault.

Git metadata can still reveal record paths, repository names, and commit
messages. Use neutral identifiers and avoid sensitive details in commit
messages.

Google email access is read-only. Google Drive access is limited to files the
backup integration creates or explicitly uses.

## Documentation

- [Setup guide](docs/setup.md)
- [Frequently asked questions](docs/faq.md)
- [Backup and recovery](docs/backups.md)
- [Incremental source ledger](docs/source-ledger.md)
- [Folder exchange](docs/folder-exchange.md)
- [Remembered decision preferences](docs/preferences.md)
- [Security and extension boundaries](docs/interfaces.md)
- [Encrypted storage format](docs/storage-format.md)

## License

MIT
