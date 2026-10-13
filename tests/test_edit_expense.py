import importlib
import re
from datetime import date, timedelta

import pytest

import database.db as db
import database.queries as queries

DEMO = {"email": "demo@spendly.com", "password": "demo123"}
NEW = {"email": "new@spendly.com", "password": "password123"}
TODAY = date(2026, 10, 12)
TODAY_S = TODAY.isoformat()
TOMORROW_S = (TODAY + timedelta(days=1)).isoformat()
CSRF = "test-csrf-token"
MISSING_ID = 999999
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


@pytest.fixture
def own_id(new_user_id):
    """Id of an expense owned by the logged-in (new) user."""
    expense_id = db.create_expense(
        new_user_id, 250.0, "Food", days_ago(7), "Lunch"
    )
    assert expense_id is not None
    return expense_id


@pytest.fixture
def demo_expense_id(app):
    """Id of an expense that belongs to the seeded demo user."""
    demo_id = db.get_user_by_email(DEMO["email"])["id"]
    conn = db.get_db()
    try:
        row = conn.execute(
            "SELECT id FROM expenses WHERE user_id = ? ORDER BY id LIMIT 1",
            (demo_id,),
        ).fetchone()
    finally:
        conn.close()
    assert row is not None, "Seed should give the demo user expenses"
    return row["id"]


def fetch_expenses():
    conn = db.get_db()
    try:
        return conn.execute("SELECT * FROM expenses ORDER BY id").fetchall()
    finally:
        conn.close()


def fetch_expense(expense_id):
    conn = db.get_db()
    try:
        return conn.execute(
            "SELECT * FROM expenses WHERE id = ?", (expense_id,)
        ).fetchone()
    finally:
        conn.close()


def snapshot(expense_id):
    row = fetch_expense(expense_id)
    return None if row is None else tuple(row)


def expense_count():
    return len(fetch_expenses())


def days_ago(n):
    return (TODAY - timedelta(days=n)).isoformat()


def edit_url(expense_id):
    return f"/expenses/{expense_id}/edit"


def valid_form(**overrides):
    form = {
        "amount": "300",
        "category": "Transport",
        "date": TODAY_S,
        "description": "Cab",
        "csrf_token": CSRF,
    }
    form.update(overrides)
    return form


# ------------------------------------------------------------------ #
# Helpers: get_expense / update_expense / get_recent_transactions     #
# ------------------------------------------------------------------ #

class TestGetExpense:
    def test_returns_dict_for_owned_expense(self, new_user_id, own_id):
        result = queries.get_expense(own_id, new_user_id)
        assert result is not None
        assert result["id"] == own_id
        assert result["amount"] == 250.0
        assert result["category"] == "Food"
        assert result["date"] == days_ago(7)
        assert result["description"] == "Lunch"

    def test_null_description_becomes_empty_string(self, new_user_id):
        expense_id = db.create_expense(new_user_id, 5, "Other", days_ago(11))
        result = queries.get_expense(expense_id, new_user_id)
        assert result["description"] == ""

    def test_missing_id_returns_none(self, new_user_id):
        assert queries.get_expense(MISSING_ID, new_user_id) is None

    def test_foreign_expense_returns_none(self, new_user_id, demo_expense_id):
        assert queries.get_expense(demo_expense_id, new_user_id) is None


class TestUpdateExpense:
    def test_updates_row_and_returns_true(self, new_user_id, own_id):
        result = db.update_expense(
            own_id, new_user_id, 300.0, "Transport", days_ago(6), "Cab"
        )
        assert result is True
        row = fetch_expense(own_id)
        assert row["amount"] == 300.0
        assert row["category"] == "Transport"
        assert row["date"] == days_ago(6)
        assert row["description"] == "Cab"
        assert row["user_id"] == new_user_id

    def test_omitted_description_stores_null(self, new_user_id, own_id):
        assert db.update_expense(
            own_id, new_user_id, 10, "Other", days_ago(6)
        ) is True
        assert fetch_expense(own_id)["description"] is None

    def test_does_not_change_row_count(self, new_user_id, own_id):
        before = expense_count()
        db.update_expense(own_id, new_user_id, 1, "Other", days_ago(6), "x")
        assert expense_count() == before

    def test_foreign_expense_returns_false_and_unchanged(
        self, new_user_id, demo_expense_id
    ):
        before = snapshot(demo_expense_id)
        result = db.update_expense(
            demo_expense_id, new_user_id, 1, "Other", days_ago(6), "hijack"
        )
        assert result is False
        assert snapshot(demo_expense_id) == before

    def test_missing_expense_returns_false(self, new_user_id):
        before = expense_count()
        assert db.update_expense(
            MISSING_ID, new_user_id, 1, "Other", days_ago(6)
        ) is False
        assert expense_count() == before

    def test_sql_injection_in_description_stored_literally(
        self, new_user_id, own_id
    ):
        payload = "x'); DROP TABLE expenses;--"
        db.update_expense(own_id, new_user_id, 1, "Other", days_ago(6), payload)
        assert fetch_expense(own_id)["description"] == payload


class TestRecentTransactionsId:
    def test_rows_include_expense_id(self, new_user_id, own_id):
        rows = queries.get_recent_transactions(new_user_id)
        assert len(rows) == 1
        assert rows[0]["id"] == own_id


# ------------------------------------------------------------------ #
# Auth guard                                                          #
# ------------------------------------------------------------------ #

class TestAuthGuard:
    def test_get_logged_out_redirects_to_login(self, client, own_id):
        resp = client.get(edit_url(own_id))
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_post_logged_out_redirects_and_changes_nothing(
        self, client, own_id
    ):
        before = snapshot(own_id)
        resp = client.post(edit_url(own_id), data=valid_form())
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]
        assert snapshot(own_id) == before, "Row must be unchanged"


# ------------------------------------------------------------------ #
# GET form                                                            #
# ------------------------------------------------------------------ #

class TestEditForm:
    def get_html(self, auth_client, expense_id):
        resp = auth_client.get(edit_url(expense_id))
        assert resp.status_code == 200
        return resp.get_data(as_text=True)

    def test_form_renders_heading_button_and_fields(self, auth_client, own_id):
        html = self.get_html(auth_client, own_id)
        assert "Edit expense" in html
        assert "Save changes" in html
        for name in ("amount", "category", "date", "description"):
            assert f'name="{name}"' in html, f"Missing field {name}"

    def test_form_posts_to_edit_url_with_csrf(self, auth_client, own_id):
        html = self.get_html(auth_client, own_id)
        assert f'action="{edit_url(own_id)}"' in html
        assert f'name="csrf_token" value="{CSRF}"' in html

    def test_form_prefilled_with_current_values(self, auth_client, own_id):
        html = self.get_html(auth_client, own_id)
        assert 'value="250.00"' in html, "Amount should have 2 decimals"
        assert '<option value="Food" selected>' in html
        assert f'value="{days_ago(7)}"' in html
        assert 'value="Lunch"' in html

    def test_only_current_category_is_selected(self, auth_client, own_id):
        html = self.get_html(auth_client, own_id)
        for cat in CATEGORIES:
            if cat != "Food":
                assert f'<option value="{cat}" selected>' not in html

    def test_date_input_max_is_today(self, auth_client, own_id):
        html = self.get_html(auth_client, own_id)
        assert f'max="{TODAY_S}"' in html

    def test_null_description_renders_empty_field(
        self, auth_client, new_user_id
    ):
        expense_id = db.create_expense(new_user_id, 5, "Other", days_ago(11))
        html = self.get_html(auth_client, expense_id)
        assert 'value="None"' not in html

    def test_form_has_cancel_link_to_profile(self, auth_client, own_id):
        html = self.get_html(auth_client, own_id)
        assert "Cancel" in html
        assert 'href="/profile"' in html


# ------------------------------------------------------------------ #
# Valid POST                                                          #
# ------------------------------------------------------------------ #

class TestValidPost:
    def test_valid_post_redirects_to_profile(self, auth_client, own_id):
        resp = auth_client.post(edit_url(own_id), data=valid_form())
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/profile")

    def test_valid_post_updates_db_row(
        self, auth_client, own_id, new_user_id
    ):
        auth_client.post(
            edit_url(own_id),
            data=valid_form(date=days_ago(11), description="Cab ride"),
        )
        row = fetch_expense(own_id)
        assert row["amount"] == 300.0
        assert row["category"] == "Transport"
        assert row["date"] == days_ago(11)
        assert row["description"] == "Cab ride"
        assert row["user_id"] == new_user_id

    def test_valid_post_flashes_expense_updated_on_profile(
        self, auth_client, own_id
    ):
        resp = auth_client.post(
            edit_url(own_id), data=valid_form(), follow_redirects=True
        )
        assert resp.status_code == 200
        assert "Expense updated" in resp.get_data(as_text=True)

    def test_profile_shows_new_amount_and_category(self, auth_client, own_id):
        auth_client.post(edit_url(own_id), data=valid_form())
        html = auth_client.get("/profile").get_data(as_text=True)
        assert "₹300.00" in html, "New amount/total should be shown"
        assert "₹250.00" not in html, "Old amount should be gone"
        assert "Transport" in html
        assert "Cab" in html

    def test_transaction_count_unchanged(self, auth_client, own_id):
        before = expense_count()
        auth_client.post(edit_url(own_id), data=valid_form())
        assert expense_count() == before
        html = auth_client.get("/profile").get_data(as_text=True)
        assert html.count('class="prof-tx-row"') == 1

    def test_only_target_row_is_changed(
        self, auth_client, own_id, new_user_id
    ):
        other_id = db.create_expense(
            new_user_id, 40, "Bills", days_ago(10), "Power"
        )
        before = snapshot(other_id)
        auth_client.post(edit_url(own_id), data=valid_form())
        assert snapshot(other_id) == before

    @pytest.mark.parametrize("blank", ["", "   ", "\t "])
    def test_blank_description_stored_as_null(
        self, auth_client, own_id, blank
    ):
        resp = auth_client.post(
            edit_url(own_id), data=valid_form(description=blank)
        )
        assert resp.status_code == 302
        assert fetch_expense(own_id)["description"] is None

    def test_description_is_stripped(self, auth_client, own_id):
        auth_client.post(
            edit_url(own_id), data=valid_form(description="  Hi  ")
        )
        assert fetch_expense(own_id)["description"] == "Hi"

    def test_amount_rounds_half_up(self, auth_client, own_id):
        auth_client.post(edit_url(own_id), data=valid_form(amount="10.455"))
        assert fetch_expense(own_id)["amount"] == 10.46

    @pytest.mark.parametrize("category", CATEGORIES)
    def test_every_listed_category_is_accepted(
        self, auth_client, own_id, category
    ):
        resp = auth_client.post(
            edit_url(own_id), data=valid_form(category=category)
        )
        assert resp.status_code == 302
        assert fetch_expense(own_id)["category"] == category

    def test_max_amount_and_today_are_accepted(self, auth_client, own_id):
        resp = auth_client.post(
            edit_url(own_id),
            data=valid_form(amount="100000000", date=TODAY_S),
        )
        assert resp.status_code == 302
        row = fetch_expense(own_id)
        assert row["amount"] == 100000000.0
        assert row["date"] == TODAY_S

    def test_description_of_exactly_200_chars_is_accepted(
        self, auth_client, own_id
    ):
        resp = auth_client.post(
            edit_url(own_id), data=valid_form(description="a" * 200)
        )
        assert resp.status_code == 302
        assert fetch_expense(own_id)["description"] == "a" * 200

    def test_sql_injection_in_description_stored_literally(
        self, auth_client, own_id
    ):
        payload = "x'); DROP TABLE expenses;--"
        resp = auth_client.post(
            edit_url(own_id), data=valid_form(description=payload)
        )
        assert resp.status_code == 302
        assert fetch_expense(own_id)["description"] == payload

    def test_posted_user_id_is_ignored(
        self, auth_client, own_id, new_user_id
    ):
        demo_id = db.get_user_by_email(DEMO["email"])["id"]
        assert demo_id != new_user_id
        auth_client.post(
            edit_url(own_id), data=valid_form(user_id=str(demo_id))
        )
        row = fetch_expense(own_id)
        assert row["user_id"] == new_user_id, "Owner must not change"
        assert row["amount"] == 300.0, "Edit itself should still apply"


# ------------------------------------------------------------------ #
# Invalid POST                                                        #
# ------------------------------------------------------------------ #

INVALID_AMOUNTS = [
    "", "0", "-5", "abc", "nan", "inf", "0.001", "100000000.01", "1e3",
]
INVALID_CATEGORIES = ["", "Rent", "food"]
INVALID_DATES = [
    "", "2026-13-01", "12/10/2026", "20261012", TOMORROW_S, "2099-01-01",
]


class TestInvalidPost:
    def assert_rejected(self, client, expense_id, form):
        before = snapshot(expense_id)
        count = expense_count()
        resp = client.post(edit_url(expense_id), data=form)
        assert resp.status_code == 400, f"Expected 400 for {form}"
        html = resp.get_data(as_text=True)
        assert 'class="auth-error"' in html, "Expected inline error block"
        assert snapshot(expense_id) == before, "Row must be unchanged"
        assert expense_count() == count
        return html

    @pytest.mark.parametrize("amount", INVALID_AMOUNTS)
    def test_invalid_amount_returns_400(self, auth_client, own_id, amount):
        self.assert_rejected(auth_client, own_id, valid_form(amount=amount))

    @pytest.mark.parametrize("category", INVALID_CATEGORIES)
    def test_invalid_category_returns_400(self, auth_client, own_id, category):
        self.assert_rejected(
            auth_client, own_id, valid_form(category=category)
        )

    @pytest.mark.parametrize("bad_date", INVALID_DATES)
    def test_invalid_date_returns_400(self, auth_client, own_id, bad_date):
        self.assert_rejected(auth_client, own_id, valid_form(date=bad_date))

    def test_description_over_200_chars_returns_400(self, auth_client, own_id):
        self.assert_rejected(
            auth_client, own_id, valid_form(description="a" * 201)
        )

    def test_missing_fields_returns_400(self, auth_client, own_id):
        self.assert_rejected(auth_client, own_id, {"csrf_token": CSRF})

    def test_failed_post_rerenders_submitted_values(self, auth_client, own_id):
        html = self.assert_rejected(
            auth_client,
            own_id,
            valid_form(
                amount="12.5",
                category="Health",
                date=TOMORROW_S,  # future -> rejected
                description="Pharmacy",
            ),
        )
        assert 'value="12.5"' in html
        assert f'value="{TOMORROW_S}"' in html
        assert 'value="Pharmacy"' in html
        assert '<option value="Health" selected>' in html
        assert '<option value="Food" selected>' not in html
        assert 'value="250.00"' not in html, "Must not show stored amount"

    def test_failed_post_keeps_other_values_and_edit_action(
        self, auth_client, own_id
    ):
        html = self.assert_rejected(
            auth_client,
            own_id,
            valid_form(amount="abc", category="Bills", description="Rent bill"),
        )
        assert "Edit expense" in html
        assert '<option value="Bills" selected>' in html
        assert 'value="Rent bill"' in html
        assert f'action="{edit_url(own_id)}"' in html


# ------------------------------------------------------------------ #
# Ownership and not-found                                             #
# ------------------------------------------------------------------ #

class TestOwnership:
    def test_get_foreign_expense_returns_404(
        self, auth_client, demo_expense_id
    ):
        resp = auth_client.get(edit_url(demo_expense_id))
        assert resp.status_code == 404

    def test_post_foreign_expense_returns_404_and_unchanged(
        self, auth_client, demo_expense_id
    ):
        before = snapshot(demo_expense_id)
        resp = auth_client.post(
            edit_url(demo_expense_id), data=valid_form(amount="1")
        )
        assert resp.status_code == 404
        assert snapshot(demo_expense_id) == before

    def test_invalid_form_on_foreign_id_is_still_404(
        self, auth_client, demo_expense_id
    ):
        before = snapshot(demo_expense_id)
        resp = auth_client.post(
            edit_url(demo_expense_id), data=valid_form(amount="abc")
        )
        assert resp.status_code == 404, "Ownership is checked before validation"
        assert snapshot(demo_expense_id) == before

    def test_foreign_post_with_user_id_does_not_take_over(
        self, auth_client, demo_expense_id, new_user_id
    ):
        before = snapshot(demo_expense_id)
        resp = auth_client.post(
            edit_url(demo_expense_id),
            data=valid_form(user_id=str(new_user_id)),
        )
        assert resp.status_code == 404
        assert snapshot(demo_expense_id) == before

    def test_foreign_and_missing_responses_match(
        self, auth_client, demo_expense_id
    ):
        foreign = auth_client.get(edit_url(demo_expense_id))
        missing = auth_client.get(edit_url(MISSING_ID))
        assert foreign.status_code == missing.status_code == 404
        assert foreign.get_data() == missing.get_data()

    def test_get_nonexistent_returns_404(self, auth_client):
        assert auth_client.get(edit_url(MISSING_ID)).status_code == 404

    def test_post_nonexistent_returns_404(self, auth_client):
        before = expense_count()
        resp = auth_client.post(edit_url(MISSING_ID), data=valid_form())
        assert resp.status_code == 404
        assert expense_count() == before

    def test_demo_user_cannot_edit_new_users_expense(
        self, client, app, new_user_id, own_id
    ):
        """The demo user cannot edit the new user's expense."""
        client.post("/login", data=DEMO)
        with client.session_transaction() as sess:
            sess["csrf_token"] = CSRF
        before = snapshot(own_id)
        assert client.get(edit_url(own_id)).status_code == 404
        resp = client.post(edit_url(own_id), data=valid_form())
        assert resp.status_code == 404
        assert snapshot(own_id) == before


# ------------------------------------------------------------------ #
# CSRF                                                                #
# ------------------------------------------------------------------ #

class TestCsrf:
    @pytest.mark.parametrize("token", [None, "", "wrong-token"])
    def test_missing_or_wrong_csrf_token_returns_400(
        self, auth_client, own_id, token
    ):
        form = valid_form()
        if token is None:
            del form["csrf_token"]
        else:
            form["csrf_token"] = token
        before = snapshot(own_id)
        resp = auth_client.post(edit_url(own_id), data=form)
        assert resp.status_code == 400
        assert snapshot(own_id) == before, "Row must be unchanged"


# ------------------------------------------------------------------ #
# Profile integration                                                 #
# ------------------------------------------------------------------ #

class TestProfileEditLinks:
    def test_each_row_has_edit_link_with_its_id(
        self, auth_client, own_id, new_user_id
    ):
        second_id = db.create_expense(
            new_user_id, 40, "Bills", days_ago(10), "Power"
        )
        html = auth_client.get("/profile").get_data(as_text=True)
        rows = re.findall(r'<tr class="prof-tx-row">(.*?)</tr>', html, re.S)
        assert len(rows) == 2
        joined = " ".join(rows)
        assert f'href="{edit_url(own_id)}"' in joined
        assert f'href="{edit_url(second_id)}"' in joined

    def test_edit_link_has_descriptive_aria_label(self, auth_client, own_id):
        html = auth_client.get("/profile").get_data(as_text=True)
        assert 'aria-label="Edit Lunch expense"' in html

    def test_aria_label_falls_back_to_category(
        self, auth_client, new_user_id
    ):
        db.create_expense(new_user_id, 5, "Health", days_ago(11))
        html = auth_client.get("/profile").get_data(as_text=True)
        assert 'aria-label="Edit Health expense"' in html

    def test_table_has_visually_hidden_actions_header(
        self, auth_client, own_id
    ):
        html = auth_client.get("/profile").get_data(as_text=True)
        assert '<span class="sr-only">Actions</span>' in html

    def test_profile_links_only_own_expenses(
        self, auth_client, own_id, demo_expense_id
    ):
        html = auth_client.get("/profile").get_data(as_text=True)
        assert f'href="{edit_url(demo_expense_id)}"' not in html


# ------------------------------------------------------------------ #
# Regression: add expense and delete stub                             #
# ------------------------------------------------------------------ #

class TestOtherRoutesUntouched:
    def test_add_expense_get_still_renders(self, auth_client):
        resp = auth_client.get("/expenses/add")
        html = resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert "Add expense" in html
        assert f'value="{TODAY_S}"' in html

    def test_add_expense_post_still_creates_row(
        self, auth_client, new_user_id
    ):
        before = expense_count()
        resp = auth_client.post("/expenses/add", data=valid_form())
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/profile")
        rows = fetch_expenses()
        assert len(rows) == before + 1
        assert rows[-1]["user_id"] == new_user_id

    def test_add_expense_invalid_post_still_returns_400(self, auth_client):
        resp = auth_client.post("/expenses/add", data=valid_form(amount="0"))
        assert resp.status_code == 400
        assert 'class="auth-error"' in resp.get_data(as_text=True)

    def test_delete_stub_still_returns_stub_text(self, client):
        resp = client.get("/expenses/1/delete")
        assert resp.status_code == 200
        assert "coming in Step 9" in resp.get_data(as_text=True)
