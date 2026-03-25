import sqlite3
import os
from datetime import datetime

DB_PATH = os.getenv("DB_PATH", "alerts.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_type TEXT,
            camera_id TEXT,
            details TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def save_alert(alert_type, camera_id, details):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO alerts (alert_type, camera_id, details) VALUES (?, ?, ?)",
        (alert_type, camera_id, details)
    )
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print(f"[*] Database initialized at {DB_PATH}")
