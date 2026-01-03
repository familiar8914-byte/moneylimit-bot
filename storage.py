import sqlite3
from datetime import date

conn = sqlite3.connect("moneylimit.db", check_same_thread=False)
cursor = conn.cursor()

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
conn.commit()


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