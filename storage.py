import sqlite3
from datetime import date

conn = sqlite3.connect("moneylimit.db", check_same_thread=False)
cursor = conn.cursor()

# ---------- USERS ----------
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    money_left INTEGER NOT NULL,
    days_left INTEGER NOT NULL,
    daily_limit INTEGER NOT NULL,
    today_spent INTEGER NOT NULL,
    last_date TEXT NOT NULL
)
""")

# ---------- STATS ----------
cursor.execute("""
CREATE TABLE IF NOT EXISTS stats (
    key TEXT PRIMARY KEY,
    value INTEGER NOT NULL
)
""")

# ---------- DAILY ACTIVITY (DAU) ----------
cursor.execute("""
CREATE TABLE IF NOT EXISTS daily_activity (
    day TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    PRIMARY KEY (day, user_id)
)
""")

# init counters
for key in ("starts", "spent_actions"):
    cursor.execute(
        "INSERT OR IGNORE INTO stats (key, value) VALUES (?, 0)",
        (key,)
    )

conn.commit()

# ---------- USERS API ----------
def get_user(user_id: int):
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        return None
    return {
        "user_id": row[0],
        "money_left": row[1],
        "days_left": row[2],
        "daily_limit": row[3],
        "today_spent": row[4],
        "last_date": date.fromisoformat(row[5]),
    }


def save_user(user_id: int, data: dict):
    cursor.execute("""
    INSERT OR REPLACE INTO users
    (user_id, money_left, days_left, daily_limit, today_spent, last_date)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        data["money_left"],
        data["days_left"],
        data["daily_limit"],
        data["today_spent"],
        data["last_date"].isoformat()
    ))
    conn.commit()

# ---------- STATS API ----------
def inc_stat(key: str, amount: int = 1):
    cursor.execute(
        "UPDATE stats SET value = value + ? WHERE key = ?",
        (amount, key)
    )
    conn.commit()


def get_stat(key: str) -> int:
    cursor.execute(
        "SELECT value FROM stats WHERE key = ?",
        (key,)
    )
    row = cursor.fetchone()
    return row[0] if row else 0

# ---------- DAILY ACTIVITY ----------
def mark_daily_activity(user_id: int):
    today = date.today().isoformat()
    cursor.execute(
        "INSERT OR IGNORE INTO daily_activity (day, user_id) VALUES (?, ?)",
        (today, user_id)
    )
    conn.commit()


def get_dau(day: str | None = None) -> int:
    if not day:
        day = date.today().isoformat()
    cursor.execute(
        "SELECT COUNT(*) FROM daily_activity WHERE day = ?",
        (day,)
    )
    return cursor.fetchone()[0]
