"""Read-only query helpers for the profile page.

Pure data access — no Flask imports. Every helper opens its own connection
with get_db() and closes it before returning.
"""
from datetime import datetime

from database.db import get_db

# Optional inclusive date bounds (YYYY-MM-DD strings or None). Appended after
# "WHERE user_id = ?" and bound with _range_params() — values never touch the SQL.
_DATE_RANGE_SQL = " AND (? IS NULL OR date >= ?) AND (? IS NULL OR date <= ?)"


def _range_params(start_date, end_date):
    return (start_date, start_date, end_date, end_date)


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

def get_summary_stats(user_id, start_date=None, end_date=None):
    """Return {total_spent, transaction_count, top_category} for user_id,
    optionally limited to expenses dated within [start_date, end_date]."""
    params = (user_id, *_range_params(start_date, end_date))
    conn = get_db()
    try:
        totals = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS cnt "
            "FROM expenses WHERE user_id = ?" + _DATE_RANGE_SQL,
            params,
        ).fetchone()
        top = conn.execute(
            "SELECT category FROM expenses WHERE user_id = ?" + _DATE_RANGE_SQL
            + " GROUP BY category ORDER BY SUM(amount) DESC, category ASC "
            "LIMIT 1",
            params,
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

def get_recent_transactions(user_id, limit=10, start_date=None, end_date=None):
    """Return up to limit expenses for user_id, newest first, optionally
    limited to expenses dated within [start_date, end_date]."""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT id, date, description, category, amount FROM expenses "
            "WHERE user_id = ?" + _DATE_RANGE_SQL
            + " ORDER BY date DESC, id DESC LIMIT ?",
            (user_id, *_range_params(start_date, end_date), limit),
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "id": row["id"],
            "date": row["date"],
            "description": row["description"] or "",
            "category": row["category"],
            "amount": row["amount"],
        }
        for row in rows
    ]


def get_expense(expense_id, user_id):
    """Return one expense if user_id owns expense_id, else None.

    Not found and not owned look the same, so callers can't tell them apart.
    """
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id, amount, category, date, description FROM expenses "
            "WHERE id = ? AND user_id = ?",
            (expense_id, user_id),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return {
        "id": row["id"],
        "amount": row["amount"],
        "category": row["category"],
        "date": row["date"],
        "description": row["description"] or "",
    }


# ------------------------------------------------------------------ #
# Category breakdown                                                  #
# ------------------------------------------------------------------ #

def get_category_breakdown(user_id, start_date=None, end_date=None):
    """Return [{name, amount, pct}] for user_id, largest amount first,
    optionally limited to expenses dated within [start_date, end_date]."""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT category, SUM(amount) AS total FROM expenses "
            "WHERE user_id = ?" + _DATE_RANGE_SQL
            + " GROUP BY category ORDER BY total DESC, category ASC",
            (user_id, *_range_params(start_date, end_date)),
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
