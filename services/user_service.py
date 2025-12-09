"""Simple user identity service backed by UserRepository."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Optional

from models import UserAccount
from storage.user_repository import UserRepository


class UserAlreadyExistsError(Exception):
    """Raised when an email is already associated with a different user."""


class UserNotFoundError(Exception):
    """Raised when no account exists for the requested email."""


class UserService:
    def __init__(self, repository: Optional[UserRepository] = None) -> None:
        self.repository = repository or UserRepository()

    def get(self, email: str) -> Optional[UserAccount]:
        return self.repository.get_by_email(email.strip().lower())

    def create(self, email: str, name: str) -> UserAccount:
        normalized_email = email.strip().lower()
        existing = self.get(normalized_email)
        if existing:
            raise UserAlreadyExistsError(existing)
        account = UserAccount(email=normalized_email, name=name.strip(), created_at=datetime.utcnow())
        self.repository.save(account)
        return account

    def ensure_account(self, email: str, name: str) -> UserAccount:
        existing = self.get(email)
        if existing:
            return existing
        return self.create(email, name)

    def update_name(self, email: str, name: str) -> UserAccount:
        account = self.get(email)
        if not account:
            raise UserNotFoundError(email)
        account.name = name.strip()
        self.repository.save(account)
        return account

    @staticmethod
    def serialize(account: UserAccount) -> dict:
        payload = asdict(account)
        payload["created_at"] = account.created_at.isoformat()
        return payload
