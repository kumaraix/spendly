# CLAUDE.md

## Project overview

Spendly is a lightweight personal expense tracker built with Flask and SQLite.

---

## Architecture
```
spendly/
├── app.py              # All routes — single file, no blueprints
├── database/
│   ├── db.py           # SQLite helpers: get_db(), init_db(), seed_db(),
│                       #   get_user_by_email(), create_user(), create_expense(),
│                       #   update_expense()
│   └── queries.py      # Read-only page queries:
│                       #   get_user_by_id()
│                       #   get_summary_stats(), get_recent_transactions(),
│                       #     get_category_breakdown() — take optional
│                       #     start_date=/end_date= (YYYY-MM-DD, inclusive)
│                       #   get_expense(expense_id, user_id) — owner-only lookup,
│                       #     None when missing or another user's
├── templates/
│   ├── base.html       # Shared layout — all templates must extend this
│   ├── _flash.html     # Partial: flashed messages ({% include %}, not a page)
│   ├── _expense_fields.html  # Partial: amount/category/date/description
│                       #   fields shared by add_expense.html and edit_expense.html
│   └── *.html          # One template per page
├── static/
│   ├── css/
│   │   ├── style.css       # Global styles
│   │   ├── landing.css     # Landing-page-only styles
│   │   ├── profile.css     # Profile-page-only styles (prof-* classes)
│   │   ├── analytics.css   # Analytics coming-soon page styles (soon-* classes)
│   │   └── expense.css     # Add/edit expense form styles (exp-* classes)
│   └── js/
│       └── main.js         # Vanilla JS only
├── tests/
│   ├── conftest.py     # `app` fixture — patches DB_PATH to a temp file
│   └── test_*.py       # One test file per feature
├── pytest.ini          # pythonpath = . ; testpaths = tests
└── requirements.txt
```

**Where things belong:**
- New routes → `app.py` only, no blueprints
- DB logic → `database/db.py` (writes, auth) or `database/queries.py` (read-only page queries), never inline in routes
- New pages → new `.html` file extending `base.html`
- Page-specific styles → new `.css` file, not inline `<style>` tags

---

## Code style

- Python: PEP 8, snake_case for all variables and functions
- Templates: Jinja2 with `url_for()` for every internal link — never hardcode URLs
- Route functions: one responsibility only — fetch data, render template, done
- DB queries: always use parameterized queries (`?` placeholders) — never f-strings in SQL
- Error handling: use `abort()` for HTTP errors, not bare `return "error string"`

---

## Tech constraints

- **Flask only** — no FastAPI, no Django, no other web frameworks
- **SQLite only** — no PostgreSQL, no SQLAlchemy ORM, no external DB
- **Vanilla JS only** — no React, no jQuery, no npm packages
- **No new pip packages** — work within `requirements.txt` as-is unless explicitly told otherwise
- Python 3.10+ assumed — f-strings and `match` statements are fine

---

## Subagent Policy
- Always use a builtin explore subagent for codebase exploration 
  before implementing any new feature
- Always use a subagent to verify test results 
  after any implementation
- When asked to plan, delegate codebase research 
  to a subagent before presenting the plan
- always use a builtin plan subagent in plan mode

---

## Commands
```bash
# Setup
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Run dev server (port 5001); debugger only with FLASK_DEBUG=1
FLASK_DEBUG=1 python app.py

# Run all tests
pytest

# Run a specific test file
pytest tests/test_foo.py

# Run a specific test by name
pytest -k "test_name"

# Run tests with output visible
pytest -s
```

---

## Implemented vs stub routes

| Route | Status |
|---|---|
| `GET /` | Implemented — renders `landing.html`; redirects to `profile` if signed in |
| `GET /register` | Implemented — renders `register.html`; redirects to `profile` if signed in |
| `POST /register` | Implemented (Step 2) — validates, creates user, flashes success, redirects to `login` |
| `GET /login` | Implemented — renders `login.html`; redirects to `profile` if signed in |
| `POST /login` | Implemented (Step 3) — checks credentials, sets session `user_id`/`user_name`, redirects to `profile` |
| `GET /logout` | Implemented (Step 3) — clears session, flashes, redirects to `login` |
| `GET /profile` | Implemented (Step 5) — logged-in only; renders `profile.html` with the user's details, stats, recent transactions and category breakdown from the DB (`database/queries.py`); stale session → cleared, redirect to `login`. Step 6: optional `?start_date=`/`?end_date=` (YYYY-MM-DD, inclusive) filter stats, transactions and breakdown, with presets; invalid or reversed range → all-time data + inline error (200) |
| `GET /analytics` | Implemented — logged-in only (`@login_required`); renders the `analytics.html` "Coming Soon" page (from the Figma design). Navbar shows an "Analytics" link only when signed in, marked `nav-link--active` + `aria-current="page"` when `request.endpoint == 'analytics'` |
| `GET/POST /expenses/add` | Implemented (Step 7) — logged-in only; GET renders `add_expense.html` with today's date pre-filled; POST checks CSRF, validates with `_validate_expense_form()` (per-field `_parse_*` helpers; reusable for Step 8), inserts via `create_expense()`, flashes "Expense added", redirects to `profile`; invalid input → form re-rendered with inline error and preserved input (400) |
| `GET/POST /expenses/<id>/edit` | Implemented (Step 8) — logged-in, owner-only: `get_expense(id, user_id)` → `abort(404)` when missing or another user's (checked before CSRF/validation); GET renders `edit_expense.html` pre-filled; POST checks CSRF, validates with `_validate_expense_form()`, updates via `update_expense()`, flashes "Expense updated", redirects to `profile`; invalid input → 400 with inline error and preserved input. Profile's recent transactions link each row to it |
| `GET /expenses/<id>/delete` | Stub — Step 9 |

**Do not implement a stub route unless the active task explicitly targets that step.**

---

## Warnings and things to avoid

- **Never use raw string returns for stub routes** once a step is implemented — always render a template
- **Never hardcode URLs** in templates — always use `url_for()`
- **Never put DB logic in route functions** — it belongs in `database/db.py`
- **Never install new packages** mid-feature without flagging it — keep `requirements.txt` in sync
- **Never use JS frameworks** — the frontend is intentionally vanilla
- **`database/db.py` and `database/queries.py` only have the helpers listed under Architecture** — do not assume others exist until the step that implements them
- **Never import `app` at the top of a test file** — `app.py` runs `init_db()`/`seed_db()` on import; use the `app` fixture in `tests/conftest.py` so the real `expense_tracker.db` is never touched
- **`app.secret_key`** comes from the `SECRET_KEY` env var (dev fallback in `app.py`) — required for `flash()` and sessions
- **Session holds only `user_id`, `user_name` and `csrf_token`** — never email/password/hash; login and logout both call `session.clear()` first. Any feature that changes the user's name must update `session["user_name"]`
- **Protect logged-in pages with `@login_required`** (defined in `app.py`) — it redirects to `login` when `session["user_id"]` is missing
- **Flash messages render per page** via `{% include "_flash.html" %}` (`login.html`, `profile.html`), not in `base.html` — a page that is the target of a flashing redirect must include it itself
- **Every state-changing POST form needs CSRF protection** — add `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">` to the form and call `_check_csrf()` (in `app.py`) first in the POST branch; it `abort(400)`s on a mismatch. Tests set `sess["csrf_token"]` via `client.session_transaction()` and post the same value
- **Request bodies are capped** at 16 KB (`MAX_CONTENT_LENGTH`) — oversized POSTs get 413
- **Format money with the `inr` Jinja filter** (`{{ amount|inr }}` → `₹1,23,456.50`, Indian grouping) — never `$` or `"{:,.2f}"`
- **Date-range filters** go through `_DATE_RANGE_SQL` / `_range_params()` in `database/queries.py` — bounds are always bound with `?`, and validated as strict YYYY-MM-DD in `app.py` before reaching SQL
- **FK enforcement is manual** — SQLite foreign keys are off by default; `get_db()` must run `PRAGMA foreign_keys = ON` on every connection
- The app runs on **port 5001**, not the Flask default 5000 — don't change this