# FAQ

## Google OAuth

### Why use separate Google Cloud projects for Gmail and Drive?

Gmail intake requests the restricted `gmail.readonly` scope. Drive backup uses
the non-sensitive `drive.file` scope. Separate projects isolate their
credentials and prevent Gmail's verification warning from making the narrower
Drive setup look incorrect.

One project can technically support both grants because `pdocs` requests them
separately, but two projects are clearer and reduce the effect of credential or
configuration changes.

### What are the exact scopes?

Gmail intake:

```text
https://www.googleapis.com/auth/gmail.readonly
```

Expected category: `Restricted scopes`.

Google Drive backup:

```text
https://www.googleapis.com/auth/drive.file
```

Expected category: `Non-sensitive scopes`.

Do not use these broader Drive scopes:

```text
https://www.googleapis.com/auth/docs
https://www.googleapis.com/auth/drive
```

### Google says the app requires verification. Must I submit it?

Not for a personal-use app that only the owner authorizes. Leave the app
unverified, publish it to `In production`, and accept Google's unverified-app
warning during Gmail authorization.

Verification is required before distributing the OAuth app broadly. Do not
present this personal setup as a public multi-user service.

### Why publish an unverified app to production?

For an external app in `Testing`, refresh tokens expire after seven days.
That breaks unattended Drive backups and requires weekly reauthorization.
`In production` removes that seven-day testing limit.

Publishing does not list or advertise the app. It changes the OAuth publishing
status. Gmail authorization can still display an unverified-app warning.

### How do I continue past the unverified-app warning?

Google can display:

```text
Google hasn't verified this app
```

This is expected when the user created the OAuth project for personal use and
has not submitted it for public verification. Verify all of the following
before proceeding:

1. The app name matches the OAuth project configured for this deployment.
2. The displayed developer email belongs to the user who created the project.
3. Gmail requests only read-only access to messages and settings
   (`gmail.readonly`).
4. Drive requests only access to files created or explicitly used by the app
   (`drive.file`).

After those checks, select **Advanced**, then
**Go to _app name_ (unsafe)**. Google's “unsafe” label on this page means the
OAuth publisher is unverified. It does not override the identity and scope
checks above.

Do not continue if the developer email is unfamiliar, the app name is
unexpected, or the screen requests sending email, deleting email, or full
Drive access. Public or multi-user distribution requires a different security
review and may require Google verification.

### I selected the wrong Drive scope. How do I correct it?

1. Remove `.../auth/docs`, `.../auth/drive`, or other unintended scopes from
   Google Auth Platform Data Access.
2. Add only `https://www.googleapis.com/auth/drive.file`.
3. Revoke the old app grant in the Google Account's third-party access page.
4. Run `pdocs backup auth` again.
5. Run `pdocs backup github-secrets --repository OWNER/REPOSITORY` again.

Existing GitHub secrets must be updated because the new authorization produces
a new refresh token.

### Can Gmail and Drive reuse the same downloaded JSON file?

They can if both APIs and scopes are configured in one Google Cloud project.
The recommended setup uses separate JSON files:

```toml
[gmail]
oauth_client = "~/.config/pdocs/google-gmail-oauth-client.json"

[backup]
oauth_client = "~/.config/pdocs/google-drive-oauth-client.json"
```

OAuth client JSON files are credentials. Keep them outside Git.

### Where are refresh tokens stored?

Local Gmail and Drive refresh tokens are stored in Apple Keychain. The Drive
credentials required by GitHub Actions are also stored as encrypted secrets in
the private vault repository.

Commands do not print refresh tokens.

## Apple Keychain

### How are accidental Keychain overwrites prevented?

PDM treats the Keychain `(service, account)` pair as a secret's address and
uses these safeguards:

- first-time secret and token writes are create-only and fail if the item exists
- every deployment has a required UUID that namespaces all Keychain accounts
- encryption, Gmail, and Drive use separate fixed Keychain services
- encryption secrets are never replaced in place and initialization has no
  force option
- automatic OAuth refresh uses compare-before-replace against the token it read
- interactive OAuth replacement requires an explicit `--replace-existing` flag
- access repair makes and verifies a temporary Keychain recovery item before
  deleting the original, then verifies the recreated original before cleanup

Generate a new `[deployment].id` UUID for every PDM instance. Copying a
configuration also copies its identity, so change the UUID before initializing
the copied deployment.

### How do I deliberately reauthorize Google?

Normal `pdocs gmail auth` and `pdocs backup auth` commands refuse to overwrite
an existing token. After confirming the deployment UUID and configured account,
use:

```bash
pdocs gmail auth --replace-existing
pdocs backup auth --replace-existing
```

The replacement is accepted only if the Keychain value still matches the value
read before browser authorization. A concurrent or unexpected change aborts
the update.

### Why did `pdocs` ask for my login password repeatedly?

Older versions created the Keychain item through `/usr/bin/security`, which
trusted that utility rather than the installed `pdocs` runtime. Choosing
one-time `Allow` caused another dialog for each new CLI process.

Repair the access control without rotating the encryption secret:

```bash
pdocs secrets repair-access
```

The migration can require one final login-password approval. Subsequent
commands from the same installed `pdocs` runtime should be prompt-free.

### Can Keychain use Touch ID instead?

The current agent-oriented mode grants the installed CLI ongoing access after
initial provisioning. Requiring Touch ID for every retrieval would interrupt
each agent command and unattended maintenance, so biometric-per-access mode is
not currently implemented.

Legacy login-keychain authorization dialogs request the account password rather
than Touch ID. `repair-access` avoids those repeated dialogs instead of
replacing them with repeated biometric prompts.

### Can I force-create a new encryption secret?

No. `pdocs secrets init` has no force option. Replacing the passphrase without
atomically re-encrypting and verifying every historical record can make the
vault permanently unreadable.

For a new vault, generate a new `[deployment].id` UUID and run
`pdocs secrets init`. Existing vaults keep their original deployment UUID and
secret; `pdocs secrets repair-access` changes access control without changing
its value.

## Backups

### Does Google Drive receive plaintext documents?

No. The backup action uploads a Git bundle of the private vault. Document
contents are already encrypted `.pdoc` records. The bundle still reveals Git
metadata such as filenames, repository name, and commit messages.

### Does every push create another full backup file?

No. Every push creates a complete bundle locally, then replaces one stable
Drive file. The latest bundle contains the repository's Git history.

### What if the backup workflow fails after a push?

The GitHub push remains valid, but the Drive backup is stale. Inspect and rerun
the failed GitHub Actions workflow before treating the repository as fully
protected.

## References

- [Google OAuth app verification exceptions](https://support.google.com/cloud/answer/13464323)
- [Google OAuth token expiration](https://developers.google.com/identity/protocols/oauth2)
- [Google Drive scope guidance](https://developers.google.com/workspace/drive/api/guides/api-specific-auth)
- [Gmail API scopes](https://developers.google.com/workspace/gmail/api/auth/scopes)
