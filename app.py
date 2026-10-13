import hmac
import os
import re
import secrets
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from functools import wraps

from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from database.db import (
    CATEGORIES,
    create_expense,
    create_user,
    get_user_by_email,
    init_db,
    seed_db,
    update_expense,
)
from database.queries import (
    get_category_breakdown,
    get_expense,
    get_recent_transactions,
    get_summary_stats,
    get_user_by_id,
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-insecure-secret-key")
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
# Forms here are a few fields; anything bigger is rejected with 413.
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024

MAX_EXPENSE_AMOUNT = 100_000_000  # ₹10 crore
MAX_DESCRIPTION_LEN = 200

with app.app_context():
    init_db()
    seed_db()


def _is_valid_email(email):
    """Basic shape check: something@something.tld"""
    at = email.find("@")
    return at > 0 and "." in email[at + 1:].strip(".")


# Checked against when the email is unknown, so failed logins take the same
# time whether or not the account exists.
_DUMMY_PASSWORD_HASH = generate_password_hash("spendly-dummy-password")


def login_required(view):
    """Redirect to the sign-in page unless a user is in the session."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


@app.template_global("csrf_token")
def _csrf_token():
    """Return the session's CSRF token, creating it on first use."""
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(16)
    return session["csrf_token"]


def _check_csrf():
    """Abort with 400 unless the form's csrf_token matches the session's."""
    expected = session.get("csrf_token", "")
    submitted = request.form.get("csrf_token", "")
    if not expected or not hmac.compare_digest(expected, submitted):
        abort(400)


@app.after_request
def _no_store_when_signed_in(response):
    """Keep signed-in pages (expense data, CSRF tokens) out of browser caches."""
    if session.get("user_id") and request.endpoint != "static":
        response.headers["Cache-Control"] = "no-store"
    return response


@app.template_filter("inr")
def format_inr(amount):
    """Format a number as rupees with Indian digit grouping: ₹1,23,456.50"""
    sign = "-" if amount < 0 else ""
    whole, fraction = f"{abs(amount):.2f}".split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        whole = ",".join([head, *groups, tail])
    return f"{sign}₹{whole}.{fraction}"


def _initials(name):
    words = name.split()
    if not words:
        return "?"
    if len(words) == 1:
        return words[0][0].upper()
    return (words[0][0] + words[-1][0]).upper()


# ------------------------------------------------------------------ #
# Profile: date filter                                                #
# ------------------------------------------------------------------ #

_DATE_ERRORS = {
    "format": "Dates must be valid and in YYYY-MM-DD format — showing all time instead.",
    "order": "The start date must be on or before the end date — showing all time instead.",
}


def _today():
    """Wrapped so tests can monkeypatch the current date."""
    return date.today()


def _parse_iso_date(value):
    """Return value as a strict YYYY-MM-DD string ('' → None); raise ValueError otherwise."""
    value = (value or "").strip()
    if not value:
        return None
    # fromisoformat also accepts 20261012 and 2026-W41-1; insist on YYYY-MM-DD.
    if date.fromisoformat(value).isoformat() != value:
        raise ValueError(value)
    return value


def _parse_date_range(args):
    """Return (start_date, end_date, error) from request args.

    On any invalid input both bounds are None so the page shows all time.
    """
    try:
        start_date = _parse_iso_date(args.get("start_date"))
        end_date = _parse_iso_date(args.get("end_date"))
    except ValueError:
        return None, None, _DATE_ERRORS["format"]
    if start_date and end_date and start_date > end_date:
        return None, None, _DATE_ERRORS["order"]
    return start_date, end_date, None


def _date_presets(start_date, end_date, today=None):
    """Preset ranges relative to today, each flagged active if it matches.

    "Last 3 months" runs from the 1st of the month two months ago to today.
    """
    today = today or _today()
    first_this = today.replace(day=1)
    last_prev = first_this - timedelta(days=1)
    year, month = today.year, today.month - 2
    if month < 1:
        year, month = year - 1, month + 12
    ranges = [
        ("This month", first_this.isoformat(), today.isoformat()),
        ("Last month", last_prev.replace(day=1).isoformat(), last_prev.isoformat()),
        ("Last 3 months", date(year, month, 1).isoformat(), today.isoformat()),
        ("All time", None, None),
    ]
    return [
        {
            "label": label,
            "start_date": start,
            "end_date": end,
            "active": (start, end) == (start_date, end_date),
        }
        for label, start, end in ranges
    ]


def _format_day(iso_date):
    """'2026-10-01' → '1 Oct 2026' (portable — no %-d)."""
    d = date.fromisoformat(iso_date)
    return f"{d.day} {d.strftime('%b %Y')}"


def _range_label(start_date, end_date):
    if start_date and end_date:
        return f"Showing {_format_day(start_date)} – {_format_day(end_date)}"
    if start_date:
        return f"Showing from {_format_day(start_date)}"
    if end_date:
        return f"Showing up to {_format_day(end_date)}"
    return "Showing all time"


# ------------------------------------------------------------------ #
# Expenses: form validation                                           #
# ------------------------------------------------------------------ #

_AMOUNT_RE = re.compile(r"[0-9]+(?:\.[0-9]+)?")


def _parse_amount(raw):
    """Return (amount, error); amount is rounded half-up to 2 decimals."""
    raw = (raw or "").strip()
    if not raw:
        return None, "Amount is required."
    # Plain digits only: float() would also take "1_000", "1e3", "nan", "inf".
    if not _AMOUNT_RE.fullmatch(raw):
        return None, "Amount must be a positive number, like 250 or 99.50."
    amount = Decimal(raw).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if amount <= 0:
        return None, "Amount must be greater than 0."
    if amount > MAX_EXPENSE_AMOUNT:
        return None, f"Amount must be at most {format_inr(MAX_EXPENSE_AMOUNT)}."
    return float(amount), None


def _parse_category(raw):
    """Return (category, error); must exactly match one of CATEGORIES."""
    if not raw:
        return None, "Please choose a category."
    if raw not in CATEGORIES:
        return None, "Please choose a valid category."
    return raw, None


def _parse_expense_date(raw):
    """Return (YYYY-MM-DD, error); today or earlier only."""
    try:
        expense_date = _parse_iso_date(raw)
    except ValueError:
        return None, "Date must be a valid date (YYYY-MM-DD)."
    if expense_date is None:
        return None, "Date is required."
    if expense_date > _today().isoformat():
        return None, "Date cannot be in the future."
    return expense_date, None


def _parse_description(raw):
    """Return (description or None, error)."""
    description = (raw or "").strip()
    if len(description) > MAX_DESCRIPTION_LEN:
        return None, (
            f"Description must be {MAX_DESCRIPTION_LEN} characters or fewer."
        )
    return description or None, None


_EXPENSE_FIELDS = (
    ("amount", _parse_amount),
    ("category", _parse_category),
    ("date", _parse_expense_date),
    ("description", _parse_description),
)


def _validate_expense_form(form):
    """Return (values, error) for an add/edit expense form.

    values is {amount, category, date, description} when valid, else None;
    error is the first failing field's message, else None.
    """
    values = {}
    for name, parse in _EXPENSE_FIELDS:
        value, error = parse(form.get(name))
        if error:
            return None, error
        values[name] = value
    return values, None


def _render_expense_form(form, error=None, status=200,
                         template="add_expense.html", **context):
    """Render an add/edit expense form with the category list and today's date."""
    return render_template(
        template,
        categories=CATEGORIES,
        today=_today().isoformat(),
        form=form,
        error=error,
        **context,
    ), status


def _render_edit_form(form, expense_id, error=None, status=200):
    """Render edit_expense.html for expense_id."""
    return _render_expense_form(
        form, error, status,
        template="edit_expense.html",
        expense_id=expense_id,
    )


def _expense_form_values(expense):
    """A stored expense as form strings, shaped like request.form.

    The amount is a plain 2dp string for the number input — not display
    formatting, which goes through the inr filter.
    """
    return {
        "amount": f"{expense['amount']:.2f}",
        "category": expense["category"],
        "date": expense["date"],
        "description": expense["description"],
    }


# ------------------------------------------------------------------ #
# Profile: transaction history                                        #
# ------------------------------------------------------------------ #

def _profile_recent_expenses(user_id, start_date=None, end_date=None):
    """Recent expenses shaped for profile.html's recent_expenses."""
    return get_recent_transactions(
        user_id, start_date=start_date, end_date=end_date
    )


# ------------------------------------------------------------------ #
# Profile: summary stats                                              #
# ------------------------------------------------------------------ #

def _profile_stats(user_id, start_date=None, end_date=None):
    """Summary stats shaped for profile.html's stats."""
    return get_summary_stats(user_id, start_date=start_date, end_date=end_date)


# ------------------------------------------------------------------ #
# Profile: category breakdown                                         #
# ------------------------------------------------------------------ #

def _profile_category_breakdown(user_id, start_date=None, end_date=None):
    """Category totals shaped for profile.html's category_breakdown."""
    return [
        {"category": c["name"], "total": c["amount"], "percent": c["pct"]}
        for c in get_category_breakdown(
            user_id, start_date=start_date, end_date=end_date
        )
    ]


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    if session.get("user_id"):
        return redirect(url_for("profile"))
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("profile"))

    if request.method == "GET":
        return render_template("register.html")

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    error = None
    if not name or not email or not password.strip():
        error = "Name, email and password are all required."
    elif not _is_valid_email(email):
        error = "Please enter a valid email address."
    elif len(password) < 8:
        error = "Password must be at least 8 characters."
    elif get_user_by_email(email) is not None:
        error = "An account with that email already exists."
    elif create_user(name, email, password) is None:
        error = "An account with that email already exists."

    if error:
        return render_template(
            "register.html", error=error, name=name, email=email
        ), 400

    flash("Account created — please sign in", "success")
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("profile"))

    if request.method == "GET":
        return render_template("login.html")

    email_input = request.form.get("email", "").strip()
    email = email_input.lower()
    password = request.form.get("password", "")

    if not email or not password:
        return render_template(
            "login.html",
            error="Email and password are both required.",
            email=email_input,
        ), 400

    user = get_user_by_email(email)
    if user is None:
        check_password_hash(_DUMMY_PASSWORD_HASH, password)
        valid = False
    else:
        valid = check_password_hash(user["password_hash"], password)

    if not valid:
        return render_template(
            "login.html", error="Invalid email or password.", email=email_input
        ), 401

    session.clear()
    session["user_id"] = user["id"]
    session["user_name"] = user["name"]
    return redirect(url_for("profile"))


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been signed out", "success")
    return redirect(url_for("login"))


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/profile")
@login_required
def profile():
    user_id = session["user_id"]
    user = get_user_by_id(user_id)
    if user is None:
        session.clear()
        return redirect(url_for("login"))
    start_date, end_date, filter_error = _parse_date_range(request.args)
    return render_template(
        "profile.html",
        user={**user, "initials": _initials(user["name"])},
        stats=_profile_stats(user_id, start_date, end_date),
        recent_expenses=_profile_recent_expenses(user_id, start_date, end_date),
        category_breakdown=_profile_category_breakdown(
            user_id, start_date, end_date
        ),
        start_date=start_date,
        end_date=end_date,
        range_label=_range_label(start_date, end_date),
        presets=_date_presets(start_date, end_date),
        filter_error=filter_error,
    )


@app.route("/analytics")
@login_required
def analytics():
    return render_template("analytics.html")


@app.route("/expenses/add", methods=["GET", "POST"])
@login_required
def add_expense():
    if request.method == "GET":
        return _render_expense_form({"date": _today().isoformat()})

    _check_csrf()
    values, error = _validate_expense_form(request.form)
    if error:
        return _render_expense_form(request.form, error, 400)

    expense_id = create_expense(
        session["user_id"],
        values["amount"],
        values["category"],
        values["date"],
        values["description"],
    )
    if expense_id is None:
        # The account behind this session no longer exists.
        session.clear()
        flash("Please sign in again", "error")
        return redirect(url_for("login"))
    flash("Expense added", "success")
    return redirect(url_for("profile"))


@app.route("/expenses/<int:id>/edit", methods=["GET", "POST"])
@login_required
def edit_expense(id):
    user_id = session["user_id"]
    expense = get_expense(id, user_id)
    if expense is None:
        # Not found and not owned get the same response.
        abort(404)

    if request.method == "GET":
        return _render_edit_form(_expense_form_values(expense), id)

    _check_csrf()
    values, error = _validate_expense_form(request.form)
    if error:
        return _render_edit_form(request.form, id, error, 400)

    updated = update_expense(
        id,
        user_id,
        amount=values["amount"],
        category=values["category"],
        expense_date=values["date"],
        description=values["description"],
    )
    if not updated:
        # The expense was deleted after the ownership check above.
        abort(404)
    flash("Expense updated", "success")
    return redirect(url_for("profile"))


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", port=5001)
