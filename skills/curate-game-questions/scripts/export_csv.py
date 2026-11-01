"""Refresh the readable CSV export from the canonical JSON question bank."""

import csv
import json
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DIRECTORY = ROOT / "storage/curated_question_bank"
FIELDS = ("id", "text", "level", "themes", "approved_at")


def main():
    bank = json.loads((DIRECTORY / "questions.json").read_text(encoding="utf-8"))
    target = DIRECTORY / "questions.csv"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", newline="", dir=DIRECTORY, delete=False
        ) as output:
            temporary = Path(output.name)
            writer = csv.DictWriter(output, fieldnames=FIELDS)
            writer.writeheader()
            for question in bank["questions"]:
                writer.writerow({**question, "themes": "; ".join(question["themes"])})
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    print(f"Exported {len(bank['questions'])} questions to {target}")


if __name__ == "__main__":
    main()
