"""
CSV Handler
===========
Handles reading and writing of user data CSV files with
deduplication and merge capabilities.
"""

import csv
from datetime import datetime
from pathlib import Path
from typing import Optional


class CSVHandler:
    """Read, write, and manage CSV data files for the automation suite."""

    @staticmethod
    def write_users(
        users: list[dict],
        filepath: str | Path,
        columns: list[str] | None = None,
    ) -> Path:
        """
        Write a list of user dictionaries to a CSV file.

        Args:
            users:    List of dicts, each representing a user.
            filepath: Output file path (supports {timestamp} placeholder).
            columns:  Column order. If None, inferred from first user dict.

        Returns:
            The resolved Path of the written file.
        """
        filepath = str(filepath).replace(
            "{timestamp}",
            datetime.now().strftime("%Y%m%d_%H%M%S"),
        )
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)

        if not users:
            # Write header-only file
            cols = columns or ["username"]
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=cols)
                writer.writeheader()
            return path

        cols = columns or list(users[0].keys())

        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(users)

        return path

    @staticmethod
    def read_users(
        filepath: str | Path,
        username_column: str = "username",
    ) -> list[dict]:
        """
        Read users from a CSV file.

        Args:
            filepath:        Path to the CSV file.
            username_column: Column name that contains the username.

        Returns:
            List of user dictionaries.

        Raises:
            FileNotFoundError: If the CSV doesn't exist.
            ValueError:        If the username column is missing.
        """
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"CSV file not found: {path}")

        with open(path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)

            if reader.fieldnames and username_column not in reader.fieldnames:
                raise ValueError(
                    f"Column '{username_column}' not found. "
                    f"Available: {reader.fieldnames}"
                )

            return list(reader)

    @staticmethod
    def deduplicate(
        users: list[dict],
        key: str = "username",
    ) -> list[dict]:
        """Remove duplicate users based on a key field."""
        seen = set()
        unique = []
        for user in users:
            val = user.get(key, "").strip().lower()
            if val and val not in seen:
                seen.add(val)
                unique.append(user)
        return unique

    @staticmethod
    def append_log_entry(
        log_path: str | Path,
        entry: dict,
    ) -> None:
        """
        Append a single log entry to a CSV log file.
        Creates the file with headers if it doesn't exist.
        """
        path = Path(log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        file_exists = path.exists() and path.stat().st_size > 0

        with open(path, "a", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=list(entry.keys()))
            if not file_exists:
                writer.writeheader()
            writer.writerow(entry)

    @staticmethod
    def get_messaged_users(
        log_path: str | Path,
        username_column: str = "username",
    ) -> set[str]:
        """
        Read the outreach log and return a set of already-messaged usernames.
        Returns an empty set if the log doesn't exist.
        """
        path = Path(log_path)
        if not path.exists():
            return set()

        messaged = set()
        with open(path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                username = row.get(username_column, "").strip().lower()
                status = row.get("status", "").lower()
                if username and status == "sent":
                    messaged.add(username)
        return messaged
