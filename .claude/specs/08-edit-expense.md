# Spec: Edit Expense

## Overview
Step 8 lets a logged-in user correct an expense they have already recorded.
Step 7 added the first write path (`/expenses/add`), but a typo in the amount,
category, date or description can currently only be lived with. This step
replaces the `GET /expenses/<id>/edit` stub with a real edit form pre-filled
from the database, adds a `POST` handler that reuses Step 7's
`_validate_expense_form()` and updates the row, and adds an "Edit" link to each
row of the profile page's recent transactions. Ownership is enforced on every
read and write: a user can only ever see or change their own expenses.

## Depends on
- Step 1: Database setup (`expenses` table, `CATEGORIES`, `get_db()`)
- Step 3: Login / Logout (`session["user_id"]`, `@login_required`)
- Step 5: Profile backend routes (`get_recent_transactions()` feeds the table that gets the Edit links)
- Step 7: Add expense (`_validate_expense_form()`, `_parse_*` helpers, `_render_expense_form()`, `expense.css`, `_check_csrf()` usage pattern)

## Routes
- `GET /expenses/<int:id>/edit` — renders the edit form pre-filled with the
  expense's current amount, category, date and description — logged-in
- `POST /expenses/<int:id>/edit` — checks CSRF, validates with
  `_validate_expense_form()`; on success updates the expense, flashes
  "Expense updated" and redirects to `profile`; on failure re-renders the form
  with status 400, an inline error and the submitted input preserved —
  logged-in

Both methods live on the existing `edit_expense` endpoint
(`@app.route("/expenses/<int:id>/edit", methods=["GET", "POST"])`) so
`url_for('edit_expense', id=...)` keeps working.

Ownership and not-found handling:
- If the expense does not exist **or** belongs to another user, both GET and
  POST `abort(404)` — the same response in both cases, so expense ids of other
  users are not revealed. A POST for someone else's expense changes nothing.
- The ownership check happens before validation, so a foreign id returns 404
  even when the submitted form is invalid.
- CSRF is checked first in the POST branch (400 on mismatch), as in Step 7.

Validation is identical to Step 7 (first failing rule wins): amount required,
plain positive number, ≤ ₹10 crore, rounded to 2 decimals; category exactly one
of `CATEGORIES`; date strict `YYYY-MM-DD`, not in the future; description
optional, stripped, ≤ 200 chars, empty → `NULL`.

The Step 9 delete stub is left untouched.

## Database changes
No database changes. The existing `expenses` table has every column needed.

Add two helpers:
- `database/queries.py` — `get_expense(expense_id, user_id)` — read-only;
  `SELECT id, amount, category, date, description FROM expenses WHERE id = ?
  AND user_id = ?`; returns a dict (description `None` → `""`) or `None` when
  not found / not owned
- `database/db.py` — `update_expense(expense_id, user_id, amount, category,
  expense_date, description=None)` — parameterised `UPDATE ... WHERE id = ?
  AND user_id = ?`, commits, returns `True` if exactly one row changed else
  `False`; rolls back and re-raises on error; always closes the connection

Also change `get_recent_transactions()` in `database/queries.py` to select and
return each expense's `id`, so the profile template can build Edit links.

## Templates
- **Create:** `templates/edit_expense.html` — extends `base.html`, links
  `expense.css`, same card/field layout and `exp-*` classes as
  `add_expense.html`, with:
  - Heading "Edit expense", subtitle "Update this spend"
  - `<form method="post" action="{{ url_for('edit_expense', id=expense_id) }}">`
    with the hidden `csrf_token` input
  - Amount, Category, Date (`max="{{ today }}"`), Description fields, filled
    from `form` (DB values on GET, submitted values after a failed POST)
  - "Save changes" submit button and a "Cancel" link to `url_for('profile')`
  - Inline `auth-error` block when `error` is set
  - (Alternatively, factor the shared fields into a `_expense_fields.html`
    partial included by both pages — acceptable as long as `add_expense.html`
    renders exactly as before)
- **Modify:** `templates/profile.html` — add an actions column to the recent
  transactions table: an empty-label `<th scope="col"><span class="sr-only">Actions</span></th>`
  (or equivalent visually-hidden text) and, per row, an "Edit" link to
  `url_for('edit_expense', id=expense.id)` with an accessible label such as
  `aria-label="Edit {{ expense.description or expense.category }} expense"`

## Files to change
- `app.py`
  - Import `update_expense` from `database.db` and `get_expense` from
    `database.queries`
  - Generalise `_render_expense_form()` to take the template name (and any
    extra context such as `expense_id`) so add and edit share it; the add
    route's behaviour must not change
  - Replace the `edit_expense` stub with a `@login_required` GET/POST view:
    fetch with `get_expense(id, session["user_id"])` → `abort(404)` if `None`;
    GET renders the form; POST checks CSRF, validates, calls
    `update_expense`, flashes, redirects
- `database/db.py` — add `update_expense()`
- `database/queries.py` — add `get_expense()`; include `id` in
  `get_recent_transactions()` results
- `templates/profile.html` — Edit link per transaction row
- `static/css/profile.css` — style for the row Edit link / actions column
  (`prof-*` classes), readable at phone width
- `tests/test_add_expense.py` — the stub-route test currently asserts
  `/expenses/1/edit` returns "coming in Step 8"; drop that case (keep the
  Step 9 delete assertion)
- `CLAUDE.md` — mark `GET/POST /expenses/<id>/edit` implemented (Step 8) in
  the routes table; list `update_expense()` under `database/db.py` and
  `get_expense()` under `database/queries.py` in Architecture

## Files to create
- `templates/edit_expense.html` — the edit form page
- `tests/test_edit_expense.py` — tests for this feature (see Definition of done)

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` via `get_db()` only
- Parameterised queries only — `?` placeholders, never f-strings in SQL
- Passwords hashed with werkzeug (unchanged by this step)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- No inline `<style>` tags; page styles go in `expense.css` / `profile.css`
- Every internal link and form action uses `url_for()`
- `user_id` always comes from `session["user_id"]` — never from the form or
  query string; every SELECT/UPDATE on an expense filters by both `id` and
  `user_id`
- Reuse `_validate_expense_form()` and the `_parse_*` helpers — do not
  duplicate validation logic
- Not found and not owned are indistinguishable: both `abort(404)`
- Use `abort()` for HTTP errors — never a bare string return
- Amounts displayed anywhere use the `inr` filter — never `$`
- DB logic stays in `database/db.py` / `database/queries.py`; the route does
  not touch `get_db()`
- No JavaScript is required; any added must be vanilla, in `static/js/main.js`
- Do not implement Step 9 (delete expense) — that stub stays

## Definition of done
- [ ] Visiting `/expenses/<id>/edit` while logged out redirects to `/login`; a POST while logged out also redirects and changes nothing
- [ ] Each row in the profile's recent transactions has an "Edit" link to `/expenses/<that id>/edit`
- [ ] Visiting the edit page for your own expense shows the "Edit expense" form pre-filled with its current amount, category, date and description
- [ ] Submitting valid changes (e.g. amount → ₹300.00, category → Transport) redirects to `/profile`, shows an "Expense updated" flash, and the row shows the new values
- [ ] After editing, total spent and the category breakdown reflect the new amount/category; transaction count is unchanged
- [ ] Clearing the description and saving stores `NULL`
- [ ] Invalid amount (`0`, `-5`, `abc`, `nan`, blank), invalid category (`Rent`), malformed or future date, or a 201-character description returns 400 with an inline error, keeps the submitted values in the form, and leaves the DB row unchanged
- [ ] GET or POST to `/expenses/<id>/edit` for another user's expense returns 404 and leaves that expense unchanged
- [ ] GET or POST to `/expenses/999999/edit` (non-existent) returns 404
- [ ] A POST with a missing or wrong `csrf_token` returns 400 and changes nothing
- [ ] A `user_id` field added to the POST body is ignored — the expense stays with its owner
- [ ] `/expenses/add` still works exactly as in Step 7
- [ ] The edit form and the profile table's Edit links are usable at phone width with no horizontal page scroll
- [ ] `/expenses/<id>/delete` still returns its Step 9 stub response
- [ ] `pytest` passes, including the new `tests/test_edit_expense.py`
