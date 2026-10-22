# Local Bookkeeper

A local Python + SQLite bookkeeping workspace. Import statements, review each
transaction, keep separate business books, and export Excel reports. The server
listens on `127.0.0.1`; normal processing does not use a cloud service.

## Setup and run

For Docker, run `docker compose up -d --build`, then open
<http://127.0.0.1:8766/>. Profiles and settings persist in a volume. See the
[Docker setup guide](docs/docker.md) for existing profiles, host-folder storage,
ports and updates.

### Native Python setup

Python 3.11 or later is required. From PowerShell in the project folder:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\run_local_bookkeeper.bat
```

Open <http://127.0.0.1:8765/>. Keep the terminal open; Ctrl+C stops the server.
Installation needs internet access once. The application works offline after
dependencies are installed. The launcher uses `.venv` when present.

Open the app through its local URL, rather than double-clicking `index.html`.
The file-only page provides a link to the running Python app.
The server versions interface assets by their content so a browser reload uses
matching scripts/styles after an update instead of mixing cached older files.

## Resume from exported books

An exported **SQLite database** contains the full profile: all transactions and
categorizations, credit decisions, merchant/credit rules with their account scopes
and automation levels, categories, businesses, accounts, confirmed import layouts,
view preferences, history and original row archives. Open it directly with **Open
profile**, or use **Restore export / backup** to copy it into new books.

Excel expense ledgers now default to **Include reusable profile** in Reports.
The visible financial worksheets follow the business/year report filters. The
embedded profile covers **every business and year**, which is stated beside the
export button and on the workbook's **Profile Restore** tab. Uncheck the option
to share just the filtered report without a profile copy. The profile uses a
checksum-verified SQLite snapshot stored in workbook cells, so its rules and IDs
resume exactly rather than being inferred from ledger labels or rounded amounts.

To start a new session, open the profile chooser, select **Restore export /
backup**, upload the exported `.xlsx` or `.sqlite3` file, and choose a new empty
folder. The restored profile opens with its rules and categorization decisions;
those rules continue running on future matching imports. The uploaded file can
come from another local device or the browser connected to Docker.

Editing the visible spreadsheet report does not change its embedded profile.
Make decisions in the app and export a new copy. Older Excel reports, CSV ledgers,
and reports exported without reusable profile data cannot recreate saved rules;
restore a newer portable export or SQLite database instead. Excel embedding
supports database snapshots up to 64 MB. Database exports have no Excel limit.

Original statement **row data** is retained in the database and reusable ledger.
Original statement **files** are included by **Download profile backup**; use that
ZIP when you want those files transferred too. Restores always use new/empty
folders and never merge or overwrite existing books.

## Profiles for each user

A profile keeps its own books, saved rules, categories, source accounts, confirmed
import layouts and preferences. In **Data & storage → Open / switch profile**:

- **Open profile:** choose a `.profile.json` file, a SQLite database (any filename),
  or an existing books folder. Use **Check location & saved rules** to see the
  database path, transaction count and rule count before opening it. SQL text
  exports are not SQLite files; reusable ledgers and backup ZIPs use Restore export / backup.
- **Create profile:** choose a new or empty folder outside the app, a profile name
  and the first business name. Each user can create independent books and rules.
- **Copy profile:** choose the source profile/database and a new empty destination.
  A consistent copy retains its rules and preferences. The source is preserved.
- **Restore export / backup:** upload a reusable Excel ledger, exported SQLite
  database or profile backup ZIP, or choose its path on the server. Select a new
  empty destination. Checksums and database integrity are checked before opening.
  Browser uploads support 20 MB; use a server file path for larger exports.

The active profile name appears in the top bar. Data & storage shows its database,
profile-file path, saved record counts and a profile-name editor. Recent profiles
are listed by name and location. Switching profiles clears old selections and
filters so one profile's business IDs and pending decisions do not carry over.

A new profile folder normally contains:

```text
My profile/
  bookkeeper.profile.json   # Portable locator/name; uses a relative database path
  bookkeeper.sqlite3        # Books, rules, categories, layouts and preferences
  documents/                # Retained original statements
```

Keep the folder together, or use **Download profile backup** to move it between
computers. Another user installs the app and selects their own profile. Browser
storage is not required to recover rules or preferences. Reporting year, business
selection, sort order and import-grouping choices are saved in the profile's
SQLite metadata. New profiles start at All businesses / All years. If filters
hide all rows, a notice shows the profile's total and offers **Show all profile
transactions**.

Transaction **Sort** is in the table toolbar beside the search/account controls
in Transactions and Review queue. Credits & payments has the same newest/oldest,
amount and merchant sorting options. The selected sort order is saved per profile.

## Import → review → report

1. Add a source account using a nickname and optional last four digits. An
   account's business owner organizes accounts; each transaction's business
   assignment determines which books contain it.
2. In **Imports**, choose a CSV or XLSX statement, inspect the preview, and choose
   the source account explicitly. No transactions are saved by previewing.
3. American Express transaction workbooks have a dedicated adapter. It locates
   the transaction table, preserves worksheet/row references, and reconciles
   charges, credits and net amounts against the summary when present. A mismatch
   stops import. Confirm the provider's sign mapping before committing.
4. Generic CSV/XLSX tables recognize common date, description, amount, debit,
   credit and type headers within the first 50 rows. An ambiguous signed Amount
   column remains direction-unknown for review. Formula-containing transaction
   rows and multiple transaction tables are rejected with an explanation.
5. New transactions start unapproved, unassigned and outside expense totals before enabled import rules run.
   Provider categories remain source evidence. Enabled automation rules may assign categories; review business purpose, category,
   direction and kind yourself. Card payments are suggested as transfers; merchant
   credits require review before being treated as refunds.
6. **Review queue** supports individual editing and batch actions. Expense totals
   accept reviewed business debit expenses/fees and credit refunds only. Personal
   activity, transfers, excluded rows and confirmed duplicates remain searchable.
7. Exact file re-imports require explicit confirmation. Matching transactions on
   the same source account are candidates; the transaction drawer lets you mark
   one duplicate or retain both as distinct. Nothing is silently deleted.
8. The drawer shows source evidence and change history. **Data & storage** lists
   recent actions with Undo. Rows edited after the original action are reported
   as conflicts and retained; successful reversals create new audit records.
9. **Reports** exports a workbook for the selected business/year with Expense
   Ledger, Monthly Summary, Category Summary, Tax Preparation Summary, Review
   Queue, Excluded Transactions, and Duplicate-Transfer Transactions worksheets.
   Refunds reduce expense totals. Source accounts, documents and rows remain
   traceable. CSV remains available at `/api/export.csv` with the same filters.

Every new import also stores an immutable source archive in SQLite. CSV records
and cell values from every XLSX worksheet are kept in separate source tables,
alongside each transaction's original import values. **Imports → Original data**
opens the stored rows even if the uploaded file is later unavailable. The
transaction detail panel compares the original normalized values with the
current editable values and highlights changes. Existing books are upgraded
from retained source evidence; if a matching original file is still present,
the migration also archives its full cell data. Otherwise the archive clearly
reports that it covers imported transaction rows only. Spreadsheet formatting
and images remain in the retained file.

Reports assist bookkeeping and tax preparation; inclusion is not a determination
of tax deductibility. Unassigned activity on personal/shared source accounts is
shown in All activity/Personal until assigned to a business.

## Fast categorization

**Review queue → Suggested batches** groups pending services and vehicle charges,
sets aside general-retailer purchases for receipt review, and highlights possible
refunds or rewards offsets. Cards show the affected count and amount, why rows
were grouped, and a question about their purpose. The panel follows the current
business, year, account, search, and other transaction filters. Use **Show all
batches** for the remaining groups and expand **Possible refunds and offsets**
to compare credits with earlier purchases.

**Review charges** opens the existing checked-row categorization dialog with a
category suggestion where appropriate; review and totals inclusion stay unchecked.
**Personal…** opens a separate confirmation. Credit comparisons show candidate
purchases without linking or changing them. Inspect a purchase and return to the
credit decision, then explicitly choose its treatment and any related link.
These suggestions run locally without an AI service or internet connection.
Groups and candidates are recomputed after edits; reading the panel never saves
a transaction decision or rule.

The app checks for **Personal / non-business** categories that are still assigned
to business books. Existing conflicts appear in a profile-wide notice, the
Review queue, and the **Check classification** filter, including previously
reviewed transactions. The notice shows how much is currently included in
expense totals. Saved decisions and totals stay in place until you correct them.
Open a flagged transaction and choose **Mark Personal**, then save, or choose a
business category. Quick categorization offers **Move checked rows to Personal**
with a separate confirmation. These checks also block new conflicting business
rules and prevent existing conflicting rules from applying on import; pause or
edit those rules in Rules & automation. Undo keeps a correction in place if its
old state would recreate the conflict.

**Transactions** and **Review queue** now have a shared categorization workspace:

- Quick filters for uncategorized, unassigned, rule suggestions, duplicates and
  review status. More filters includes the statement's original category, your
  category, books assignment, movement, date range and amount range.
- Search matches merchant, description, account, category, original statement
  category, filename and notes. Space-separated words must all match; `|` separates
  alternatives, for example `shell | exxon`. Press `/` to focus search.
- **Merchant groups** brings repeated descriptions together within each source
  account. Long numeric references are ignored for grouping only; the original
  descriptions remain unchanged. **Categorize entire group** opens one decision
  for every transaction in that card. **View rows** keeps a **Categorize all**
  action above the listed group. To apply one decision across multiple groups,
  filter the list, then use **Categorize all** in the merchant groups toolbar.
  The count always reflects the current filters. The dialog lists every affected
  transaction, provides a category dropdown with a custom category option, and
  previews the batch before saving the checked transactions.
- **Statement category groups** batches every transaction by the category
  description in its original statement, including matching transactions across
  merchants and accounts. Blank source categories form a separate group. The
  import preview can remember an option to open these groups after each import;
  each batch can receive one business/category decision. This uses the statement
  label as a suggested category, which can be changed before applying.
- Select rows, a merchant group or all filtered results, then **Categorize &
  assign** (keyboard: `C`). Choose a business and category, optionally create a
  custom category, then preview the exact changes before saving. Keep current
  business assignments when categorizing across already-assigned businesses.
- Categorizing alone saves rows for review and keeps them outside totals.
  **Mark reviewed** and **Include eligible expenses** are separate explicit
  choices. Transfers, confirmed duplicates and invalid reporting rows require
  separate attention. An exception prevents the entire batch from being saved.
- Expand **See all transactions** in a category or credit batch to check or
  uncheck individual rows. The selected count, amount and preview update to the
  checked set; leaving a row out only omits it from this batch and does not mark
  it excluded from bookkeeping.
- A category preview's **Needs attention** rows offer **Review transaction**,
  **Leave out of this batch**, and **Leave all flagged rows out**. Review opens
  the transaction drawer and returns to the batch after saving or going back,
  preserving the selection, business, category and review choices. Preview again
  after a repair. Credits can also be handled separately and left out of the
  category batch. Nothing is applied while checked rows remain blocked.
- Preview revisions detect intervening transaction or rule changes. Every
  applied batch has field history and can be reversed in **Data & storage**.
- **Save this decision as a rule** is available while categorizing a batch,
  reviewing a business expense in the transaction drawer, or making a credit
  decision. Choose **This account** or **All accounts in this profile**. The
  description phrase must match the selected rows. Rules use that phrase and
  money direction; unrelated activity on the account keeps its own decision.
- Choose **Apply this decision automatically** to reuse the category/credit
  handling and current review/totals choice on future imports. Unreviewed category
  decisions stay awaiting review. Choose **Suggest this decision for review** to
  keep future matches unapproved and outside totals. The preview explains the
  saved rule, scope and reporting behavior before applying the batch.
- A newly saved decision replaces prior rules for exactly the same description
  conditions and account scope. Account-specific rules take precedence over an
  all-account rule with the same description. More specific conditions and
  conflicts continue to follow the rules described below. Saved rules survive
  undoing transaction changes and can be edited or paused in Rules & automation.
- **Merchant rules** lets you create, preview, edit, pause and enable rules.
  Existing rules start in Suggest only mode. Suggestions are computed for new/unreviewed activity; reviewed transactions
  remain in place. Conflicting destinations are flagged instead of choosing one.
  Select matching rows and **Apply rule suggestions** to preview and save their
  proposed categories. Applied suggestions remain unapproved and outside totals.

The fastest first pass for a structured card statement is often **More filters →
Statement category → Select all results → Categorize & assign**. Use merchant
groups and saved rules for the repeat work in later imports. Selection is limited
to the current filtered results and the server accepts up to 5,000 rows per batch.

## Statement category rules and group layouts

In **Transactions** or **Review queue**, choose **Statement category groups**.
Use **Create statement category rule** on a card (**Create category rule** in
Details), or check several groups and choose **Create / add to category rule**.
The picker lists original statement category labels, rather than merchant names.
It can create a new category rule or add labels to an existing category rule.

Choose **Money out** for expense categorization or **Money in** for credit
handling. A mixed group has separate rules for its charges and credits. In the
builder, choose business/category or credit treatment, source account or all
accounts, and an automation level. Leave merchant descriptions blank to match
new merchants carrying those original labels. Up to 200 statement categories
can share a rule; any listed label matches, ignoring case and punctuation.
Preview checks that all chosen rows fit the conditions before saving.

While categorizing or deciding credits, **Save this decision as a rule** also
lets you choose **Original statement categories** as the matching basis. Rules
use retained original categories, independently of the editable bookkeeping
category. Blank source categories cannot create a catch-all category rule.
Merchant-specific rules can still provide exceptions; a single-category rule
outranks a multi-category rule when the other conditions are equally specific.

Group views now provide **Cards / Details**. Details shows one merchant,
statement category or credit group per table row, with counts, amounts, source
accounts, current categories/decisions, checkboxes and the same review/rule
actions. Selecting groups works in either layout. Use **Transactions** (or
**Rows** in Credits & payments) for individual transaction rows. The group layout
choice is saved per profile and included in database/reusable-ledger exports.

The menu above the results changes to **Sort groups** in either group layout.
Largest/smallest total uses each group's combined activity; newest activity uses
its latest transaction and oldest activity uses its earliest transaction.
Name A–Z uses the merchant or original statement category label. Individual
transaction views sort their rows instead. The expanded **See all transactions**
lists in category and credit decisions have their own **Sort transactions** menu;
changing this order keeps the checked rows and pending decision unchanged.

## Combine selected transaction groups into a rule

In **Transactions** or **Review queue**, switch to **Merchant groups** and check
several group cards. Choose **Create / add to rule** in the selection controls.
The same action is available for selected groups in **Credits & payments**.

- The picker lists the chosen merchants with checkboxes. Leave unwanted groups
  out, then choose **Create a new combined rule** or an existing active merchant
  rule of the same type.
- Continue to the rule builder to confirm all merchant phrases, the source
  account (or all accounts), category/credit decision and automation level.
  Adding to an existing rule keeps its earlier phrases and other conditions.
- Preview checks that every chosen transaction matches the proposed rule. If an
  existing rule's account, source category or amount limits leave groups out,
  adjust those conditions explicitly or return to the picker.
- Save creates or updates one rule with up to 200 alternative merchant phrases.
  Its future matches can contain any one phrase. Existing transaction decisions
  are preserved; use the normal categorization/credit decision or existing-row
  automation preview to change them.
- **Save this decision as a rule** in category/credit batches also accepts several
  merchants: one phrase per line, filled from the selected groups.

## Rules & automation

Open the **Rules & automation** sidebar tab to manage expense and credit rules
in one place. Existing saved rules retain their destinations and begin in
**Suggest only** mode.

- Create rules from any category card, or choose **Create rule**. Add up to 200
  merchant phrases (one per line; any phrase can match), up to 200 original
  statement categories (any label can match), source account and optional USD
  amount bounds. All other
  supplied conditions must match together. Expense rules match money out; credit
  rules match money in.
- Choose the business/category or a credit treatment: payment, refund, statement
  benefit or other excluded credit. Refunds may belong to business books or stay
  outside them. Rules never automatically link payment pairs or original purchases.
- **Suggest only** proposes a decision. **Auto-categorize** assigns it during
  import and leaves the row awaiting review, outside expense totals.
  **Auto-review** requires the explicit trusted-rule checkbox. Including eligible
  business expenses/refunds in totals requires another separate checkbox.
- Preview historical matches before saving. Saving a rule affects future imports;
  it does not silently change existing rows. **Run rule check**
  shows the exact proposed changes across all books and years before applying.
  Reviewed, excluded, linked and possible duplicate rows remain in place.
- Rules with merchant phrases outrank broad original-category mappings. Within
  that level, account-specific rules outrank rules across all accounts, followed
  by original-category and amount conditions. Equally specific conflicting
  destinations stay for review. Identical destinations use the least automatic
  setting when their automation levels differ.

To run a rule pass on the current database, choose **Run rule check** at the top
of **Review queue**, **Transactions** or **Rules & automation**, inspect the
results, then choose **Apply this preview** to commit automatic decisions. This
checks eligible rows across the
entire active profile, regardless of the business/year filters on screen. It
preserves already-reviewed decisions, including rows previously auto-reviewed by
a trusted rule. Suggest-only matches are available in **Transactions → Rule
suggestions** or **Credits & payments** and require their separate review action.
The pass runs automatically on new rows when an import is confirmed. Saving a
rule does not rerun it across existing rows, and no background sweep is scheduled.

- **Rule ideas** are generated from at least two consistent reviewed decisions
  for a merchant/account. Find them in **Rules & automation → View rule ideas**,
  or scroll to **Combine rule ideas by category** on that page. Review and save
  each idea yourself before it can run. Broad original-category rules do not hide
  more precise merchant ideas; active merchant rules covering all examples do.
- **Combine rule ideas by category** collects store ideas for the same category,
  business and source account. Choose a Meals, Fuel or other group, then check
  the stores to accept together. Search the list, select all shown stores, leave
  individual stores out, or clear the selection. The summary counts selected
  stores and their reviewed transactions. Search keeps selections outside the
  visible results. Different businesses, source accounts and credit treatments
  remain separate groups, available in the picker's dropdown.
- **Continue with selected stores** opens one rule with the checked merchant
  phrases and the group's category, business and account already filled in.
  Choose automation, preview and save to accept them as a single rule. **Back to
  store picker** preserves the selection for changes. Up to 200 merchant phrases
  fit in one rule; saving does not modify existing transactions. All available
  ideas are shown, rather than a global top-50 list.
- Each confirmed import shows categorized, automatically reviewed, suggestion,
  conflict, unmatched and attention counts. Open each result group to inspect its
  rows. **Imports → Automation results** reopens the historical summary.
- Transaction explanations and history record the matching conditions and rule
  identifier. **Undo automatic decisions** reverses an import's automation while
  retaining its original rows/files. Later edits are retained as conflicts.
  Existing-row automation is also undoable in **Data & storage**.

Schema version 8 adds rule settings while preserving existing transaction values,
rule destinations and original source archives. No automatic behavior is enabled
for existing saved rules by this upgrade.

## Credits and card payments

Open **Credits & payments** to review money-in transactions separately from
charges. The queue uses the imported money movement; source amount signs vary
by provider. Filter descriptions/accounts, select rows, or make one decision for
an entire recurring-credit group. Merchant and statement-category groups also
offer **Handle credits** for their money-in rows.

- **Card payment / transfer** keeps payments outside income and expense totals.
  Optionally link an equal bank withdrawal on a different source account; the
  preview explicitly includes both sides and marks them as transfers.
- **Statement credit / account benefit** keeps a Walmart-style benefit or reward
  outside business books. Its original membership charge retains its own
  category and expense decision.
- **Purchase refund / reversal** can be recorded outside business books or
  assigned to a business expense category. Only the explicit **Reduce business
  expense totals by this refund** checkbox makes it reduce expenses. An optional
  purchase link helps compare the two rows, including partial refunds.
- **Other credit outside business books** excludes the credit while retaining
  its source and full activity history. **Leave unclear** returns it to review
  outside totals.

Related-transaction matching suggests compatible amounts/accounts/dates. Search
by description, date or amount to find another compatible match. Related rows
are visible in transaction details; linked amount/account/movement changes
require unlinking first. Preview revisions protect against intervening edits.
Saved credit decisions, pair links and reporting effects have audit history and
can be undone in **Data & storage**. Saved description rules remain available
after undo and can be paused in **Credit rules**.

Built-in description suggestions never automatically approve credits or include refunds. Saving a credit decision as a rule lets you explicitly reuse its approval and refund inclusion choice, or save a suggestion instead. Future rules never reuse transaction-specific payment or purchase links. Existing imports and approvals are preserved during the schema
upgrade and appear in **Needs decision** until a specific credit decision is
recorded. A business's normal ledger shows its assigned business activity and
unassigned activity on its owned accounts. Transfers and credits placed outside
business books remain in **All businesses**; the credit workspace also retains
them for its owned accounts. Excel/CSV exports include recorded credit decisions
and related transaction identifiers.

## Storage and backups

Your chosen profile folder contains its `.profile.json` locator, SQLite database and managed originals in
`documents/`. Keep that folder together; it is independent of the installed app.
The suggested new location is `Documents\Local Bookkeeper Books` (or a folder
under your home directory when Documents is unavailable). SQLite is authoritative;
originals are copied before their database references are committed. Import
previews persist for 30 minutes and can be committed once. Schema upgrades are
additive and preserve existing books.

The last selected profile/database location and recent profile names are remembered in
`%LOCALAPPDATA%\LocalBookkeeper\settings.json` on Windows, or
`~/.config/LocalBookkeeper/settings.json` elsewhere. An unavailable saved location
returns to setup instead of creating an empty replacement. `LOCAL_BOOKKEEPER_CONFIG`
can override this preference-file path. `LOCAL_BOOKKEEPER_DATA` is recognized as a
legacy location to offer during setup; saved user preferences take precedence.
`LOCAL_BOOKKEEPER_PORT` changes the local HTTP port.
`LOCAL_BOOKKEEPER_HOST` changes the bind address (native default `127.0.0.1`).
`LOCAL_BOOKKEEPER_ALLOWED_HOSTS` adds explicit comma-separated `host:port`
addresses when a container port mapping uses a different browser port. Requests
with an Origin must match the request's Host. `LOCAL_BOOKKEEPER_BOOKS_DIR` changes
the suggested new-profile location. Docker sets `LOCAL_BOOKKEEPER_STORAGE_ROOT`
to keep new profiles on its persistent volume.

No financial data or absolute personal location is stored in the source repository.
Switching books is serialized with database requests. Write requests identify the
active workspace, so a stale browser page cannot save into newly selected books.

**Data & storage → Download profile backup** creates a ZIP containing a consistent SQLite
snapshot, its profile locator, retained originals and a SHA-256 manifest. Rules and
preferences are included in the database snapshot. Pending previews are
omitted. A manifest records any missing originals. Keep backups private.

Restore into a **new** directory; existing books are never overwritten:

```powershell
# Stop the app first.
.\.venv\Scripts\python.exe backup.py restore C:\Backups\bookkeeper-backup.zip C:\RestoredBooks
.\run_local_bookkeeper.bat
```

Then choose **Open profile** and select `C:\RestoredBooks\bookkeeper.profile.json` in the app. The in-app Restore backup option also performs this workflow without terminal commands.

Restore validates checksums, safe paths, SQLite integrity and foreign keys before
making the restored directory available. Verify the restored books before
retiring your previous copy.

## Import and category explanations

- The import preview shows **How this statement was read**: detected provider,
  parser version, worksheet, header row, exact source-column map, skipped rows,
  amount/direction convention and date interpretation.
- **Why these values?** under each previewed transaction explains the original
  date and amount, source cents, normalized cents, direction and transaction kind.
  Bank categories remain source evidence, not approved business categories.
- Confirm the extraction before committing. Optionally remember the exact layout
  for the selected source account. Future matching layouts show the prior
  confirmation date; changed columns, adapter version or sheet are a different
  layout. Every import still needs confirmation and remains outside totals.
- **Data & storage → Confirmed import layouts** lets you revoke remembered
  layouts. Remembering a layout never approves transactions or trusts a different
  source account automatically.
- The transaction drawer shows **Why these values and this category?**, including
  original source values and the recorded category decision. Bulk decisions show
  their row count and selected activity total; rule previews show each match's
  phrase, account scope, source row, original amount and movement.
- Older imports without detailed saved evidence are labeled as such. The app
  does not invent a historical explanation; existing audit history and original
  rows remain available.

## Scope and privacy

- CSV and XLSX import/review/export, bulk categorization and merchant suggestion
  rules are implemented. PDF, OCR, saved manual column mappings, and a restore
  wizard remain future work.
- This is a single-user local app, not a hosted or network accounting service.
- The web server serves only the interface assets and defined APIs. Project
  documents, source code and data directories are not served as static files.
  Requests from other website origins are blocked.
- `Test docs/`, `data/`, `.venv/`, generated outputs and SQLite databases are
  ignored by Git. Keep private statements in the ignored folders, not in source.
- Amounts use integer USD cents; original amount/sign and raw source rows are
  preserved separately. SQLite constraints and API validation enforce inclusion
  and review rules. No fictional transactions or accounts are seeded.

## API overview

The frontend and API share the local server. JSON endpoints include:

Use `GET /api/health` first. If `setupRequired` is true, use setup before accessing
the books. Other write requests must send `X-Bookkeeper-Workspace` with the
`workspaceId` returned by health. Re-fetch health after changing books.

- `GET /api/setup`, `POST /api/setup` — `mode` (`create`, `open`, `copy`, `restore`),
  `directory` (a profile/SQLite file/folder for open; a new destination folder
  otherwise), optional `profileName`, first `businessName` for create, and
  `sourceDirectory` (source profile/database for copy, or SQLite/portable Excel/
  backup ZIP path for restore). Restore can instead accept `contentBase64` for a
  browser upload up to 20 MB; an uploaded file takes precedence over the path.
  `POST /api/setup/browse` accepts `kind` (`directory`, `file`, `backup`).
- `POST /api/setup/inspect` — `path`; read-only profile record counts and database
  location before opening.
- `POST /api/profile/settings` — partial profile preferences (`workspace`, `year`,
  `sort`, `groupImportsBySourceCategory`); writes require the active workspace ID.
- `POST /api/profile/name` — rename the active profile and update its locator.
- `GET /api/health`, `/api/businesses`, `/api/accounts`, `/api/categories`,
  `/api/documents`, `/api/transactions`
- `POST /api/businesses`, `/api/accounts`
- `POST /api/imports/preview` — `filename`, `contentBase64`
- `POST /api/imports/commit` — `token`, `accountId`, `confirmExtraction: true`,
  provider `confirmMapping`, optional `rememberLayout`, explicit `allowDuplicate`
- `PATCH /api/transactions/{id}` — reviewed fields, including explicit
  `includeInTotals`
- `POST /api/review/batch` — unique `ids`, `action`, optional `businessId`
- `GET /api/review/actions`, `GET /api/transactions/{id}/history`
- `GET /api/transactions/{id}/explanation`
- `GET /api/documents/{id}/source` — SQLite source archive, optional `sheet` and
  `offset` for pages of 100 stored rows.
- `GET /api/import-profiles`, `POST /api/import-profiles/revoke` — remembered
  import layouts and revocation by profile `id`.
- `POST /api/review/undo` — `actionId`
- `POST /api/duplicates/resolve` — `transactionId`, `canonicalId`,
  `decision` (`duplicate` or `distinct`)
- `GET /api/export.xlsx`, `/api/export.csv` — optional `businessId`, `year`.
  XLSX includes the full reusable profile by default (`portable=1`); use
  `portable=0` for a report without profile data. CSV contains report rows only.
- `GET /api/backup`
- `POST /api/categorization/preview` and `/api/categorization/apply` — selected
  `ids`, category/business, review/inclusion choices; apply requires the returned
  preview `revision`.
- `GET /api/suggestions`, `GET /api/rules`, `POST /api/rules/preview`,
  `POST /api/rules` — local merchant rules and non-approving suggestions.
- `GET /api/export.sqlite3` — download a consistent standalone SQLite snapshot
  of the active profile, including committed WAL data, saved rules/preferences
  and original row archives. Report filters do not limit this download. Staged
  imports are omitted from the copy; original statement files stay in the profile
  folder and are included by the full profile backup. Reports & exports provides
  an **Export SQLite database** button.
- `GET /api/automation` — unified rules, historical match counts, rule ideas and
  automation action statuses.
- `POST /api/automation/rules/preview`, `POST /api/automation/rules` — preview/save
  expense or credit rules with `patterns`, `sourceCategories` (or legacy
  `sourceCategory` for one label), `accountId`, optional
  `minAmount`/`maxAmount`, business/category or credit treatment, `mode`
  (`suggest`, `categorize`, `review`) and explicit `includeInTotals`.
  `id`, `type` and boolean `active` pause/enable an existing rule.
- `POST /api/automation/preview`, `POST /api/automation/apply` — preview/apply
  enabled automation to eligible existing rows. Apply requires the preview
  `revision`; intervening rule or transaction changes require a fresh preview.
- `GET /api/credits/suggestions`, `GET /api/credits/rules` — credit-only
  suggestions and saved description rules; `POST /api/credits/rules` accepts
  rule `id` and boolean `active` to pause/enable a rule.
- `GET /api/credits/{id}/candidates?treatment=payment|refund` — possible related
  transactions; optional `q` searches compatible original rows.
- `POST /api/credits/preview`, `POST /api/credits/apply` — selected `ids`,
  `treatment` (`payment`, `refund`, `statement_credit`, `excluded_credit`, or
  empty for unclear). Refunds specify `refundUsage` (`business` or `outside`),
  business/category and explicit `includeInTotals`. A single-credit decision
  may include `relatedId` (or null to unlink). Apply requires the preview
  `revision`. Optional `rememberRule`, `rulePattern`, `ruleAccountId` and
  `ruleAllAccounts` save a rule. `ruleMatch=sourceCategory` and
  `ruleSourceCategories` save the decision by original statement category.
  `rulePatterns` can supply several merchant
  phrases instead of the legacy `rulePattern` string. `ruleMode` selects `suggest` (the API default),
  `categorize`, or `review`. Category batch/transaction edits support the same
  rule options; automatic review requires a reviewed current decision.

Run the financial and source-retention regression checks with:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
