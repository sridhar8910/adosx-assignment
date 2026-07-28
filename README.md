# DealerOS Reconciliation

A full-stack tool that loads two systems' records of the same events, finds where they disagree, and shows those disagreements per tenant.

**Stack:** Django 6 + Django REST Framework · React 18 + Vite · PostgreSQL

---

## How to run it

### Prerequisites

- Python 3.12+
- Node.js 18+ and npm
- PostgreSQL 14+ running locally

### Database setup

Copy `.env.example` to `.env` and set `DB_PASSWORD` to your local Postgres password. Create the database if needed:

```bash
psql -U postgres -h 127.0.0.1 -c "CREATE DATABASE adosx_db;"
```

### Backend

```bash
# Copy the env template and fill in your PostgreSQL password
cp .env.example .env
# Then export required vars (or use a tool like python-decouple to load .env):
export DB_PASSWORD=your-postgres-password-here   # Windows: $env:DB_PASSWORD='...'

# Install Python dependencies
python -m pip install -r requirements.txt

# Create the database tables
python manage.py migrate

# Load the CSV data
python manage.py load_data

# Run the reconciliation engine
python manage.py reconcile

# Start the API server
python manage.py runserver
```


The API will be at `http://127.0.0.1:8000/api/`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. The Vite dev server proxies `/api/*` to Django.

### Tests

Tests use SQLite in-memory (via `test_settings.py`), so no database setup is needed.

```bash
python -m pip install pytest pytest-django
python -m pytest
```

---

## What I built

**Importer (`load_data` management command)**
Reads `locations.csv`, `system_a.csv`, and `system_b.csv`. Every anomaly is logged to an `ImportIssue` table — nothing is silently dropped. Dirty `record_ref` values (`rec1034`, `1112`, ` REC - 1070 `) are normalised to canonical form before FK lookup. Comma-separated numbers (including Indian-style `1,25,400.00`) are parsed by stripping commas; the original string is preserved in `value_raw`. Truly unparseable or blank values are stored as NULL with the raw string kept for display (e.g. REC-1050's blank System B value).

**Reconciliation engine (`reconciler.py`)**
A pure function `find_disagreements()` that takes plain dicts and returns disagreements. No Django ORM inside, so it is trivially testable. Catches five disagreement types: missing in B, orphan in B, duplicate in B, value mismatch, unparseable value. Reconciliation runs against the **global** dataset (all orgs at once) so that cross-tenant `record_id` matches — where System A records a row under `ORG-A` but System B records the same row under `ORG-B` — are correctly resolved rather than silently dropped as `MISSING_IN_B`. Tenant isolation is enforced at query time in the API layer.

**API**
Five endpoints under `/api/`:
- `GET /api/disagreements/?org=ORG-A` — returns disagreements for one tenant, with optional `?reason=` filter and `?sort=` (prefix `-` for descending)
- `GET /api/reasons/` — reason codes and display labels
- `GET /api/orgs/` — list of org IDs for the UI selector
- `GET /api/import-issues/` — the full import anomaly log (admin-style; not tenant-scoped — in production this would be restricted to privileged users)
- `POST /api/reconcile/` — re-run reconciliation and return the disagreement count

Tenant isolation: every disagreement query is filtered through `location__org_id`. An org-A user cannot see org-B rows even if they guess the URL.

**Frontend**
A single-page React app designed as an **Observability Control Room Split-Pane Workspace** (inspired by tools like Sentry and Datadog). Features:
- **Workspace Navigation Bar:** Segmented controls to toggle between Overview Dashboard, Split-View Explorer, Visual Topology, Audit Logs, and Operations Logs.
- **Observability Control Sidebar:** Holds the global re-run reconciler action panel, dynamic tenant org scopes, and live find queries.
- **Split-View Explorer:** Left-hand scrolling discrepancy card stream with right-hand sticky comparison panel showing raw system deltas, location scopes, audit trace messages, and formatted JSON dynamic fields.
- **Visual Topology Diagram:** Interactive SVG displaying data flows from System A locations to the central Reconciler Core and System B entry points. Clicking LOC nodes quick-filters location lists.
- **Logs Console:** Simulated terminal buffer showing real-time execution steps and status logs during a reconciliation run.
- Single styling stylesheet (`index.css`) with zero third-party component libraries.

---

## What I deliberately did not build

- **Authentication.** The brief says skip it. The org parameter stands in for what would be a session claim in production.
- **Pagination.** 120 rows × 2 systems = no need.
- **Date / location disagreement detection.** The brief's minimum set is value, missing, orphan, duplicate. Date and location mismatches exist in the data (e.g. REC-1077 filed under different locations in A vs B) but are not surfaced as disagreement types when values agree.
- **Tenant-scoped import issues.** The import-issues endpoint returns all orgs' anomalies for debugging; production would scope this to admin roles.
- **Production deployment config.** No gunicorn, nginx, or Docker — not asked for.

---

## How I worked with the agent

I used Kiro (Claude-backed) for the whole thing. It wrote first drafts of everything — models, importer, reconciler, views, tests, React app. I steered it, reviewed what it produced, and caught the things it missed.

**a. Name one thing the AI agent got wrong. How did you notice?**

The big one was how it handled tenant boundaries during reconciliation. The agent's first version of `reconcile_from_db()` looped through each org separately — fetch ORG-A's System A records, fetch ORG-A's System B entries, compare, move on to ORG-B. Sounds reasonable, and it works for 99% of the data. But there's one row in the dataset that breaks it: REC-1077 lives in LOC-102 (that's ORG-A), but its matching System B entry ENT/2026/4077 is filed under LOC-201 (ORG-B). So when the agent ran the ORG-A pass, that B entry was invisible — wrong org, filtered out — and REC-1077 got flagged as `MISSING_IN_B`. During the ORG-B pass, the entry was there but its matching A record wasn't, so it just… vanished. Not an orphan, not a match, just gone.

I caught it because the numbers didn't add up. The app said 3 records were missing in B, and I went through the CSVs by hand and could only find 2. Took me a while to figure out which record was the extra one, but once I landed on REC-1077 and saw it was cross-org, the bug was obvious. The fix was to stop filtering by org during comparison — run the match globally, then let the API layer handle who sees what. That's where tenant isolation belongs anyway.

**b. Which part of your submission are you least confident about, and why?**

Honestly, the `_normalise_record_ref` function. It works perfectly for the three dirty patterns in this dataset — `rec1034`, `1112`, ` REC - 1070 ` — but it's basically a regex that grabs trailing digits and slaps `REC-` in front. If someone sends a ref like `REC-1034-AMENDED` or `REC-1034/V2`, it would grab the wrong number or fail entirely. I kept it simple because the brief said to, and overengineering a parser for patterns that don't exist in the data felt like the wrong trade-off for a one-day exercise. But in production, I'd want explicit format recognition with a fallback to "log it and move on" rather than silent mismatches.

**c. If you had a second day, what would you fix first?**

Authentication. Right now tenant isolation works correctly — ORG-A genuinely can't see ORG-B's data — but it's held together by a query parameter that anyone can change. That's fine for a take-home where the brief explicitly says to skip auth, but it would keep me up at night in production. I'd add SimpleJWT or Django's built-in token auth, derive the org from the token claims, and remove the `?org=` parameter entirely. One change, and the isolation goes from "correct by convention" to "actually secure."

After that, I'd add location and date disagreement detection. The data has at least one clear case (REC-1077 at different locations in A vs B) that the current system resolves correctly but doesn't surface as its own disagreement type. That feels like something a real user would want to see.

