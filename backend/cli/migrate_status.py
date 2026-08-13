"""Usage: python migrate_status.py

One-off migration: renames session status "completed" to "processed" to
match the standardised terminal status used across app/api/routes/sheets.py
and models/schemas.py.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.db import get_sync_db  # noqa: E402


def main() -> None:
    db = get_sync_db()
    result = db.sessions.update_many(
        {"status": "completed"}, {"$set": {"status": "processed"}}
    )
    print(f"Matched {result.matched_count}, updated {result.modified_count} session(s).")


if __name__ == "__main__":
    main()
