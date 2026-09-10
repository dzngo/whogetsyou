"""Count saved question texts without counting reprocessing copies twice."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

# Direct file execution puts question_bank/, not the project root, on sys.path.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from question_bank.semantic import normalize_question


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog="A question matches a status if any saved copy has that status.",
    )
    parser.add_argument(
        "--filter", default="all",
        choices=("all", "staged", "rejected", "operationally_unresolved",
                 "awaiting_human_review", "proposed"),
    )
    parser.add_argument(
        "--database", type=Path,
        default=Path("storage/question_bank_v2/question_bank_v2.sqlite3"),
    )
    args = parser.parse_args()
    try:
        db = sqlite3.connect(args.database.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            rows = db.execute(
                "SELECT text, level FROM candidates WHERE ? = 'all' OR state = ?",
                (args.filter, args.filter),
            ).fetchall()
        finally:
            db.close()
    except sqlite3.Error as error:
        parser.exit(1, f"Cannot read question bank: {error}\n")

    unique = {normalize_question(text) for text, _ in rows}
    print(f"{args.filter}: {len(unique)} unique questions ({len(rows)} saved records)")
    for level in ("shallow", "deep"):
        count = len({normalize_question(text) for text, value in rows if value == level})
        print(f"  {level}: {count}")


if __name__ == "__main__":
    main()
