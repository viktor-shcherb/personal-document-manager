# Decision Preferences

User feedback about inclusion and organization is durable policy, not
conversational memory. Effective rules are replayed from encrypted events at:

```text
VAULT/.pdocs/state/preferences/events/
```

## Decision Order

For each candidate:

1. Consult `pdocs preference list --json`.
2. Apply the most specific matching source-qualified preference.
3. Otherwise apply the record policy and established neighboring structure.
4. Ask only if the remaining uncertainty could materially change retention,
   lifecycle, ownership, retrieval, or a recurring organization.

Do not ask for confirmation when a competent administrator would consider the
choice routine and reversible.

## Asking Well

Ask one focused question and include:

- the concrete document or document kind
- the consequential ambiguity
- a recommended choice with one short reason
- the proposed narrow category that future items will follow

Example:

```text
This monthly brokerage statement is durable financial evidence, so I recommend
adding it as an event under finance/brokerage/statements. Should I use that
rule for future statements from this brokerage?
```

Treat a plain yes/no or correction as feedback for the proposed narrow
category unless the user explicitly says it is one-off. Do not ask a second
question merely to obtain wording for the rule.

## Remembering Inclusion

```bash
pdocs preference remember inclusion \
  --match "monthly brokerage statements from Example Brokerage" \
  --decision add \
  --source-kind gmail \
  --instruction "Retain each statement as durable financial evidence."
```

Use `skip` for a reusable exclusion. The match should identify the document
kind and distinguishing issuer, sender, person, case, or source profile where
relevant.

## Remembering Organization

First inspect existing record IDs and taxonomy. Prefer consistency over a new
hierarchy. Ask only when multiple plausible structures have materially
different retrieval semantics.

```bash
pdocs preference remember organization \
  --match "monthly brokerage statements from Example Brokerage" \
  --domain finance-insurance \
  --owner self \
  --lifecycle event \
  --id-prefix "finance-insurance/brokerage/example/statements" \
  --instruction "Group statements by calendar year."
```

Organization preferences may cover domain, owner, lifecycle, ID prefix, and
free-form grouping guidance. They control stable semantic organization in the
encrypted vault. The readable projection defaults to one descriptive folder
per domain and descriptive filenames derived from record titles.

Store issue dates in metadata unless a date or period is part of the document's
identity. If a better readable name or placement is discovered later, use
`pdocs record organize` and commit the encrypted record. Do not manually rename
generated view files because refresh will replace unmanaged presentation
changes.

Readable folders should be flat by default. Use nested folders for a coherent
property, legal case, or similar dossier only when the grouping materially
improves retrieval.

## Scope And Conflicts

Keep every rule as narrow as the evidence supports. Do not infer that feedback
about one bank applies to all financial institutions, or that feedback about
one household member applies to another.

If a current instruction conflicts with a remembered rule:

```bash
pdocs preference show RULE_ID
pdocs preference forget RULE_ID
pdocs preference remember ...
```

Commit `.pdocs/state/preferences/` after remembering or forgetting. Never put
the plaintext feedback in Git, commit messages, or source profile names.
