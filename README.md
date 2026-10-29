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

### Reuse just rules and categories

In **Rules & automation** or **Data & storage**, use **Export rules & categories**
to download a standalone JSON file. It contains all categories (including tax
groups, review flags and inactive categories), expense and credit rules, merchant
text, original statement category conditions, account/business references, amount
limits, automation/inclusion settings and paused status. This covers the entire
active profile regardless of page filters. It contains no transactions, source
documents, account digits, history or local database paths.

Use **Import rules & categories** in the destination profile to select the file,
map its businesses and source accounts, and **Preview import**. Add missing
businesses/accounts through the usual app controls first. Unmapped businesses and
accounts are skipped; scoped rules never silently become rules for every account.
Shared categories remain shared. Existing category settings and existing rules
are kept; identical rules are skipped, and differing rules with the same matching
conditions are left out with an explanation. Imported entries are additive.

New rules default to **Suggest only**. Check **Keep the file’s automation and
expense-inclusion settings** to preserve automatic categorization/trusted review
and expense inclusion. Paused rules stay paused. Inspect the destination, scope,
automation and skipped-item reasons, then choose **Import this preview**. Changed
rules/categories or changed mappings require another preview. Importing never
re-categorizes transactions; use **Run rule check** separately when desired.
Version 1 JSON files support up to 5 MB and 5,000 entries per collection. These
additive imports do not have a batch Undo; newly imported rules can be paused in
Rules & automation. The preview is the place to review the import before saving.

### Resume the full profile

An exported **SQLite database** contains the full profile: all transactions and
categorizations, credit decisions, merchant/credit rules with their account scopes
and automation levels, categories, businesses, accounts, confirmed import layouts,
view preferences, history and original row archives. Open it directly with **Open
profile**, or use **Restore export / backup** to copy it into new books.

Reports exports an **accountant summary** with three worksheets: category totals
and activity outside expense totals on the first, monthly totals on the second,
and **Transactions** on the third. The selected business and year limit all three
worksheets. **All businesses** combines every business in the profile, automatically
including businesses added later, and excludes transactions classified **Personal**
from the app view and every report export.
Unassigned activity on personal or shared accounts also stays in Personal holding
until assigned to a business. Business expenses paid through those accounts are
included after business assignment.
Select the year, open **Reports**, then choose **Export report → Excel** to collect the combined accountant summary and
transaction details in one workbook. Personal activity remains in **Personal holding**.
Transactions lists every non-personal row in that scope, including pending,
excluded, duplicate, payment and refund activity. It includes dates,
descriptions, businesses, source accounts, categories, amounts, review status,
totals inclusion and exclusion reasons, source references, notes and transaction
IDs. Filter the headers or scroll with the date/description columns frozen.
The Net expense USD column reconciles to the summary; activity outside totals
has no contribution. Charges and refunds remain separate in the summaries.
The workbook contains no hidden profile, rules or original raw row archives.
Use the separate SQLite export or profile backup for complete books.

Choose **Export report** to select a file type before downloading. **Excel (.xlsx)**
contains the three worksheets described above. **CSV (.csv)** contains the same
complete transaction table in one flat file for imports into other tools, without
summary worksheets or formatting. **PDF (.pdf)** contains printable category and
monthly summaries followed by all transactions with source references. Every
format follows the selected business and year and preserves the same expense
inclusion decisions. CSV and PDF exports cannot restore a profile.

Previously exported reusable Excel ledgers remain restorable. The legacy
`view=ledger&portable=1` API export retains that format for compatibility, with
a checksum-verified SQLite snapshot containing decisions and preferences but
excluding automation rule definitions.

To resume from a SQLite export or a previously created reusable Excel ledger,
open the profile chooser, select **Restore export / backup**, upload that
`.xlsx` or `.sqlite3` file, and choose a new empty
folder. Both formats retain categorization decisions. Only a direct SQLite
database restores saved rules. Excel and ZIP restores exclude rules, including
rules hidden in older Excel exports. Import an editable rules JSON file through
**Rules & automation** to add rules separately. The uploaded file can come from
another local device or the browser connected to Docker.

Editing the visible spreadsheet report does not change its embedded profile.
Make decisions in the app and export a new copy. Older Excel reports, CSV ledgers,
and reports exported without reusable profile data cannot recreate a profile;
restore a newer portable export or SQLite database instead. Excel embedding
supports database snapshots up to 64 MB. Database exports have no Excel limit.

Original statement **row data** is retained in the database and reusable ledger.
Original statement **files** are included by **Download profile backup**; use that
ZIP when you want those files transferred too. ZIP backups retain the full
database for recovery, but the app's ZIP restore excludes rule definitions.
Export rules JSON separately, or extract and open the SQLite database when you
want to recover rules. Restores always use new/empty folders and never merge or
overwrite existing books.

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

## Edit rules outside the app

An **Are you sure?** prompt explains rule and profile actions before they run. It
names the active profile and describes account/business scope, automatic review
and totals behavior, profile switching/restoration, or exported file contents as
appropriate. Saving, importing, enabling/pausing rules, applying automation,
creating/copying/opening/restoring/renaming profiles, changing import grouping,
and copying/opening/exporting rule files require confirmation. Cancel stops that
action before it sends a request or starts a download. Previews and routine view
filters remain available without committing changes.

**Rules & automation** is the central place to manage expense and credit rules.
The save-rule controls beside transaction decisions create rules in this same
collection. CSV and Excel statement imports apply saved rules to new rows but
never create or edit rule definitions. SQLite databases and explicit rules JSON
imports are the supported ways to bring in rules from a file.

In **Rules & automation**, choose **Export JSON** to download
`local-bookkeeper-rules.json`. Edit it in any text editor, then choose **Import
JSON** in the same screen to save your changes to the active profile.

Every export starts with a `_comments` guide explaining the file sections, every
rule field, matching priority, expense categories, credit treatments, review
levels and `includeInTotals`, with examples. It is ordinary JSON data rather than
`//` comments, so the file stays valid JSON. The importer ignores this guide and
its examples; only objects in `rules` are saved as rules. You may edit or remove
the guide. Existing unedited exports receive it during the next confirmed refresh.

Reports shows one **Rules JSON** path with **Copy path** and **Open file** buttons.
Both create `bookkeeper.rules.json` beside the active profile if needed, containing
every saved expense and credit rule across all accounts and businesses, including
paused rules. After the active profile loads on app startup, a confirmation offers
to refresh its rules JSON automatically. This runs once per app session, without
requiring a visit to Reports. An unedited export also refreshes when copied or
opened. External file edits are preserved; import them explicitly in Rules &
automation to apply them. Open file uses the default desktop application on Windows,
or displays the saved JSON in the browser when running in Docker. The profile
locator (`bookkeeper.profile.json`) remains in Data & storage and contains only
the database location. Use **Export JSON** for a separate download of current rules.

- Keep an exported entry's `id` to update that rule. To add a rule, copy an entry
  and remove its `id`, or write a new entry without `id`.
- `reference` lists your active business IDs, account IDs and category names.
  Copy those values into the rules; editing `reference` does not create accounts,
  businesses or categories. Create those in the app first.
- Every rule must specify `accountId`. Explicit `null` means **Universal** and
  covers all current and future accounts in this profile. A specific account ID
  limits the rule to that account. Missing or blank scope is rejected, including
  when updating an existing rule. Expense rules need `businessId` and `category`.
- Unchanged rules and repeated identical additions are skipped. Entries omitted
  from the file remain saved. Set `active: false` to pause an exported rule.
- The entire file is validated before saving. An invalid entry reports its rule
  number and leaves all rules unchanged. Existing transactions stay as they are;
  use **Preview rules on existing rows** to review and apply the saved rules.

For example, a new expense rule can look like this. Replace the business ID with
one from your exported file's `reference.businesses` list:

```json
{
  "format": "local-bookkeeper-rules",
  "version": 1,
  "rules": [
    {
      "type": "expense",
      "patterns": ["OFFICE DEPOT", "STAPLES"],
      "accountId": null,
      "businessId": "COPY-YOUR-BUSINESS-ID-HERE",
      "category": "Office supplies",
      "mode": "categorize",
      "includeInTotals": false,
      "active": true
    }
  ]
}
```

`patterns` match merchant/description phrases with optional spaces and trailing store numbers, with any phrase sufficient
to match. Use `sourceCategories` for original statement category labels. If both
lists are present, a transaction must match a phrase **and** a category. Optional
`minAmount` and `maxAmount` set inclusive, nonnegative amount limits in dollars
(for example, `"10.25"`); `null` leaves a limit open.

Automation `mode` is `suggest`, `categorize` or `review`. `suggest` proposes a
decision; `categorize` assigns it but leaves review pending; `review` automatically
approves eligible future matches. Only a `review` rule for a business expense or
refund can set `includeInTotals: true`.

Money-in rules use `type: "credit"` and a `treatment` of `payment`, `refund`,
`statement_credit` or `excluded_credit`. Business refunds also use `businessId`
and `category`. File import supports up to 1,000 rules and browser uploads up to
5 MB. File edits take effect after you import the file.

## Import → review → report

Use **Add transaction** in **Transactions** or **Review queue** to enter an item
without importing a statement. Choose its source account, date, description,
positive USD amount, money movement, kind, business/personal assignment, category
and optional notes. New entries start with no account selected and totals off.
They are saved for review unless you explicitly include a valid business expense
or refund. Incoming amounts can be reviewed further in **Credits & payments**.
Manual entries do not automatically apply or create rules.

The original entered values remain read-only after edits, with their creation
and review history retained. Manual entries appear in transaction exports and
reports and are labeled **Manual entry** rather than assigned an invented source
document. Matching future statement rows are flagged as possible duplicates.
Repeated saves after a lost response return the same transaction.

Choose **Single file** or **Batch upload** when importing. Batch upload accepts
up to 25 statements, 20 MB per file, and 100 MB total. Select one source account
and shared settings for the entire batch: remember layouts, group by statement
category, and explicitly permit duplicate documents if needed. Use the statement
picker to inspect each preview, confirm the shared settings once, then import
all files together. CSV, XLSX, and supported Chase checking PDFs can be mixed.
A PDF identifying a different account stops the batch before any new file saves.
Remove unsupported files to continue with the others. Canceling releases unused
previews and leaves saved originals alone. Each new batch starts with a blank
account and fresh layout, duplicate and confirmation choices.

Each statement saves independently. If a later statement fails, completed files
stay imported; retrying the batch does not add them again. Reload an expired
preview and confirm it again before retrying. Previews expire after 30 minutes.

1. Add a source account using a nickname and optional last four digits. An
   account's business owner organizes accounts; each transaction's business
   assignment determines which books contain it.
2. In **Imports**, choose a CSV, XLSX or supported PDF statement, inspect the preview, and choose
   the source account explicitly. No transactions are saved by previewing.
3. American Express transaction workbooks have a dedicated adapter. It locates
   the transaction table, preserves worksheet/row references, and reconciles
   charges, credits and net amounts against the summary when present. A mismatch
   stops import. Confirm the provider's sign mapping before committing.
4. Text-based **Chase checking PDFs** with a Checking Summary and a
   `DATE / DESCRIPTION / AMOUNT / BALANCE` transaction table can be imported,
   including continued tables across pages and December/January year changes.
   Negative amounts are bank withdrawals; positive amounts are deposits.
   Every running balance, gross deposits/withdrawals and the closing balance
   must reconcile before the preview opens. Card-payment descriptions retain
   transfer kinds; deposits remain money-in activity for review. Select the
   checking account shown in the preview; known last-four mismatches and credit
   card accounts are rejected. Confirm extraction and amount mapping to import.
   The original PDF and extracted page/line text are retained. Scanned/image-only,
   locked, multi-account and other PDF layouts need CSV/XLSX instead; OCR and
   generic PDF mapping are not implemented.
5. Generic CSV/XLSX tables recognize common date, description, amount, debit,
   credit and type headers within the first 50 rows. An ambiguous signed Amount
   column remains direction-unknown for review. Formula-containing transaction
   rows and multiple transaction tables are rejected with an explanation.
6. New transactions start unapproved, unassigned and outside expense totals before enabled import rules run.
   Provider categories remain source evidence. Enabled automation rules may assign categories; review business purpose, category,
   direction and kind yourself. Card payments are suggested as transfers; merchant
   credits require review before being treated as refunds.
7. **Review queue** supports individual editing and batch actions. Expense totals
   accept reviewed business debit expenses/fees and credit refunds only. Personal
   activity, transfers, excluded rows and confirmed duplicates remain searchable.
8. Exact file re-imports require explicit confirmation. Matching transactions on
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

**Overview → Uncategorized spending** shows the total money out still missing a
bookkeeping category and its transaction count. **Review uncategorized charges**
opens those transactions using the same business and year. Uncategorized money
in and amounts with an unknown direction are shown separately, so credits never
cancel out spending. Personal items, transfers, excluded rows, confirmed
duplicates, and credits already handled as payments/benefits are omitted.

**Review queue** and **Transactions** show a **Still to categorize** summary for
the current filters, including account, search, date and status filters. Choose
**Show uncategorized** to narrow the list. Empty categories and labels containing
Uncategorized use the same definition in the summary and filter. Categorizing
rows updates these amounts even before approval. **Reports → Behind the report**
shows the same category backlog for its business/year, with links to the rows;
it does not change the included expense total or exported report calculations.

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
accounts, and an automation level. A blank new rule requires you to choose its
scope; rules created from one account default to that account. Selections across
accounts require an explicit choice, and a previous rule's scope is never reused
for a new rule. Choose **Universal** to cover every current and future account in
this profile. Leave merchant descriptions blank to match
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
- Merchant rules match names in the merchant field or full transaction description,
  ignoring case and punctuation. Spaces between phrase words may be omitted, and
  store numbers may follow a name: `MAVIS` matches `MAVIS123`, and `ADVANCE AUTO`
  matches `ADVANCEAUTO`. Word boundaries stay intact: `MAVIS` does not match
  `MAVISION`, and `APPLE.COM` does not match `PINEAPPLE.COM`. Explicit store
  numbers stay exact: `STORE 12` does not match `STORE 123`. No wildcard is needed.
  Existing merchant rules use this behavior too. Original statement category
  labels still match complete normalized labels. To change existing eligible
  unreviewed transactions, choose **Run rule check**, inspect the preview, then
  apply it. New imports use the saved rule's automation level automatically.
- Expense rules targeting **Personal / non-business** classify matches as personal,
  remove the business assignment and exclude them from expense totals. Their
  business selection identifies the existing category catalog only. Keep
  `includeInTotals` false. Business refunds cannot use a personal category.
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

- CSV, XLSX and supported text-based Chase checking PDF imports, review/export,
  bulk categorization and merchant suggestion rules are implemented. Scanned PDF
  OCR, other PDF statement layouts and saved manual column mappings remain future work.
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
- `GET /api/export.xlsx`, `/api/export.csv`, `/api/export.pdf` — optional `businessId`, `year`.
  XLSX defaults to the accountant summary (`view=summary`), without profile data.
  Legacy detailed exports use `view=ledger`; explicitly add `portable=1` to embed
  a reusable profile. Summary exports reject embedded profiles. CSV defaults to
  the included expense ledger; `view=transactions` exports all transaction details
  in the selected scope. PDF includes summaries and a complete transaction appendix.
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
