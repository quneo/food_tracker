"""Consistent online copy of the SQLite database: python -m app.backup [directory]

Uses SQLite's backup API, so it is safe while the app is running. Keeps the newest
BACKUP_KEEP copies (14 by default)."""

import os
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

from app.config import get_settings


def main():
    source = get_settings().database_url.removeprefix("sqlite:///")
    target_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "/data/backups")
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    target = target_dir / f"food-{stamp}.db"
    db, copy = sqlite3.connect(source), sqlite3.connect(target)
    try:
        db.backup(copy)
    finally:
        copy.close()
        db.close()
    keep = int(os.environ.get("BACKUP_KEEP", "14"))
    copies = sorted(target_dir.glob("food-*.db"))
    for old in copies[:-keep]:
        old.unlink()
    print(target)


if __name__ == "__main__":
    main()
