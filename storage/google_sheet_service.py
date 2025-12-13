"""Lightweight helper to append rows to a Google Sheet."""

from __future__ import annotations

import json
import os
from datetime import datetime
from functools import lru_cache
from typing import Any, Dict, List, Optional

import gspread
import streamlit as st
from gspread.exceptions import APIError, SpreadsheetNotFound
from google.oauth2.service_account import Credentials


class GoogleSheetServiceError(Exception):
    """Raised when Google Sheets operations fail."""


def _load_credentials() -> Dict[str, Any]:
    """Load service account credentials from Streamlit secrets or environment."""
    secret_blob = st.secrets.get("GCP_CREDENTIALS")
    if secret_blob:
        if isinstance(secret_blob, str):
            return json.loads(secret_blob)
        return dict(secret_blob)
    env_blob = os.getenv("GCP_CREDENTIALS")
    if env_blob:
        return json.loads(env_blob)
    raise GoogleSheetServiceError("GCP_CREDENTIALS not configured in secrets or environment.")


def _load_sheet_url() -> str:
    secret_url = st.secrets.get("FEEDBACK_GOOGLE_SHEET_URL")
    if secret_url:
        return str(secret_url)
    env_url = os.getenv("FEEDBACK_GOOGLE_SHEET_URL")
    if env_url:
        return env_url
    raise GoogleSheetServiceError("FEEDBACK_GOOGLE_SHEET_URL not configured in secrets or environment.")


@lru_cache(maxsize=1)
def _authorize_client() -> gspread.Client:
    service_account_info = _load_credentials()
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(service_account_info, scopes=scopes)
    return gspread.authorize(creds)


class GoogleSheetService:
    HEADERS = ["date", "user", "question", "theme", "level", "action", "reason"]

    def __init__(self) -> None:
        client = _authorize_client()
        sheet_url = _load_sheet_url()
        try:
            self.worksheet = client.open_by_url(sheet_url).sheet1
        except SpreadsheetNotFound as exc:
            raise GoogleSheetServiceError(
                "Google Sheet not found or inaccessible. Share it with the service account email."
            ) from exc
        except APIError as exc:
            raise GoogleSheetServiceError(f"Google Sheets API error: {exc}") from exc
        self._ensure_header()

    def append_feedback(
        self,
        *,
        user: str,
        question: str,
        theme: str,
        level: str,
        action: str,
        reason: Optional[str] = None,
    ) -> None:
        row: List[Any] = [
            datetime.utcnow().isoformat(),
            user,
            question,
            theme,
            level,
            action,
            reason or "",
        ]
        try:
            self.worksheet.append_row(row, value_input_option="USER_ENTERED")
        except APIError as exc:
            raise GoogleSheetServiceError(f"Unable to append feedback to Google Sheet: {exc}") from exc

    def _ensure_header(self) -> None:
        try:
            existing = self.worksheet.row_values(1)
        except APIError as exc:
            raise GoogleSheetServiceError(f"Google Sheets API error: {exc}") from exc
        expected = [header.lower() for header in self.HEADERS]
        normalized_existing = [value.strip().lower() for value in existing]
        if normalized_existing[: len(expected)] != expected:
            self.worksheet.update("A1", [self.HEADERS])
