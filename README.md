# Local Bookkeeper

A local Python + SQLite bookkeeping workspace. Import statements, review each
transaction, keep separate business books, and export Excel reports. The server
listens on `127.0.0.1`; normal processing does not use a cloud service.

## Setup and run

Python 3.11 or later is required. From PowerShell in the project folder:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\run_local_bookkeeper.bat
```

Open <http://127.0.0.1:8765/>. Keep the terminal open; Ctrl+C stops the server.
Installation needs internet access once. The application works offline after
dependencies are installed. The launcher uses `.venv` when present.

On first run, the app asks where your books should live:

- **Create new books:** choose a new or empty local folder outside the app folder
  and enter your first business name. No business belonging to the developer or
  another user is seeded.
- **Open existing books:** choose a folder containing `bookkeeper.sqlite3` and
  its retained `documents/` directory. Legacy books are preserved and upgraded.
- **Copy existing books:** choose the source and a new or empty destination
  outside the app folder. A consistent copy of the database and retained originals
  is created; the source stays in place. Missing originals must be recovered
  before copying.

Use **Data & storage → Choose or move books** to choose another database later.
The app remembers the selected folder for the current computer user. A native
folder picker is available; enter the absolute path if the picker is unavailable.

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
5. New transactions start unapproved, unassigned and outside expense totals.
   Provider categories remain source evidence. Review business purpose, category,
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

Reports assist bookkeeping and tax preparation; inclusion is not a determination
of tax deductibility. Unassigned activity on personal/shared source accounts is
shown in All activity/Personal until assigned to a business.

## Fast categorization

**Transactions** and **Review queue** now have a shared categorization workspace:

- Quick filters for uncategorized, unassigned, rule suggestions, duplicates and
  review status. More filters includes the statement's original category, your
  category, books assignment, movement, date range and amount range.
- Search matches merchant, description, account, category, original statement
  category, filename and notes. Space-separated words must all match; `|` separates
  alternatives, for example `shell | exxon`. Press `/` to focus search.
- **Merchant groups** brings repeated descriptions together within each source
  account. Long numeric references are ignored for grouping only; the original
  descriptions remain unchanged. Open a group to inspect its rows.
- Select rows, a merchant group or all filtered results, then **Categorize &
  assign** (keyboard: `C`). Choose a business and category, optionally create a
  custom category, then preview the exact changes before saving. Keep current
  business assignments when categorizing across already-assigned businesses.
- Categorizing alone saves rows for review and keeps them outside totals.
  **Mark reviewed** and **Include eligible expenses** are separate explicit
  choices. Transfers, confirmed duplicates and invalid reporting rows require
  separate attention. An exception prevents the entire batch from being saved.
- Preview revisions detect intervening transaction or rule changes. Every
  applied batch has field history and can be reversed in **Data & storage**.
- **Remember this merchant** can save a source-account-scoped rule with the batch.
  The phrase must match every selected row. Choose All source accounts explicitly
  to broaden scope. A saved rule survives undoing transaction changes and can be
  paused independently.
- **Merchant rules** lets you create, preview, edit, pause and enable rules.
  Suggestions are computed for new/unreviewed activity; reviewed transactions
  remain in place. Conflicting destinations are flagged instead of choosing one.
  Select matching rows and **Apply rule suggestions** to preview and save their
  proposed categories. Applied suggestions remain unapproved and outside totals.

The fastest first pass for a structured card statement is often **More filters →
Statement category → Select all results → Categorize & assign**. Use merchant
groups and saved rules for the repeat work in later imports. Selection is limited
to the current filtered results and the server accepts up to 5,000 rows per batch.

## Storage and backups

Your chosen books folder contains `bookkeeper.sqlite3` and managed originals in
`documents/`. Keep that folder together; it is independent of the installed app.
The suggested new location is `Documents\Local Bookkeeper Books` (or a folder
under your home directory when Documents is unavailable). SQLite is authoritative;
originals are copied before their database references are committed. Import
previews persist for 30 minutes and can be committed once. Schema upgrades are
additive and preserve existing books.

Only the selected location is remembered in
`%LOCALAPPDATA%\LocalBookkeeper\settings.json` on Windows, or
`~/.config/LocalBookkeeper/settings.json` elsewhere. An unavailable saved location
returns to setup instead of creating an empty replacement. `LOCAL_BOOKKEEPER_CONFIG`
can override this preference-file path. `LOCAL_BOOKKEEPER_DATA` is recognized as a
legacy location to offer during setup; saved user preferences take precedence.
`LOCAL_BOOKKEEPER_PORT` changes the local HTTP port.

No financial data or absolute personal location is stored in the source repository.
Switching books is serialized with database requests. Write requests identify the
active workspace, so a stale browser page cannot save into newly selected books.

**Data & storage → Download backup** creates a ZIP containing a consistent SQLite
snapshot, its retained originals and a SHA-256 manifest. Pending previews are
omitted. A manifest records any missing originals. Keep backups private.

Restore into a **new** directory; existing books are never overwritten:

```powershell
# Stop the app first.
.\.venv\Scripts\python.exe backup.py restore C:\Backups\bookkeeper-backup.zip C:\RestoredBooks
.\run_local_bookkeeper.bat
```

Then choose **Open existing books** and select `C:\RestoredBooks` in the app.

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

- `GET /api/setup`, `POST /api/setup` — `mode` (`create`, `open`, `copy`),
  absolute folder `directory`, first `businessName` for create, `sourceDirectory`
  for copy. `POST /api/setup/browse` opens the local folder picker.
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
- `GET /api/import-profiles`, `POST /api/import-profiles/revoke` — remembered
  import layouts and revocation by profile `id`.
- `POST /api/review/undo` — `actionId`
- `POST /api/duplicates/resolve` — `transactionId`, `canonicalId`,
  `decision` (`duplicate` or `distinct`)
- `GET /api/export.xlsx`, `/api/export.csv` — optional `businessId`, `year`
- `GET /api/backup`
- `POST /api/categorization/preview` and `/api/categorization/apply` — selected
  `ids`, category/business, review/inclusion choices; apply requires the returned
  preview `revision`.
- `GET /api/suggestions`, `GET /api/rules`, `POST /api/rules/preview`,
  `POST /api/rules` — local merchant rules and non-approving suggestions.
