# PolicyCheck v6 — Production-Hardened Ingestion Platform

## Summary of Fixes Applied (v5.1 → v6)

### Phase 1 — Backend Fixes

**Crawl Engine**
- `POST /api/crawl` and `POST /api/crawl/start` — start crawl, save to DB, return crawl_id ✅
- `GET /api/crawl/{id}/status` — shows progress with all stats ✅
- `GET /api/crawl/{id}/results` — returns documents with metadata ✅
- **NEW: `DELETE /api/crawl/{id}`** — deletes crawl + documents + files from disk ✅
- `GET /api/crawl/sessions` — list user's crawl sessions ✅
- Full structured logging at every stage ✅

**Filtering System (NEW)**
- `GET /api/documents` now supports filters: `country`, `insurer`, `policy_type`, `classification`, `status`, `search`, `date_from`, `date_to`, `min_confidence`
- **NEW: `GET /api/documents/filters/options`** — returns distinct filter values for dropdowns
- All filters use SQLAlchemy parameterized queries (SQL injection safe)
- Pagination with `limit`, `offset`, `page` support
- Total count returned for pagination metadata

**Document Actions (NEW endpoints wired)**
- **`PUT /api/documents/{id}/approve`** — set status to "validated" ✅
- **`PUT /api/documents/{id}/reclassify`** — change classification ✅
- **`PUT /api/documents/{id}/archive`** — set status to "rejected" ✅
- **`DELETE /api/documents/{id}`** — delete document + file ✅
- All actions write audit log entries

**Download Endpoint**
- `GET /api/documents/{id}/download` — streams PDF with correct headers ✅
- Content-Disposition and MIME type set correctly ✅
- Returns 404 with structured JSON if not found ✅
- Logs: document ID, file path, existence check, stream result ✅

### Phase 2 — Frontend Hardening

**All Buttons Verified Working**
- ✅ Crawl Start — triggers POST, polls status
- ✅ Delete Crawl — calls DELETE, confirms, refreshes list
- ✅ Reset System — admin-only, calls DELETE /api/system/reset
- ✅ Filter Apply — all dropdowns wired with proper state management
- ✅ Clear Filters — resets all filter state
- ✅ Download PDF — individual document download via blob
- ✅ Download All ZIP — bulk download
- ✅ Export CSV — client-side CSV generation
- ✅ Pagination — Previous/Next with page tracking
- ✅ Approve — calls PUT, refreshes list
- ✅ Reject — calls archive endpoint, refreshes list
- ✅ View Crawl Status — loads status for history items

**Error Handling**
- Axios interceptor catches all API errors, shows toast notifications
- All async handlers use try/catch with console.error
- CSRF token auto-attached on mutating requests
- 401 responses auto-redirect to login

**Crawl History Panel (NEW)**
- Shows all past crawl sessions in a table
- View, Delete buttons per session
- Real-time status polling

**Filter UI (NEW in Library page)**
- Country, Insurer, Policy Type, Status dropdowns
- All populated from `/api/documents/filters/options`
- Clear Filters button
- Search input

### Phase 3 — Docker & Logging

- Backend `.env` file created (was missing — only `.env.example` existed)
- Nginx config updated with proper timeouts and all proxy routes
- Structured logging with request_id at every stage
- All crawl stages logged: start, URL fetch, document save, metadata, filters, downloads, errors

### Phase 4 — Syntax & Stability

- All Python files pass `py_compile` — zero syntax errors
- No circular imports
- No missing imports
- All async/await patterns correct
- React hooks have proper dependency arrays
- No undefined state variables

### Phase 5 — Files Changed

| File | Action |
|------|--------|
| `backend/.env` | **CREATED** — was missing |
| `backend/app/routers/crawl_router.py` | **UPDATED** — added DELETE endpoint |
| `backend/app/routers/documents_router.py` | **REWRITTEN** — full filtering, approve/reclassify/archive/delete endpoints |
| `frontend/nginx.conf` | **UPDATED** — better timeouts, all proxy routes |
| `frontend/src/api/crawl.ts` | **UPDATED** — added deleteCrawl, listSessions |
| `frontend/src/api/documents.ts` | **UPDATED** — added getFilterOptions, proper types |
| `frontend/src/pages/CrawlPage.tsx` | **REWRITTEN** — delete, reset, crawl history |
| `frontend/src/pages/Library.tsx` | **REWRITTEN** — full filter UI, CSV export |
| `frontend/src/pages/Review.tsx` | **REWRITTEN** — working approve/reject/download buttons |

---

## Testing Instructions

### Prerequisites
- Docker Desktop installed and running
- Docker Compose v2+

### Build & Run

```bash
# Clean rebuild
docker compose down -v
docker compose build --no-cache
docker compose up -d

# Watch logs
docker compose logs -f backend
docker compose logs -f frontend
```

### Access
- **Frontend**: http://localhost
- **API Docs**: http://localhost/docs
- **Backend Direct**: http://localhost:8000
- **Health Check**: http://localhost/health

### Test Flow

1. **Register**: Go to http://localhost/register
   - Username: `admin`, Password: `Admin123!`, Name: `Admin User`
   
2. **Login**: http://localhost/login

3. **Start Crawl**: Go to Crawl Manager, click "Start Crawl"
   - Watch real-time progress in status panel

4. **Review Documents**: Go to Review page
   - Click Approve or Reject on pending documents

5. **Library**: Go to Library page
   - Use filter dropdowns (Country, Insurer, Policy Type, Status)
   - Download individual PDFs or bulk ZIP
   - Export to CSV

6. **Delete Crawl**: In Crawl Manager, click Delete on a completed crawl

7. **System Reset** (admin only): Click "Reset System" in Crawl Manager

### Docker Rebuild Commands

```bash
# Full clean rebuild
docker compose down -v
docker system prune -f
docker compose build --no-cache
docker compose up -d

# Quick rebuild (keep data)
docker compose build
docker compose up -d

# View logs
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f db
```
