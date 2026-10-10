import pytest

import database.db as db

DEMO = {"email": "demo@spendly.com", "password": "demo123"}


def post_login(client, follow_redirects=False, **overrides):
    return client.post(
        "/login", data={**DEMO, **overrides}, follow_redirects=follow_redirects
    )


def session_data(client):
    with client.session_transaction() as sess:
        return dict(sess)


def test_get_login_renders_form(client):
    resp = client.get("/login")
    html = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert 'action="/login"' in html
    assert "auth-error" not in html


def test_login_success_redirects_to_landing(client):
    resp = post_login(client)
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/"


def test_navbar_shows_user_after_login(client):
    html = post_login(client, follow_redirects=True).get_data(as_text=True)
    assert 'class="nav-user"' in html
    assert "Demo User" in html
    assert "Sign out" in html
    assert "Sign in" not in html
    assert "Get started" not in html


def test_navbar_signed_out_by_default(client):
    html = client.get("/").get_data(as_text=True)
    assert "Sign in" in html
    assert "Get started" in html
    assert "Sign out" not in html


@pytest.mark.parametrize("email", ["DEMO@spendly.com", "  demo@spendly.com  "])
def test_login_email_is_normalised(client, email):
    resp = post_login(client, email=email)
    assert resp.status_code == 302
    assert "user_id" in session_data(client)


@pytest.mark.parametrize("email, password", [
    ("demo@spendly.com", "wrong-password"),
    ("nobody@example.com", "demo123"),
])
def test_invalid_credentials_rejected(client, email, password):
    resp = post_login(client, email=email, password=password)
    html = resp.get_data(as_text=True)
    assert resp.status_code == 401
    assert "Invalid email or password." in html
    assert f'value="{email}"' in html
    assert password not in html
    assert "user_id" not in session_data(client)


def test_invalid_credential_responses_are_identical(client):
    wrong_password = post_login(client, password="wrong-password")
    unknown_email = post_login(client, email="nobody@example.com",
                               password="wrong-password")
    assert wrong_password.status_code == unknown_email.status_code
    a = wrong_password.get_data(as_text=True).replace("demo@spendly.com", "")
    b = unknown_email.get_data(as_text=True).replace("nobody@example.com", "")
    assert a == b


@pytest.mark.parametrize("email, password", [
    ("", "demo123"),
    ("demo@spendly.com", ""),
    ("", ""),
    ("   ", "demo123"),
])
def test_missing_fields_rejected(client, email, password):
    resp = post_login(client, email=email, password=password)
    assert resp.status_code == 400
    assert "Email and password are both required." in resp.get_data(as_text=True)
    assert "user_id" not in session_data(client)


@pytest.mark.parametrize("path", ["/login", "/register"])
def test_signed_in_users_are_redirected_from_auth_pages(client, path):
    post_login(client)
    resp = client.get(path)
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/"


def test_signed_in_post_register_does_not_create_user(client, count_users):
    post_login(client)
    before = count_users()
    resp = client.post("/register", data={
        "name": "Someone New",
        "email": "new@example.com",
        "password": "supersecret1",
    })
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/"
    assert count_users() == before


def test_logout_clears_session_and_redirects(client):
    post_login(client)
    resp = client.get("/logout")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/login")
    assert "user_id" not in session_data(client)


def test_logout_shows_message_and_restores_navbar(client):
    post_login(client)
    html = client.get("/logout", follow_redirects=True).get_data(as_text=True)
    assert "You have been signed out" in html
    assert 'class="auth-success"' in html
    assert "Get started" in html
    assert "Sign out" not in html


def test_logout_when_not_signed_in(client):
    resp = client.get("/logout")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/login")
    assert client.get("/login").status_code == 200


def test_session_contains_only_id_and_name(client):
    post_login(client)
    data = session_data(client)
    assert set(data) == {"user_id", "user_name"}
    assert data["user_name"] == "Demo User"
    assert data["user_id"] == db.get_user_by_email(DEMO["email"])["id"]


def test_session_cookie_has_no_sensitive_data(app, client):
    post_login(client)
    raw = client.get_cookie("session").value
    data = app.session_interface.get_signing_serializer(app).loads(raw)
    assert set(data) == {"user_id", "user_name"}
    for secret in ("demo@spendly.com", "demo123", "scrypt", "pbkdf2"):
        assert secret not in str(data)


def test_login_clears_stale_session(client):
    with client.session_transaction() as sess:
        sess["stale"] = "x"
    post_login(client)
    assert "stale" not in session_data(client)


def test_session_cookie_flags(client):
    cookie = post_login(client).headers["Set-Cookie"]
    assert "SameSite=Lax" in cookie
    assert "HttpOnly" in cookie


def test_registered_user_can_login(client):
    client.post("/register", data={
        "name": "Nitish Kumar",
        "email": "Nitish@Example.com",
        "password": "supersecret1",
    })
    resp = post_login(client, email="nitish@example.com", password="supersecret1")
    assert resp.status_code == 302
    assert session_data(client)["user_name"] == "Nitish Kumar"
