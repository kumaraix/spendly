import os
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
# Profile: transaction history                                        #
# ------------------------------------------------------------------ #

def _profile_recent_expenses(user_id):
    """Recent expenses shaped for profile.html's recent_expenses."""
    return get_recent_transactions(user_id)


# ------------------------------------------------------------------ #
# Profile: summary stats                                              #
# ------------------------------------------------------------------ #

def _profile_stats(user_id):
    """Summary stats shaped for profile.html's stats."""
    return get_summary_stats(user_id)


# ------------------------------------------------------------------ #
# Profile: category breakdown                                         #
# ------------------------------------------------------------------ #

def _profile_category_breakdown(user_id):
    """Category totals shaped for profile.html's category_breakdown."""
    return [
        {"category": c["name"], "total": c["amount"], "percent": c["pct"]}
        for c in get_category_breakdown(user_id)
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
    return render_template(
        "profile.html",
        user={**user, "initials": _initials(user["name"])},
        stats=_profile_stats(user_id),
        recent_expenses=_profile_recent_expenses(user_id),
        category_breakdown=_profile_category_breakdown(user_id),
    )


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
