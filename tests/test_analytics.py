import re

import pytest

DEMO = {"email": "demo@spendly.com", "password": "demo123"}


def login(client):
    return client.post("/login", data=DEMO)


def get_analytics(client):
    resp = client.get("/analytics")
    return resp, resp.get_data(as_text=True)


def analytics_link_tag(html):
    """Return the opening <a ...> tag whose href is /analytics, or None."""
    match = re.search(r'<a\b[^>]*href="/analytics"[^>]*>', html)
    return match.group(0) if match else None


# ---------------------------------------------------------------------------
# Auth guard
# ---------------------------------------------------------------------------

def test_analytics_logged_out_redirects_to_login(client):
    resp = client.get("/analytics")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/login")


def test_analytics_logged_out_follow_redirects_lands_on_login_page(client):
    resp = client.get("/analytics", follow_redirects=True)
    html = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert 'action="/login"' in html
    assert "Coming Soon" not in html


def test_analytics_forged_session_without_user_id_redirects(client):
    with client.session_transaction() as sess:
        sess["user_name"] = "Ghost"
    resp = client.get("/analytics")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/login")


def test_analytics_after_logout_redirects_to_login(client):
    login(client)
    assert client.get("/analytics").status_code == 200
    client.get("/logout")
    resp = client.get("/analytics")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/login")


# ---------------------------------------------------------------------------
# Page content
# ---------------------------------------------------------------------------

def test_analytics_logged_in_returns_200(client):
    login(client)
    resp, _ = get_analytics(client)
    assert resp.status_code == 200


@pytest.mark.parametrize("text", ["Advanced Analytics", "Coming Soon"])
def test_analytics_page_contains_headline_text(client, text):
    login(client)
    _, html = get_analytics(client)
    assert text in html


def test_analytics_page_contains_crafting_message(client):
    login(client)
    _, html = get_analytics(client)
    assert (
        "We're crafting something special" in html
        or "We&#39;re crafting something special" in html
        or "We&#34;re crafting something special" in html
        or "crafting something special" in html
    )


def test_analytics_page_contains_description_text(client):
    login(client)
    _, html = get_analytics(client)
    assert "powerful insights and visualizations" in html


def test_analytics_page_title_contains_analytics(client):
    login(client)
    _, html = get_analytics(client)
    match = re.search(r"<title>(.*?)</title>", html, re.S | re.I)
    assert match, "Expected a <title> element"
    assert "Analytics" in match.group(1)


def test_analytics_page_heading_is_h1(client):
    login(client)
    _, html = get_analytics(client)
    match = re.search(r"<h1\b[^>]*>(.*?)</h1>", html, re.S | re.I)
    assert match, "Expected an <h1> element"
    assert "Advanced Analytics" in match.group(1)


def test_analytics_page_links_analytics_stylesheet(client):
    login(client)
    _, html = get_analytics(client)
    assert "css/analytics.css" in html


def test_analytics_page_extends_base_layout(client):
    login(client)
    _, html = get_analytics(client)
    assert "Spendly" in html
    assert "<nav" in html
    assert "<footer" in html


# ---------------------------------------------------------------------------
# Navbar: visibility
# ---------------------------------------------------------------------------

def test_navbar_signed_in_shows_analytics_link_on_profile(client):
    login(client)
    html = client.get("/profile").get_data(as_text=True)
    tag = analytics_link_tag(html)
    assert tag is not None, "Expected Analytics link on /profile"
    assert "nav-analytics" in tag
    assert "Analytics" in html


@pytest.mark.parametrize("path", ["/", "/login", "/register", "/terms"])
def test_navbar_signed_out_hides_analytics_link(client, path):
    resp = client.get(path)
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'href="/analytics"' not in html


# ---------------------------------------------------------------------------
# Navbar: active state
# ---------------------------------------------------------------------------

def test_navbar_analytics_link_active_on_analytics_page(client):
    login(client)
    _, html = get_analytics(client)
    tag = analytics_link_tag(html)
    assert tag is not None, "Expected Analytics link on /analytics"
    assert "nav-analytics" in tag
    assert "nav-link--active" in tag
    assert 'aria-current="page"' in tag


def test_navbar_analytics_link_not_active_on_profile(client):
    login(client)
    html = client.get("/profile").get_data(as_text=True)
    tag = analytics_link_tag(html)
    assert tag is not None
    assert "nav-link--active" not in tag
    assert 'aria-current="page"' not in tag


# ---------------------------------------------------------------------------
# Navbar: no regressions
# ---------------------------------------------------------------------------

def test_navbar_user_link_and_sign_out_still_present_on_analytics(client):
    login(client)
    _, html = get_analytics(client)
    assert 'href="/profile" class="nav-user"' in html
    assert "Sign out" in html
    assert "Demo User" in html
