# Record Policy

## Retain

Retain an item when it provides durable evidence of at least one of:

- identity, status, entitlement, or authorization
- education or professional qualification
- employment terms, compensation, or termination
- tax, banking, insurance, or material purchase facts
- household rights, obligations, or shared administration
- a legal or administrative decision
- a consequential commitment, approval, rejection, notice, or dispute
- provenance needed to understand another retained record

## Do Not Retain

Do not retain:

- application state, caches, logs, or game saves
- reference libraries unless explicitly within managed scope
- routine email notifications after their durable document is retained
- duplicate exports with no distinct evidentiary value
- credentials, recovery codes, encryption keys, or OAuth tokens

## Current Versus Historical

Choose `replaceable` when users normally ask for "the current X." Keep a
stable record identifier and let Git hold older issues.

Choose `event` when the date and occurrence are part of the record's meaning.

An expired document can still be an event or case record when it proves a past
status. Do not assume expiration makes it disposable.

## Email

Retain the original `.eml` when the message itself is evidence. An attachment
alone is insufficient when the body provides terms, interpretation, delivery,
approval, or rejection.

Retain an attachment separately when it is an independently issued document
that will later be replaced, referenced, or shared without the email.

## Ownership

Use:

- `self` for the user's own records
- `household` for genuinely shared administration
- a specific person identifier for records supplied by another person

Ownership is not the same as storage location. A housing dossier can contain
records with several owners.

## Conflicts

Preserve originals and report conflicts such as inconsistent dates,
nationalities, names, addresses, or contract terms. Do not edit an issued
document to correct it. Record corrections as new evidence.
