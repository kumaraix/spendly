"""Read-only query helpers for the profile page.

Pure data access — no Flask imports. Every helper opens its own connection
with get_db() and closes it before returning.
"""
from datetime import datetime

from database.db import get_db


def get_user_by_id(user_id):
    """Return {name, email, member_since} for user_id, or None."""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT name, email, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    created = datetime.strptime(row["created_at"][:10], "%Y-%m-%d")
    return {
        "name": row["name"],
        "email": row["email"],
        "member_since": created.strftime("%B %Y"),
    }


# ------------------------------------------------------------------ #
# Summary stats                                                       #
# ------------------------------------------------------------------ #

def get_summary_stats(user_id):
    """Return {total_spent, transaction_count, top_category} for user_id."""
    conn = get_db()
    try:
        totals = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS cnt "
            "FROM expenses WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        top = conn.execute(
            "SELECT category FROM expenses WHERE user_id = ? "
            "GROUP BY category ORDER BY SUM(amount) DESC, category ASC "
            "LIMIT 1",
            (user_id,),
        ).fetchone()
    finally:
        conn.close()
    if totals["cnt"] == 0:
        return {"total_spent": 0, "transaction_count": 0, "top_category": "—"}
    return {
        "total_spent": round(float(totals["total"]), 2),
        "transaction_count": totals["cnt"],
        "top_category": top["category"],
    }


# ------------------------------------------------------------------ #
# Transaction history                                                 #
# ------------------------------------------------------------------ #

def get_recent_transactions(user_id, limit=10):
    """Return up to limit expenses for user_id, newest first."""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT date, description, category, amount FROM expenses "
            "WHERE user_id = ? ORDER BY date DESC, id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "date": row["date"],
            "description": row["description"] or "",
            "category": row["category"],
            "amount": row["amount"],
        }
        for row in rows
    ]


# ------------------------------------------------------------------ #
# Category breakdown                                                  #
# ------------------------------------------------------------------ #

def get_category_breakdown(user_id):
    """Return [{name, amount, pct}] for user_id, largest amount first."""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT category, SUM(amount) AS total FROM expenses "
            "WHERE user_id = ? GROUP BY category "
            "ORDER BY total DESC, category ASC",
            (user_id,),
        ).fetchall()
    finally:
        conn.close()

    grand_total = sum(row["total"] for row in rows)
    if not rows or grand_total <= 0:
        return []

    breakdown = [
        {
            "name": row["category"],
            "amount": round(float(row["total"]), 2),
            "pct": round(row["total"] / grand_total * 100),
        }
        for row in rows
    ]
    # Absorb rounding drift into the largest category so pcts sum to 100.
    breakdown[0]["pct"] += 100 - sum(item["pct"] for item in breakdown)
    return breakdown
