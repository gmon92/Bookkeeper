"""Local-only HTTP and SQLite backend for the Ledgerly prototype."""
from __future__ import annotations

import base64
import csv
import datetime as dt
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
import os
import re
import secrets
import sqlite3
import socket
import threading
import zipfile
import uuid
from contextlib import contextmanager
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse
from statement_import import parse_statement
from reports import excel_report, safe_text
from backup import create_backup, restore_backup
import categorization
import credits
import workspace_store
import source_archive

ROOT = Path(__file__).resolve().parent
DEFAULT_DATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local-bookkeeper")) / "LocalBookkeeper"
DATA_DIR = Path(os.environ.get("LOCAL_BOOKKEEPER_DATA", DEFAULT_DATA_DIR)).resolve()
DOCS_DIR = DATA_DIR / "documents"
DB_PATH = DATA_DIR / "bookkeeper.sqlite3"
HOST = "127.0.0.1"
PORT = int(os.environ.get("LOCAL_BOOKKEEPER_PORT", "8765"))
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
STAGING_LOCK = threading.Lock()
WORKSPACE_LOCK = threading.RLock()
WORKSPACE_READY = False
WORKSPACE_ID = ''
SETUP_ERROR = ''

BASE_CATEGORIES = [
    "Fuel", "Vehicle maintenance", "Tires", "Insurance", "Registration / taxes",
    "Parking / tolls", "Cleaning / detailing", "Software / dispatch", "Phone / internet",
    "Advertising", "Professional services", "Bank / payment fees", "Office supplies",
    "Meals", "Contractor payments", "Business licenses", "Loan payments", "Interest",
    "Owner contributions", "Owner draws", "Transfers", "Personal / non-business", "Uncategorized / review",
]


@contextmanager
def connect():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA journal_mode = WAL")
    try:
        with db:
            yield db
    finally:
        db.close()


def initialize(initial_business=None) -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        if db.execute('PRAGMA user_version').fetchone()[0] > 7:
            raise RuntimeError('This database was created by a newer version of Local Bookkeeper.')
        db.executescript("""
        CREATE TABLE IF NOT EXISTS businesses (
          id TEXT PRIMARY KEY, legal_name TEXT NOT NULL, display_name TEXT NOT NULL,
          active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)), notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS accounts (
          id TEXT PRIMARY KEY, business_id TEXT REFERENCES businesses(id), nickname TEXT NOT NULL,
          institution TEXT NOT NULL DEFAULT '', last_four TEXT NOT NULL DEFAULT '', account_type TEXT NOT NULL DEFAULT 'checking',
          active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)), notes TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS categories (
          id TEXT PRIMARY KEY, business_id TEXT REFERENCES businesses(id), name TEXT NOT NULL,
          tax_group TEXT NOT NULL DEFAULT '', requires_review INTEGER NOT NULL DEFAULT 0 CHECK(requires_review IN (0,1)),
          active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)), UNIQUE(business_id, name)
        );
        CREATE TABLE IF NOT EXISTS documents (
          id TEXT PRIMARY KEY, filename TEXT NOT NULL, file_hash TEXT NOT NULL, stored_path TEXT NOT NULL,
          provider TEXT NOT NULL DEFAULT '', format TEXT NOT NULL, statement_start TEXT, statement_end TEXT,
          imported_at TEXT NOT NULL, default_classification TEXT NOT NULL DEFAULT 'unknown', parser_version TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_documents_hash ON documents(file_hash);
        CREATE TABLE IF NOT EXISTS transactions (
          id TEXT PRIMARY KEY, document_id TEXT REFERENCES documents(id), account_id TEXT NOT NULL REFERENCES accounts(id),
          business_id TEXT REFERENCES businesses(id), date TEXT NOT NULL, posted_date TEXT,
          description TEXT NOT NULL, merchant TEXT NOT NULL DEFAULT '', raw_amount_text TEXT NOT NULL,
          source_amount_cents INTEGER NOT NULL, amount_cents INTEGER NOT NULL CHECK(amount_cents >= 0),
          direction TEXT NOT NULL CHECK(direction IN ('debit','credit','unknown')),
          transaction_kind TEXT NOT NULL CHECK(transaction_kind IN ('expense','refund','transfer','fee','adjustment','unknown')),
          include_in_totals INTEGER NOT NULL DEFAULT 0 CHECK(include_in_totals IN (0,1)),
          source_fingerprint TEXT NOT NULL, duplicate_of TEXT REFERENCES transactions(id), classification TEXT NOT NULL
            CHECK(classification IN ('business','personal','transfer','unknown')),
          category_id TEXT REFERENCES categories(id), category_name TEXT NOT NULL DEFAULT 'Uncategorized / review',
          status TEXT NOT NULL CHECK(status IN ('needs_review','suggested','approved','excluded')),
          source_page INTEGER, source_row INTEGER, source_raw_json TEXT NOT NULL DEFAULT '{}', notes TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
          CHECK((classification = 'business' AND business_id IS NOT NULL) OR (classification <> 'business' AND business_id IS NULL)),
          CHECK(include_in_totals = 0 OR (status = 'approved' AND classification = 'business' AND direction <> 'unknown' AND transaction_kind <> 'transfer' AND duplicate_of IS NULL))
        );
        CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(date);
        CREATE INDEX IF NOT EXISTS idx_transactions_account ON transactions(account_id);
        CREATE INDEX IF NOT EXISTS idx_transactions_fingerprint ON transactions(source_fingerprint);
        CREATE TABLE IF NOT EXISTS transaction_history (
          id TEXT PRIMARY KEY, transaction_id TEXT NOT NULL REFERENCES transactions(id), action_id TEXT,
          field_name TEXT NOT NULL, old_value TEXT, new_value TEXT, action TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '', changed_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS review_actions (
          id TEXT PRIMARY KEY, action_type TEXT NOT NULL, description TEXT NOT NULL, created_at TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','undone','partially_undone'))
        );
        CREATE TABLE IF NOT EXISTS review_action_items (
          id TEXT PRIMARY KEY, action_id TEXT NOT NULL REFERENCES review_actions(id), transaction_id TEXT NOT NULL REFERENCES transactions(id),
          old_state TEXT NOT NULL, new_state TEXT NOT NULL, outcome TEXT NOT NULL DEFAULT 'applied'
        );
        """)
        now = utc_now()
        business = db.execute("SELECT id FROM businesses ORDER BY created_at LIMIT 1").fetchone()
        if business is None and initial_business:
            business_id = str(uuid.uuid4())
            db.execute("INSERT INTO businesses(id,legal_name,display_name,created_at) VALUES(?,?,?,?)",
                       (business_id, initial_business, initial_business, now))
        elif business is None:
            business_id = None
        else:
            business_id = business["id"]
        for name in BASE_CATEGORIES if business_id else []:
            db.execute("INSERT OR IGNORE INTO categories(id,business_id,name) VALUES(?,?,?)",
                       ("cat-" + slug(name), business_id, name))
        columns = {r['name'] for r in db.execute('PRAGMA table_info(documents)')}
        if 'metadata_json' not in columns:
            db.execute("ALTER TABLE documents ADD COLUMN metadata_json TEXT NOT NULL DEFAULT '{}'")
        if 'excluded' not in {r['name'] for r in db.execute('PRAGMA table_info(transactions)')}:
            db.execute('ALTER TABLE transactions ADD COLUMN excluded INTEGER NOT NULL DEFAULT 0 CHECK(excluded IN (0,1))')
            db.execute("UPDATE transactions SET excluded=1,status='approved',include_in_totals=0 WHERE status='excluded'")
        db.executescript('''
        CREATE TABLE IF NOT EXISTS staged_imports (
          token TEXT PRIMARY KEY, content BLOB NOT NULL, parsed_json TEXT NOT NULL,
          file_hash TEXT NOT NULL, created_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS duplicate_decisions (
          first_id TEXT NOT NULL REFERENCES transactions(id), second_id TEXT NOT NULL REFERENCES transactions(id),
          decision TEXT NOT NULL CHECK(decision IN ('duplicate','distinct')), reviewed_at TEXT NOT NULL,
          PRIMARY KEY(first_id, second_id)
        );
        ''')
        for operation in ('INSERT','UPDATE'):
            db.execute(f'''CREATE TRIGGER IF NOT EXISTS validate_transaction_{operation.lower()} BEFORE {operation} ON transactions
            WHEN typeof(NEW.amount_cents)<>'integer' OR NEW.status NOT IN ('needs_review','suggested','approved') OR
              (NEW.include_in_totals=1 AND (NEW.excluded=1 OR NEW.amount_cents=0 OR lower(NEW.category_name) LIKE '%uncategorized%' OR
              NOT ((NEW.direction='debit' AND NEW.transaction_kind IN ('expense','fee')) OR (NEW.direction='credit' AND NEW.transaction_kind='refund'))))
            BEGIN SELECT RAISE(ABORT,'Transaction violates amount, review or reporting rules'); END''')
        categorization.initialize(db)
        db.executescript('''
        CREATE TABLE IF NOT EXISTS app_metadata (key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS import_profiles (
          id TEXT PRIMARY KEY,account_id TEXT NOT NULL REFERENCES accounts(id),layout_key TEXT NOT NULL,
          provider TEXT NOT NULL,format TEXT NOT NULL,extraction_json TEXT NOT NULL,confirmed_at TEXT NOT NULL,
          active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
          UNIQUE(account_id,layout_key)
        );
        ''')
        db.execute("INSERT OR IGNORE INTO app_metadata VALUES('workspace_id',?)",(str(uuid.uuid4()),))
        db.execute(f'PRAGMA application_id={workspace_store.APP_ID}')
        source_archive.initialize(db, now, DATA_DIR)
        credits.initialize(db)
        db.execute("PRAGMA user_version=7")


def activate_workspace(directory, business=None, remember=False):
    global DATA_DIR,DOCS_DIR,DB_PATH,WORKSPACE_READY,WORKSPACE_ID,SETUP_ERROR
    previous = DATA_DIR,DOCS_DIR,DB_PATH,WORKSPACE_READY,WORKSPACE_ID
    DATA_DIR,DOCS_DIR,DB_PATH = directory,directory/'documents',directory/'bookkeeper.sqlite3'
    try:
        initialize(business)
        with connect() as db:
            workspace_id = db.execute("SELECT value FROM app_metadata WHERE key='workspace_id'").fetchone()[0]
        if remember: workspace_store.save_preferences(directory)
        WORKSPACE_READY,WORKSPACE_ID,SETUP_ERROR = True,hashlib.sha256((workspace_id+'|'+str(DB_PATH)).encode()).hexdigest(),''
    except Exception:
        DATA_DIR,DOCS_DIR,DB_PATH,WORKSPACE_READY,WORKSPACE_ID = previous
        raise


def setup_status():
    candidates = []
    for path in (DATA_DIR,DEFAULT_DATA_DIR,ROOT/'data'):
        if (path/'bookkeeper.sqlite3').is_file() and str(path) not in candidates:
            candidates.append(str(path))
    return {'configured':WORKSPACE_READY,'directory':str(DATA_DIR) if WORKSPACE_READY else None,
            'defaultDirectory':str(workspace_store.default_directory()),'existingDirectories':candidates,
            'error':SETUP_ERROR,'applicationDirectory':str(ROOT)}


def configure_workspace(body):
    mode = body.get('mode')
    directory = workspace_store.directory_path(body.get('directory'))
    if mode not in {'create','open','copy'}: raise ValueError('Choose create, open, or copy existing books.')
    if mode in {'create','copy'} and (directory==ROOT or directory.is_relative_to(ROOT)):
        raise ValueError('Choose a books folder outside the app folder so updates and reinstalls keep your data separate.')
    if mode == 'create':
        name = body.get('businessName','')
        if not isinstance(name,str) or not name.strip() or len(name.strip())>200:
            raise ValueError('Enter the first business name, up to 200 characters.')
        if directory.exists() and any(directory.iterdir()):
            raise ValueError('Choose a new or empty folder. Use Open existing books for a folder that already contains a database.')
        directory.mkdir(parents=True,exist_ok=True)
        # Reserve a new database file exclusively; never overwrite existing books.
        try:
            with (directory/'bookkeeper.sqlite3').open('xb'): pass
        except FileExistsError as exc:
            raise ValueError('That folder already contains books. Choose Open existing books or another folder.') from exc
        activate_workspace(directory,name.strip(),remember=True)
    elif mode == 'open':
        workspace_store.validate_existing(directory)
        activate_workspace(directory,remember=True)
    else:
        source = workspace_store.directory_path(body.get('sourceDirectory'))
        workspace_store.validate_existing(source)
        if directory.exists() and any(directory.iterdir()): raise ValueError('Copy books into a new or empty folder. Existing files are never overwritten.')
        content = create_backup(source/'bookkeeper.sqlite3',source)
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            if json.loads(archive.read('manifest.json'))['missingSources']:
                raise ValueError('Some retained originals are missing. Restore them before copying the books, or open the existing folder.')
        restore_backup(io.BytesIO(content),directory,allow_empty=True)
        activate_workspace(directory,remember=True)
    return {'ok':True,'directory':str(DATA_DIR),'database':str(DB_PATH),'workspaceId':WORKSPACE_ID}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def normalize_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lstrip("\ufeff").lower())


def parse_money(value: str) -> tuple[int, str]:
    raw = (value or "").strip()
    negative = raw.startswith("(") and raw.endswith(")")
    cleaned = raw[1:-1] if negative else raw
    cleaned = cleaned.replace(",", "").replace("$", "").replace(" ", "")
    if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d{1,2})?|\.\d{1,2})", cleaned):
        raise ValueError("invalid amount")
    try:
        amount = int(abs(Decimal(cleaned)) * 100)
    except InvalidOperation as exc:
        raise ValueError("invalid amount") from exc
    if negative or cleaned.startswith("-"):
        source_cents = -amount
    else:
        source_cents = amount
    return source_cents, raw


def parse_date(value: str) -> str | None:
    value = (value or "").strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y", "%d/%m/%Y"):
        try:
            return dt.datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            pass
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return None


def parse_csv(content: bytes, filename: str) -> dict:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("cp1252")
    try:
        rows = list(csv.reader(io.StringIO(text, newline="")))
    except csv.Error as exc:
        raise ValueError(f"Could not parse CSV: {exc}") from exc
    header_index = next((i for i, row in enumerate(rows[:50]) if
        {normalize_header(c) for c in row} & {'description', 'merchant', 'payee', 'details', 'name'} and
        {normalize_header(c) for c in row} & {'amount', 'transactionamount', 'debit', 'credit', 'withdrawals', 'debits', 'credits'}), None)
    if header_index is None:
        raise ValueError('Could not find a transaction header in the first 50 rows.')
    if len(rows) < header_index + 2:
        raise ValueError("CSV has a header but no transaction rows.")
    headers = [cell.strip() for cell in rows[header_index]]
    normalized = [normalize_header(h) for h in headers]
    def find(*names: str) -> int:
        return next((i for i, item in enumerate(normalized) if item in names), -1)
    date_i = find("date", "transactiondate", "purchasedate")
    posted_i = find("posteddate", "postingdate")
    type_i = find("type", "transactiontype", "debitcredit", "activitytype")
    desc_i = find("description", "merchant", "name", "payee", "transaction", "details")
    amount_i = find("amount", "transactionamount")
    debit_i = find("debit", "debits", "withdrawal", "withdrawals")
    credit_i = find("credit", "credits", "deposit", "deposits")
    if desc_i < 0 or (amount_i < 0 and debit_i < 0 and credit_i < 0):
        raise ValueError("Could not identify description and amount columns. Expected Date, Description, Amount or Debit/Credit.")
    result, warnings = [], {"invalid_amount": 0, "invalid_date": 0, "blank_description": 0, "invalid_rows": 0}
    for source_row, values in enumerate(rows[header_index + 1:], start=header_index + 2):
        if not any(cell.strip() for cell in values):
            continue
        if len(result) >= 50000:
            raise ValueError('Statement exceeds the 50,000 row limit.')
        values = values + [""] * max(0, len(headers) - len(values))
        raw_description = values[desc_i].strip()
        raw_date = values[date_i].strip() if date_i >= 0 else ""
        raw_amount = values[amount_i].strip() if amount_i >= 0 else ""
        source_type = values[type_i].strip().lower() if type_i >= 0 else ""
        transaction_kind = "unknown"
        if source_type in {"refund", "return", "reversal"}:
            transaction_kind = "refund"
        elif source_type in {"transfer", "account transfer"}:
            transaction_kind = "transfer"
        elif source_type in {"fee", "service fee", "bank fee"}:
            transaction_kind = "fee"
        elif source_type in {"adjustment", "statement credit"}:
            transaction_kind = "adjustment"
        source_cents, direction = 0, "unknown"
        try:
            if amount_i >= 0:
                source_cents, raw_amount = parse_money(raw_amount)
                if source_type in {"debit", "withdrawal", "purchase", "payment"}:
                    direction = "debit"
                elif source_type in {"credit", "deposit", "refund", "return"}:
                    direction = "credit"
                else:
                    # Sign is retained as source evidence, not treated as a trusted direction mapping.
                    direction = "unknown"
            else:
                debit_raw = values[debit_i].strip() if debit_i >= 0 else ""
                credit_raw = values[credit_i].strip() if credit_i >= 0 else ""
                debit_cents = parse_money(debit_raw)[0] if debit_raw else 0
                credit_cents = parse_money(credit_raw)[0] if credit_raw else 0
                if debit_cents and credit_cents:
                    warnings["invalid_rows"] += 1
                    raw_amount = f"debit={debit_raw}; credit={credit_raw}"
                else:
                    source_cents = credit_cents if credit_cents else debit_cents
                    raw_amount = credit_raw or debit_raw
                    direction = "credit" if credit_cents else "debit" if debit_cents else "unknown"
        except ValueError:
            source_cents, direction = 0, "unknown"
        if source_cents == 0:
            warnings["invalid_amount"] += 1
        parsed_date = parse_date(raw_date)
        if not parsed_date:
            warnings["invalid_date"] += 1
        if not raw_description:
            warnings["blank_description"] += 1
        description = raw_description or f"Unknown transaction (row {source_row})"
        amount_cents = abs(source_cents)
        fingerprint_base = "|".join((parsed_date or raw_date, parse_date(values[posted_i]) or '' if posted_i >= 0 else '', str(amount_cents), direction, normalize_header(description)))
        result.append({
            "date": parsed_date or raw_date or "", "posted_date": parse_date(values[posted_i]) if posted_i >= 0 else None,
            "description": description, "merchant": raw_description, "raw_amount_text": raw_amount,
            "source_amount_cents": source_cents, "amount_cents": amount_cents, "direction": direction,
            "transaction_kind": transaction_kind if transaction_kind != "unknown" else ("expense" if direction == "debit" else "unknown"), "classification": "unknown",
            "category_name": "Uncategorized / review", "status": "needs_review", "include_in_totals": 0,
            "source_row": source_row, "source_page": None, "raw": {"headers": headers, "values": values},
            "fingerprint": hashlib.sha256(fingerprint_base.encode("utf-8")).hexdigest(),
        })
    if not result:
        raise ValueError("No monetary transaction rows could be parsed. Check the amount columns.")
    warnings["total"] = sum(warnings.values())
    column_indexes = {'date':date_i,'postedDate':posted_i,'description':desc_i,'amount':amount_i,'debit':debit_i,'credit':credit_i,'type':type_i,'sourceCategory':find(*source_archive.CATEGORY_HEADERS)}
    columns = {key:{'index':index,'header':headers[index],
        'purpose':'Not used: Amount column takes priority.' if amount_i>=0 and key in {'debit','credit'} else
            'Retained as statement evidence, not an approved business category.' if key=='sourceCategory' else 'Read by the import adapter.'}
        for key,index in column_indexes.items() if index>=0}
    return {"filename":Path(filename).name,"headers":headers,"rows":result,"warnings":warnings,
        'extraction':{'headerRow':header_index+1,'sheet':None,'columns':columns,'metadataRowsSkipped':header_index,
            'blankRowsSkipped':sum(not any(c.strip() for c in row) for row in rows[header_index+1:]),'otherSheets':[]}}


def transaction_json(row: sqlite3.Row) -> dict:
    raw = json.loads(row['source_raw_json'])
    source_values = dict(zip((normalize_header(str(h)) for h in raw.get('headers',[])),raw.get('values',[])))
    return {
        "id": row["id"], "documentId": row["document_id"], "businessId": row["business_id"],
        "accountId": row["account_id"], "account": row["account_nickname"] + (f" ···· {row['last_four']}" if row["last_four"] else ""),
        "date": row["date"], "postedDate": row["posted_date"], "merchant": row["merchant"] or row["description"],
        "detail": (row["source_filename"] or "Manual entry") + (f" · row {row['source_row']}" if row["source_row"] else ""),
        "description": row["description"], "rawAmountText": row["raw_amount_text"],
        "sourceAmountCents": row["source_amount_cents"], "amountCents": row["amount_cents"],
        "direction": row["direction"], "kind": row["transaction_kind"], "classification": row["classification"],
        "includeInTotals": bool(row["include_in_totals"]), "category": row["category_name"], "status": row["status"],
        "excluded": bool(row['excluded']),
        "creditTreatment": row['credit_treatment'], "relatedTransactionId": row['related_transaction_id'],
        "duplicateOf": row["duplicate_of"], "duplicateCandidate": row["duplicate_candidate"],
        "sourceRow": row["source_row"], "sourceFilename": row["source_filename"],
        "sourceSheet": raw.get('sheet'),
        "sourceCategory": row['original_source_category'] if 'original_source_category' in row.keys() and row['original_source_category'] is not None else source_archive.category(raw),
        "notes": row["notes"], "fingerprint": row["source_fingerprint"],
    }


class LocalHTTPServer(ThreadingHTTPServer):
    # Windows SO_REUSEADDR permits two live servers to share a port, allowing
    # an older process to keep serving stale code after an apparent restart.
    allow_reuse_address = os.name != 'nt'

    def server_bind(self):
        if os.name == 'nt':
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class Handler(SimpleHTTPRequestHandler):
    server_version = "LedgerlyLocal/0.1"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, fmt, *args):
        print(f"[{self.log_date_time_string()}] {self.address_string()} {fmt % args}")

    def send_json(self, status: int, payload: dict | list):
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length > MAX_UPLOAD_BYTES * 2:
            raise ValueError("Request is too large.")
        if length < 0:
            raise ValueError('Invalid request length.')
        body = json.loads(self.rfile.read(length) or b"{}")
        if not isinstance(body, dict):
            raise ValueError('Expected a JSON object.')
        return body

    def local_request(self):
        host = self.headers.get('Host', '')
        allowed = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
        origin = self.headers.get('Origin')
        return host in allowed and (not origin or origin in {'http://' + value for value in allowed})

    def do_GET(self):
        try:
            with WORKSPACE_LOCK:
                return self.get_request()
        except (ValueError,sqlite3.Error) as exc:
            return self.send_json(400, {'error':str(exc)})
        except Exception:
            import traceback
            traceback.print_exc()
            return self.send_json(500, {'error':'The request could not be completed. Check the server terminal.'})

    def get_request(self):
        if not self.local_request():
            return self.send_json(403, {'error': 'Open the app at its local address.'})
        path = unquote(urlparse(self.path).path)
        if path == "/api/health":
            return self.send_json(200, {"ok": True, "setupRequired":not WORKSPACE_READY,'workspaceId':WORKSPACE_ID,
                "database":str(DB_PATH) if WORKSPACE_READY else None,"dataDirectory":str(DATA_DIR) if WORKSPACE_READY else None,'setup':setup_status()})
        if path == '/api/setup':
            return self.send_json(200,setup_status())
        if path.startswith('/api/') and not WORKSPACE_READY:
            return self.send_json(409,{'error':'Choose or create your books folder to begin.','setupRequired':True})
        if path == '/api/import-profiles':
            with connect() as db:
                return self.send_json(200,[dict(r) for r in db.execute('SELECT p.id,p.provider,p.format,p.confirmed_at,a.nickname,a.last_four FROM import_profiles p JOIN accounts a ON a.id=p.account_id WHERE p.active=1 ORDER BY p.confirmed_at DESC')])
        if path == '/api/credits/suggestions':
            with connect() as db: return self.send_json(200,credits.suggestions(db))
        if path == '/api/credits/rules':
            with connect() as db: return self.send_json(200,credits.rules(db))
        if path.startswith('/api/credits/') and path.endswith('/candidates'):
            query = parse_qs(urlparse(self.path).query)
            with connect() as db: return self.send_json(200,credits.candidates(db,path.split('/')[3],query.get('treatment',[''])[0],query.get('q',[''])[0]))
        if path.startswith('/api/documents/') and path.endswith('/source'):
            query = parse_qs(urlparse(self.path).query, keep_blank_values=True)
            offset = int(query.get('offset', ['0'])[0])
            if offset < 0: raise ValueError('Choose a nonnegative source row offset.')
            with connect() as db:
                return self.send_json(200, source_archive.document_rows(db, path.split('/')[3], query.get('sheet', [None])[0], offset))
        if path.endswith('/explanation') and path.startswith('/api/transactions/'):
            return self.explain_transaction(path.split('/')[3])
        if path == "/api/businesses":
            with connect() as db:
                return self.send_json(200, [dict(r) for r in db.execute("SELECT * FROM businesses WHERE active=1 ORDER BY display_name")])
        if path == "/api/accounts":
            with connect() as db:
                return self.send_json(200, [dict(r) for r in db.execute("SELECT id,business_id,nickname,institution,last_four,account_type FROM accounts WHERE active=1 ORDER BY nickname")])
        if path == "/api/categories":
            with connect() as db:
                return self.send_json(200, [dict(r) for r in db.execute("SELECT id,business_id,name,tax_group,requires_review FROM categories WHERE active=1 ORDER BY name")])
        if path == "/api/transactions":
            with connect() as db:
                rows = db.execute("""SELECT t.*,a.nickname AS account_nickname,a.last_four,d.filename AS source_filename,o.source_category AS original_source_category,
                    (SELECT t2.id FROM transactions t2 WHERE t2.id <> t.id AND t2.account_id=t.account_id AND t2.source_fingerprint=t.source_fingerprint AND NOT EXISTS (SELECT 1 FROM duplicate_decisions dd WHERE dd.decision='distinct' AND ((dd.first_id=t.id AND dd.second_id=t2.id) OR (dd.first_id=t2.id AND dd.second_id=t.id))) ORDER BY t2.created_at LIMIT 1) AS duplicate_candidate
                    FROM transactions t JOIN accounts a ON a.id=t.account_id LEFT JOIN documents d ON d.id=t.document_id LEFT JOIN original_transactions o ON o.transaction_id=t.id
                    ORDER BY t.date DESC,t.created_at DESC""").fetchall()
                return self.send_json(200, [transaction_json(r) for r in rows])
        if path == "/api/documents":
            with connect() as db:
                rows = db.execute("SELECT * FROM documents ORDER BY imported_at DESC").fetchall()
                return self.send_json(200, [{k:r[k] for k in ('id','filename','file_hash','format','provider','imported_at','statement_start','statement_end')} | {'sourceAvailable': (DATA_DIR / r['stored_path']).is_file(), 'metadata': json.loads(r['metadata_json'])} for r in rows])
        if path == '/api/review/actions':
            with connect() as db:
                return self.send_json(200, [dict(r) for r in db.execute('SELECT * FROM review_actions ORDER BY rowid DESC LIMIT 100')])
        if path == '/api/rules':
            with connect() as db:
                return self.send_json(200,categorization.rules(db))
        if path == '/api/suggestions':
            with connect() as db:
                return self.send_json(200,categorization.suggestions(db))
        if path.endswith('/history') and path.startswith('/api/transactions/'):
            with connect() as db:
                return self.send_json(200, [dict(r) for r in db.execute('SELECT * FROM transaction_history WHERE transaction_id=? ORDER BY rowid', (path.split('/')[3],))])
        if path == '/api/backup':
            return self.backup()
        if path == '/api/export.xlsx':
            return self.export_excel()
        if path == "/api/export.csv":
            return self.export_csv()
        if path in {'/', '/index.html', '/app.js', '/styles.css', '/categorize.js', '/categorize.css','/setup.js','/setup.css','/source.js','/source.css','/credits.js','/credits.css','/batch_selection.js'}:
            return super().do_GET()
        return self.send_error(404)

    def do_HEAD(self):
        # SimpleHTTPRequestHandler otherwise allows HEAD to bypass GET's allowlist.
        if self.local_request() and unquote(urlparse(self.path).path) in {'/', '/index.html', '/app.js', '/styles.css', '/categorize.js', '/categorize.css','/setup.js','/setup.css','/source.js','/source.css','/credits.js','/credits.css','/batch_selection.js'}:
            return super().do_HEAD()
        return self.send_error(404)

    def do_POST(self):
        if not self.local_request():
            return self.send_json(403, {'error':'Requests must come from the local app.'})
        if urlparse(self.path).path == '/api/setup/browse':
            try:
                body = self.read_json()
                return self.send_json(200,{'directory':workspace_store.choose_directory(str(body.get('initial','')))})
            except (ValueError,OSError) as exc:
                return self.send_json(400,{'error':str(exc)})
        with WORKSPACE_LOCK:
            return self.post_request()

    def post_request(self):
        if not self.local_request():
            return self.send_json(403, {'error': 'Requests must come from the local app.'})
        path = urlparse(self.path).path
        try:
            if path == '/api/setup':
                return self.send_json(200,configure_workspace(self.read_json()))
            if not WORKSPACE_READY:
                return self.send_json(409,{'error':'Choose or create your books folder to begin.'})
            if self.headers.get('X-Bookkeeper-Workspace') != WORKSPACE_ID:
                return self.send_json(409,{'error':'The active database changed or this page is out of date. Refresh before saving changes.'})
            if path == '/api/import-profiles/revoke':
                body = self.read_json()
                with connect() as db: db.execute('UPDATE import_profiles SET active=0 WHERE id=?',(body.get('id'),))
                return self.send_json(200,{'ok':True})
            if path in {'/api/credits/preview','/api/credits/apply'}:
                body = self.read_json()
                with connect() as db:
                    if path.endswith('/apply'):
                        db.execute('BEGIN IMMEDIATE')
                        result = credits.commit(db,body,self,utc_now())
                    else: result = credits.plan(db,body,self.validate_transaction)[0]
                return self.send_json(200,result)
            if path == '/api/credits/rules':
                body = self.read_json()
                if set(body) != {'id','active'} or type(body['active']) is not bool: raise ValueError('Choose a credit rule and whether it is active.')
                with connect() as db:
                    if not db.execute('SELECT id FROM credit_rules WHERE id=?',(body['id'],)).fetchone(): raise ValueError('Credit rule not found.')
                    db.execute('UPDATE credit_rules SET active=? WHERE id=?',(int(body['active']),body['id']))
                return self.send_json(200,{'ok':True})
            if path in {'/api/categorization/preview','/api/categorization/apply'}:
                body = self.read_json()
                with connect() as db:
                    if path.endswith('/apply'):
                        db.execute('BEGIN IMMEDIATE')
                        result = categorization.commit(db,body,self,utc_now())
                    else:
                        result = categorization.plan(db,body,self.validate_transaction)[0]
                return self.send_json(200,result)
            if path in {'/api/rules','/api/rules/preview'}:
                body = self.read_json()
                with connect() as db:
                    db.execute('BEGIN IMMEDIATE')
                    if path.endswith('/preview'):
                        result = categorization.preview_rule(db,body)
                    elif body.get('id') and set(body) <= {'id','active'}:
                        if type(body.get('active')) is not bool: raise ValueError('Rule activation must be true or false.')
                        if not db.execute('SELECT id FROM merchant_rules WHERE id=?',(body['id'],)).fetchone(): raise ValueError('Rule not found.')
                        db.execute('UPDATE merchant_rules SET active=? WHERE id=?',(int(body['active']),body['id']))
                        result = {'ok':True}
                    else:
                        rule = categorization.rule_values(db,body)
                        rule_id = body.get('id') or str(uuid.uuid4())
                        if body.get('id'):
                            if not db.execute('SELECT id FROM merchant_rules WHERE id=?',(rule_id,)).fetchone(): raise ValueError('Rule not found.')
                            db.execute('UPDATE merchant_rules SET pattern=?,account_id=?,business_id=?,category_name=? WHERE id=?',(rule['pattern'],rule['account_id'],rule['business_id'],rule['category_name'],rule_id))
                        else:
                            db.execute('INSERT INTO merchant_rules(id,pattern,account_id,business_id,category_name,created_at) VALUES(?,?,?,?,?,?)',(rule_id,rule['pattern'],rule['account_id'],rule['business_id'],rule['category_name'],utc_now()))
                        result = {'id':rule_id,'ok':True}
                return self.send_json(200,result)
            if path == "/api/imports/preview":
                body = self.read_json()
                filename = Path(str(body.get("filename", "statement.csv"))).name
                content = base64.b64decode(body.get("contentBase64", ""), validate=True)
                if len(content) > MAX_UPLOAD_BYTES:
                    return self.send_json(413, {"error": "Statement is larger than the 20 MB limit."})
                parsed = parse_statement(content, filename, parse_csv)
                file_hash = hashlib.sha256(content).hexdigest()
                with connect() as db:
                    existing = db.execute("SELECT id FROM documents WHERE file_hash=?", (file_hash,)).fetchone()
                    profiles = [dict(r) for r in db.execute('SELECT p.id,p.account_id,p.confirmed_at,a.nickname FROM import_profiles p JOIN accounts a ON a.id=p.account_id WHERE p.active=1 AND p.layout_key=?',(parsed['layout_key'],))]
                    duplicate_count = 0
                    for tx in parsed["rows"]:
                        duplicate_count += bool(db.execute("SELECT 1 FROM transactions WHERE source_fingerprint=? LIMIT 1", (tx["fingerprint"],)).fetchone())
                token = secrets.token_urlsafe(24)
                with connect() as db:
                    db.execute('DELETE FROM staged_imports WHERE created_at<?', (dt.datetime.now().timestamp() - 1800,))
                    if db.execute('SELECT count(*) FROM staged_imports').fetchone()[0] >= 10:
                        raise ValueError('Finish or wait for existing import previews to expire before adding more files.')
                    db.execute('INSERT INTO staged_imports VALUES(?,?,?,?,?)', (token, content, json.dumps(parsed), file_hash, dt.datetime.now().timestamp()))
                debits = sum(r["amount_cents"] for r in parsed["rows"] if r["direction"] == "debit")
                credit_total = sum(r["amount_cents"] for r in parsed["rows"] if r["direction"] == "credit")
                return self.send_json(200, {"token": token, "filename": filename, "fileHash": file_hash,
                    "alreadyImported": bool(existing), "possibleDuplicates": duplicate_count,
                    "rowCount": len(parsed["rows"]), "debitCents": debits, "creditCents": credit_total,
                    "headers": parsed["headers"], "warnings": parsed["warnings"],
                    "provider": parsed['provider'], "reconciliation": parsed['reconciliation'], "requiresMappingConfirmation": parsed['provider'] == 'American Express',
                    'extraction':parsed['extraction'],'rememberedLayouts':profiles,
                    'sourceCategoryGroups': source_archive.category_groups(parsed),
                    "rows": [{"date":r["date"],"description":r["description"],"amountCents":r["amount_cents"],"sourceAmountCents":r["source_amount_cents"],"direction":r["direction"],"sourceRow":r["source_row"],'evidence':r['raw']['evidence'],'kind':r['transaction_kind']} for r in parsed["rows"][:20]]})
            if path == "/api/imports/commit":
                return self.commit_import()
            if path == '/api/review/undo':
                return self.undo_review()
            if path == '/api/duplicates/resolve':
                return self.resolve_duplicate()
            if path.startswith("/api/transactions/"):
                return self.update_transaction(unquote(path.rsplit("/", 1)[-1]))
            if path == "/api/review/batch":
                return self.batch_review()
            if path == "/api/businesses":
                return self.create_business()
            if path == "/api/accounts":
                return self.create_account()
            return self.send_json(404, {"error": "Unknown API endpoint."})
        except (ValueError, json.JSONDecodeError, base64.binascii.Error) as exc:
            return self.send_json(400, {"error": str(exc)})
        except sqlite3.IntegrityError as exc:
            return self.send_json(409, {"error": f"Database constraint rejected the change: {exc}"})
        except Exception as exc:
            return self.send_json(500, {"error": str(exc)})

    def explain_transaction(self, transaction_id):
        with connect() as db:
            row = db.execute('SELECT t.*,d.filename,d.provider,d.metadata_json FROM transactions t LEFT JOIN documents d ON d.id=t.document_id WHERE t.id=?',(transaction_id,)).fetchone()
            if not row: return self.send_json(404,{'error':'Transaction not found.'})
            baseline = source_archive.original(db, transaction_id)
            raw = baseline['raw'] if baseline else json.loads(row['source_raw_json'])
            history = db.execute('''SELECT h.reason,h.changed_at,h.action,a.description FROM transaction_history h
                LEFT JOIN review_actions a ON a.id=h.action_id WHERE h.transaction_id=?
                AND h.field_name IN ('category','category_name') ORDER BY h.rowid DESC LIMIT 1''',(transaction_id,)).fetchone()
            category_reason = (history['reason'] or history['description'] or 'Explicit transaction edit') if history else (
                'No business category has been assigned; this row is awaiting review.' if 'uncategorized' in row['category_name'].lower() else
                'This category predates detailed decision explanations. Check its retained review history; no reason has been inferred.')
            value = categorization.suggestion(row,categorization.rules(db))
            result = {'source':{'filename':row['filename'],'provider':row['provider'],'row':row['source_row'],'sheet':raw.get('sheet')},
                'importEvidence':raw.get('evidence'),'extraction':json.loads(row['metadata_json'] or '{}').get('extraction'),
                'sourceColumns':[{'header':str(h),'value':str(v)} for h,v in zip(raw.get('headers',[]),raw.get('values',[])) if str(h).strip()],
                'original': baseline,
                'current':{'date':row['date'],'postedDate':row['posted_date'],'description':row['description'],'merchant':row['merchant'],'amountCents':row['amount_cents'],'direction':row['direction'],'kind':row['transaction_kind'],
                    'category':row['category_name'],'classification':row['classification'],'includeInTotals':bool(row['include_in_totals'])},
                'categoryReason':category_reason,'categoryDecidedAt':history['changed_at'] if history else None,'suggestion':value}
        return self.send_json(200,result)

    def commit_import(self):
        body = self.read_json()
        with connect() as db:
            db.execute('BEGIN IMMEDIATE')
            staged = db.execute('SELECT * FROM staged_imports WHERE token=? AND created_at>?', (body.get('token'), dt.datetime.now().timestamp() - 1800)).fetchone()
            if not staged:
                return self.send_json(404, {'error': 'Import preview expired or was already committed. Choose the file again.'})
            parsed = json.loads(staged['parsed_json'])
            if 'extraction' not in parsed:
                raise ValueError('This preview predates the import explanation update. Choose the file again to review its columns.')
            if body.get('confirmExtraction') is not True:
                raise ValueError('Confirm the source columns, selected rows and amount interpretation before importing.')
            account_id = body.get('accountId')
            if not db.execute('SELECT id FROM accounts WHERE id=? AND active=1', (account_id,)).fetchone():
                raise ValueError('Choose a valid source account.')
            if parsed['provider'] == 'American Express' and body.get('confirmMapping') is not True:
                raise ValueError('Confirm the American Express mapping: positive amounts are charges; negative amounts are payments or credits.')
            existing = db.execute('SELECT id FROM documents WHERE file_hash=?', (staged['file_hash'],)).fetchone()
            if existing and body.get('allowDuplicate') is not True:
                raise ValueError('This exact document is already imported. Explicitly confirm re-import to retain another copy for review.')
            document_id, now = str(uuid.uuid4()), utc_now()
            archive = source_archive.capture(staged['content'], parsed['filename'])
            target = DOCS_DIR / (document_id + Path(parsed['filename']).suffix.lower())
            # Write before committing database references. A failed DB transaction
            # removes this new file; originals belonging to previous imports stay intact.
            temporary = target.with_suffix('.tmp')
            try:
                with temporary.open('xb') as output:
                    output.write(staged['content']); output.flush(); os.fsync(output.fileno())
                temporary.replace(target)
                metadata = {'reconciliation':parsed['reconciliation'],'rowCount':len(parsed['rows']),'mappingConfirmed':body.get('confirmMapping') is True,'extractionConfirmed':True,'extraction':parsed['extraction']}
                dates = [r['date'] for r in parsed['rows'] if parse_date(r['date'])]
                db.execute('INSERT INTO documents(id,filename,file_hash,stored_path,provider,format,statement_start,statement_end,imported_at,default_classification,parser_version,metadata_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                    (document_id, parsed['filename'], staged['file_hash'], target.relative_to(DATA_DIR).as_posix(), parsed['provider'], parsed['format'], min(dates) if dates else None, max(dates) if dates else None, now, 'unknown', parsed['parser_version'], json.dumps(metadata)))
                source_archive.save_document(db, document_id, staged['file_hash'], archive, now)
                inserted = []
                for tx in parsed['rows']:
                    tx_id = str(uuid.uuid4())
                    possible = db.execute('SELECT id FROM transactions WHERE account_id=? AND source_fingerprint=? LIMIT 1', (account_id, tx['fingerprint'])).fetchone()
                    db.execute('''INSERT INTO transactions(id,document_id,account_id,date,posted_date,description,merchant,raw_amount_text,source_amount_cents,amount_cents,direction,transaction_kind,source_fingerprint,classification,category_name,status,source_row,source_raw_json,created_at,updated_at)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                        (tx_id,document_id,account_id,tx['date'],tx['posted_date'],tx['description'],tx['merchant'],tx['raw_amount_text'],tx['source_amount_cents'],tx['amount_cents'],tx['direction'],tx['transaction_kind'],tx['fingerprint'],'unknown',tx['category_name'],'needs_review',tx['source_row'],json.dumps(tx['raw']),now,now))
                    baseline = {'date':tx['date'],'postedDate':tx['posted_date'],'description':tx['description'],
                        'merchant':tx['merchant'],'amountCents':tx['amount_cents'],'direction':tx['direction'],
                        'kind':tx['transaction_kind'],'category':tx['category_name'],'classification':'unknown','includeInTotals':False}
                    source_archive.save_transaction(db, tx_id, document_id, tx['raw'], tx['source_row'], now, baseline, parsed['extraction'])
                    inserted.append({'id':tx_id, 'duplicateCandidate':possible['id'] if possible else None})
                db.execute('DELETE FROM staged_imports WHERE token=?', (body['token'],))
                if body.get('rememberLayout') is True:
                    db.execute('''INSERT INTO import_profiles(id,account_id,layout_key,provider,format,extraction_json,confirmed_at)
                      VALUES(?,?,?,?,?,?,?) ON CONFLICT(account_id,layout_key) DO UPDATE SET extraction_json=excluded.extraction_json,confirmed_at=excluded.confirmed_at,active=1''',
                      (str(uuid.uuid4()),account_id,parsed['layout_key'],parsed['provider'],parsed['format'],json.dumps(parsed['extraction']),now))
                db.commit()
            except Exception:
                temporary.unlink(missing_ok=True)
                target.unlink(missing_ok=True)
                raise
        return self.send_json(201, {'documentId':document_id, 'rowCount':len(inserted), 'inserted':inserted})

    def undo_review(self):
        body = self.read_json()
        with connect() as db:
            db.execute('BEGIN IMMEDIATE')
            action = db.execute('SELECT * FROM review_actions WHERE id=?', (body.get('actionId'),)).fetchone()
            if not action or action['status'] != 'active' or action['action_type'] == 'undo':
                raise ValueError('Choose an active review action to undo.')
            reversal, now = str(uuid.uuid4()), utc_now()
            db.execute('INSERT INTO review_actions(id,action_type,description,created_at) VALUES(?,?,?,?)', (reversal,'undo','Undo '+action['description'],now))
            conflicts, restored = [], []
            for item in db.execute('SELECT * FROM review_action_items WHERE action_id=?', (action['id'],)).fetchall():
                current = db.execute('SELECT * FROM transactions WHERE id=?', (item['transaction_id'],)).fetchone()
                old, new = json.loads(item['old_state']), json.loads(item['new_state'])
                later = db.execute('SELECT 1 FROM transaction_history WHERE transaction_id=? AND rowid>(SELECT coalesce(max(rowid),0) FROM transaction_history WHERE action_id=?) LIMIT 1', (item['transaction_id'],action['id'])).fetchone()
                if not current or later or any(key not in current.keys() or current[key] != value for key,value in new.items()):
                    conflicts.append(item['transaction_id'])
                    db.execute("UPDATE review_action_items SET outcome='conflict' WHERE id=?", (item['id'],))
                    continue
                self.record_change(db, current['id'], new, old, reversal, 'undo', now)
                assignments = ','.join(key+'=?' for key in old)
                db.execute('UPDATE transactions SET '+assignments+',updated_at=? WHERE id=?', (*old.values(),now,current['id']))
                restored.append(current['id'])
                db.execute("UPDATE review_action_items SET outcome='undone' WHERE id=?", (item['id'],))
            db.execute('UPDATE review_actions SET status=? WHERE id=?', ('partially_undone' if conflicts else 'undone',action['id']))
        return self.send_json(200, {'actionId':reversal,'restored':restored,'conflicts':conflicts})

    @staticmethod
    def record_change(db, tx_id, old, new, action_id, action, now):
        db.execute('INSERT INTO review_action_items(id,action_id,transaction_id,old_state,new_state) VALUES(?,?,?,?,?)', (str(uuid.uuid4()),action_id,tx_id,json.dumps(old),json.dumps(new)))
        for key in new:
            if old.get(key) != new[key]:
                db.execute('INSERT INTO transaction_history(id,transaction_id,action_id,field_name,old_value,new_value,action,changed_at) VALUES(?,?,?,?,?,?,?,?)', (str(uuid.uuid4()),tx_id,action_id,key,json.dumps(old.get(key)),json.dumps(new[key]),action,now))

    def resolve_duplicate(self):
        body = self.read_json()
        first, second = body.get('transactionId'), body.get('canonicalId')
        decision = body.get('decision')
        if not first or first == second or decision not in {'duplicate','distinct'}:
            raise ValueError('Choose two different transactions and a duplicate decision.')
        with connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM transactions WHERE id=?', (first,)).fetchone()
            canonical = db.execute('SELECT * FROM transactions WHERE id=?', (second,)).fetchone()
            if not row or not canonical or row['account_id'] != canonical['account_id']:
                raise ValueError('Duplicate decisions require two transactions on the same source account.')
            if decision == 'duplicate':
                if canonical['duplicate_of'] or db.execute('SELECT 1 FROM transactions WHERE duplicate_of=?', (first,)).fetchone():
                    raise ValueError('Choose a canonical transaction that is not itself a duplicate. Duplicate chains are not allowed.')
                now, action_id = utc_now(), str(uuid.uuid4())
                db.execute('INSERT INTO review_actions(id,action_type,description,created_at) VALUES(?,?,?,?)', (action_id,'mark_duplicate','Confirm duplicate',now))
                old = {k:row[k] for k in ('duplicate_of','include_in_totals')}
                new = {'duplicate_of':second, 'include_in_totals':0}
                db.execute('UPDATE transactions SET duplicate_of=?,include_in_totals=0,updated_at=? WHERE id=?', (second,now,first))
                self.record_change(db,first,old,new,action_id,'duplicate',now)
            a,b = sorted((first,second))
            db.execute('INSERT OR REPLACE INTO duplicate_decisions VALUES(?,?,?,?)', (a,b,decision,utc_now()))
        return self.send_json(200, {'ok':True})

    def update_transaction(self, transaction_id: str):
        body = self.read_json()
        allowed = {"date", "postedDate", "description", "merchant", "amountCents", "direction", "kind", "classification", "businessId", "accountId", "category", "status", "includeInTotals", "notes"}
        with connect() as db:
            db.execute('BEGIN IMMEDIATE')
            current = db.execute("SELECT * FROM transactions WHERE id=?", (transaction_id,)).fetchone()
            if not current:
                return self.send_json(404, {"error": "Transaction not found."})
            values = dict(current)
            mapping = {"postedDate":"posted_date", "amountCents":"amount_cents", "kind":"transaction_kind", "businessId":"business_id", "accountId":"account_id", "includeInTotals":"include_in_totals"}
            action_id = str(uuid.uuid4()); now = utc_now()
            db.execute("INSERT INTO review_actions(id,action_type,description,created_at) VALUES(?,?,?,?)", (action_id, "edit_transaction", "Edit transaction", now))
            columns = {'category_name','category_id','excluded'} | {mapping.get(k,k) for k in allowed if k != 'category'}
            old_state = {key: current[key] for key in columns}
            for key, value in body.items():
                if key not in allowed: continue
                col = mapping.get(key, key)
                if key == "includeInTotals":
                    if not isinstance(value, bool): raise ValueError('Totals inclusion must be true or false.')
                    value = int(value)
                if key == "status" and value == "review": value = "needs_review"
                if col == "business_id" and not value: value = None
                values[col] = value
            if values["classification"] == "business" and not values["business_id"]:
                raise ValueError('Choose a business for this transaction.')
            if values["classification"] != "business": values["business_id"] = None; values["include_in_totals"] = 0
            if values["transaction_kind"] == "transfer": values["include_in_totals"] = 0
            if values["duplicate_of"]: values["include_in_totals"] = 0
            if values["include_in_totals"] and values["direction"] == "unknown":
                raise ValueError('Choose debit or credit before including this transaction in totals.')
            if values["include_in_totals"] and values["status"] != "approved": values["status"] = "approved"
            if values['include_in_totals']: values['excluded'] = 0
            if "category" in body:
                category = db.execute("SELECT id,name FROM categories WHERE name=? AND (business_id=? OR business_id IS NULL) ORDER BY business_id IS NULL LIMIT 1", (body["category"], values["business_id"])).fetchone()
                values["category_name"] = category["name"] if category else body["category"]
                values["category_id"] = category["id"] if category else None
            else:
                values["category_name"] = current["category_name"]; values["category_id"] = current["category_id"]
            if values['classification'] == 'business':
                category = db.execute('SELECT id FROM categories WHERE active=1 AND name=? AND (business_id=? OR business_id IS NULL) ORDER BY business_id IS NULL LIMIT 1', (values['category_name'],values['business_id'])).fetchone()
                if not category:
                    raise ValueError('Choose a category belonging to this business.')
                values['category_id'] = category['id']
            self.validate_transaction(db, values)
            if any(values[k]!=current[k] for k in ('amount_cents','account_id','direction','transaction_kind')) and (current['related_transaction_id'] or db.execute('SELECT 1 FROM transactions WHERE related_transaction_id=?',(transaction_id,)).fetchone()):
                raise ValueError('Unlink this transaction in Credits & payments before changing its amount, source account, movement or kind.')
            values["updated_at"] = now
            db.execute("""UPDATE transactions SET date=?,posted_date=?,description=?,merchant=?,account_id=?,amount_cents=?,direction=?,transaction_kind=?,classification=?,business_id=?,category_id=?,category_name=?,status=?,include_in_totals=?,excluded=?,notes=?,updated_at=? WHERE id=?""",
              (values["date"],values["posted_date"],values["description"],values["merchant"],values["account_id"],values["amount_cents"],values["direction"],values["transaction_kind"],values["classification"],values["business_id"],values["category_id"],values["category_name"],values["status"],values["include_in_totals"],values['excluded'],values["notes"],now,transaction_id))
            new_row = db.execute("SELECT * FROM transactions WHERE id=?", (transaction_id,)).fetchone()
            new_state = {key: new_row[key] for key in columns}
            self.record_change(db,transaction_id,old_state,new_state,action_id,'edit',now)
            db.execute('UPDATE transaction_history SET reason=? WHERE action_id=?',('You explicitly saved this transaction in the editor. The chosen category is “'+new_row['category_name']+'”; amount '+format(Decimal(new_row['amount_cents'])/100,'.2f')+' USD and movement '+new_row['direction']+'.',action_id))
        return self.send_json(200, {"ok": True, 'actionId':action_id})

    @staticmethod
    def validate_transaction(db, values, check_category=True):
        credits.validate_treatment(values)
        if values['status'] not in {'needs_review','suggested','approved'}:
            raise ValueError('Choose a valid review status.')
        if type(values['amount_cents']) is not int or not 0 <= values['amount_cents'] <= 999999999999:
            raise ValueError('Amount must be nonnegative integer USD cents, within the supported range.')
        if not isinstance(values['date'],str) or parse_date(values['date']) != values['date']:
            raise ValueError('Enter a valid date in YYYY-MM-DD format.')
        if values.get('posted_date') and parse_date(values['posted_date']) != values['posted_date']:
            raise ValueError('Enter a valid posted date in YYYY-MM-DD format.')
        for key in ('description','merchant','notes','category_name'):
            if not isinstance(values[key],str) or len(values[key]) > 10000:
                raise ValueError('Transaction text fields must contain at most 10,000 characters.')
        if not values['description'].strip(): raise ValueError('Description is required.')
        if not db.execute('SELECT id FROM accounts WHERE id=? AND active=1',(values['account_id'],)).fetchone():
            raise ValueError('Choose an active source account.')
        if values['business_id'] and not db.execute('SELECT id FROM businesses WHERE id=? AND active=1',(values['business_id'],)).fetchone():
            raise ValueError('Choose an active business.')
        if check_category and values['classification'] == 'business' and not db.execute('SELECT id FROM categories WHERE active=1 AND name=? AND (business_id=? OR business_id IS NULL)',(values['category_name'],values['business_id'])).fetchone():
            raise ValueError('Choose a category belonging to this business.')
        if values['include_in_totals']:
            valid_kind = (values['direction'] == 'debit' and values['transaction_kind'] in {'expense','fee'}) or (values['direction'] == 'credit' and values['transaction_kind'] == 'refund')
            if not valid_kind or values['classification'] != 'business' or not values['business_id'] or values['duplicate_of'] or values['status'] != 'approved' or values['amount_cents'] == 0 or 'uncategorized' in values['category_name'].lower() or not values['category_name'].strip():
                raise ValueError('Expense totals require an approved, categorized business expense/fee or a reviewed refund, with a valid amount and no duplicate link.')

    def batch_review(self):
        body = self.read_json(); ids = body.get("ids", []); action = body.get("action")
        if not isinstance(ids,list) or not ids or len(ids)>5000 or any(not isinstance(i,str) for i in ids) or len(set(ids)) != len(ids) or action not in {"approve", "include", "personal", "transfer", "exclude"}:
            return self.send_json(400, {"error": "Select transactions and a valid review action."})
        action_id, now = str(uuid.uuid4()), utc_now()
        with connect() as db:
            db.execute('BEGIN IMMEDIATE')
            target_business = body.get("businessId")
            selected_rows = [db.execute("SELECT * FROM transactions WHERE id=?", (tx_id,)).fetchone() for tx_id in ids]
            if any(row is None for row in selected_rows):
                return self.send_json(400, {"error": "A selected transaction no longer exists. Refresh and select the rows again."})
            if action == "include":
                if any(row["classification"] == "unknown" for row in selected_rows):
                    if not db.execute("SELECT id FROM businesses WHERE id=? AND active=1", (target_business,)).fetchone():
                        return self.send_json(400, {"error": "Choose the business for unassigned transactions."})
                for row in selected_rows:
                    if (row["direction"] == "unknown" or row["transaction_kind"] in ("unknown", "transfer")
                        or row["classification"] in ("personal", "transfer") or row["duplicate_of"]
                        or "uncategorized" in row["category_name"].lower() or not parse_date(row["date"]) or row["amount_cents"] <= 0):
                        return self.send_json(400, {"error": "Review the date, amount, category, and classification of each selected row before inclusion."})
            db.execute("INSERT INTO review_actions(id,action_type,description,created_at) VALUES(?,?,?,?)", (action_id,"batch_"+action,"Batch review: "+action,now))
            for tx_id in ids:
                row = db.execute("SELECT * FROM transactions WHERE id=?", (tx_id,)).fetchone()
                if not row: continue
                old = {"status":row["status"],"classification":row["classification"],"transaction_kind":row["transaction_kind"],"include_in_totals":row["include_in_totals"],"business_id":row["business_id"], 'excluded':row['excluded']}
                classification, kind, status, include, business_id = row["classification"],row["transaction_kind"],row["status"],row["include_in_totals"],row["business_id"]
                if action == "approve": status, include = "approved", 0
                elif action == "include":
                    status = "approved"
                    if classification == "unknown": classification = "business"; business_id = target_business
                    include = int(classification == "business" and row["direction"] != "unknown" and kind != "transfer" and row["duplicate_of"] is None)
                elif action == "personal": classification, business_id, status, include = "personal", None, "approved", 0
                elif action == "transfer": classification, business_id, kind, status, include = "transfer", None, "transfer", "approved", 0
                elif action == "exclude": status, include = "approved", 0
                excluded = int(action == 'exclude')
                candidate = dict(row) | {'classification':classification,'business_id':business_id,'transaction_kind':kind,'status':status,'include_in_totals':include,'excluded':excluded}
                if action in {'approve','include'}: self.validate_transaction(db,candidate)
                db.execute("UPDATE transactions SET classification=?,business_id=?,transaction_kind=?,status=?,include_in_totals=?,excluded=?,updated_at=? WHERE id=?", (classification,business_id,kind,status,include,excluded,now,tx_id))
                new = {"status":status,"classification":classification,"transaction_kind":kind,"include_in_totals":include,"business_id":business_id,'excluded':excluded}
                db.execute("INSERT INTO review_action_items(id,action_id,transaction_id,old_state,new_state) VALUES(?,?,?,?,?)", (str(uuid.uuid4()),action_id,tx_id,json.dumps(old),json.dumps(new)))
                for key in old:
                    if old[key] != new[key]: db.execute("INSERT INTO transaction_history(id,transaction_id,action_id,field_name,old_value,new_value,action,changed_at) VALUES(?,?,?,?,?,?,?,?)", (str(uuid.uuid4()),tx_id,action_id,key,str(old[key]),str(new[key]),action,now))
        return self.send_json(200,{"ok":True,"actionId":action_id,"count":len(ids)})

    def create_business(self):
        body=self.read_json(); name=str(body.get("legalName","")).strip()
        if not name: return self.send_json(400,{"error":"Business name is required."})
        business_id=str(uuid.uuid4()); now=utc_now()
        with connect() as db:
            db.execute("INSERT INTO businesses(id,legal_name,display_name,created_at) VALUES(?,?,?,?)",(business_id,name,body.get("displayName") or name,now))
            for cat in BASE_CATEGORIES: db.execute("INSERT OR IGNORE INTO categories(id,business_id,name) VALUES(?,?,?)",("cat-"+business_id[:8]+"-"+slug(cat),business_id,cat))
        return self.send_json(201,{"id":business_id,"legalName":name,"displayName":body.get("displayName") or name})

    def create_account(self):
        body=self.read_json(); nickname=str(body.get("nickname","")).strip(); last_four=str(body.get("lastFour","")).strip()
        if not nickname: return self.send_json(400,{"error":"Account nickname is required."})
        if last_four and not re.fullmatch(r"\d{4}",last_four): return self.send_json(400,{"error":"Enter only the last four digits."})
        if len(nickname)>100 or len(str(body.get('institution','')))>100:
            raise ValueError('Account name and institution must be at most 100 characters.')
        if body.get('accountType','checking') not in {'checking','savings','credit','other'}:
            raise ValueError('Choose a valid account type.')
        account_id=str(uuid.uuid4())
        with connect() as db:
            db.execute("INSERT INTO accounts(id,business_id,nickname,institution,last_four,account_type) VALUES(?,?,?,?,?,?)",(account_id,body.get("businessId") or None,nickname,body.get("institution","") ,last_four,body.get("accountType","checking")))
        return self.send_json(201,{"id":account_id,"nickname":nickname,"last_four":last_four})

    def export_csv(self):
        query = parse_qs(urlparse(self.path).query)
        business_id = query.get("businessId", [""])[0]
        year = query.get("year", [""])[0]
        if year and not re.fullmatch(r"\d{4}", year):
            return self.send_json(400, {"error": "Choose a valid reporting year."})
        filters, parameters = [], []
        if business_id:
            filters.append("t.business_id=?")
            parameters.append(business_id)
        if year:
            filters.append("t.date>=? AND t.date<?")
            parameters.extend((year + "-01-01", str(int(year) + 1).zfill(4) + "-01-01"))
        extra_where = (" AND " + " AND ".join(filters)) if filters else ""
        with connect() as db:
            rows=db.execute("""SELECT t.date,t.description,a.nickname,a.last_four,t.category_name,t.amount_cents,t.direction,t.classification,t.status,d.filename,t.source_row,t.credit_treatment,t.related_transaction_id
              FROM transactions t JOIN accounts a ON a.id=t.account_id LEFT JOIN documents d ON d.id=t.document_id
              WHERE t.status='approved' AND t.excluded=0 AND t.classification='business' AND t.include_in_totals=1 AND ((t.direction='debit' AND t.transaction_kind IN ('expense','fee')) OR (t.direction='credit' AND t.transaction_kind='refund')) AND t.duplicate_of IS NULL""" + extra_where +
              " ORDER BY t.date,t.created_at", parameters).fetchall()
        out=io.StringIO(newline=""); writer=csv.writer(out)
        writer.writerow(["Date","Description","Source account","Category","Amount USD","Direction","Classification","Review status","Source document","Source row","Credit decision","Related transaction ID"])
        for r in rows:
            signed_cents = -r["amount_cents"] if r["direction"] == "credit" else r["amount_cents"]
            writer.writerow([r["date"],safe_text(r["description"]),safe_text(r["nickname"]+(f" ···· {r['last_four']}" if r["last_four"] else "")),safe_text(r["category_name"]),f"{Decimal(signed_cents)/100:.2f}",r["direction"],r["classification"],r["status"],safe_text(r["filename"]),r["source_row"] or "",credits.LABELS.get(r["credit_treatment"],"") if r["direction"]=="credit" or r["credit_treatment"] else "",r["related_transaction_id"] or ""])
        data=out.getvalue().encode("utf-8-sig")
        self.send_response(200);self.send_header("Content-Type","text/csv; charset=utf-8");self.send_header("Content-Disposition","attachment; filename=expense-ledger.csv");self.send_header("Content-Length",str(len(data)));self.end_headers();self.wfile.write(data)

    def download(self, data, filename, content_type):
        self.send_response(200)
        self.send_header('Content-Type',content_type)
        self.send_header('Content-Disposition','attachment; filename="'+filename+'"')
        self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store')
        self.end_headers(); self.wfile.write(data)

    def export_excel(self):
        query = parse_qs(urlparse(self.path).query)
        business = query.get('businessId',[''])[0]
        year = query.get('year',[''])[0]
        if year and not re.fullmatch(r'\d{4}',year):
            return self.send_json(400, {'error':'Choose a valid reporting year.'})
        where, params = [], []
        with connect() as db:
            label = 'All businesses'
            if business:
                record = db.execute('SELECT display_name FROM businesses WHERE id=?',(business,)).fetchone()
                if not record: return self.send_json(400, {'error':'Choose a valid business.'})
                label = record[0]
                where.append('(t.business_id=? OR a.business_id=?)'); params.extend((business,business))
            if year:
                where.append('t.date>=? AND t.date<?'); params.extend((year+'-01-01',str(int(year)+1).zfill(4)+'-01-01'))
            rows = db.execute('''SELECT t.*,a.nickname,a.last_four,d.filename,b.display_name AS business_name FROM transactions t
                JOIN accounts a ON a.id=t.account_id LEFT JOIN documents d ON d.id=t.document_id LEFT JOIN businesses b ON b.id=t.business_id'''+(' WHERE '+' AND '.join(where) if where else '')+' ORDER BY t.date,t.id',params).fetchall()
        try:
            data = excel_report(rows,label,year)
        except ImportError:
            return self.send_json(503, {'error':'Install Excel support with python -m pip install -r requirements.txt.'})
        return self.download(data,'bookkeeper-report.xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    def backup(self):
        # Serialize with imports so the database snapshot and document set agree.
        with STAGING_LOCK:
            data = create_backup(DB_PATH,DATA_DIR)
        return self.download(data,'bookkeeper-backup-'+dt.date.today().isoformat()+'.zip','application/zip')

    def do_PATCH(self):
        return self.do_POST()


def main() -> None:
    global SETUP_ERROR
    preferences,error = workspace_store.load_preferences()
    SETUP_ERROR = error
    if preferences:
        try:
            directory = workspace_store.directory_path(preferences['directory'])
            workspace_store.validate_existing(directory)
            activate_workspace(directory)
        except (ValueError,OSError,sqlite3.Error) as exc:
            SETUP_ERROR = str(exc)
    server = LocalHTTPServer((HOST, PORT), Handler)
    print(f"Local Bookkeeper running at http://{HOST}:{PORT}")
    if WORKSPACE_READY:
        print(f"SQLite database: {DB_PATH}")
        print(f"Managed source files: {DOCS_DIR}")
    else:
        print('Choose Create or Open books in the app to select your database location.')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping local server…")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
