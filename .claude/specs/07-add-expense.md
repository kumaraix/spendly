# Spec: Add Expense

## Overview
Step 7 lets a logged-in user record a new expense. Until now the only
expenses in the database come from `seed_db()` or tests, so the profile
page's stats, recent transactions and category breakdown can never change
through the app. This step replaces the `GET /expenses/add` stub with a real
form (amount, category, date, optional description) and adds a `POST`
handler that validates the input, inserts the row for `session["user_id"]`,
flashes a success message and redirects to `/profile`, where the new expense
immediately shows up. It is the first write path for expenses and sets the
validation pattern that Step 8 (edit) will reuse.

## Depends on
- Step 1: Database setup (`expenses` table, `CATEGORIES`, `get_db()` with FK enforcement)
- Step 3: Login / Logout (`session["user_id"]` and `@login_required`)
- Step 5: Profile backend routes (profile reads expenses from the DB, so new rows appear there)
- Step 6: Date filter (`_parse_iso_date()` in `app.py` — reuse it for the expense date)

## Routes
- `GET /expenses/add` — renders the add-expense form with the date
  pre-filled to today and no category pre-selected — logged-in
- `POST /expenses/add` — validates the form; on success inserts the expense,
  flashes "Expense added", and redirects to `profile`; on failure re-renders
  the form with status 400, an inline error and the user's input preserved —
  logged-in

Both methods live on the existing `add_expense` endpoint
(`@app.route("/expenses/add", methods=["GET", "POST"])`) so `url_for('add_expense')`
keeps working. The Step 8 and Step 9 stubs are left untouched.

Validation (first failing rule wins, one error message shown):
- Amount is required, must parse as a number, must be finite and greater
  than 0, and at most 10,00,00,000 (₹10 crore); stored rounded to 2 decimals
- Category is required and must be one of `database.db.CATEGORIES`
  (exact match — the select's values are not trusted)
- Date is required and must be a strict `YYYY-MM-DD` date (use
  `_parse_iso_date`); dates in the future are rejected
- Description is optional, stripped, max 200 characters; empty → stored as `NULL`

## Database changes
No database changes. The existing `expenses` table already has every column
needed (`user_id`, `amount`, `category`, `date`, `description`, `created_at`).

Add one write helper to `database/db.py`:
- `create_expense(user_id, amount, category, expense_date, description=None)`
  — inserts one row with a parameterised `INSERT`, commits, returns the new
  expense id; rolls back and re-raises on error; always closes the connection

## Templates
- **Create:** `templates/add_expense.html` — extends `base.html`; a card
  with the heading "Add expense", a `<form method="post"
  action="{{ url_for('add_expense') }}">` containing:
  - Amount: `<input type="number" name="amount" step="0.01" min="0.01" required>`
    with a "₹" prefix
  - Category: `<select name="category" required>` with a disabled placeholder
    option and one option per entry in `categories` (passed from the route)
  - Date: `<input type="date" name="date" max="{{ today }}" required>`
  - Description: `<input type="text" name="description" maxlength="200">`
    marked "(optional)"
  - "Add expense" submit button and a "Cancel" link to `url_for('profile')`
  - Inline error block (when `error` is set) using the existing form/alert
    styling from `style.css`
  - All fields re-filled from the submitted values after a failed POST
- **Modify:** `templates/profile.html` — add an "Add expense" button linking
  to `url_for('add_expense')` in the page header, and a link to it inside the
  recent-transactions empty state

## Files to change
- `app.py`
  - Import `CATEGORIES` and `create_expense` from `database.db`
  - Replace the `add_expense` stub with a `@login_required` GET/POST view
  - Add a small `_validate_expense_form(form)` helper returning
    `(values, error)` so Step 8 can reuse it; the route itself only
    validates, calls `create_expense`, flashes and redirects/renders
- `database/db.py` — add `create_expense()`
- `templates/profile.html` — "Add expense" entry points
- `static/css/profile.css` — style for the header "Add expense" button (if
  the existing button classes in `style.css` don't already cover it)
- `CLAUDE.md` — mark `GET/POST /expenses/add` implemented (Step 7) in the
  routes table, list `create_expense()` under `database/db.py` in
  Architecture, and add `expense.css` to the static tree

## Files to create
- `templates/add_expense.html` — the add-expense form page
- `static/css/expense.css` — form-page styles (`exp-*` classes), shared with
  Step 8's edit page later
- `tests/test_add_expense.py` — tests for this feature (see Definition of done)

## New dependencies
No new dependencies. Number and date parsing use the standard library.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` via `get_db()` only
- Parameterised queries only — `?` placeholders, never f-strings in SQL
- Passwords hashed with werkzeug (unchanged by this step)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- No inline `<style>` tags; page styles go in `static/css/expense.css`
- Every internal link and form action uses `url_for()`
- `user_id` always comes from `session["user_id"]` — never from the form
  or query string
- Server-side validation is authoritative; HTML `required`/`min`/`max`
  attributes are a convenience only
- Invalid input returns 400 with the form re-rendered — never a 500, never a
  bare string return
- Amounts displayed anywhere use the `inr` filter (₹, Indian grouping) — never `$`
- DB logic stays in `database/db.py`; the route does not touch `get_db()`
- No JavaScript is required; if any is added it must be vanilla and live in
  `static/js/main.js`
- Do not implement Steps 8–9 (edit / delete expense) — those stubs stay

## Definition of done
- [ ] Visiting `/expenses/add` while logged out redirects to `/login`; a POST while logged out also redirects and inserts nothing
- [ ] Visiting `/expenses/add` while logged in shows the "Add expense" form with Amount, Category, Date and Description fields, the date pre-filled with today
- [ ] The category dropdown lists exactly Food, Transport, Bills, Health, Entertainment, Shopping, Other
- [ ] Submitting a valid expense (e.g. ₹250.00, Food, today, "Lunch") redirects to `/profile`, shows an "Expense added" flash, and the expense appears at the top of recent transactions
- [ ] After adding, the profile's total spent, transaction count and category breakdown include the new expense
- [ ] Leaving description blank succeeds and stores `NULL`
- [ ] Amount `0`, `-5`, `abc`, `nan`, `inf` or blank returns 400 with an inline error and inserts nothing
- [ ] A category not in the list (e.g. "Rent" sent by a crafted POST) returns 400 and inserts nothing
- [ ] A missing, malformed (`2026-13-01`, `12/10/2026`) or future date returns 400 and inserts nothing
- [ ] A description over 200 characters returns 400 and inserts nothing
- [ ] After a failed submit, the previously entered amount, category, date and description are still in the form
- [ ] A `user_id` field added to the POST body is ignored — the expense belongs to the logged-in user
- [ ] The profile page has an "Add expense" button that links to `/expenses/add`
- [ ] The form is usable at phone width with no horizontal scrolling
- [ ] `/expenses/<id>/edit` and `/expenses/<id>/delete` still return their Step 8/9 stub responses
- [ ] `pytest` passes, including the new `tests/test_add_expense.py`
