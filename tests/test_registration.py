import pytest
from werkzeug.security import check_password_hash

import database.db as db

VALID = {
    "name": "Nitish Kumar",
    "email": "nitish@example.com",
    "password": "supersecret1",
}


def post_register(client, **overrides):
    return client.post("/register", data={**VALID, **overrides})


def test_get_register_renders_form(client):
    resp = client.get("/register")
    html = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert 'action="/register"' in html
    assert 'minlength="8"' in html


def test_register_success_creates_user_and_redirects(client, count_users):
    before = count_users()
    resp = post_register(client)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/login")
    assert count_users() == before + 1
    assert db.get_user_by_email(VALID["email"]) is not None


def test_register_success_shows_flash_on_login(client):
    resp = client.post("/register", data=VALID, follow_redirects=True)
    html = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "Account created — please sign in" in html
    assert 'class="auth-success"' in html


def test_password_is_hashed(client):
    post_register(client)
    row = db.get_user_by_email(VALID["email"])
    assert row["password_hash"] != VALID["password"]
    assert check_password_hash(row["password_hash"], VALID["password"])


def test_email_stored_lowercase(client):
    post_register(client, email="Mixed@Example.COM")
    row = db.get_user_by_email("mixed@example.com")
    assert row is not None
    assert row["email"] == "mixed@example.com"


@pytest.mark.parametrize("email", ["demo@spendly.com", "DEMO@spendly.com"])
def test_duplicate_email_rejected(client, count_users, email):
    before = count_users()
    resp = post_register(client, email=email)
    assert resp.status_code == 400
    assert "An account with that email already exists" in resp.get_data(as_text=True)
    assert count_users() == before


@pytest.mark.parametrize("field, value", [
    ("name", ""),
    ("name", "   "),
    ("email", ""),
    ("password", ""),
    ("password", "         "),
])
def test_missing_fields_rejected(client, count_users, field, value):
    before = count_users()
    resp = post_register(client, **{field: value})
    assert resp.status_code == 400
    assert "Name, email and password are all required." in resp.get_data(as_text=True)
    assert count_users() == before


@pytest.mark.parametrize("email", [
    "nitish",
    "nitish@",
    "nitish@example",
    "@example.com",
])
def test_invalid_email_rejected(client, count_users, email):
    before = count_users()
    resp = post_register(client, email=email)
    assert resp.status_code == 400
    assert "Please enter a valid email address." in resp.get_data(as_text=True)
    assert count_users() == before


def test_short_password_rejected(client, count_users):
    before = count_users()
    resp = post_register(client, password="short7!")
    assert resp.status_code == 400
    assert "Password must be at least 8 characters." in resp.get_data(as_text=True)
    assert count_users() == before


def test_failed_submission_keeps_name_and_email_not_password(client):
    resp = post_register(client, password="tiny")
    html = resp.get_data(as_text=True)
    assert 'value="Nitish Kumar"' in html
    assert 'value="nitish@example.com"' in html
    assert "tiny" not in html


def test_validation_reports_first_error_only(client):
    resp = post_register(client, name="", email="bad")
    html = resp.get_data(as_text=True)
    assert "Name, email and password are all required." in html
    assert "Please enter a valid email address." not in html


def test_login_without_flash_has_no_success_message(client):
    html = client.get("/login").get_data(as_text=True)
    assert "auth-success" not in html
