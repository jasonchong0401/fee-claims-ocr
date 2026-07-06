# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Initialize database (first time)
mysql -u root -p < sql/init.sql

# Run the server (with auto-reload)
python -m app.main
# Serves on http://0.0.0.0:8000 — Swagger at /docs, ReDoc at /redoc
```

There are no tests, linters, or type-checkers configured yet.

## Architecture

FastAPI expense-reimbursement system: users upload receipt images → OCR extracts fields → structured records in MySQL. JWT auth with admin/user roles, plus a browser frontend (login + upload pages served as static HTML).

### Request flow (upload)

```
Browser: POST /api/upload (multipart image + Bearer token)
  → get_current_user() dependency resolves Employee from JWT
  → Receipt row created (status=0, UUID generated)
  → File saved to uploads/receipts/{employee_id}/{YYYY-MM-DD}/{uuid}.ext
  → OCRService.recognize(path) → OCRResult
  → Non-admin users: OCR applicant must match logged-in username/employee_id
  → Receipt updated with extracted fields (status=1) or error (status=-1)
```

### OCR pipeline (the most complex subsystem)

`app/ocr_service.py` is a **compatibility wrapper** — it delegates to the real package at `app/ocr/`. All new OCR work goes in `app/ocr/`, not `app/ocr_service.py`.

```
app/ocr/
├── __init__.py              # get_ocr_service(engine) factory
├── base.py                  # BaseOCRService ABC + OCRResult dataclass
├── mock.py                  # MockOCRService — random preset receipts
├── easy_ocr.py              # EasyOCRService — PyTorch-based, ch_sim+en
├── paddle_ocr.py            # PaddleOCRService — PP-Structure v3
├── deepseek_ocr.py          # DeepSeekOCRService — EasyOCR text → DeepSeek extraction
├── deepseek_extractor.py    # extract_hybrid(): DeepSeek API → regex fallback
└── extractors.py            # Regex field extractors (amount, applicant, merchant, type, head_count, date)
```

**Engine selection** (`get_ocr_service`):
- `"auto"` (default): DeepSeekOCR → EasyOCR → Mock (first available wins)
- `"deepseek"`: EasyOCR + DeepSeek AI extraction (requires `DEEPSEEK_API_KEY` and `openai` package)
- `"easyocr"`: EasyOCR + regex extractors
- `"paddle"`: PaddleOCR + regex extractors
- `"mock"`: Random preset data, no image reading

**DeepSeekOCR flow** (`deepseek_ocr.py`):
1. EasyOCR reads image → raw text lines
2. `extract_hybrid()` sends text to DeepSeek API with a prompt asking for JSON
3. If DeepSeek returns valid JSON with a non-null `total_amount` → use AI result
4. If DeepSeek fails (no API key, network error, bad JSON) → falls back to regex extractors
5. If DeepSeek returns partial result → merge: AI fields take priority, regex fills gaps

**Regex extractors** (`extractors.py`): Priority-based amount extraction (合计/总计 label → ¥ symbol fallback → max amount heuristic), multi-line merchant matching (label on one line, value on next), OCR-tolerant patterns (人→入, 报→报).

### Auth

`app/auth.py` — JWT via `python-jose`, password hashing via `passlib[bcrypt]`.

- `get_current_user` — FastAPI dependency: extracts Bearer token, decodes JWT, queries `Employee` table, returns Employee or 401
- `require_admin` — chains on `get_current_user`, returns 403 if `role != "admin"`
- `get_optional_user` — like `get_current_user` but returns None instead of 401 (for optional-auth endpoints)
- JWT payload: `{"sub": username, "role": role, "exp": ...}`
- Config: `JWT_SECRET`, `JWT_ALGORITHM` (HS256), `JWT_EXPIRE_MINUTES` (480 = 8h) in `.env`

### Database

`app/database.py` — engine creation with 3 retries, `SessionLocal` factory, `get_db()` dependency (yields session, rollback on exception, close in finally). Connection pool: 10 + 20 overflow, pre-ping, 1h recycle.

`app/models.py` — `Receipt` and `Employee` on `DeclarativeBase`. Both have `to_dict()` methods. Tables auto-created on startup via `Base.metadata.create_all()`.

### API surface

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | none | Login page (static HTML) |
| GET | `/upload` | none | Upload page (JS checks token) |
| GET | `/api/health` | none | Health check |
| POST | `/api/login` | none | Login → JWT |
| POST | `/api/register` | none | Register (first user → admin) |
| GET/PUT | `/api/me` | user | View/update own profile |
| PUT | `/api/me/password` | user | Change own password |
| GET/POST | `/api/employees` | admin | List / create users |
| GET/PUT | `/api/employees/{id}` | admin | View / update any user |
| POST | `/api/upload` | user | Upload receipt image |
| GET | `/api/receipt/{uuid}` | user | Get single receipt |
| PUT | `/api/receipt/{uuid}` | user | Update receipt fields |
| GET | `/api/receipts` | user | Paginated list with filters |

### Response convention

All API responses follow `{"code": int, "msg": str, "data": ...}`. Success: `code=0`. List responses add `total`, `page`, `page_size`.

### Frontend

`static/login.html` and `static/index.html` — vanilla HTML/JS, served directly by FastAPI. No build step, no framework. The upload page stores the JWT in localStorage and attaches it as `Authorization: Bearer` on fetch requests.

### Config

`config.py` — reads `.env` via `python-dotenv`. Key settings: `database_url` (property, constructed from DB_* vars with `quote_plus`), `UPLOAD_DIR`, `MAX_FILE_SIZE_BYTES` (from MB env var), `ALLOWED_EXTENSIONS` (parsed from comma-separated string), JWT and DeepSeek settings.

### File storage layout

```
uploads/receipts/{employee_id}/{YYYY-MM-DD}/{uuid}.{ext}
```

UUID-renamed, organized by employee and date. Served at `/uploads/` via `StaticFiles` mount.
