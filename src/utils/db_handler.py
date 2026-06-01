import sqlite3
from typing import List, Dict, Any
from pathlib import Path
from loguru import logger

class DatabaseHandler:
    def __init__(self, db_path: str = "./data/real_estate.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            # HACK: Using ON CONFLICT REPLACE for simplistic upserts.
            # In a real distributed system (e.g., Postgres), we'd use ON CONFLICT DO UPDATE.
            conn.execute('''
                CREATE TABLE IF NOT EXISTS leads (
                    username TEXT PRIMARY KEY,
                    display_name TEXT,
                    profile_url TEXT,
                    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'pending'
                )
            ''')
            # Optimize lookups for the outreach queue
            conn.execute('CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status)')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS outreach_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT,
                    status TEXT,
                    error_msg TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(username) REFERENCES leads(username)
                )
            ''')

    def save_leads(self, leads: List[Dict[str, Any]]):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            for lead in leads:
                cursor.execute('''
                    INSERT INTO leads (username, display_name, profile_url)
                    VALUES (?, ?, ?)
                    ON CONFLICT(username) DO UPDATE SET 
                        display_name=excluded.display_name,
                        profile_url=excluded.profile_url
                ''', (lead.get("username"), lead.get("display_name"), lead.get("profile_url")))
            logger.info(f"Persisted {len(leads)} leads to database.")

    def get_pending_leads(self) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM leads WHERE status = 'pending'")
            return [dict(row) for row in cursor.fetchall()]

    def log_outreach(self, username: str, status: str, error_msg: str = ""):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT INTO outreach_logs (username, status, error_msg)
                VALUES (?, ?, ?)
            ''', (username, status, error_msg))
            
            if status == "sent":
                conn.execute("UPDATE leads SET status = 'contacted' WHERE username = ?", (username,))
            elif status == "rate_limited" or status == "failed":
                conn.execute("UPDATE leads SET status = 'failed' WHERE username = ?", (username,))
