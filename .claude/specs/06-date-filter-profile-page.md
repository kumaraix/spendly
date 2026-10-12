# Spec: Date Filter for Profile Page

## Overview
Step 6 lets a logged-in user narrow the profile page to a date range. Step 5
wired the summary stats, recent transactions and category breakdown to the
database, but they always cover a user's entire history. This step adds a
filter bar to `/profile` with two date inputs (from / to) and quick presets
(This month, Last month, Last 3 months, All time). The chosen range travels
as query-string parameters on `GET /profile`, so every filtered view has a
shareable, bookmarkable URL and no new route is needed. User details
(name, email, member since) are never filtered.

## Depends on
- Step 1: Database setup (`expenses.date` stored as `YYYY-MM-DD` text)
- Step 3: Login / Logout (`session["user_id"]` and `@login_required`)
- Step 4: Profile page design (`templates/profile.html`, `static/css/profile.css`)
- Step 5: Profile backend routes (`database/queries.py` helpers feeding `/profile`)

## Routes
No new routes. The existing route is modified:
- `GET /profile?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD` — renders the
  profile with stats, recent transactions and category breakdown limited to
  expenses whose `date` falls within the range (both ends inclusive) —
  logged-in
  - Both parameters are optional. A missing or empty parameter leaves that
    end of the range open (`start_date` only → that date onwards;
    `end_date` only → up to and including that date; neither → all time,
    identical to Step 5 behaviour)
  - A value that is not a valid ISO date (e.g. `2026-13-01`, `abc`) or a
    range where `start_date` is after `end_date` is not applied: the page
    renders all-time data with status 200 and an inline error message
    above the stats. It must never return 500

## Database changes
No database changes. `expenses.date` is already `TEXT NOT NULL` in
`YYYY-MM-DD` format, which sorts and compares correctly as a string.

The read-only helpers in `database/queries.py` gain two optional keyword
arguments, `start_date=None` and `end_date=None` (ISO strings or `None`):
- `get_summary_stats(user_id, start_date=None, end_date=None)`
- `get_recent_transactions(user_id, limit=10, start_date=None, end_date=None)`
- `get_category_breakdown(user_id, start_date=None, end_date=None)`

Calling them without the new arguments must behave exactly as in Step 5.
`get_user_by_id` is unchanged.

## Templates
- **Create:** none
- **Modify:** `templates/profile.html`
  - Add a filter bar between the header and the stats section:
    - A `<form method="get" action="{{ url_for('profile') }}">` with two
      labelled `<input type="date">` fields named `start_date` and
      `end_date`, pre-filled with the active range, and an "Apply" button
    - Preset links built with `url_for('profile', start_date=..., end_date=...)`:
      This month, Last month, Last 3 months, All time
      (All time = `url_for('profile')` with no params). The preset matching
      the active range gets an active style and `aria-current="true"`
    - A "Clear" link to `url_for('profile')`, shown only when a filter is active
  - Show a short label of the active range above the stats, e.g.
    "Showing 1 Oct 2026 – 12 Oct 2026", or "Showing all time" when unfiltered
  - Show the inline error message (when present) using the existing
    error/alert styling from `style.css`
  - When a filter is active and no expenses match, the empty states read
    "No expenses in this period" and "No spending in this period" instead of
    the Step 5 wording

## Files to change
- `app.py`
  - Add a helper that reads `start_date` / `end_date` from `request.args`,
    validates them with `datetime.date.fromisoformat`, and returns the
    validated range plus an optional error message
  - Add a helper that computes the preset ranges relative to `date.today()`
  - Pass the range through `_profile_stats`, `_profile_recent_expenses` and
    `_profile_category_breakdown` to the query helpers
  - Pass `start_date`, `end_date`, `range_label`, `presets` and
    `filter_error` to `profile.html`
- `database/queries.py` — add the optional date-range arguments to the three
  helpers listed under Database changes
- `templates/profile.html` — filter bar, range label, error message and
  filtered empty-state wording
- `static/css/profile.css` — styles for the filter bar, date inputs, preset
  chips (including active state) and range label; must stack cleanly at
  phone width
- `CLAUDE.md` — mark the date filter as implemented (Step 6) in the routes
  table and note the new query-helper arguments under Architecture

## Files to create
- `tests/test_date_filter.py` — tests for this feature (see Definition of done)

## New dependencies
No new dependencies. Date parsing uses the standard library `datetime`.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` via `get_db()` only
- Parameterised queries only — the date bounds are bound with `?`
  placeholders, never formatted into the SQL string. Prefer a single static
  query with optional bounds, e.g.
  `AND (? IS NULL OR date >= ?) AND (? IS NULL OR date <= ?)`,
  over building SQL by string concatenation
- Passwords hashed with werkzeug (unchanged by this step)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- No inline `<style>` tags; new styles go in `static/css/profile.css`
- No JavaScript is required — the filter works through a plain GET form.
  If any JS is added, it must be vanilla and live in `static/js/main.js`
- Every internal link uses `url_for()`, including preset links
- All amounts keep using the `inr` filter (₹, Indian grouping)
- DB logic stays in `database/queries.py`; the `profile()` route only parses
  input, calls helpers and renders
- Validate dates before they reach SQL; invalid input never causes a 500
- Expenses are always scoped to `session["user_id"]` — the filter must never
  expose another user's expenses
- Category breakdown `pct` values must still sum to 100 for any non-empty range
- Do not implement Steps 7–9 (add / edit / delete expense) — those stubs stay

## Definition of done
- [ ] Visiting `/profile` with no query parameters shows the same totals, transactions and breakdown as Step 5 (seed user: ₹5,548.50, 8 transactions, top category "Bills")
- [ ] The profile page shows a filter bar with "From" and "To" date inputs, an "Apply" button and the presets This month, Last month, Last 3 months and All time
- [ ] Choosing a From/To range and clicking Apply reloads `/profile?start_date=…&end_date=…` and updates total spent, transaction count, top category, recent transactions and category breakdown to that range only
- [ ] Expenses dated exactly on `start_date` or `end_date` are included (inclusive range)
- [ ] Supplying only `start_date`, or only `end_date`, filters by that one bound
- [ ] The date inputs stay pre-filled with the active range after the page reloads
- [ ] Clicking "This month" shows only the current month's expenses and highlights that preset; "All time" removes the filter
- [ ] The page shows the active range ("Showing 1 Oct 2026 – 12 Oct 2026" or "Showing all time")
- [ ] A range with no matching expenses shows ₹0.00, 0 transactions, "—" as top category, and the "in this period" empty states — no errors
- [ ] `/profile?start_date=abc` and `/profile?start_date=2026-10-12&end_date=2026-10-01` return 200, show an inline error, and fall back to all-time data
- [ ] Category percentages still add up to 100% for any filtered range that has expenses
- [ ] Another user's expenses never appear, whatever range is chosen
- [ ] `/profile?start_date=…` while logged out still redirects to `/login`
- [ ] The filter bar is usable at phone width with no horizontal scrolling
- [ ] `pytest` passes, including the new `tests/test_date_filter.py`, which inserts expenses with fixed dates rather than relying on the seed data's dates
