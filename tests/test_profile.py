import pytest
from flask import render_template

import database.db as db

DEMO = {"email": "demo@spendly.com", "password": "demo123"}


def login(client):
    return client.post("/login", data=DEMO)


def get_profile_html(client):
    login(client)
    resp = client.get("/profile")
    assert resp.status_code == 200
    return resp.get_data(as_text=True)


def test_profile_redirects_when_signed_out(client):
    resp = client.get("/profile")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/login")


def test_profile_renders_for_signed_in_user(client):
    html = get_profile_html(client)
    assert "Demo User" in html
    assert ">DU<" in html
    assert "Member since" in html
    assert "coming in Step 4" not in html
    assert "css/profile.css" in html


def test_profile_shows_amounts_in_inr(client):
    html = get_profile_html(client)
    assert "₹5,548.50" in html
    assert "$" not in html


def test_profile_lists_recent_transactions(client):
    html = get_profile_html(client)
    assert html.count('class="prof-tx-row"') == 8


def test_profile_shows_category_breakdown(client):
    html = get_profile_html(client)
    assert html.count('class="prof-cat-row"') == len(db.CATEGORIES)
    for category in db.CATEGORIES:
        assert f'<span class="prof-cat-name">{category}</span>' in html
    assert 'style="width: 33%"' in html


def test_navbar_links_to_profile_when_signed_in(client):
    html = get_profile_html(client)
    assert 'href="/profile" class="nav-user"' in html


def test_signed_in_user_is_redirected_from_landing(client):
    login(client)
    resp = client.get("/")
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/profile"


def test_landing_renders_when_signed_out(client):
    assert client.get("/").status_code == 200


def test_profile_empty_state(app):
    context = {
        "user": {"name": "New User", "email": "new@spendly.com",
                 "member_since": "October 2026", "initials": "NU"},
        "stats": {"total_spent": 0, "transaction_count": 0, "top_category": "—"},
        "recent_expenses": [],
        "category_breakdown": [],
    }
    with app.test_request_context("/profile"):
        html = render_template("profile.html", **context)
    assert "No expenses yet" in html
    assert "<table" not in html
    assert "prof-bar-track" not in html
    assert "₹0.00" in html


@pytest.mark.parametrize(
    "amount, expected",
    [
        (0, "₹0.00"),
        (999.5, "₹999.50"),
        (1234, "₹1,234.00"),
        (123456.5, "₹1,23,456.50"),
        (12345678, "₹1,23,45,678.00"),
        (-1850, "-₹1,850.00"),
    ],
)
def test_inr_filter(app, amount, expected):
    assert app.jinja_env.filters["inr"](amount) == expected
