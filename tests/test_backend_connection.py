from datetime import date

import pytest

import database.db as db
from database.queries import (
    get_category_breakdown,
    get_recent_transactions,
    get_summary_stats,
    get_user_by_id,
)

DEMO = {"email": "demo@spendly.com", "password": "demo123"}
SEED_TOTAL = sum(amount for _, amount, _ in db.SEED_EXPENSES)  # 5548.50


@pytest.fixture
def demo_id(app):
    return db.get_user_by_email(DEMO["email"])["id"]


@pytest.fixture
def empty_user_id(app):
    """A registered user with no expenses."""
    return db.create_user("New User", "new@spendly.com", "password123")


def add_expense(user_id, amount, category, expense_date, description=""):
    conn = db.get_db()
    try:
        conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, category, expense_date, description),
        )
        conn.commit()
    finally:
        conn.close()


def get_profile_html(client, credentials=DEMO):
    client.post("/login", data=credentials)
    resp = client.get("/profile")
    assert resp.status_code == 200
    return resp.get_data(as_text=True)


# ------------------------------------------------------------------ #
# get_user_by_id                                                      #
# ------------------------------------------------------------------ #

def test_get_user_by_id_returns_user(demo_id):
    user = get_user_by_id(demo_id)
    assert user == {
        "name": "Demo User",
        "email": "demo@spendly.com",
        "member_since": date.today().strftime("%B %Y"),
    }


def test_get_user_by_id_unknown_returns_none(app):
    assert get_user_by_id(99999) is None


# ------------------------------------------------------------------ #
# /profile route                                                      #
# ------------------------------------------------------------------ #

def test_profile_redirects_when_signed_out(client):
    resp = client.get("/profile")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/login")


def test_profile_shows_seed_user_from_db(client):
    html = get_profile_html(client)
    assert "Demo User" in html
    assert "demo@spendly.com" in html
    assert f"Member since {date.today().strftime('%B %Y')}" in html
    assert "₹" in html
    assert "$" not in html


def test_profile_new_user_sees_empty_profile(client, empty_user_id):
    html = get_profile_html(
        client, {"email": "new@spendly.com", "password": "password123"}
    )
    assert "New User" in html
    assert "new@spendly.com" in html
    assert "₹0.00" in html
    assert "No expenses yet" in html
    assert "prof-cat-row" not in html


def test_profile_stale_session_redirects_to_login(client, app):
    with client.session_transaction() as sess:
        sess["user_id"] = 99999
        sess["user_name"] = "Ghost"
    resp = client.get("/profile")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/login")
    with client.session_transaction() as sess:
        assert "user_id" not in sess


# ------------------------------------------------------------------ #
# Summary stats                                                       #
# ------------------------------------------------------------------ #

def test_summary_stats_demo_user(demo_id):
    stats = get_summary_stats(demo_id)
    assert stats["total_spent"] == pytest.approx(SEED_TOTAL)
    assert stats["total_spent"] == pytest.approx(5548.50)
    assert stats["transaction_count"] == 8
    assert stats["top_category"] == "Bills"


def test_summary_stats_empty_user(empty_user_id):
    assert get_summary_stats(empty_user_id) == {
        "total_spent": 0,
        "transaction_count": 0,
        "top_category": "—",
    }


def test_summary_stats_reflect_new_expenses(demo_id):
    add_expense(demo_id, 5000.00, "Food", date.today().isoformat(), "Feast")
    stats = get_summary_stats(demo_id)
    assert stats["total_spent"] == pytest.approx(SEED_TOTAL + 5000.00)
    assert stats["transaction_count"] == 9
    assert stats["top_category"] == "Food"


def test_summary_stats_isolated_per_user(demo_id, empty_user_id):
    before = get_summary_stats(demo_id)
    add_expense(empty_user_id, 99999.00, "Travel", date.today().isoformat())
    assert get_summary_stats(demo_id) == before
    other = get_summary_stats(empty_user_id)
    assert other["total_spent"] == pytest.approx(99999.00)
    assert other["transaction_count"] == 1
    assert other["top_category"] == "Travel"


def test_summary_stats_rendered_on_profile(client):
    html = get_profile_html(client)
    assert "₹5,548.50" in html
    assert "Bills" in html
    assert '<span class="prof-stat-value">8</span>' in html


# ------------------------------------------------------------------ #
# Transaction history                                                 #
# ------------------------------------------------------------------ #

def test_recent_transactions_demo_returns_seed_rows_newest_first(demo_id):
    rows = get_recent_transactions(demo_id)
    assert len(rows) == len(db.SEED_EXPENSES) == 8
    for row in rows:
        assert isinstance(row, dict)
        assert set(row) == {"id", "date", "description", "category", "amount"}
    dates = [row["date"] for row in rows]
    assert dates == sorted(dates, reverse=True)


def test_recent_transactions_respects_limit(demo_id):
    assert len(get_recent_transactions(demo_id, limit=3)) == 3


def test_recent_transactions_same_date_newer_id_first(demo_id):
    add_expense(demo_id, 10.00, "Food", "2099-01-01", "First added")
    add_expense(demo_id, 20.00, "Food", "2099-01-01", "Second added")
    rows = get_recent_transactions(demo_id, limit=2)
    assert [row["description"] for row in rows] == ["Second added", "First added"]


def test_recent_transactions_empty_user_returns_empty_list(empty_user_id):
    assert get_recent_transactions(empty_user_id) == []


def test_recent_transactions_isolated_per_user(demo_id, empty_user_id):
    add_expense(empty_user_id, 99.00, "Other", "2099-06-01", "New user only")
    add_expense(demo_id, 77.00, "Other", "2099-06-02", "Demo only")
    demo_desc = [row["description"] for row in get_recent_transactions(demo_id)]
    new_rows = get_recent_transactions(empty_user_id)
    assert "New user only" not in demo_desc
    assert "Demo only" in demo_desc
    assert [row["description"] for row in new_rows] == ["New user only"]


def test_recent_transactions_route_renders_rows_newest_first(client, demo_id):
    html = get_profile_html(client)
    assert html.count('class="prof-tx-row"') == 8
    dates = sorted(
        {row["date"] for row in get_recent_transactions(demo_id)}, reverse=True
    )
    positions = [html.index(f'<td class="prof-date">{d}</td>') for d in dates]
    assert positions == sorted(positions)


# ------------------------------------------------------------------ #
# Category breakdown                                                  #
# ------------------------------------------------------------------ #

def test_category_breakdown_demo_user(demo_id):
    breakdown = get_category_breakdown(demo_id)
    assert len(breakdown) == 7
    assert {c["name"] for c in breakdown} == set(db.CATEGORIES)
    amounts = [c["amount"] for c in breakdown]
    assert amounts == sorted(amounts, reverse=True)
    assert breakdown[0]["name"] == "Bills"
    assert breakdown[0]["amount"] == 1850.0
    food = next(c for c in breakdown if c["name"] == "Food")
    assert food["amount"] == 770.5
    assert all(isinstance(c["pct"], int) for c in breakdown)
    assert sum(c["pct"] for c in breakdown) == 100


def test_category_breakdown_rounding_remainder_goes_to_largest(empty_user_id):
    for category in ("Food", "Bills", "Health"):
        add_expense(empty_user_id, 100.0, category, "2026-01-01")
    breakdown = get_category_breakdown(empty_user_id)
    assert len(breakdown) == 3
    assert sum(c["pct"] for c in breakdown) == 100
    assert breakdown[0]["pct"] == 34
    assert [c["pct"] for c in breakdown[1:]] == [33, 33]


def test_category_breakdown_empty_user(empty_user_id):
    assert get_category_breakdown(empty_user_id) == []


def test_category_breakdown_isolated_per_user(demo_id, empty_user_id):
    add_expense(empty_user_id, 50.0, "Shopping", "2026-01-01")
    breakdown = get_category_breakdown(empty_user_id)
    assert breakdown == [{"name": "Shopping", "amount": 50.0, "pct": 100}]
    assert len(get_category_breakdown(demo_id)) == 7


def test_category_breakdown_route_renders_demo_rows(client):
    html = get_profile_html(client)
    assert html.count('class="prof-cat-row"') == 7
    for category in db.CATEGORIES:
        assert f'<span class="prof-cat-name">{category}</span>' in html
    assert 'style="width: 33%"' in html
