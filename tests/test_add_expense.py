import importlib
import re
from datetime import date

import pytest

import database.db as db

DEMO = {"email": "demo@spendly.com", "password": "demo123"}
NEW = {"email": "new@spendly.com", "password": "password123"}
TODAY = date(2026, 10, 12)
TODAY_S = TODAY.isoformat()
CSRF = "test-csrf-token"
# Deliberately duplicated from db.CATEGORIES: pins the list the spec requires.
CATEGORIES = [
    "Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other",
]


# ------------------------------------------------------------------ #
# Fixtures and helpers                                                #
# ------------------------------------------------------------------ #

@pytest.fixture
def app_module(app, monkeypatch):
    module = importlib.import_module("app")
    monkeypatch.setattr(module, "_today", lambda: TODAY)
    return module


@pytest.fixture
def client(app_module):
    return app_module.app.test_client()


@pytest.fixture
def new_user_id(app):
    """A registered user with no expenses."""
    return db.create_user("New User", NEW["email"], NEW["password"])


@pytest.fixture
def auth_client(client, new_user_id):
    resp = client.post("/login", data=NEW)
    assert resp.status_code == 302, "Login should redirect on success"
    with client.session_transaction() as sess:
        sess["csrf_token"] = CSRF
    return client


def fetch_expenses():
    conn = db.get_db()
    try:
        return conn.execute(
            "SELECT * FROM expenses ORDER BY id"
        ).fetchall()
    finally:
        conn.close()


def expense_count():
    return len(fetch_expenses())


def valid_form(**overrides):
    form = {
        "amount": "250",
        "category": "Food",
        "date": TODAY_S,
        "description": "Lunch",
        "csrf_token": CSRF,
    }
    form.update(overrides)
    return form


# ------------------------------------------------------------------ #
# db.create_expense                                                   #
# ------------------------------------------------------------------ #

class TestCreateExpense:
    def test_create_expense_returns_new_id_and_inserts_row(self, new_user_id):
        before = expense_count()
        new_id = db.create_expense(new_user_id, 12.5, "Food", "2026-01-02", "Tea")
        assert isinstance(new_id, int), "Expected an integer id"
        rows = fetch_expenses()
        assert len(rows) == before + 1
        row = [r for r in rows if r["id"] == new_id][0]
        assert row["user_id"] == new_user_id
        assert row["amount"] == 12.5
        assert row["category"] == "Food"
        assert row["date"] == "2026-01-02"
        assert row["description"] == "Tea"

    def test_create_expense_without_description_stores_null(self, new_user_id):
        new_id = db.create_expense(new_user_id, 5, "Other", "2026-01-02")
        row = [r for r in fetch_expenses() if r["id"] == new_id][0]
        assert row["description"] is None

    def test_create_expense_unknown_user_returns_none(self, app):
        before = expense_count()
        result = db.create_expense(99999, 5, "Food", "2026-01-02")
        assert result is None, "Missing user must yield None (FK)"
        assert expense_count() == before


# ------------------------------------------------------------------ #
# Auth guard                                                          #
# ------------------------------------------------------------------ #

class TestAuthGuard:
    def test_get_logged_out_redirects_to_login(self, client):
        resp = client.get("/expenses/add")
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_post_logged_out_redirects_and_inserts_nothing(self, client):
        before = expense_count()
        resp = client.post("/expenses/add", data=valid_form())
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]
        assert expense_count() == before, "Nothing may be inserted"


# ------------------------------------------------------------------ #
# GET form                                                            #
# ------------------------------------------------------------------ #

class TestAddForm:
    def get_html(self, auth_client):
        resp = auth_client.get("/expenses/add")
        assert resp.status_code == 200
        return resp.get_data(as_text=True)

    def test_form_renders_heading_and_fields(self, auth_client):
        html = self.get_html(auth_client)
        assert "Add expense" in html
        for name in ("amount", "category", "date", "description"):
            assert f'name="{name}"' in html, f"Missing field {name}"

    def test_form_date_prefilled_with_today_and_max_today(self, auth_client):
        html = self.get_html(auth_client)
        assert f'value="{TODAY_S}"' in html
        assert f'max="{TODAY_S}"' in html

    def test_form_category_options_are_exactly_categories(self, auth_client):
        html = self.get_html(auth_client)
        select = re.search(
            r'<select[^>]*name="category".*?</select>', html, re.S
        )
        assert select, "Category select not found"
        values = re.findall(r'<option[^>]*value="([^"]*)"', select.group(0))
        assert values == [""] + CATEGORIES

    def test_form_has_disabled_placeholder_option(self, auth_client):
        html = self.get_html(auth_client)
        placeholder = re.search(r'<option[^>]*value=""[^>]*>', html)
        assert placeholder, "Placeholder option not found"
        assert "disabled" in placeholder.group(0)

    def test_form_has_no_category_selected_by_default(self, auth_client):
        html = self.get_html(auth_client)
        for cat in CATEGORIES:
            assert f'<option value="{cat}" selected>' not in html


# ------------------------------------------------------------------ #
# Valid POST                                                          #
# ------------------------------------------------------------------ #

class TestValidPost:
    def test_valid_post_redirects_to_profile(self, auth_client):
        resp = auth_client.post("/expenses/add", data=valid_form())
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/profile")

    def test_valid_post_inserts_row_for_session_user(
        self, auth_client, new_user_id
    ):
        before = expense_count()
        auth_client.post("/expenses/add", data=valid_form())
        rows = fetch_expenses()
        assert len(rows) == before + 1
        row = rows[-1]
        assert row["user_id"] == new_user_id
        assert row["amount"] == 250.0
        assert row["category"] == "Food"
        assert row["date"] == TODAY_S
        assert row["description"] == "Lunch"

    def test_valid_post_flashes_expense_added_on_profile(self, auth_client):
        resp = auth_client.post(
            "/expenses/add", data=valid_form(), follow_redirects=True
        )
        assert resp.status_code == 200
        assert "Expense added" in resp.get_data(as_text=True)

    def test_newest_expense_is_first_row(self, auth_client):
        auth_client.post(
            "/expenses/add",
            data=valid_form(date="2026-10-01", description="Older"),
        )
        auth_client.post(
            "/expenses/add",
            data=valid_form(date=TODAY_S, description="Newest"),
        )
        html = auth_client.get("/profile").get_data(as_text=True)
        rows = re.findall(r'<tr class="prof-tx-row">(.*?)</tr>', html, re.S)
        assert len(rows) == 2
        assert "Newest" in rows[0]
        assert "Older" in rows[1]

    def test_total_includes_all_added_expenses(self, auth_client):
        auth_client.post("/expenses/add", data=valid_form(amount="250"))
        auth_client.post("/expenses/add", data=valid_form(amount="250"))
        html = auth_client.get("/profile").get_data(as_text=True)
        assert "₹500.00" in html, "Total should include both expenses"

    def test_amount_is_rounded_to_two_decimals(self, auth_client):
        auth_client.post("/expenses/add", data=valid_form(amount="10.456"))
        assert fetch_expenses()[-1]["amount"] == 10.46

    def test_amount_rounds_half_up(self, auth_client):
        # float round(10.455, 2) gives 10.45; money should round half up.
        auth_client.post("/expenses/add", data=valid_form(amount="10.455"))
        assert fetch_expenses()[-1]["amount"] == 10.46

    @pytest.mark.parametrize("blank", ["", "   ", "\t "])
    def test_blank_description_stored_as_null(self, auth_client, blank):
        resp = auth_client.post(
            "/expenses/add", data=valid_form(description=blank)
        )
        assert resp.status_code == 302
        assert fetch_expenses()[-1]["description"] is None

    def test_description_is_stripped(self, auth_client):
        auth_client.post("/expenses/add", data=valid_form(description="  Hi  "))
        assert fetch_expenses()[-1]["description"] == "Hi"

    def test_posted_user_id_is_ignored(self, auth_client, new_user_id):
        demo_id = db.get_user_by_email(DEMO["email"])["id"]
        assert demo_id != new_user_id
        auth_client.post("/expenses/add", data=valid_form(user_id=str(demo_id)))
        assert fetch_expenses()[-1]["user_id"] == new_user_id

    @pytest.mark.parametrize("category", CATEGORIES)
    def test_every_listed_category_is_accepted(self, auth_client, category):
        resp = auth_client.post(
            "/expenses/add", data=valid_form(category=category)
        )
        assert resp.status_code == 302
        assert fetch_expenses()[-1]["category"] == category

    def test_max_amount_is_accepted(self, auth_client):
        resp = auth_client.post(
            "/expenses/add", data=valid_form(amount="100000000")
        )
        assert resp.status_code == 302
        assert fetch_expenses()[-1]["amount"] == 100000000.0

    def test_today_is_accepted(self, auth_client):
        resp = auth_client.post("/expenses/add", data=valid_form(date=TODAY_S))
        assert resp.status_code == 302

    def test_description_of_exactly_200_chars_is_accepted(self, auth_client):
        resp = auth_client.post(
            "/expenses/add", data=valid_form(description="a" * 200)
        )
        assert resp.status_code == 302
        assert fetch_expenses()[-1]["description"] == "a" * 200

    def test_sql_injection_in_description_stored_literally(self, auth_client):
        payload = "x'); DROP TABLE expenses;--"
        resp = auth_client.post(
            "/expenses/add", data=valid_form(description=payload)
        )
        assert resp.status_code == 302
        assert fetch_expenses()[-1]["description"] == payload


# ------------------------------------------------------------------ #
# Invalid POST                                                        #
# ------------------------------------------------------------------ #

INVALID_AMOUNTS = [
    "", "0", "-5", "abc", "nan", "inf", "0.001", "100000000.01",
    "1_000", "1e3", "١٢", "+5", "5.",
]
INVALID_CATEGORIES = ["", "Rent", "food"]
INVALID_DATES = [
    "", "2026-13-01", "12/10/2026", "20261012", "2026-10-13", "2099-01-01",
]


class TestInvalidPost:
    def assert_rejected(self, client, form):
        before = expense_count()
        resp = client.post("/expenses/add", data=form)
        assert resp.status_code == 400, f"Expected 400 for {form}"
        html = resp.get_data(as_text=True)
        assert 'class="auth-error"' in html, "Expected inline error block"
        assert expense_count() == before, "Nothing may be inserted"
        return html

    @pytest.mark.parametrize("amount", INVALID_AMOUNTS)
    def test_invalid_amount_returns_400(self, auth_client, amount):
        self.assert_rejected(auth_client, valid_form(amount=amount))

    @pytest.mark.parametrize("category", INVALID_CATEGORIES)
    def test_invalid_category_returns_400(self, auth_client, category):
        self.assert_rejected(auth_client, valid_form(category=category))

    @pytest.mark.parametrize("bad_date", INVALID_DATES)
    def test_invalid_date_returns_400(self, auth_client, bad_date):
        self.assert_rejected(auth_client, valid_form(date=bad_date))

    def test_description_over_200_chars_returns_400(self, auth_client):
        self.assert_rejected(auth_client, valid_form(description="a" * 201))

    def test_missing_fields_returns_400(self, auth_client):
        self.assert_rejected(auth_client, {"csrf_token": CSRF})

    def test_failed_post_rerenders_submitted_values(self, auth_client):
        html = self.assert_rejected(
            auth_client,
            valid_form(
                amount="12.5",
                category="Health",
                date="2026-10-13",  # future -> rejected
                description="Pharmacy",
            ),
        )
        assert 'value="12.5"' in html
        assert 'value="2026-10-13"' in html
        assert 'value="Pharmacy"' in html
        assert '<option value="Health" selected>' in html
        assert '<option value="Food" selected>' not in html

    def test_failed_post_with_invalid_amount_keeps_other_values(
        self, auth_client
    ):
        html = self.assert_rejected(
            auth_client,
            valid_form(amount="abc", category="Bills", description="Rent bill"),
        )
        assert '<option value="Bills" selected>' in html
        assert 'value="Rent bill"' in html
        assert f'value="{TODAY_S}"' in html


# ------------------------------------------------------------------ #
# CSRF, request size, stale session                                   #
# ------------------------------------------------------------------ #

class TestRequestGuards:
    def test_form_renders_csrf_token_from_session(self, auth_client):
        html = auth_client.get("/expenses/add").get_data(as_text=True)
        assert f'name="csrf_token" value="{CSRF}"' in html

    @pytest.mark.parametrize("token", [None, "", "wrong-token"])
    def test_missing_or_wrong_csrf_token_returns_400(self, auth_client, token):
        form = valid_form()
        if token is None:
            del form["csrf_token"]
        else:
            form["csrf_token"] = token
        before = expense_count()
        resp = auth_client.post("/expenses/add", data=form)
        assert resp.status_code == 400
        assert expense_count() == before

    def test_oversized_body_returns_413(self, auth_client):
        before = expense_count()
        resp = auth_client.post(
            "/expenses/add", data=valid_form(description="a" * 20_000)
        )
        assert resp.status_code == 413
        assert expense_count() == before

    def test_deleted_user_is_signed_out(self, auth_client, new_user_id):
        conn = db.get_db()
        try:
            conn.execute("DELETE FROM users WHERE id = ?", (new_user_id,))
            conn.commit()
        finally:
            conn.close()
        resp = auth_client.post(
            "/expenses/add", data=valid_form(), follow_redirects=True
        )
        assert resp.request.path == "/login"
        assert "Please sign in again" in resp.get_data(as_text=True)
        with auth_client.session_transaction() as sess:
            assert "user_id" not in sess


# ------------------------------------------------------------------ #
# Profile integration                                                 #
# ------------------------------------------------------------------ #

class TestProfileIntegration:
    def test_profile_header_has_add_expense_link(self, auth_client):
        html = auth_client.get("/profile").get_data(as_text=True)
        assert "Add expense" in html
        assert 'href="/expenses/add"' in html

    def test_profile_empty_state_links_to_add_expense(self, auth_client):
        html = auth_client.get("/profile").get_data(as_text=True)
        assert "No expenses yet" in html
        # header link + empty-state link
        assert html.count('href="/expenses/add"') >= 2

    def test_profile_totals_use_rupee_with_indian_grouping(self, auth_client):
        auth_client.post("/expenses/add", data=valid_form(amount="250"))
        html = auth_client.get("/profile").get_data(as_text=True)
        assert "₹250.00" in html
        assert "$" not in html

    def test_profile_indian_grouping_for_large_amount(self, auth_client):
        auth_client.post("/expenses/add", data=valid_form(amount="123456.5"))
        html = auth_client.get("/profile").get_data(as_text=True)
        assert "₹1,23,456.50" in html

    def test_added_expense_removes_empty_state(self, auth_client):
        auth_client.post("/expenses/add", data=valid_form())
        html = auth_client.get("/profile").get_data(as_text=True)
        assert "No expenses yet" not in html
        assert html.count('class="prof-tx-row"') == 1


# ------------------------------------------------------------------ #
# Remaining stubs                                                     #
# ------------------------------------------------------------------ #

class TestStubsUntouched:
    def test_delete_stub_still_returns_stub_text(self, client):
        resp = client.get("/expenses/1/delete")
        assert resp.status_code == 200
        assert "coming in Step 9" in resp.get_data(as_text=True)
