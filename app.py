import os
from datetime import date, timedelta
from functools import wraps

from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from database.db import create_user, get_user_by_email, init_db, seed_db
from database.queries import (
    get_category_breakdown,
    get_recent_transactions,
    get_summary_stats,
    get_user_by_id,
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-insecure-secret-key")
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

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


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #


@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)
