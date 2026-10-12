import importlib
import re
from datetime import date

import pytest

import database.db as db
from database.queries import (
    get_category_breakdown,
    get_recent_transactions,
    get_summary_stats,
)

DEMO = {"email": "demo@spendly.com", "password": "demo123"}
NEW = {"email": "new@spendly.com", "password": "password123"}
OTHER = {"email": "other@spendly.com", "password": "password123"}
EMPTY_STATS = {"total_spent": 0, "transaction_count": 0, "top_category": "—"}


# ------------------------------------------------------------------ #
# Fixtures and helpers                                                #
# ------------------------------------------------------------------ #

@pytest.fixture
def app_module(app):
    return importlib.import_module("app")


@pytest.fixture
def demo_id(app):
    return db.get_user_by_email(DEMO["email"])["id"]


@pytest.fixture
def empty_user_id(app):
    """A registered user with no expenses."""
    return db.create_user("New User", NEW["email"], NEW["password"])


@pytest.fixture
def other_user_id(app):
    """A second registered user, used to check data isolation."""
    return db.create_user("Other User", OTHER["email"], OTHER["password"])


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


def login(client, credentials):
    resp = client.post("/login", data=credentials)
    assert resp.status_code == 302, "Login should redirect on success"


def get_html(client, query=""):
    resp = client.get("/profile" + query)
    assert resp.status_code == 200, f"GET /profile{query} should return 200"
    return resp.get_data(as_text=True)


def row_count(html):
    return html.count('class="prof-tx-row"')


@pytest.fixture
def filter_user(empty_user_id):
    """New user with fixed-date (2020) expenses spanning several days."""
    add_expense(empty_user_id, 100.00, "Food", "2020-01-10", "jan10")
    add_expense(empty_user_id, 200.00, "Bills", "2020-01-15", "jan15")
    add_expense(empty_user_id, 300.00, "Food", "2020-01-20", "jan20")
    add_expense(empty_user_id, 400.00, "Travel", "2020-02-05", "feb05")
    return empty_user_id


# ------------------------------------------------------------------ #
# get_summary_stats with a range                                      #
# ------------------------------------------------------------------ #

def test_summary_stats_range_limits_to_matching_rows(filter_user):
    stats = get_summary_stats(
        filter_user, start_date="2020-01-12", end_date="2020-02-01"
    )
    assert stats["total_spent"] == pytest.approx(500.00)
    assert stats["transaction_count"] == 2
    assert stats["top_category"] == "Food"


def test_summary_stats_top_category_reflects_range(filter_user):
    ranged = get_summary_stats(
        filter_user, start_date="2020-01-15", end_date="2020-01-15"
    )
    assert ranged["top_category"] == "Bills"


def test_summary_stats_no_match_returns_empty_values(filter_user):
    stats = get_summary_stats(
        filter_user, start_date="2021-01-01", end_date="2021-12-31"
    )
    assert stats == EMPTY_STATS


def test_summary_stats_bounds_are_inclusive(filter_user):
    stats = get_summary_stats(
        filter_user, start_date="2020-01-10", end_date="2020-01-20"
    )
    assert stats["transaction_count"] == 3, "Rows on start and end must count"
    assert stats["total_spent"] == pytest.approx(600.00)


def test_summary_stats_one_day_outside_bounds_excluded(filter_user):
    stats = get_summary_stats(
        filter_user, start_date="2020-01-11", end_date="2020-01-19"
    )
    assert stats["transaction_count"] == 1
    assert stats["total_spent"] == pytest.approx(200.00)


def test_summary_stats_start_only(filter_user):
    stats = get_summary_stats(filter_user, start_date="2020-01-20")
    assert stats["transaction_count"] == 2
    assert stats["total_spent"] == pytest.approx(700.00)


def test_summary_stats_end_only(filter_user):
    stats = get_summary_stats(filter_user, end_date="2020-01-15")
    assert stats["transaction_count"] == 2
    assert stats["total_spent"] == pytest.approx(300.00)


def test_summary_stats_no_args_unchanged(filter_user):
    stats = get_summary_stats(filter_user)
    assert stats["transaction_count"] == 4
    assert stats["total_spent"] == pytest.approx(1000.00)


def test_summary_stats_no_args_demo_user_unchanged(demo_id):
    stats = get_summary_stats(demo_id)
    assert stats["total_spent"] == pytest.approx(5548.50)
    assert stats["transaction_count"] == 8
    assert stats["top_category"] == "Bills"


def test_summary_stats_range_ignores_other_users(filter_user, other_user_id):
    add_expense(other_user_id, 9999.00, "Shopping", "2020-01-15")
    stats = get_summary_stats(
        filter_user, start_date="2020-01-01", end_date="2020-12-31"
    )
    assert stats["total_spent"] == pytest.approx(1000.00)
    assert stats["transaction_count"] == 4


# ------------------------------------------------------------------ #
# get_recent_transactions with a range                                #
# ------------------------------------------------------------------ #

def test_recent_transactions_range_limits_rows(filter_user):
    rows = get_recent_transactions(
        filter_user, start_date="2020-01-12", end_date="2020-02-01"
    )
    assert [r["description"] for r in rows] == ["jan20", "jan15"]


def test_recent_transactions_range_is_newest_first(filter_user):
    rows = get_recent_transactions(
        filter_user, start_date="2020-01-01", end_date="2020-12-31"
    )
    dates = [r["date"] for r in rows]
    assert dates == sorted(dates, reverse=True)
    assert len(rows) == 4


def test_recent_transactions_row_shape(filter_user):
    rows = get_recent_transactions(
        filter_user, start_date="2020-02-05", end_date="2020-02-05"
    )
    assert len(rows) == 1
    row = rows[0]
    for key in ("date", "description", "category", "amount"):
        assert key in row, f"Missing key {key}"
    assert row["category"] == "Travel"
    assert row["amount"] == pytest.approx(400.00)


def test_recent_transactions_bounds_inclusive(filter_user):
    rows = get_recent_transactions(
        filter_user, start_date="2020-01-10", end_date="2020-01-20"
    )
    assert {r["description"] for r in rows} == {"jan10", "jan15", "jan20"}


def test_recent_transactions_excludes_day_before_and_after(filter_user):
    rows = get_recent_transactions(
        filter_user, start_date="2020-01-11", end_date="2020-01-19"
    )
    assert [r["description"] for r in rows] == ["jan15"]


def test_recent_transactions_start_only(filter_user):
    rows = get_recent_transactions(filter_user, start_date="2020-01-20")
    assert [r["description"] for r in rows] == ["feb05", "jan20"]


def test_recent_transactions_end_only(filter_user):
    rows = get_recent_transactions(filter_user, end_date="2020-01-15")
    assert [r["description"] for r in rows] == ["jan15", "jan10"]


def test_recent_transactions_limit_respected_with_range(filter_user):
    rows = get_recent_transactions(
        filter_user, limit=2, start_date="2020-01-01", end_date="2020-12-31"
    )
    assert len(rows) == 2
    assert [r["description"] for r in rows] == ["feb05", "jan20"]


def test_recent_transactions_no_match_returns_empty_list(filter_user):
    rows = get_recent_transactions(
        filter_user, start_date="2021-01-01", end_date="2021-01-31"
    )
    assert rows == []


def test_recent_transactions_no_args_unchanged(demo_id):
    rows = get_recent_transactions(demo_id)
    assert len(rows) == 8
    dates = [r["date"] for r in rows]
    assert dates == sorted(dates, reverse=True)


def test_recent_transactions_range_ignores_other_users(
    filter_user, other_user_id
):
    add_expense(other_user_id, 1.00, "Other", "2020-01-15", "theirs")
    rows = get_recent_transactions(
        filter_user, start_date="2020-01-01", end_date="2020-12-31"
    )
    assert "theirs" not in [r["description"] for r in rows]


# ------------------------------------------------------------------ #
# get_category_breakdown with a range                                 #
# ------------------------------------------------------------------ #

def test_category_breakdown_range_limits_categories(filter_user):
    result = get_category_breakdown(
        filter_user, start_date="2020-01-12", end_date="2020-01-31"
    )
    by_name = {c["name"]: c for c in result}
    assert set(by_name) == {"Bills", "Food"}
    assert by_name["Bills"]["amount"] == pytest.approx(200.00)
    assert by_name["Food"]["amount"] == pytest.approx(300.00)


def test_category_breakdown_sorted_amount_desc(filter_user):
    result = get_category_breakdown(
        filter_user, start_date="2020-01-01", end_date="2020-12-31"
    )
    amounts = [c["amount"] for c in result]
    assert amounts == sorted(amounts, reverse=True)


def test_category_breakdown_pct_sums_to_100_for_range(filter_user):
    result = get_category_breakdown(
        filter_user, start_date="2020-01-01", end_date="2020-12-31"
    )
    assert all(isinstance(c["pct"], int) for c in result)
    assert sum(c["pct"] for c in result) == 100


def test_category_breakdown_three_equal_amounts_sum_to_100(empty_user_id):
    for cat in ("Food", "Bills", "Travel"):
        add_expense(empty_user_id, 100.00, cat, "2020-03-01")
    result = get_category_breakdown(
        empty_user_id, start_date="2020-03-01", end_date="2020-03-31"
    )
    assert len(result) == 3
    assert sum(c["pct"] for c in result) == 100


def test_category_breakdown_no_match_returns_empty_list(filter_user):
    result = get_category_breakdown(
        filter_user, start_date="2021-01-01", end_date="2021-12-31"
    )
    assert result == []


def test_category_breakdown_bounds_inclusive(filter_user):
    result = get_category_breakdown(
        filter_user, start_date="2020-01-15", end_date="2020-01-15"
    )
    assert [c["name"] for c in result] == ["Bills"]
    assert result[0]["pct"] == 100


def test_category_breakdown_start_only(filter_user):
    result = get_category_breakdown(filter_user, start_date="2020-02-01")
    assert [c["name"] for c in result] == ["Travel"]


def test_category_breakdown_end_only(filter_user):
    result = get_category_breakdown(filter_user, end_date="2020-01-10")
    assert [c["name"] for c in result] == ["Food"]


def test_category_breakdown_no_args_demo_user_unchanged(demo_id):
    result = get_category_breakdown(demo_id)
    assert result[0]["name"] == "Bills"
    assert sum(c["pct"] for c in result) == 100


def test_category_breakdown_range_ignores_other_users(
    filter_user, other_user_id
):
    add_expense(other_user_id, 5000.00, "Shopping", "2020-01-15")
    result = get_category_breakdown(
        filter_user, start_date="2020-01-01", end_date="2020-12-31"
    )
    assert "Shopping" not in [c["name"] for c in result]


# ------------------------------------------------------------------ #
# _parse_date_range                                                   #
# ------------------------------------------------------------------ #

def test_parse_date_range_valid_both(app_module):
    start, end, error = app_module._parse_date_range(
        {"start_date": "2026-10-01", "end_date": "2026-10-12"}
    )
    assert (start, end) == ("2026-10-01", "2026-10-12")
    assert not error


def test_parse_date_range_same_day_is_valid(app_module):
    start, end, error = app_module._parse_date_range(
        {"start_date": "2026-10-01", "end_date": "2026-10-01"}
    )
    assert (start, end) == ("2026-10-01", "2026-10-01")
    assert not error


@pytest.mark.parametrize("args, expected", [
    ({}, (None, None)),
    ({"start_date": "", "end_date": ""}, (None, None)),
    ({"start_date": "2026-10-01"}, ("2026-10-01", None)),
    ({"end_date": "2026-10-12"}, (None, "2026-10-12")),
    ({"start_date": "2026-10-01", "end_date": ""}, ("2026-10-01", None)),
    ({"start_date": "", "end_date": "2026-10-12"}, (None, "2026-10-12")),
])
def test_parse_date_range_missing_or_empty_is_open(app_module, args, expected):
    start, end, error = app_module._parse_date_range(args)
    assert (start, end) == expected
    assert not error


@pytest.mark.parametrize("bad", [
    "abc", "2026-13-01", "2026-02-30", "20261012", "2026-W41-1",
])
@pytest.mark.parametrize("key", ["start_date", "end_date"])
def test_parse_date_range_invalid_value_returns_error(app_module, key, bad):
    start, end, error = app_module._parse_date_range({key: bad})
    assert (start, end) == (None, None)
    assert error, "Expected a non-empty error message"


def test_parse_date_range_invalid_with_valid_other_side(app_module):
    start, end, error = app_module._parse_date_range(
        {"start_date": "abc", "end_date": "2026-10-12"}
    )
    assert (start, end) == (None, None)
    assert error


def test_parse_date_range_start_after_end_returns_error(app_module):
    start, end, error = app_module._parse_date_range(
        {"start_date": "2026-10-12", "end_date": "2026-10-01"}
    )
    assert (start, end) == (None, None)
    assert error


# ------------------------------------------------------------------ #
# _date_presets                                                       #
# ------------------------------------------------------------------ #

def presets_by_label(app_module, start, end, today):
    presets = app_module._date_presets(start, end, today=today)
    return {p["label"]: p for p in presets}


def test_date_presets_returns_four_in_order(app_module):
    presets = app_module._date_presets(None, None, today=date(2026, 10, 12))
    assert [p["label"] for p in presets] == [
        "This month", "Last month", "Last 3 months", "All time",
    ]
    for p in presets:
        for key in ("label", "start_date", "end_date", "active"):
            assert key in p


@pytest.mark.parametrize("today, expected", [
    (date(2026, 10, 12), {
        "This month": ("2026-10-01", "2026-10-12"),
        "Last month": ("2026-09-01", "2026-09-30"),
        "Last 3 months": ("2026-08-01", "2026-10-12"),
        "All time": (None, None),
    }),
    (date(2026, 1, 15), {
        "This month": ("2026-01-01", "2026-01-15"),
        "Last month": ("2025-12-01", "2025-12-31"),
        "Last 3 months": ("2025-11-01", "2026-01-15"),
        "All time": (None, None),
    }),
    (date(2026, 2, 10), {
        "This month": ("2026-02-01", "2026-02-10"),
        "Last month": ("2026-01-01", "2026-01-31"),
        "Last 3 months": ("2025-12-01", "2026-02-10"),
        "All time": (None, None),
    }),
    (date(2028, 3, 10), {
        "This month": ("2028-03-01", "2028-03-10"),
        "Last month": ("2028-02-01", "2028-02-29"),
        "Last 3 months": ("2028-01-01", "2028-03-10"),
        "All time": (None, None),
    }),
])
def test_date_presets_ranges(app_module, today, expected):
    result = presets_by_label(app_module, None, None, today)
    for label, (start, end) in expected.items():
        assert (result[label]["start_date"], result[label]["end_date"]) == (
            start, end
        ), f"Wrong range for {label} on {today}"


def test_date_presets_all_time_active_when_no_filter(app_module):
    result = presets_by_label(app_module, None, None, date(2026, 10, 12))
    assert result["All time"]["active"]
    assert not any(
        p["active"] for l, p in result.items() if l != "All time"
    )


@pytest.mark.parametrize("label, start, end", [
    ("This month", "2026-10-01", "2026-10-12"),
    ("Last month", "2026-09-01", "2026-09-30"),
    ("Last 3 months", "2026-08-01", "2026-10-12"),
])
def test_date_presets_matching_range_is_only_active(
    app_module, label, start, end
):
    result = presets_by_label(app_module, start, end, date(2026, 10, 12))
    assert result[label]["active"]
    assert sum(1 for p in result.values() if p["active"]) == 1


def test_date_presets_custom_range_has_no_active(app_module):
    result = presets_by_label(
        app_module, "2026-10-03", "2026-10-05", date(2026, 10, 12)
    )
    assert not any(p["active"] for p in result.values())


def test_date_presets_one_sided_range_has_no_active(app_module):
    result = presets_by_label(app_module, "2026-10-01", None, date(2026, 10, 12))
    assert not any(p["active"] for p in result.values())


# ------------------------------------------------------------------ #
# _range_label and _today                                             #
# ------------------------------------------------------------------ #

@pytest.mark.parametrize("start, end, expected", [
    ("2026-10-01", "2026-10-12", "Showing 1 Oct 2026 – 12 Oct 2026"),
    ("2026-10-01", None, "Showing from 1 Oct 2026"),
    (None, "2026-10-12", "Showing up to 12 Oct 2026"),
    (None, None, "Showing all time"),
])
def test_range_label_formats(app_module, start, end, expected):
    assert app_module._range_label(start, end) == expected


def test_today_returns_current_date(app_module):
    assert app_module._today() == date.today()


# ------------------------------------------------------------------ #
# GET /profile - auth guard                                           #
# ------------------------------------------------------------------ #

@pytest.mark.parametrize("query", [
    "?start_date=2026-10-01",
    "?start_date=2026-10-01&end_date=2026-10-12",
    "?start_date=abc",
])
def test_profile_with_params_redirects_when_signed_out(client, query):
    resp = client.get("/profile" + query)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/login")


# ------------------------------------------------------------------ #
# GET /profile - unfiltered                                           #
# ------------------------------------------------------------------ #

def test_profile_no_params_shows_step5_data(client):
    login(client, DEMO)
    html = get_html(client)
    assert row_count(html) == 8
    assert "₹5,548.50" in html
    assert "Bills" in html


def test_profile_no_params_shows_all_time_label(client):
    login(client, DEMO)
    html = get_html(client)
    assert "Showing all time" in html


def test_profile_no_params_all_time_preset_is_current(client):
    login(client, DEMO)
    html = get_html(client)
    assert html.count('aria-current="true"') == 1
    assert re.search(
        r'<a[^>]*aria-current="true"[^>]*>\s*All time\s*</a>', html
    ), "All time preset should carry aria-current"


def test_profile_no_params_has_no_clear_link(client):
    login(client, DEMO)
    html = get_html(client)
    assert 'class="prof-filter-clear"' not in html


def test_profile_no_params_shows_filter_form_and_presets(client):
    login(client, DEMO)
    html = get_html(client)
    assert 'name="start_date"' in html
    assert 'name="end_date"' in html
    assert html.count('type="date"') == 2
    assert "Apply" in html
    for label in ("This month", "Last month", "Last 3 months", "All time"):
        assert label in html, f"Missing preset {label}"


def test_profile_empty_user_unfiltered_keeps_step5_wording(
    client, empty_user_id
):
    login(client, NEW)
    html = get_html(client)
    assert "No expenses yet" in html
    assert "No expenses in this period" not in html
    assert "₹0.00" in html


# ------------------------------------------------------------------ #
# GET /profile - filtered                                             #
# ------------------------------------------------------------------ #

def test_profile_filtered_limits_stats_rows_and_breakdown(client, filter_user):
    login(client, NEW)
    html = get_html(client, "?start_date=2020-01-12&end_date=2020-02-01")
    assert row_count(html) == 2
    assert "jan20" in html and "jan15" in html
    assert "jan10" not in html and "feb05" not in html
    assert "₹500.00" in html
    assert '<span class="prof-stat-value">2</span>' in html
    assert html.count('class="prof-cat-row"') == 2
    assert "Travel" not in html


def test_profile_filtered_inclusive_bounds(client, filter_user):
    login(client, NEW)
    html = get_html(client, "?start_date=2020-01-10&end_date=2020-01-20")
    assert row_count(html) == 3
    assert "₹600.00" in html


def test_profile_filtered_excludes_one_day_outside(client, filter_user):
    login(client, NEW)
    html = get_html(client, "?start_date=2020-01-11&end_date=2020-01-19")
    assert row_count(html) == 1
    assert "jan15" in html


def test_profile_start_date_only(client, filter_user):
    login(client, NEW)
    html = get_html(client, "?start_date=2020-01-20")
    assert row_count(html) == 2
    assert "₹700.00" in html
    assert "Showing from 20 Jan 2020" in html


def test_profile_end_date_only(client, filter_user):
    login(client, NEW)
    html = get_html(client, "?end_date=2020-01-15")
    assert row_count(html) == 2
    assert "₹300.00" in html
    assert "Showing up to 15 Jan 2020" in html


def test_profile_filtered_inputs_prefilled(client, filter_user):
    login(client, NEW)
    html = get_html(client, "?start_date=2020-01-10&end_date=2020-01-20")
    assert re.search(
        r'<input[^>]*name="start_date"[^>]*value="2020-01-10"', html
    ) or re.search(
        r'<input[^>]*value="2020-01-10"[^>]*name="start_date"', html
    ), "start_date input should be pre-filled"
    assert re.search(
        r'<input[^>]*name="end_date"[^>]*value="2020-01-20"', html
    ) or re.search(
        r'<input[^>]*value="2020-01-20"[^>]*name="end_date"', html
    ), "end_date input should be pre-filled"


def test_profile_filtered_shows_clear_link(client, filter_user):
    login(client, NEW)
    html = get_html(client, "?start_date=2020-01-10&end_date=2020-01-20")
    assert 'class="prof-filter-clear"' in html
    assert "Clear" in html


def test_profile_filtered_shows_range_label(client, filter_user):
    login(client, NEW)
    html = get_html(client, "?start_date=2020-01-10&end_date=2020-01-20")
    assert "Showing 10 Jan 2020 – 20 Jan 2020" in html
    assert "Showing all time" not in html


def test_profile_filtered_user_details_not_filtered(client, filter_user):
    login(client, NEW)
    html = get_html(client, "?start_date=2021-01-01&end_date=2021-01-31")
    assert "New User" in html
    assert "new@spendly.com" in html


def test_profile_filtered_top_category_reflects_range(client, filter_user):
    login(client, NEW)
    html = get_html(client, "?start_date=2020-01-15&end_date=2020-01-15")
    assert "Bills" in html
    assert "Food" not in html


def test_profile_filtered_amounts_use_indian_grouping(client, empty_user_id):
    add_expense(empty_user_id, 123456.50, "Rent", "2020-05-05", "big")
    login(client, NEW)
    html = get_html(client, "?start_date=2020-05-01&end_date=2020-05-31")
    assert "₹1,23,456.50" in html


def test_profile_filtered_sql_injection_is_rejected_safely(client, filter_user):
    login(client, NEW)
    html = get_html(client, "?start_date=2020-01-01'%20OR%20'1'='1")
    assert "auth-error" in html
    assert row_count(html) == 4


# ------------------------------------------------------------------ #
# GET /profile - presets (deterministic via _today)                   #
# ------------------------------------------------------------------ #

def test_profile_preset_links_use_escaped_ampersand(
    client, app_module, monkeypatch
):
    monkeypatch.setattr(app_module, "_today", lambda: date(2026, 10, 12))
    login(client, DEMO)
    html = get_html(client)
    assert "start_date=2026-10-01&amp;end_date=2026-10-12" in html
    assert "start_date=2026-09-01&amp;end_date=2026-09-30" in html
    assert "start_date=2026-08-01&amp;end_date=2026-10-12" in html


def test_profile_this_month_preset_active_when_range_matches(
    client, app_module, monkeypatch
):
    monkeypatch.setattr(app_module, "_today", lambda: date(2026, 10, 12))
    login(client, DEMO)
    html = get_html(client, "?start_date=2026-10-01&end_date=2026-10-12")
    assert html.count('aria-current="true"') == 1
    assert re.search(
        r'<a[^>]*aria-current="true"[^>]*>\s*This month\s*</a>', html
    )
    assert "Showing 1 Oct 2026 – 12 Oct 2026" in html


def test_profile_last_month_preset_active_when_range_matches(
    client, app_module, monkeypatch
):
    monkeypatch.setattr(app_module, "_today", lambda: date(2026, 10, 12))
    login(client, DEMO)
    html = get_html(client, "?start_date=2026-09-01&end_date=2026-09-30")
    assert re.search(
        r'<a[^>]*aria-current="true"[^>]*>\s*Last month\s*</a>', html
    )


def test_profile_custom_range_has_no_active_preset(
    client, app_module, monkeypatch
):
    monkeypatch.setattr(app_module, "_today", lambda: date(2026, 10, 12))
    login(client, DEMO)
    html = get_html(client, "?start_date=2020-01-01&end_date=2020-01-02")
    assert 'aria-current="true"' not in html


# ------------------------------------------------------------------ #
# GET /profile - invalid input                                        #
# ------------------------------------------------------------------ #

@pytest.mark.parametrize("query", [
    "?start_date=abc",
    "?end_date=abc",
    "?start_date=2026-13-01",
    "?start_date=2026-02-30&end_date=2026-03-01",
    "?start_date=20261012",
    "?start_date=2026-10-12&end_date=2026-10-01",
])
def test_profile_invalid_range_shows_error_and_all_time_data(client, query):
    login(client, DEMO)
    html = get_html(client, query)
    assert "auth-error" in html, "Expected inline error message"
    assert row_count(html) == 8
    assert "₹5,548.50" in html
    assert "Showing all time" in html


@pytest.mark.parametrize("query", [
    "?start_date=abc",
    "?start_date=2026-10-12&end_date=2026-10-01",
])
def test_profile_invalid_range_has_no_clear_link(client, query):
    login(client, DEMO)
    html = get_html(client, query)
    assert 'class="prof-filter-clear"' not in html


def test_profile_valid_range_has_no_error(client, filter_user):
    login(client, NEW)
    html = get_html(client, "?start_date=2020-01-10&end_date=2020-01-20")
    assert "auth-error" not in html


def test_profile_no_params_has_no_error(client):
    login(client, DEMO)
    html = get_html(client)
    assert "auth-error" not in html


# ------------------------------------------------------------------ #
# GET /profile - empty filtered range                                 #
# ------------------------------------------------------------------ #

def test_profile_filtered_empty_range_shows_period_wording(client, filter_user):
    login(client, NEW)
    html = get_html(client, "?start_date=2021-01-01&end_date=2021-12-31")
    assert "₹0.00" in html
    assert "No expenses in this period" in html
    assert "No spending in this period" in html
    assert "No expenses yet" not in html
    assert row_count(html) == 0
    assert '<span class="prof-stat-value">0</span>' in html
    assert "prof-cat-row" not in html
    assert "—" in html


def test_profile_filtered_empty_range_still_shows_clear_link(
    client, filter_user
):
    login(client, NEW)
    html = get_html(client, "?start_date=2021-01-01&end_date=2021-12-31")
    assert 'class="prof-filter-clear"' in html


def test_profile_filtered_empty_user_shows_period_wording(
    client, empty_user_id
):
    login(client, NEW)
    html = get_html(client, "?start_date=2020-01-01&end_date=2020-01-31")
    assert "No expenses in this period" in html


# ------------------------------------------------------------------ #
# GET /profile - data isolation                                       #
# ------------------------------------------------------------------ #

@pytest.mark.parametrize("query", [
    "",
    "?start_date=2020-01-01&end_date=2020-12-31",
    "?start_date=2020-01-15",
    "?end_date=2020-01-15",
    "?start_date=2020-01-15&end_date=2020-01-15",
])
def test_profile_never_shows_other_users_expenses(
    client, filter_user, other_user_id, query
):
    add_expense(other_user_id, 77777.00, "Secret", "2020-01-15", "theirs-only")
    login(client, NEW)
    html = get_html(client, query)
    assert "theirs-only" not in html
    assert "Secret" not in html
    assert "77,777.00" not in html


def test_profile_other_user_sees_only_own_filtered_data(
    client, filter_user, other_user_id
):
    add_expense(other_user_id, 55.00, "Gifts", "2020-01-15", "mine")
    login(client, OTHER)
    html = get_html(client, "?start_date=2020-01-01&end_date=2020-12-31")
    assert row_count(html) == 1
    assert "mine" in html
    assert "jan15" not in html
    assert "₹55.00" in html
