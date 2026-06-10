# Setup

This setup creates two repositories:

1. this public orchestration repository
2. a separate private repository containing encrypted personal records

## 1. Prerequisites

On macOS, install:

```bash
brew install git gh gnupg uv
```

Install the CLI with Google API support from a local clone:

```bash
uv tool install '.[google]'
```

Install the agent skill:

```bash
mkdir -p ~/.codex/skills
cp -R skills/manage-personal-documents ~/.codex/skills/
```

## 2. Create Paths

Choose three distinct paths:

```text
vault     encrypted canonical Git repository
inbox     temporary plaintext intake
readable  generated plaintext latest view
```

The inbox and readable paths must not be inside the vault.

Copy the example configuration:

```bash
mkdir -p ~/.config/pdocs
cp config/profile.example.toml ~/.config/pdocs/config.toml
chmod 600 ~/.config/pdocs/config.toml
```

Edit the paths, Gmail account, and taxonomy for the user.

## 3. Create The Encryption Secret

```bash
pdocs secrets init
```

This generates a high-entropy passphrase and stores it in macOS Keychain. The
command does not print it.

Create one independent offline recovery copy. Do not place that copy in either
Git repository.

## 4. Create The Private Vault

```bash
mkdir -p "$HOME/Documents/Personal Documents Vault/records"
cd "$HOME/Documents/Personal Documents Vault"
git init
printf '%s\n' '*.tmp' '.DS_Store' > .gitignore
git add .gitignore
git commit --allow-empty -m "Initialize encrypted document vault"
```

Create a private GitHub repository and add it as `origin`:

```bash
gh repo create personal-documents --private --source=. --remote=origin --push
```

Run:

```bash
pdocs check
```

## 5. Configure Gmail OAuth

In Google Cloud Console:

1. Create a project.
2. Enable the Gmail API.
3. Configure the Google Auth Platform for an external desktop application.
4. Add only `https://www.googleapis.com/auth/gmail.readonly`.
5. Add the user's Google account as a test user.
6. Publish the app to production so offline refresh tokens do not expire after
   seven days.
7. Create an OAuth client of type `Desktop app`.
8. Download the JSON file to the `oauth_client` path from the configuration.

The OAuth client JSON stays outside Git. Authorize:

```bash
pdocs gmail auth
```

The refresh token is stored in macOS Keychain.

## 6. Configure Google Drive Backup

In the same Google Cloud project:

1. Enable the Google Drive API.
2. Add `https://www.googleapis.com/auth/drive.file` to the consent screen.
3. Keep the user's Google account as an allowed user.
4. Set the OAuth publishing status to `Production`. In `Testing`, refresh
   tokens expire after seven days.
5. Reuse the desktop OAuth client JSON configured in `[backup]`.

Authorize the separate Drive grant:

```bash
pdocs backup auth
pdocs backup status
```

Copy the required values directly from Keychain into GitHub Actions secrets
without printing them:

```bash
pdocs backup github-secrets \
  --repository OWNER/personal-documents
```

Install the push-triggered workflow into the private vault:

```bash
pdocs backup install-workflow
git add .github/workflows/backup-google-drive.yml
git commit -m "Back up Git history to Google Drive"
git push
```

The first successful run creates `Personal Document Backups` in My Drive and
uploads a stable `OWNER-personal-documents.bundle` file. Confirm the run:

```bash
gh run list --repo OWNER/personal-documents --workflow backup-google-drive.yml
```

The workflow backs up only encrypted Git history. It does not upload the inbox,
readable view, Keychain secret, or recovery copy. See
[backups.md](backups.md) for verification and recovery details.

## 7. Test The Document Workflow

```bash
pdocs gmail search 'newer_than:7d'
pdocs gmail show MESSAGE_ID
pdocs gmail thread THREAD_ID
pdocs gmail export MESSAGE_ID
```

Add an exported email as an immutable event:

```bash
pdocs record add \
  "$HOME/Documents/Personal Documents Inbox/email/MESSAGE_ID/message.eml" \
  --id "employment/example/correspondence/2026-06-10-offer" \
  --title "Employment offer" \
  --domain employment \
  --owner self \
  --lifecycle event \
  --source-kind gmail \
  --source-ref MESSAGE_ID
```

Commit the encrypted record, then generate the readable view from that commit:

```bash
git add records
git commit -m "Add employment offer"
git push
pdocs view build
```

## Recovery

The vault can be reconstructed from Git plus the Keychain secret or its offline
recovery copy. If GitHub is unavailable, restore the current Git bundle from
Google Drive. The readable view is disposable.
