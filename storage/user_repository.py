"""JSON-backed storage for user identities."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional

from models import UserAccount


class UserRepository:
    """Very small helper around a JSON file storing user accounts."""

    def __init__(self, storage_path: Optional[Path] = None) -> None:
        default_path = Path(__file__).resolve().parent / "users.json"
        self.storage_path = storage_path or default_path
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

    def get_by_email(self, email: str) -> Optional[UserAccount]:
        if not email:
            return None
        normalized = email.strip().lower()
        data = self._load()
        payload = data.get(normalized)
        return UserAccount.from_dict(payload) if payload else None

    def save(self, account: UserAccount) -> None:
        data = self._load()
        data[account.email.lower()] = account.to_dict()
        self._write(data)

    def list_accounts(self) -> Dict[str, UserAccount]:
        return {email: UserAccount.from_dict(payload) for email, payload in self._load().items()}

    def _load(self) -> Dict[str, Dict[str, str]]:
        if not self.storage_path.exists():
            return {}
        with self.storage_path.open("r", encoding="utf-8") as fh:
            raw = json.load(fh)
        if isinstance(raw, list):
            # legacy format: list of accounts
            result: Dict[str, Dict[str, str]] = {}
            for entry in raw:
                if "email" in entry:
                    result[entry["email"].lower()] = entry
            return result
        return {email.lower(): payload for email, payload in raw.items()}

    def _write(self, data: Dict[str, Dict[str, str]]) -> None:
        with self.storage_path.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
