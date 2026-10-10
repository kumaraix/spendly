# Spec: Login and Logout

## Overview
Make the sign-in page work and add sign-out. `GET /login` already renders
`login.html`, but the form posts to a route that accepts only GET, and
`/logout` is a raw-string stub. This step adds `POST /login`, which looks the
user up by email, checks the password against the werkzeug hash stored in
Step 2, and on success stores the user in Flask's signed session cookie. It
also implements `GET /logout`, which clears the session, and updates the shared
navbar so signed-in users see their name and a "Sign out" link instead of
"Sign in" / "Get started". Every logged-in feature that follows (profile,
expenses) depends on knowing who the current user is, which is what this step
establishes.

## Depends on
- **Step 1 — Database setup**: `users` table and `get_db()`.
- **Step 2 — Registration**: `get_user_by_email()`, emails stored lowercase,
  passwords hashed with `generate_password_hash`, `app.secret_key` set,
  `login.html` rendering flashed messages, `.auth-success` style.

## Routes
- `GET /login` — render the sign-in form; if already signed in, redirect to
  `landing` — public (already exists; extend it)
- `POST /login` — validate credentials; on success clear and set the session,
  then redirect to `landing`; on failure re-render `login.html` with a generic
  error and the entered email, status 401 (400 for missing fields) — public
- `GET /logout` — clear the session, flash "You have been signed out", redirect
  to `login` — public (safe to hit when not signed in; replaces the Step 3 stub)
- `GET /register` — additionally redirect to `landing` if already signed in —
  public (existing route, small change only)

Implement `GET`/`POST /login` on the existing `login()` view with
`methods=["GET", "POST"]`. Do not add a separate endpoint.

## Database changes
No database changes. Login only reads the existing `users` table through the
existing `get_user_by_email()` helper. No new helpers are required.

## Templates
- **Create:** none
- **Modify:**
  - `templates/login.html`
    - Change `action="/login"` to `action="{{ url_for('login') }}"`
    - Repopulate the `email` input from the value passed back after a failed
      attempt (never repopulate the password)
  - `templates/base.html`
    - In `.nav-links`: when `session.user_id` is set, show the signed-in
      user's name (`session.user_name`) and a "Sign out" link to
      `url_for('logout')`; otherwise keep the existing "Sign in" and
      "Get started" links

## Files to change
- `app.py`
  - Import `session` from Flask and `check_password_hash` from
    `werkzeug.security`
  - Set `SESSION_COOKIE_SAMESITE="Lax"` in `app.config` (HttpOnly is already
    Flask's default)
  - `login()` handles GET and POST as described in Routes
  - `register()` redirects signed-in users to `landing` on GET and POST
  - Replace the `/logout` stub with the real implementation
- `templates/login.html` — see Templates
- `templates/base.html` — see Templates
- `static/css/style.css` — add a `.nav-user` style for the signed-in name in
  the navbar, using existing CSS variables only
- `CLAUDE.md` — mark `POST /login` and `GET /logout` as implemented (Step 3)
  in the routes table

## Files to create
- `tests/test_login_logout.py` — pytest tests for login, logout, navbar state
  and signed-in redirects, using the existing `app` / `client` fixtures from
  `tests/conftest.py` (temp DB with the seeded `demo@spendly.com` / `demo123`
  user)

## New dependencies
No new dependencies. Flask sessions and `werkzeug.security` are already
available.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only (`?` placeholders), never f-strings in SQL
- Passwords hashed with werkzeug: verify with `check_password_hash`; never
  compare plain text, never log or re-render the password
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- All DB access goes through `database/db.py`; the route only validates,
  calls helpers, sets the session, and renders or redirects
- Use `url_for()` for every internal link and redirect; never hardcode URLs
- Normalise the submitted email with `.strip().lower()` before lookup
- Missing email or password → re-render with
  "Email and password are both required." and status 400
- Unknown email **and** wrong password → the same message,
  "Invalid email or password.", status 401, so the response never reveals
  whether an email is registered
- On success call `session.clear()` before setting `session["user_id"]` and
  `session["user_name"]`, so no stale data survives across accounts
- Store only the user's id and name in the session — never the email,
  password, or hash
- `logout()` must call `session.clear()` and work even when nobody is signed in
- Do not flash a message on successful login: flashes are only rendered on
  `login.html`, so a login flash would appear later on the wrong page
- Do not implement `/profile` or any `/expenses/...` stub; do not add a
  `login_required` decorator yet (Step 4 introduces the first protected page)
- Keep the dev server on port 5001

## Definition of done
- [ ] `python app.py` starts on port 5001 with no errors
- [ ] `GET /login` shows the form and its `action` is generated by `url_for`
- [ ] Signing in as `demo@spendly.com` / `demo123` redirects to `/`, and the
      navbar shows "Demo User" and "Sign out" instead of "Sign in" /
      "Get started"
- [ ] Signing in with `DEMO@spendly.com` (uppercase) also works
- [ ] A wrong password and an unregistered email both show
      "Invalid email or password." with status 401, and the email field keeps
      its value while the password field is empty
- [ ] Submitting a blank email or password shows
      "Email and password are both required." with status 400
- [ ] While signed in, visiting `/login` or `/register` redirects to `/`
- [ ] Clicking "Sign out" clears the session, redirects to `/login`, shows
      "You have been signed out", and the navbar shows "Sign in" /
      "Get started" again
- [ ] Visiting `/logout` while not signed in still redirects to `/login`
      without an error
- [ ] The session cookie contains only `user_id` and `user_name` (no email,
      password, or hash)
- [ ] A user registered through `/register` in Step 2 can sign in with the
      password they chose
- [ ] No hex colour values are added to any CSS file
- [ ] `pytest` passes, including the existing registration tests and the new
      tests in `tests/test_login_logout.py`
