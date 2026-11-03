"""Desktop preferences and session history backed by ``QSettings``."""

from __future__ import annotations

import json

from PySide6.QtCore import QByteArray, QSettings

from cgent_desktop.models.session import SessionRecord

__all__ = ["DesktopSettings", "SessionRecord", "MAX_SESSIONS"]

ORG_NAME = "Cgent"
APP_NAME = "cgent-desktop"

KEY_WORKSPACE = "connection/workspace"
KEY_GEOMETRY = "window/geometry"
KEY_SESSIONS = "history/sessions"
MAX_SESSIONS = 200


def _token_count(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


class DesktopSettings:
    """Thin typed wrapper over ``QSettings``; all reads tolerate corruption."""

    def __init__(self, settings: QSettings | None = None) -> None:
        self._settings = settings if settings is not None else QSettings(ORG_NAME, APP_NAME)

    @property
    def workspace_id(self) -> str | None:
        value = self._settings.value(KEY_WORKSPACE, "")
        if isinstance(value, str) and value:
            return value
        return None

    def set_workspace_id(self, workspace_id: str | None) -> None:
        self._settings.setValue(KEY_WORKSPACE, workspace_id or "")

    def geometry(self) -> QByteArray | None:
        value = self._settings.value(KEY_GEOMETRY)
        return value if isinstance(value, QByteArray) and not value.isEmpty() else None

    def set_geometry(self, geometry: QByteArray) -> None:
        self._settings.setValue(KEY_GEOMETRY, geometry)

    def sessions(self) -> list[SessionRecord]:
        raw = self._settings.value(KEY_SESSIONS, "")
        if not isinstance(raw, str) or not raw:
            return []
        try:
            parsed = json.loads(raw)
        except ValueError:
            return []
        if not isinstance(parsed, list):
            return []
        records: list[SessionRecord] = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            prompt = item.get("prompt")
            state = item.get("state")
            started_at = item.get("started_at")
            detail = item.get("detail")
            if not all(isinstance(part, str) for part in (prompt, state, started_at, detail)):
                continue
            records.append(
                SessionRecord(
                    prompt=prompt,
                    state=state,
                    started_at=started_at,
                    detail=detail,
                    input_tokens=_token_count(item.get("input_tokens")),
                    output_tokens=_token_count(item.get("output_tokens")),
                )
            )
        return records

    def add_session(self, record: SessionRecord) -> None:
        self._write_sessions([record, *self.sessions()][:MAX_SESSIONS])

    def delete_session(self, record: SessionRecord) -> bool:
        records = self.sessions()
        try:
            records.remove(record)
        except ValueError:
            return False
        self._write_sessions(records)
        return True

    def _write_sessions(self, records: list[SessionRecord]) -> None:
        payload = [
            {
                "prompt": item.prompt,
                "state": item.state,
                "started_at": item.started_at,
                "detail": item.detail,
                "input_tokens": item.input_tokens,
                "output_tokens": item.output_tokens,
            }
            for item in records
        ]
        self._settings.setValue(KEY_SESSIONS, json.dumps(payload, ensure_ascii=False))
