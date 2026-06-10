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

Edit the paths, Google account, and taxonomy for the user.

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

## 5. Configure Google OAuth

Use two Google Cloud projects and two desktop OAuth clients. This keeps the
non-sensitive Drive grant separate from Gmail's restricted scope and makes
Google's verification messages easier to interpret.

### Gmail intake

1. Create a Google Cloud project for Gmail intake.
2. Enable the Gmail API.
3. In Google Auth Platform, set the audience to `External`.
4. Under Data Access, add exactly:

   ```text
   https://www.googleapis.com/auth/gmail.readonly
   ```

   It must appear under `Restricted scopes` as “View your email messages and
   settings.”
5. Add the intended Google account as a test user while configuring the app.
6. Publish the app to `In production`. Do not submit a personal-use app for
   verification merely because Google displays the verification notice.
7. Create an OAuth client with application type `Desktop app`.
8. Download its JSON file to the `[gmail].oauth_client` path.

The OAuth client JSON stays outside Git. Authorize:

```bash
pdocs gmail auth
```

The refresh token is stored in macOS Keychain.

### Google Drive backup

1. Create a separate Google Cloud project for Drive backup.
2. Enable the Google Drive API.
3. In Google Auth Platform, set the audience to `External`.
4. Under Data Access, add exactly:

   ```text
   https://www.googleapis.com/auth/drive.file
   ```

   It must appear under `Non-sensitive scopes` as access only to the specific
   Drive files used with the app. Do not select `.../auth/docs` or
   `.../auth/drive`.
5. Add the intended Google account as a test user while configuring the app.
6. Publish the app to `In production`.
7. Create an OAuth client with application type `Desktop app`.
8. Download its JSON file to the `[backup].oauth_client` path.

Authorize the separate Drive grant:

```bash
pdocs backup auth
pdocs backup status
```

`Testing` mode is useful only during initial setup. Its refresh tokens expire
after seven days, so it is unsuitable for unattended backups. See
[FAQ](faq.md#google-oauth) for verification warnings, scope corrections, and
authorization troubleshooting.

## 6. Enable Google Drive Backup

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
