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

## Storage and backups

The default data folder is `%LOCALAPPDATA%\LocalBookkeeper` on Windows, or
`~/.local-bookkeeper/LocalBookkeeper` elsewhere. It contains `bookkeeper.sqlite3`
and managed original statements in `documents/`. SQLite is authoritative;
originals are copied before their database references are committed. Import
previews persist for 30 minutes and can be committed once. Schema upgrades are
additive and preserve existing books.

Set `LOCAL_BOOKKEEPER_DATA` to use another directory, and
`LOCAL_BOOKKEEPER_PORT` to change the port:

```powershell
$env:LOCAL_BOOKKEEPER_DATA='C:\MyBooks'
.\run_local_bookkeeper.bat
```

**Data & storage → Download backup** creates a ZIP containing a consistent SQLite
snapshot, its retained originals and a SHA-256 manifest. Pending previews are
omitted. A manifest records any missing originals. Keep backups private.

Restore into a **new** directory; existing books are never overwritten:

```powershell
# Stop the app first.
.\.venv\Scripts\python.exe backup.py restore C:\Backups\bookkeeper-backup.zip C:\RestoredBooks
$env:LOCAL_BOOKKEEPER_DATA='C:\RestoredBooks'
.\run_local_bookkeeper.bat
```

Restore validates checksums, safe paths, SQLite integrity and foreign keys before
making the restored directory available. Verify the restored books before
retiring your previous copy.

## Scope and privacy

- CSV and XLSX import/review/export are implemented. PDF, OCR, saved manual column
  mappings, automatic merchant rules, and a restore wizard remain future work.
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

- `GET /api/health`, `/api/businesses`, `/api/accounts`, `/api/categories`,
  `/api/documents`, `/api/transactions`
- `POST /api/businesses`, `/api/accounts`
- `POST /api/imports/preview` — `filename`, `contentBase64`
- `POST /api/imports/commit` — `token`, `accountId`, provider `confirmMapping`,
  optional explicit `allowDuplicate`
- `PATCH /api/transactions/{id}` — reviewed fields, including explicit
  `includeInTotals`
- `POST /api/review/batch` — unique `ids`, `action`, optional `businessId`
- `GET /api/review/actions`, `GET /api/transactions/{id}/history`
- `POST /api/review/undo` — `actionId`
- `POST /api/duplicates/resolve` — `transactionId`, `canonicalId`,
  `decision` (`duplicate` or `distinct`)
- `GET /api/export.xlsx`, `/api/export.csv` — optional `businessId`, `year`
- `GET /api/backup`
