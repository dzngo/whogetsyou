"""File-system backed repository for persisting Room entities."""

from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Dict, List, Optional
import streamlit as st

from models import Room


@st.cache_resource(show_spinner=False)  # type: ignore[arg-type]
def _shared_room_lock() -> Lock:
    return Lock()


class RoomRepository:
    """Very small JSON-based repository used during the early iterations."""

    def __init__(self, storage_path: Optional[Path] = None) -> None:
        default_path = Path(__file__).resolve().parent / "rooms.json"
        self.storage_path = storage_path or default_path
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = _shared_room_lock()

    def list_rooms(self) -> List[Room]:
        with self._lock:
            return list(self._load().values())

    def get_by_code(self, room_code: str) -> Optional[Room]:
        with self._lock:
            return self._load().get(room_code.upper())

    def get_by_name(self, name: str) -> Optional[Room]:
        normalized = name.strip().lower()
        with self._lock:
            for room in self._load().values():
                if room.name.strip().lower() == normalized:
                    return room
        return None

    def save(self, room: Room) -> None:
        with self._lock:
            rooms = self._load()
            rooms[room.room_code.upper()] = room
            self._write(rooms)

    def delete(self, room_code: str) -> None:
        with self._lock:
            rooms = self._load()
            key = room_code.upper()
            if key in rooms:
                del rooms[key]
                self._write(rooms)

    def _load(self) -> Dict[str, Room]:
        if not self.storage_path.exists():
            return {}
        with self.storage_path.open("r", encoding="utf-8") as fh:
            raw = json.load(fh)
        rooms: Dict[str, Room] = {}
        for payload in raw:
            room = Room.from_dict(payload)
            rooms[room.room_code.upper()] = room
        return rooms

    def _write(self, rooms: Dict[str, Room]) -> None:
        data = [room.to_dict() for room in rooms.values()]
        with self.storage_path.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
