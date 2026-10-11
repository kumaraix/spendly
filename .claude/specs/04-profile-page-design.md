# Spec: Profile Page Design

## Overview
Replace the raw-string `/profile` stub with a designed profile page and make it
the first page that requires a signed-in user. This step is about **layout and
design only**: the page shows the signed-in user's name from the session, and
everything else (email, member-since date, spending summary, recent
transactions and category breakdown) is hardcoded sample data in INR (₹) passed
from the route. Step 5 replaces that sample data with real queries against
`users` and `expenses`. Building the UI first fixes the template context the DB
step must provide and gives users a "home" to land on after signing in.

## Depends on
- **Step 1 — Database setup**: `users` and `expenses` schema and the
  `CATEGORIES` list, which the sample data must use.
- **Step 3 — Login and Logout**: `session["user_id"]` and
  `session["user_name"]` are set on sign-in, and the session-aware navbar in
  `base.html`.

## Routes
- `GET /profile` — render `profile.html` with the session user's name and
  hardcoded sample data; if nobody is signed in, redirect to `login` —
  logged-in (replaces the Step 4 stub)

No other new routes. Signed-in users are sent to `profile` after login, and
from `/`, `/login` and `/register`.

## Database changes
No database changes. Verified against `database/db.py`: `users` already has
`name`, `email`, `created_at`, and `expenses` already has `amount`,
`category`, `date`, `description`. This step adds no helpers and does not query
the DB; Step 5 does the wiring.

## Templates
- **Create:**
  - `templates/profile.html` — extends `base.html`; fills the `title`, `head`
    (links `profile.css`) and `content` blocks. Sections:
    1. **Profile header card**: avatar circle with the user's initials, name
       (from `session.user_name` via the `user` context), email, and
       "Member since <Month YYYY>".
    2. **Summary stats row**: three stat cards for Total spent (₹), Number of
       transactions, and Top category.
    3. **Recent transactions**: a table with Date, Description, Category
       (pill/badge) and Amount (₹, right-aligned). Show the 5 most recent
       sample rows.
    4. **Spending by category**: a list of each category with its ₹ total and
       a horizontal bar showing its share of the total (width set from a
       percentage in the context, no JS charting).
    - Empty states: if `recent_expenses` is empty, show "No expenses yet"
      instead of the table; if `category_breakdown` is empty, hide the bars.
- **Modify:**
  - `templates/base.html` — when `session.user_id` is set, make the user's
    name in `.nav-links` a link to `url_for('profile')` (keep "Sign out").

### Template context (contract for Step 5)
The route passes exactly these names, so Step 5 only swaps the data source:
- `user` — dict: `name`, `email`, `member_since` (display string, e.g.
  "October 2026"), `initials`
- `stats` — dict: `total_spent` (float), `transaction_count` (int),
  `top_category` (str)
- `recent_expenses` — list of dicts: `date` (YYYY-MM-DD), `description`,
  `category`, `amount` (float)
- `category_breakdown` — list of dicts: `category`, `total` (float),
  `percent` (int 0–100), sorted by `total` descending

Amounts are formatted in the template with the `inr` filter (Indian grouping,
e.g. `₹1,23,456.50`).

## Files to change
- `app.py` — replace the `/profile` stub: redirect to `login` when
  `session.get("user_id")` is falsy; otherwise build the hardcoded context
  (with `user.name` taken from `session["user_name"]`) and render
  `profile.html`. Keep the sample data in a module-level constant or small
  private helper, not inline in the route body.
- `templates/base.html` — navbar name links to the profile page.
- `CLAUDE.md` — mark `GET /profile` as implemented (Step 4) in the routes
  table (reapply the stashed edit: `git stash pop`).

## Files to create
- `templates/profile.html`
- `static/css/profile.css` — page-specific styles for the profile header,
  stat cards, transactions table, category pills and bars
- `tests/test_profile.py` — uses the `app` fixture from `conftest.py`

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only (this step adds none; do not add any)
- Passwords hashed with werkzeug (unchanged; never show or pass password data
  to the template)
- Use CSS variables — never hardcode hex values; reuse the tokens in
  `style.css` (`--paper-card`, `--border`, `--accent`, `--accent-light`,
  `--ink-muted`, `--radius-md`, `--font-display`, etc.)
- All templates extend `base.html`
- Page-specific styles go in `static/css/profile.css`, linked from
  `{% block head %}`; no inline `<style>` tags or `style=` attributes except
  the bar width (`style="width: {{ percent }}%"`)
- Use `url_for()` for every internal link and redirect
- All money shown in ₹ / INR — never `$` or USD
- Sample categories must come from `CATEGORIES` in `database/db.py`
- No DB access in this step: do not add helpers to `database/db.py` and do
  not query `expenses` (that is Step 5)
- Do not add a `login_required` decorator package; an inline session check
  in the route (or a small local decorator in `app.py`) is fine
- Session still holds only `user_id` and `user_name`; do not add the email to
  the session to fill the profile card (use sample data until Step 5)
- Do not implement any `/expenses/...` stub routes
- Layout must work at phone width (stack the stat cards and let the table
  scroll horizontally inside its card)
- Never import `app` at the top of the test file; use the `app` fixture
- Keep the dev server on port 5001

## Definition of done
- [ ] `python app.py` starts on port 5001 with no errors
- [ ] Visiting `/profile` while signed out redirects to `/login`
- [ ] Signing in as `demo@spendly.com` / `demo123` then visiting `/profile`
      returns 200 and shows "Demo User" in the profile header with initials
      "DU"
- [ ] The page shows the email, "Member since …", three stat cards, a
      recent-transactions table with 5 rows, and a category breakdown with bars
- [ ] Every amount on the page is shown with `₹` and two decimals; no `$`
      appears anywhere
- [ ] When signed in, the navbar name links to `/profile`
- [ ] The page uses `profile.css`, and no hex colour values are added to any
      CSS file
- [ ] At a phone-width viewport (~375px) the layout stacks with no
      horizontal page scroll
- [ ] `/profile` no longer returns the "coming in Step 4" string
- [ ] `pytest` passes, including the existing registration and login tests and
      the new tests in `tests/test_profile.py` (signed-out redirect, signed-in
      200 with the user's name, ₹ present)
- [ ] `CLAUDE.md` routes table marks `GET /profile` as implemented (Step 4)
