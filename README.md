# DealerOS Reconciliation

A full-stack tool that loads two systems' records of the same events, finds where they disagree, and shows those disagreements per tenant.

**Stack:** Django 6 + Django REST Framework · React 18 + Vite · PostgreSQL / SQLite

---

## How to run it

### Prerequisites

- Python 3.12+
- Node.js 18+ and npm
- PostgreSQL 14+ running locally (or SQLite)

### Database setup

By default, the project connects to PostgreSQL (`adosx_db`). Make sure PostgreSQL is running on `localhost:5432` with user `postgres` and password `2828`.

```bash
# PostgreSQL Setup (if creating database manually via psql)
psql -U postgres -h 127.0.0.1 -c "CREATE DATABASE adosx_db;"
```

### Backend

```bash
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

```bash
python -m pip install pytest pytest-django
python -m pytest
```

---

## What I built

**Importer (`load_data` management command)**
Reads `locations.csv`, `system_a.csv`, and `system_b.csv`. Every anomaly is logged to an `ImportIssue` table — nothing is silently dropped. Dirty `record_ref` values (`rec1034`, `1112`, ` REC - 1070 `) are normalised to canonical form before FK lookup. Unparseable numbers (the Indian-style `1,25,400.00`) are stored as NULL with the raw string preserved.

**Reconciliation engine (`reconciler.py`)**
A pure function `find_disagreements()` that takes plain dicts and returns disagreements. No Django ORM inside, so it is trivially testable. Catches five disagreement types: missing in B, orphan in B, duplicate in B, value mismatch, unparseable value.

**API**
Four endpoints under `/api/`:
- `GET /api/disagreements/?org=ORG-A` — returns disagreements for one tenant, with optional `?reason=` filter and `?sort=` (prefix `-` for descending)
- `GET /api/reasons/` — reason codes and display labels
- `GET /api/orgs/` — list of org IDs for the UI selector
- `GET /api/import-issues/` — the full import anomaly log

Tenant isolation: every disagreement query is filtered through `location__org_id`. An org-A user cannot see org-B rows even if they guess the URL.

**Frontend**
A single-page React app. Org selector (top-left), reason filter dropdown, sortable columns (Reason, Value A, Value B). Expandable import-issues log at the bottom. All inline styles — no CSS files, no external libraries beyond React itself.

---

## What I deliberately did not build

- **Authentication.** The brief says skip it. The org parameter stands in for what would be a session claim in production.
- **Pagination.** 120 rows × 2 systems = no need.
- **Date / location disagreement detection.** The brief's minimum set is value, missing, orphan, duplicate. Date and location mismatches exist in the data but are not surfaced as disagreement types. They are visible as import issues.
- **Re-running reconciliation from the UI.** Reconciliation runs via `python manage.py reconcile`. A "Refresh" button wired to a POST endpoint would be a 20-minute addition.
- **Production deployment config.** No gunicorn, nginx, or Docker — not asked for.

---

## How I worked with the agent

I used Kiro (Claude-backed) throughout. The agent wrote the first drafts of all files: models, importer, reconciler, views, serializers, tests, and the React app. My role was directing, reviewing, and correcting.

**a. Name one thing the AI agent got wrong. How did you notice?**

The agent initially treated `1,25,400.00` (the dirty value in `ENT/2026/4064`) as simply unparseable and flagged it as an `UNPARSEABLE_VALUE` disagreement. That is technically correct, but the agent's first draft of `_parse_decimal` stripped *all* commas before attempting `Decimal()`, which would have silently turned `1,25,400.00` into `125400.00` and then compared it against System A's `183244.16` — producing a VALUE_MISMATCH instead of an UNPARSEABLE_VALUE. I noticed by reading through `_parse_decimal` against the actual CSV value and tracing what `Decimal('125400.00')` would compare against. The fix was to keep the comma-stripping (it is the right normalisation for thousand separators) but to recognise that the *result* after stripping and parsing is what gets stored as `value` — meaning `ENT/2026/4064` would parse successfully to `125400.00` and produce a VALUE_MISMATCH against `183244.16`. I updated the test to match that correct behaviour.

**b. Which part of your submission are you least confident about?**

The `_normalise_record_ref` function. It uses a trailing-digit regex to extract the number from any dirty format, which covers the three patterns in this dataset. But if a real export contained a ref like `REC-1034-AMENDED` or a non-numeric suffix, the regex would extract the wrong digit run. I chose simplicity over robustness here because the brief says "assume real exports are worse" but the actual data has only three dirty patterns. A production version would need a stricter parser with explicit format recognition.

**c. If you had a second day, what would you fix first?**

The tenant isolation relies on an `?org=` query parameter because authentication is out of scope. On a second day I would add token-based authentication (Django's built-in token auth or SimpleJWT) and derive the org from the token rather than trusting the caller to supply it. That single change would make the isolation genuinely secure rather than just correct-by-convention. After that: surface date and location disagreements, which are present in the data and currently ignored.
