# AI transaction review: feasibility and implementation plan

Draft: October 22, 2026. Based on static inspection of the current code. No live
books were analyzed and no tests were run for this documentation change.

## Recommendation and feasibility

**Feasibility: 9/10 for AI suggestions with user review; 8/10 for a local agent
using restricted tools; 6/10 for broadly autonomous bookkeeping changes.** These
scores rate the fit with this codebase, not the likelihood that an AI's financial
judgment is correct.

The project already has a Python HTTP API, SQLite storage, a rule engine,
categorization and credit planners, revision checks, transaction history, and
conflict-aware undo. This is an extension to an existing backend. A new database,
bank integration, web framework migration, or hosted service is unnecessary for
the requested capability.

Start with an **AI review bundle and suggestion importer**. Export selected rows
with their IDs and relevant context; have Codex or another AI return structured
suggestions; import those suggestions as drafts; review and apply them through
the existing planners. This can work without embedding a model provider in the
app. A live CLI or MCP connection can use the same proposal layer later.

An even smaller experiment is to give an agent an exported SQLite copy, request a
written review, and enter its useful suggestions through the existing grouping,
categorization, and rule screens. That needs no application changes.

## What is already implemented

| Capability | Current implementation | Consequence for this addition |
| --- | --- | --- |
| Local Python + SQLite backend | `server.py:66`, `server.py:79`, `server.py:472` | Keep the existing stack. |
| Transactions, accounts, businesses, categories | `server.py:560`–`server.py:575` | The agent's core reading operations already exist. |
| Original values and decision explanations | `server.py:776`, `source_archive.py` | Give the AI evidence and preserve imported facts. |
| Categorization preview and commit | `categorization.py:101`, `categorization.py:180`; routes at `server.py:694` | Reuse validation and atomic transaction batches. |
| Credit/payment/refund workflows | `credits.py`; routes at `server.py:668` | Keep money-in decisions separate from expense categorization. |
| Rule matching, specificity and conflicts | `automation.py:39`, `automation.py:70` | AI proposes rule conditions; existing Python evaluates them. |
| Suggest, categorize, and review automation levels | `automation.py:10`, `automation.py:265` | Keep AI-generated rules in Suggest mode initially. |
| Rule preview and save | `automation.py:193`, `automation.py:223` | New rule drafts can use the existing engine. |
| Suggested rules learned from reviewed examples | `automation.py:241` | Some desired assistance already exists without a model. |
| Batch and rule UI | `categorize.js:130`, `automation.js:132` | Seed existing dialogs with an AI draft. |
| Transaction history and undo | `server.py:860`, `server.py:887` | Applied transaction changes can retain current audit behavior. |
| Portable database exports and backups | `server.py:594`, `backup.py` | Read-only review of an exported copy is available immediately. |

Existing rule ideas require at least two approved transactions with the same
normalized merchant and account, a consistent destination, and no matching saved
rule. AI would add value by reasoning about unfamiliar descriptions, suggesting
broader merchant groupings, and identifying inconsistent decisions. Business
purpose may still need a question to the user.

## Gaps that affect the design

1. **The API is local and trusts local clients.** `Handler.local_request()` checks
   Host and Origin. The workspace header prevents writes to the wrong active
   profile; it is not an agent credential. There are no distinct agent roles or
   scoped tokens. A remote agent cannot reach the user's loopback server without
   an additional connection mechanism. Codex running beside the local app can;
   a cloud Codex workspace would need an exported bundle or configured bridge.
2. **Transaction reads return the entire profile.** `/api/transactions` currently
   does not implement search, filters, field selection, or pagination. These are
   useful for a live agent, but unnecessary for an initial selected-row export.
3. **Existing suggestions come from rules.** There is no stored AI proposal model,
   model client, prompt schema, or model evaluation workflow.
4. **Rule saves do not enforce a prior server preview.** The UI previews first,
   but `automation.save()` does not require a revision. Add a revision check at
   the new proposal gateway before permitting programmatic rule writes.
5. **Transaction undo does not undo rule changes.** Rule inserts, updates, and
   activation changes lack equivalent rule history. The first version should
   allow reviewed creation of new Suggest rules, record their origin, and offer
   Pause. Editing existing rules through an agent needs rule history/revisions.
6. **Long model calls would block the current request path.** GET and POST use a
   global workspace lock, and browser requests default to a ten-second timeout
   (`app.js:166`). In-app model work must run outside that lock and outside open
   SQLite transactions, then revalidate the workspace and data on return.
7. **Current batches have one destination.** A categorization batch applies one
   category/business decision. Group imported proposals by destination and review
   them separately. An eventual heterogeneous “Apply all” needs an explicit
   transaction boundary; several HTTP calls are not one atomic operation.
8. **The ordinary CSV export is insufficient for this task.** `export_csv()`
   exports approved, included business expenses/refunds, omits review-queue rows,
   and does not export transaction IDs. Use a database copy or a dedicated JSON
   review bundle. A portable Excel ledger contains the full embedded profile by
   default; it is not a minimal export of just the visible rows.

## Alternatives and rough effort

Estimates are engineering working days for someone familiar with this repository,
using Codex for implementation. They include focused validation and assume a
single local user, existing imports, and no deployment or bank-connection work.
They are planning ranges, not completion guarantees; dependent options are not
all additive or interchangeable.

| Approach | Effort | What the user does | Main tradeoff |
| --- | --- | --- | --- |
| Existing deterministic rule ideas | Already present | Review proposed rules in Rules & automation | Limited to repeated, consistent reviewed merchants. |
| Agent reviews an exported database copy | No app changes; roughly half a day to a day for a repeatable helper/prompt | Ask for a report; implement chosen changes using existing screens | Lowest effort, manual transfer of suggestions. |
| Structured review bundle + suggestion importer | About 4–7 days total | Export, ask an AI to review, import its response, preview chosen changes | Recommended balance; one manual round trip. |
| Local CLI/MCP adapter | About 2–5 additional days after the proposal foundation | Ask a locally connected agent to inspect rows and draft changes | Requires a compatible local agent client and tool setup. |
| In-app AI review button | About 5–10 additional days after the proposal foundation | Select rows and click Review with AI | Needs model access, jobs, cost controls, and data-sharing settings. |
| Broad automatic changes and existing-rule edits | Several additional weeks, scope dependent | Configure which decisions the agent may execute | Needs rule audit/undo, tighter scopes, idempotence, and demonstrated quality. |

Read-only SQL against an exported snapshot is useful for analysis. All accepted
changes should pass through the app's planners so validation, reporting state,
history, and undo stay consistent.

## Proposed first implementation

### Phase 1: export a useful review bundle — about 1–2 days

- Add `ai_review.py` for bundle creation and schema validation, plus
  `docs/ai-review-prompt.md` with a reusable review prompt and response contract.
- Add an “Export for AI review” action for explicitly selected transactions or
  the current filtered set. Resolve the final IDs on the server and enforce the
  existing 5,000-row upper bound; cap the number of examples and output size too.
- Include a format version, bundle ID, workspace identity, selected transaction
  IDs, selection scope, and a snapshot revision. Include date, merchant,
  description, integer cents, movement/kind, current business/category, review
  state, and original statement category. Include available business/category
  IDs, relevant rule definitions, and a bounded set of reviewed examples.
- Add a profile-scoped `ai_review_bundles` table through the existing migration
  mechanism. Keep a server-side bundle record containing expected scope and
  revisions; never trust expected state supplied only by the AI's return file.
  Include rule and category context in that revision as well as transaction
  fields. Advance and validate the database schema version for this migration.
- Omit raw document blobs, local filesystem paths, account suffixes, and notes
  from the default bundle. Show the scope before export. The chosen external AI
  receives the exported information; the bookkeeping app can stay local.
- Ask the AI to suggest categories, propose rules, identify inconsistencies, and
  ask questions when purpose is unclear. Require references to supplied IDs and
  reviewed examples where applicable. Merchant names alone do not establish
  business use.

### Phase 2: import and review suggestions — about 3–5 more days

- Add a profile-scoped `ai_review_proposals` table through the existing
  initialization/migration mechanism. Store proposal payload,
  explanation, evidence IDs, lifecycle status, bundle identity, and applied
  action/rule IDs. Keep source/model information as provenance, not authority.
- Add an “Import AI suggestions” action. Parse a bounded JSON document and
  validate its version, bundle, action types, referenced IDs, categories,
  business relationships, evidence scope, and current state. Reject unknown
  executable fields. Importing stores drafts and does not change transactions
  or active rules. Render imported explanations as escaped text.
- Support two executable draft types initially: categorize eligible unreviewed
  debit expenses/fees, and create a new Suggest-only expense rule. Represent
  other findings as questions or review notes. Credits/refunds, transfers,
  duplicate decisions, reviewed-row corrections, and existing-rule changes can
  be reviewed manually using their current dedicated screens.
- Add a small review panel showing the current decision, proposed decision,
  explanation, supporting examples, and affected count. Let the user edit,
  reject, or preview each proposal. Add a seed parameter to `openCategorize()`;
  extend `openAutomationRule()` so AI drafts explicitly start in Suggest mode
  and preserve proposed amount/source-category conditions.
- Reuse `categorization.plan()` / `commit()` for transaction changes and
  `automation.values()` / `rule_preview()` / `save()` for new rules. Do not
  reinterpret an AI suggestion as an existing deterministic rule suggestion.
- Require a fresh server preview after any user edit and before commit. Bind its
  revision to the canonical proposal, selected IDs, current transaction/history
  state, category/business availability, and relevant rules. Recompute rule
  coverage at commit. An edited row, switched profile, or changed context must
  require another preview.
- First-version transaction changes remain unreviewed and outside totals. The
  agent cannot set approval or totals inclusion. Exclude approved, excluded,
  personal, transfer, duplicate, linked, or direction-unknown rows from automated
  application; retain them for explicit review.
- In one database transaction, commit the chosen action and mark its proposal
  applied. Repeating the request must return the existing result, avoiding
  duplicate rules or history. One destination group is one atomic action.
- Link transaction actions to their proposal explanation and evidence while
  retaining existing Undo. For a new rule, record its ID and origin and provide
  Pause; clearly state that undoing transaction changes does not remove a rule.
- Let the user dismiss stale suggestions or export a new bundle. If edited
  suggestions are allowed, preserve the original proposal as provenance and
  preview the edited payload as a new revision.

Suggested new API surface:

| Route | Responsibility |
| --- | --- |
| `POST /api/ai-review/export` | Validate the selected IDs, save a snapshot record, and download a JSON bundle. |
| `POST /api/ai-review/import` | Validate the returned file and store draft proposals. |
| `GET /api/ai-review/proposals` | Return proposals for the active profile, with status filtering and bounded results. |
| `POST /api/ai-review/preview` | Preview one proposal or one same-destination group against current data. |
| `POST /api/ai-review/apply` | Apply an explicitly selected, current preview and record its provenance atomically. |
| `POST /api/ai-review/dismiss` | Dismiss a proposal without changing the books. |

The existing workspace header remains required for these routes. The first
version uses the local app's existing trust model and explicit UI review. It
does not require remote agent authentication because the agent returns a file.

Example response contract, using placeholder IDs:

```json
{
  "schemaVersion": 1,
  "bundleId": "bundle-123",
  "suggestions": [
    {
      "type": "categorize",
      "transactionIds": ["tx-123"],
      "businessId": "business-123",
      "categoryId": "category-fuel",
      "reason": "Matches the merchant and account of the supplied reviewed fuel examples.",
      "evidenceTransactionIds": ["reviewed-tx-456"]
    },
    {
      "type": "create_rule",
      "ruleType": "expense",
      "patterns": ["EXAMPLE FUEL MERCHANT"],
      "accountId": "account-123",
      "businessId": "business-123",
      "categoryId": "category-fuel",
      "reason": "The supplied reviewed examples use the same destination.",
      "evidenceTransactionIds": ["reviewed-tx-456"]
    }
  ],
  "questions": [
    {
      "transactionIds": ["tx-789"],
      "question": "Was this purchase for the business or for personal use?"
    }
  ]
}
```

Rules created through this contract are forced to Suggest mode by the server.
Account-wide scope must be explicitly reviewed. Statements and descriptions are
data, not instructions to the agent. Model confidence is advisory and does not
grant write permission.

### Phase 3: optional live agent tools

Once the proposal workflow is useful, add a local CLI or stdio MCP adapter with
tools such as `list_transactions`, `get_transaction_evidence`, `list_categories`,
`list_rules`, `preview_rule`, and `submit_proposals`. Filter and paginate reads,
pin the workspace identity for each analysis, and expose an explicit tool
allowlist. The first live adapter can remain read-and-propose only; the user
continues applying proposals in the app.

For agent-executed commits, add scoped credentials or a separate restricted
local service that cannot use unrestricted legacy write routes. Scope actions
by profile, action type, and selected rows; enforce the limits in application
code. A prompt that says “read only” does not restrict the existing API.

Before allowing edits to existing rules, add rule revisions, before/after
history, conflict-aware undo, and attribution. A hosted MCP/HTTP service also
needs remote authentication and a deliberate connection to the local app;
transport changes alone do not solve access to the user's machine.

### Phase 4: optional in-app model execution

Use the same bundle/response contract with a provider adapter. Snapshot the
selected data under the workspace lock, release the lock and database connection,
then run inference in a background job. Poll for status and discard or revalidate
results if the profile or snapshot changed. Keep provider credentials on the
server, set request/token limits, and support cancellation and timeouts. A local
model can use the same contract if its suggestion quality is adequate.

## Validation and acceptance criteria for implementation

Use the current unittest fixtures and temporary databases, including
`tests/test_categorization.py`, `tests/test_credits.py`, and
`tests/test_decision_rules.py`. Add targeted tests for the new boundaries:

- Export includes selected review-queue rows and stable IDs; default export
  omits raw documents and filesystem paths.
- Import and dismissal leave transactions and active rules unchanged.
- Invalid categories, foreign profiles, invented evidence IDs, unexpected action
  fields, malformed JSON, and oversized payloads are rejected.
- A changed row, changed relevant rule/category, or profile switch invalidates a
  pending preview; apply checks again inside its database transaction.
- Mixed eligible/ineligible selections cannot silently partially apply. The user
  must choose a valid subset and preview it again.
- Agent proposals cannot approve transactions, include totals, rewrite financial
  amounts/source facts, or modify existing rules in this version.
- Repeated apply/import requests do not create duplicate actions or rules.
- Accepted transaction changes have proposal provenance and can be undone under
  the existing conflict rules. New rules remain Suggest-only and can be paused.
- Copies, SQLite exports, reusable Excel profiles, and restores retain the new
  proposal tables, without changing original source archives or report totals.
- Manual smoke review covers selection, export, import, edit, preview, commit,
  dismissal, pause, undo, and profile switching.

For model quality, later evaluate suggestions on a separately held set of
reviewed transactions, track corrections and abstentions, and keep ambiguous
business purpose as a question. Do not estimate accuracy from the model's own
confidence score.

## First deliverable

Build the export/import review bridge with expense category suggestions and new
Suggest rules. Use it on a small selected set, inspect the proposed changes, and
measure how much manual work it removes. That provides a useful addition while
keeping the local architecture and reusing the app's existing review behavior.
