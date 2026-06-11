# Remembered Decision Preferences

PDM gives agents durable, encrypted memory for user decisions about:

- whether a narrowly described document kind should be added or skipped
- how recurring documents should be organized

This state belongs to PDM rather than the conversational agent runtime. It is
shared through the private vault and available after a Git pull on another
trusted device.

## Agent Behavior

The agent should consult remembered preferences before reviewing candidates.
It should then:

1. Apply a matching rule automatically without asking again.
2. Use the record policy and existing vault structure for clear new cases.
3. Ask only when uncertainty could materially affect retention, lifecycle,
   ownership, or recurring organization.
4. Include a recommended default in the question.
5. Record the answer as a narrow encrypted rule and explain its scope.

The agent should not ask about cosmetic naming, capitalization, obvious
taxonomy choices, or other low-risk reversible details.

## Inclusion Preferences

```bash
pdocs preference remember inclusion \
  --match "monthly statements from Example Bank" \
  --decision add \
  --source-kind gmail \
  --instruction "Retain every statement as a dated financial event."
```

Use `--decision skip` for recurring items that should not enter the vault.
Source kind and source profile are optional qualifiers that prevent a rule from
being applied too broadly.

## Organization Preferences

```bash
pdocs preference remember organization \
  --match "monthly statements from Example Bank" \
  --domain finance-insurance \
  --owner self \
  --lifecycle event \
  --id-prefix "finance-insurance/banking/example/statements" \
  --instruction "Group by calendar year."
```

The record ID hierarchy remains the stable semantic organization inside the
encrypted vault. The readable view is flatter: it defaults to one descriptive
domain folder and uses the explicit filename selected by the importing agent.
Agents should inspect neighboring record IDs and use existing conventions
before asking for a new preference.

Deeper readable folders remain available for a coherent property, legal case,
or other dossier where grouping materially helps retrieval. Avoid folders that
only restate a filename, issuer, document type, or non-semantic issue date.

The importing agent must choose an explicit `--view-name` for every document.
Use a stable descriptive title and store the issue date in `issued_at`. Do not
put a date in a title or view name merely because the document was issued that
day. A date or period may remain when it is part of the document's identity,
such as a tax year or payslip month. Duplicate readable names fail refresh and
must be resolved by the agent.

If a better presentation is discovered after intake, persist it without
changing the semantic record ID:

```bash
pdocs record organize RECORD_ID \
  --name "Descriptive filename" \
  --folder "Finance, Tax and Banking"
```

## Inspect And Change Preferences

```bash
pdocs preference list
pdocs preference list --json
pdocs preference show RULE_ID
pdocs preference forget RULE_ID
```

An exact selector cannot be silently replaced. Forget the old rule, then
remember the replacement. Both operations append encrypted events, preserving
auditable history.

After remembering or forgetting:

```bash
git add .pdocs/state/preferences
git commit -m "Update document handling preference"
git push
```

Use a neutral commit message because the preference contents are encrypted but
Git metadata is not.

## Privacy And Scope

Preference matches and instructions may reveal issuers, document types,
household structure, or filing habits, so event payloads are encrypted with the
vault cipher. Filenames contain only timestamps and random identifiers.

Rules should be specific enough to avoid surprising generalization. Feedback
about one institution, person, case, or document kind should not automatically
control unrelated records. A current direct user instruction always takes
precedence over an older rule.
