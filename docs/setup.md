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

Choose distinct local paths:

```text
vault     encrypted canonical Git repository
inbox     temporary plaintext intake
readable  generated plaintext latest view
exchange  optional folder intake and readable export
```

The inbox, readable, and exchange paths must not be inside the vault.

Copy the example configuration:

```bash
mkdir -p ~/.config/pdocs
cp config/profile.example.toml ~/.config/pdocs/config.toml
chmod 600 ~/.config/pdocs/config.toml
```

Generate a unique deployment ID:

```bash
deployment_id="$(uuidgen | tr '[:upper:]' '[:lower:]')"
sed -i '' "s/REPLACE-WITH-UUID/$deployment_id/" \
  ~/.config/pdocs/config.toml
```

Edit the paths, Google account, source profiles, and taxonomy for the user.
Named source profiles give recurring imports a stable identity across sessions
and devices.

The deployment UUID is not a secret. PDM derives separate Keychain addresses
from it:

```text
pdocs.repository-encryption  DEPLOYMENT_UUID
pdocs.gmail-oauth            DEPLOYMENT_UUID:GOOGLE_ACCOUNT
pdocs.google-drive-oauth     DEPLOYMENT_UUID:GOOGLE_ACCOUNT
```

Generate a new UUID for every PDM instance. Even if a configuration is copied
with the same UUID, create-only writes prevent it from silently replacing an
existing Keychain item.

## 3. Create The Encryption Secret

```bash
pdocs secrets init
```

This generates a high-entropy passphrase and stores it in macOS Keychain. The
command does not print it. The installed `pdocs` runtime is granted access so
routine agent operations do not require repeated password prompts.

`secrets init` never replaces an existing Keychain item and has no force
option. If the derived `(service, account)` pair already exists, determine
which deployment owns it and assign a new deployment UUID rather than
overwriting it.

Create one independent offline recovery copy. Do not place that copy in either
Git repository.

If an older installation prompts for the login password on every command, run:

```bash
pdocs secrets repair-access
```

This may require one final password approval. Before touching the original
item, the command creates and verifies a temporary Keychain recovery item. It
removes that backup only after the recreated original has been read back and
verified.

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

Google normally shows **Google hasn't verified this app** for a personal OAuth
project that has not completed public verification. Before continuing, confirm:

- the displayed app name is the one configured for this deployment
- the displayed developer email belongs to the user who created the project
- the requested permission is read-only Gmail access

Then choose **Advanced** and **Go to _app name_ (unsafe)**. On this screen,
“unsafe” means Google has not verified the OAuth publisher; it is not a reason
to ignore a mismatched developer or unexpected permission. Stop if the app asks
to send or delete email.

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

Apply the same identity checks if Google displays the unverified-app warning.
The Drive grant must allow access only to files created or explicitly used by
the app, not full Drive access.

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

## 7. Test Incremental Intake

Pull the private vault before each recurring source run:

```bash
git -C "$HOME/Documents/Personal Documents Vault" pull --ff-only
pdocs source run email --profile personal-documents
```

The first run uses the configured initial window. Later runs replay the
encrypted ledger and apply the configured overlap while skipping exact source
and content duplicates.

For folder intake, place a test PDF or image in the configured `Inbox` and run:

```bash
pdocs ingest folder --profile iphone
```

Both commands print a run-specific plaintext inbox batch and an encrypted
ledger event. Review the batch, import selected records, and commit the ledger
event with the resulting records:

```bash
git -C "$HOME/Documents/Personal Documents Vault" add \
  records .pdocs/state/source-ledger
git -C "$HOME/Documents/Personal Documents Vault" commit \
  -m "Import personal document source"
git -C "$HOME/Documents/Personal Documents Vault" push
```

The event must still be committed when a successful run exports no items,
because it advances the shared source window. See
[source-ledger.md](source-ledger.md).

## 8. Configure Agent Decision Behavior

The agent uses common sense and existing vault structure for clear cases. When
inclusion or recurring organization is genuinely ambiguous, it asks one focused
question with a recommendation and records the answer as an encrypted
preference.

Inspect effective preferences:

```bash
pdocs preference list
```

Remembered preference events are committed under
`.pdocs/state/preferences/`. They contain no credentials, but their decrypted
contents can be sensitive. See [preferences.md](preferences.md).

## 9. Test The Document Workflow

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
  --source-ref MESSAGE_ID \
  --source-profile personal-documents \
  --source-key SOURCE_KEY
```

Commit the encrypted record, then generate the readable view from that commit:

```bash
git add records
git commit -m "Add employment offer"
git push
pdocs view build
```

Export the committed view to the configured folder transport:

```bash
pdocs view export folder --profile iphone
```

Use `--prune` only when stale files previously managed by PDM should be
removed. Unrelated files are always preserved. See
[folder-exchange.md](folder-exchange.md).

## Recovery

The vault can be reconstructed from Git plus the Keychain secret or its offline
recovery copy. If GitHub is unavailable, restore the current Git bundle from
Google Drive. The readable view is disposable.
