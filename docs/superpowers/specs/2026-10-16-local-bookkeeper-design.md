# Local Bookkeeper Design Specification

## Status

Design approved in conversation; awaiting review of this written specification before implementation planning.

## 1. Purpose

Create a local-first bookkeeping assistant for business expense tracking. The initial active business is Charlottesville Transportation LLC, with support for additional businesses later. The application imports messy financial documents, preserves source evidence, suggests classifications, requires user approval, and exports reviewable Excel workbooks for tax-preparation support.

The application is bookkeeping assistance, not tax advice or an automatic determination of deductibility.

## 2. Goals

- Process financial data locally on Gabriel's Windows computer.
- Use one reusable application and one SQLite database.
- Import CSV, XLSX, and PDFs from multiple providers and formats.
- Preserve original documents, raw extraction, source locations, and import metadata.
- Track the source account for every transaction using only a nickname and last four digits.
- Support multiple business entities without copied code or separate databases.
- Provide a separate Personal holding area for mostly-personal imports.
- Allow personal-source transactions to be reassigned to a business without duplicating them.
- Provide transparent category/business suggestions that always require approval.
- Support safe batch review with previews, totals, exceptions, undo/history, and no silent approval.
- Preserve excluded, personal, duplicate, and transfer records for reconciliation.
- Generate business-specific Excel exports from SQLite.

## 3. Non-goals for the initial release

- Bank-login automation or bank credentials.
- Cloud uploads, paid APIs, hosted services, or required internet access.
- Full personal budgeting or personal-finance dashboards.
- Revenue, invoicing, payroll, or accounts-receivable management.
- Automatic tax filing or definitive tax-deductibility decisions.
- Split-dollar allocations within a single transaction.
- OCR-first processing for scanned documents.
- Mobile application.

## 4. User model and workspaces

The app has two conceptual areas:

### Business workspace

A selected business workspace shows its review queue, transactions, categories, rules, and reports. The initial business is Charlottesville Transportation LLC. Additional businesses are added through the UI, not by copying code or creating another database.

### Personal holding area

The Personal area holds transactions classified as personal and provides search, notes, basic categories, review, and reclassification. It is not a full budgeting product. A transaction from a personal account may be reclassified to a business and then appears in that business's reports without creating a second transaction.

## 5. Core transaction rules

Each normalized transaction initially has exactly:

- One source account.
- One category or no category while awaiting review.
- One classification: business, personal, transfer, or unknown.
- One business when classification is business, otherwise no business.
- One status.

The source account answers "where did the money come from?" Classification answers "which books, if any, should include it?" These must remain separate.

Transactions should normally be excluded, marked personal, or marked duplicate rather than hard-deleted. Source activity and audit history must remain queryable.

## 6. Import workflow

```text
Choose file(s)
  -> choose or confirm source account and default import area
  -> detect file type/provider/format
  -> run the best adapter
  -> create candidate rows without committing approval
  -> validate extraction and statement totals where available
  -> review suggestions and exceptions
  -> approve individually or in safe batches
  -> persist normalized transactions and history
  -> export reports when requested
```

The import screen should allow a default import area of Business or Personal. A mostly personal document can therefore be imported into the Personal holding area while a few selected transactions are moved to a business.

If the account cannot be identified confidently, the app must require account selection before committing rows. It must not guess.

## 7. Import adapters

Use adapters with a shared normalized output; do not build one universal parser.

### CSV/XLSX

- Detect common headers for dates, descriptions, amounts, debits, credits, memos, and types.
- Support saved manual column mappings for unfamiliar provider formats.
- Preserve the original row and raw values.
- Validate dates, signs, amounts, and totals where available.

### Text-based PDF

- Use a provider/format profile when recognized.
- Use a generic fallback for unknown layouts with lower confidence.
- Preserve page and source-row locations.
- Handle page headers, footers, wrapped descriptions, and page breaks.
- Validate extracted row counts and debit/expense totals against statement totals when present.

### Scanned PDF/image

- Add after structured CSV/XLSX and text-PDF paths are stable.
- Route through OCR.
- Put uncertain dates, signs, and decimal amounts into a low-confidence review queue.
- Never treat nonempty OCR output as proof of complete extraction.

### Provider profiles

Provider profiles may contain institution, format fingerprints, date/amount patterns, header/footer rules, sign behavior, and parser version. Confirmed mappings can be remembered for future imports but must remain editable.

## 8. SQLite data model

The database is the canonical source of truth.

### `businesses`

- `id`
- `legal_name`
- `display_name`
- `active`
- `notes`
- `created_at`

### `accounts`

- `id`
- `business_id` nullable for personal accounts
- `nickname`
- `institution`
- `last_four`
- `account_type`
- `active`
- `notes`

Never require or persist full account numbers.

### `documents`

- `id`
- `filename`
- `file_hash`
- `stored_path`
- `provider`
- `format`
- `statement_start`
- `statement_end`
- `imported_at`
- `default_classification`
- `parser_version`

### `import_rows`

- `id`
- `document_id`
- `raw_date`
- `raw_description`
- `raw_amount`
- `raw_text`
- `confidence`
- `source_page`
- `source_row`
- `transaction_id` nullable

### `transactions`

- `id`
- `document_id` nullable for manual entries
- `account_id`
- `date`
- `posted_date` nullable
- `description`
- `merchant`
- `amount`
- `direction`
- `classification`
- `business_id` nullable
- `category_id` nullable
- `status`
- `source_page` nullable
- `source_row` nullable
- `notes`
- `created_at`
- `updated_at`

### `categories`

- `id`
- `business_id` nullable for reusable/global categories
- `name`
- `tax_group`
- `requires_review`
- `active`

Initial categories should cover fuel, vehicle maintenance, tires, insurance, registration/taxes, parking/tolls, cleaning/detailing, software/dispatch, phone/internet, advertising, professional services, bank/payment fees, office supplies, meals, contractor payments, business licenses, loan payments, interest, owner contributions, owner draws, transfers, personal/non-business, and uncategorized/review.

### `rules`

- `id`
- `scope`
- `account_id` nullable
- `business_id` nullable
- `merchant_pattern`
- `category_id` nullable
- `suggested_business_id` nullable
- `priority`
- `active`
- `created_from_action`

### `transaction_history`

- `id`
- `transaction_id`
- `field_name`
- `old_value`
- `new_value`
- `action`
- `reason`
- `changed_at`

## 9. Statuses and review behavior

Initial statuses:

- `needs_review`
- `suggested`
- `approved`
- `personal`
- `excluded`
- `duplicate`
- `transfer`
- `manually_added`

Suggestions are never approvals. Every suggestion should display its reason, such as a prior approved merchant/account mapping or keyword rule.

Batch groups should be based on normalized merchant, source account, proposed business, proposed category, and confidence. Before applying a batch action, show affected-row count, total amount, accounts, businesses, proposed changes, and exceptions. Record the batch action in history and provide undo.

Rules learned from corrections must be scoped and previewable. The app must not silently apply a new correction to historical transactions.

## 10. Interface outline

- Dashboard
- Business selector
- Business: Review Queue, Transactions, Categories, Reports
- Personal: Review Queue, Transactions, Search, Basic Categories
- Accounts
- Imports
- Rules
- Settings
- Backup/restore

Transaction editing should support date, description, merchant, amount, source account correction, business, category, classification, status, and notes. Source account should remain visible even when business classification changes.

## 11. Excel exports

Excel is an output format, not the source of truth. Generate workbooks for a selected business and tax year with:

- Expense Ledger
- Monthly Summary
- Category Summary
- Tax Preparation Summary
- Review Queue
- Excluded Transactions
- Duplicate/Transfer Transactions

Business-source transactions marked personal and business transactions found on personal accounts must remain traceable in the ledger. Include source account nickname/last four, source document, and source page/row where available.

Tax-related reports must be labeled as preparation assistance and should flag vehicle, meals, transfers, loan payments, owner draws/contributions, and mixed-use items for review.

## 12. Local storage and backup

Store the database, source documents, parser profiles, and generated exports locally. Use file hashes for duplicate-document detection. Provide a backup operation that packages the SQLite database, original documents, and parser profiles. Restore must be tested before the app is considered complete.

No external service is required for normal operation. Optional local OCR or local AI may be added later without changing the data boundary.

## 13. Verification requirements

Before release:

- Test each importer with representative files from each major provider/format.
- Confirm source account assignment and required selection when uncertain.
- Validate known statement row counts and totals.
- Test duplicate document and duplicate transaction handling.
- Confirm personal-source business transactions appear once in business reports.
- Confirm excluded/personal/duplicate records remain searchable but are excluded from business totals.
- Test category/business suggestions, reasons, batch previews, undo, and history.
- Test adding businesses and accounts through the UI.
- Test Excel exports for each business and tax year.
- Test database plus source-document backup and restore.
- Confirm no full account numbers are persisted.

## 14. Suggested implementation order

1. SQLite schema, migrations, businesses, accounts, documents, transactions, and history.
2. Local file storage and database backup/restore.
3. Transaction review UI with manual add/edit/classification.
4. CSV/XLSX importer with saved column mapping.
5. Rule-based suggestions and safe batch approval.
6. Text-based PDF adapter and generic fallback.
7. Business/personal views and business-specific Excel exports.
8. Provider profile management and stronger validation.
9. OCR adapter for scanned PDFs.

Implementation should not begin until this written specification is reviewed and approved.
