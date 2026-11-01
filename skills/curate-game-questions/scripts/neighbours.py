"""Maintain local embeddings and find the closest curated questions."""

import argparse
import hashlib
import json
import math
import sqlite3
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DIRECTORY = ROOT / "storage/curated_question_bank"
BANK = DIRECTORY / "questions.json"
DATABASE = DIRECTORY / "embeddings.sqlite3"
MODEL = "text-embedding-3-small"
DIMENSIONS = 1536


def text_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def connect():
    db = sqlite3.connect(DATABASE)
    db.execute("""CREATE TABLE IF NOT EXISTS embeddings (
        text_hash TEXT NOT NULL, model TEXT NOT NULL, dimensions INTEGER NOT NULL,
        vector BLOB NOT NULL, PRIMARY KEY (text_hash, model, dimensions))""")
    db.execute("""CREATE TABLE IF NOT EXISTS bank_vectors (
        question_id TEXT PRIMARY KEY, text_hash TEXT NOT NULL,
        model TEXT NOT NULL, dimensions INTEGER NOT NULL,
        FOREIGN KEY (text_hash, model, dimensions)
          REFERENCES embeddings(text_hash, model, dimensions))""")
    db.execute("PRAGMA foreign_keys = ON")
    return db


def encode(vector):
    if len(vector) != DIMENSIONS or not all(math.isfinite(float(v)) for v in vector):
        raise ValueError("Invalid embedding dimensions or values")
    if not any(vector):
        raise ValueError("Zero embedding")
    return struct.pack(f"<{DIMENSIONS}f", *vector)


def decode(blob):
    if len(blob) != DIMENSIONS * 4:
        raise ValueError("Invalid stored embedding; repair the vector store")
    vector = struct.unpack(f"<{DIMENSIONS}f", blob)
    if not all(math.isfinite(v) for v in vector) or not any(vector):
        raise ValueError("Invalid stored embedding; repair the vector store")
    return vector


def embed(texts):
    from dotenv import load_dotenv
    from openai import OpenAI

    load_dotenv(ROOT / ".env")
    response = OpenAI().embeddings.create(model=MODEL, input=texts, dimensions=DIMENSIONS)
    ordered = sorted(response.data, key=lambda item: item.index)
    if [item.index for item in ordered] != list(range(len(texts))):
        raise ValueError("Embedding response did not cover every question")
    return [encode(item.embedding) for item in ordered]


def ensure_embeddings(db, texts):
    unique = {text_hash(text): text for text in texts}
    missing = []
    for digest, text in unique.items():
        row = db.execute("SELECT vector FROM embeddings WHERE text_hash=? AND model=? AND dimensions=?", (digest, MODEL, DIMENSIONS)).fetchone()
        if row is None:
            missing.append((digest, text))
        else:
            try:
                decode(row[0])
            except ValueError:
                with db:
                    db.execute("DELETE FROM bank_vectors WHERE text_hash=? AND model=? AND dimensions=?", (digest, MODEL, DIMENSIONS))
                    db.execute("DELETE FROM embeddings WHERE text_hash=? AND model=? AND dimensions=?", (digest, MODEL, DIMENSIONS))
                missing.append((digest, text))
    if missing:
        vectors = embed([text for _, text in missing])
        with db:
            db.executemany("INSERT INTO embeddings VALUES (?, ?, ?, ?)",
                           [(digest, MODEL, DIMENSIONS, blob) for (digest, _), blob in zip(missing, vectors, strict=True)])
    return len(missing)


def read_bank():
    bank = json.loads(BANK.read_text(encoding="utf-8"))
    questions = bank["questions"]
    if len({q["id"] for q in questions}) != len(questions):
        raise ValueError("Bank contains duplicate question IDs")
    return questions


def sync(db, questions):
    added = ensure_embeddings(db, [q["text"] for q in questions])
    with db:
        db.execute("DELETE FROM bank_vectors")
        db.executemany("INSERT INTO bank_vectors VALUES (?, ?, ?, ?)",
                       [(q["id"], text_hash(q["text"]), MODEL, DIMENSIONS) for q in questions])
    return added


def search(db, questions, question):
    ensure_embeddings(db, [question])
    query = decode(db.execute("SELECT vector FROM embeddings WHERE text_hash=? AND model=? AND dimensions=?", (text_hash(question), MODEL, DIMENSIONS)).fetchone()[0])
    qnorm = math.sqrt(sum(x*x for x in query))
    neighbours = []
    for item in questions:
        row = db.execute("SELECT e.vector FROM bank_vectors b JOIN embeddings e USING (text_hash, model, dimensions) WHERE b.question_id=? AND b.text_hash=? AND b.model=? AND b.dimensions=?", (item["id"], text_hash(item["text"]), MODEL, DIMENSIONS)).fetchone()
        if row is None:
            raise ValueError("Bank and vector store are out of sync")
        vector = decode(row[0])
        norm = math.sqrt(sum(x*x for x in vector))
        score = sum(a*b for a, b in zip(query, vector, strict=True)) / (qnorm * norm)
        neighbours.append({"id": item["id"], "text": item["text"], "level": item["level"], "similarity": score})
    neighbours.sort(key=lambda item: item["similarity"], reverse=True)
    return neighbours[:5]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question", nargs="?", help="Find closest bank questions to this text")
    parser.add_argument("--sync", action="store_true", help="Populate or repair the bank vector store")
    args = parser.parse_args()
    if not args.question and not args.sync:
        parser.error("provide a question or --sync")
    questions = read_bank()
    with connect() as db:
        added = sync(db, questions)
        if args.question:
            neighbours = search(db, questions, args.question)
            result = {"model": MODEL, "neighbours": neighbours, "bank_embeddings_created": added}
        else:
            result = {"model": MODEL, "dimensions": DIMENSIONS, "bank_questions": len(questions), "bank_embeddings_created": added}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
