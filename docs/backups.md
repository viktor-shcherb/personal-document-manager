# Google Drive Backups

The backup is a complete Git bundle of the private encrypted vault. It contains
all fetched branches, tags, remote refs, and their reachable history.

It does not contain the plaintext inbox or readable view. Record contents
remain encrypted as `.pdoc` files, although Git metadata such as record paths
and commit messages remains visible to Google Drive just as it is to GitHub.

## Update Model

Every vault push starts a GitHub Actions workflow. The workflow:

1. checks out full history and fetches all current remote branches and tags
2. creates a lossless `.bundle`
3. verifies the bundle locally with `git bundle verify`
4. creates or updates one app-managed file in Google Drive
5. verifies the uploaded size and MD5 checksum

The Drive filename is stable: `OWNER-REPOSITORY.bundle`. Each new upload
replaces that object. This avoids storing a duplicate full-history bundle for
every commit. Historical documents remain available because Git history is
inside the latest bundle.

Concurrent workflow runs are serialized. GitHub can coalesce pending runs
during unusually rapid pushes; the newest resulting bundle still includes the
history of the earlier pushes.

Google Drive's native revision retention is useful but not relied upon.

## Authorization

The action uses a separate OAuth refresh token with only:

```text
https://www.googleapis.com/auth/drive.file
```

That scope lets the application manage only files it created or that were
explicitly opened for it. On first use, the action creates a visible
`Personal Document Backups` folder in My Drive and its bundle inside it.

The refresh token is held in two places:

- Apple Keychain for local setup and renewal
- encrypted GitHub Actions secrets for the private vault repository

It never enters either Git repository. The GitHub workflow receives only the
three named Drive credentials and has read-only repository permissions.

An OAuth app left in Google's `Testing` publishing state receives refresh
tokens that expire after seven days. Set the consent screen to `Production`
before relying on unattended backups.

## Recovery

Download the `.bundle` from Google Drive and verify it:

```bash
bundle="$HOME/Downloads/viktor-shcherb-personal-documents.bundle"
verify="$(mktemp -d)"
git -C "$verify" init --bare
git -C "$verify" bundle verify "$bundle"
git clone "$bundle" \
  "$HOME/Documents/Personal Documents Vault"
git -C "$HOME/Documents/Personal Documents Vault" fsck --full
```

Re-add the private GitHub remote if needed. The encryption passphrase from
Apple Keychain or its offline recovery copy is still required to open records.

Test recovery periodically into a temporary directory. A successful upload is
not a substitute for a restore test.
