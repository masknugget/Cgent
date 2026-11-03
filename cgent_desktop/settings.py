"""Desktop preferences and session history backed by ``QSettings``."""

from __future__ import annotations

import json
from dataclasses import replace
from uuid import uuid4

from PySide6.QtCore import QByteArray, QSettings, QSize

from cgent_desktop.models.session import SessionRecord

__all__ = ["DesktopSettings", "SessionRecord", "MAX_SESSIONS"]

ORG_NAME = "Cgent"
APP_NAME = "cgent-desktop"

KEY_WORKSPACE = "connection/workspace"
KEY_GEOMETRY = "window/geometry"
KEY_SESSIONS = "history/sessions"
KEY_WORKSPACE_PANEL_VISIBLE = "workspacePanel/visible"
KEY_WORKSPACE_PANEL_WIDTH = "workspacePanel/width"
KEY_FILE_PREVIEW_SIZE = "filePreview/size"
MAX_SESSIONS = 200
DEFAULT_WORKSPACE_PANEL_WIDTH = 300
MIN_WORKSPACE_PANEL_WIDTH = 220
MAX_WORKSPACE_PANEL_WIDTH = 480


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

    def workspace_panel_visible(self) -> bool:
        value = self._settings.value(KEY_WORKSPACE_PANEL_VISIBLE, True)
        if isinstance(value, bool):
            return value
        return str(value).lower() not in {"0", "false", "no", "off"}

    def set_workspace_panel_visible(self, visible: bool) -> None:
        self._settings.setValue(KEY_WORKSPACE_PANEL_VISIBLE, visible)

    def workspace_panel_width(self) -> int:
        value = self._settings.value(KEY_WORKSPACE_PANEL_WIDTH, DEFAULT_WORKSPACE_PANEL_WIDTH)
        try:
            width = int(value)
        except (TypeError, ValueError):
            width = DEFAULT_WORKSPACE_PANEL_WIDTH
        return max(MIN_WORKSPACE_PANEL_WIDTH, min(MAX_WORKSPACE_PANEL_WIDTH, width))

    def set_workspace_panel_width(self, width: int) -> None:
        width = max(MIN_WORKSPACE_PANEL_WIDTH, min(MAX_WORKSPACE_PANEL_WIDTH, width))
        self._settings.setValue(KEY_WORKSPACE_PANEL_WIDTH, width)

    def file_preview_size(self) -> QSize | None:
        value = self._settings.value(KEY_FILE_PREVIEW_SIZE)
        if isinstance(value, QSize) and 480 <= value.width() <= 3840:
            if 320 <= value.height() <= 2160:
                return value
        return None

    def set_file_preview_size(self, size: QSize) -> None:
        if size.isValid():
            self._settings.setValue(KEY_FILE_PREVIEW_SIZE, size)

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
        migrated = False
        for item in parsed:
            if not isinstance(item, dict):
                continue
            prompt = item.get("prompt")
            state = item.get("state")
            started_at = item.get("started_at")
            detail = item.get("detail")
            if not all(isinstance(part, str) for part in (prompt, state, started_at, detail)):
                continue
            title = item.get("title")
            if not isinstance(title, str):
                title = ""
            session_id = item.get("session_id")
            if not isinstance(session_id, str) or not session_id:
                session_id = uuid4().hex
                migrated = True
            records.append(
                SessionRecord(
                    prompt=prompt,
                    state=state,
                    started_at=started_at,
                    detail=detail,
                    input_tokens=_token_count(item.get("input_tokens")),
                    output_tokens=_token_count(item.get("output_tokens")),
                    title=title,
                    session_id=session_id,
                )
            )
        if migrated:
            self._write_sessions(records)
        return records

    def add_session(self, record: SessionRecord) -> None:
        if not record.session_id:
            record = replace(record, session_id=uuid4().hex)
        self._write_sessions([record, *self.sessions()][:MAX_SESSIONS])

    def rename_session(self, session_id: str, title: str) -> bool:
        title = title.strip()
        if not title:
            return False
        records = self.sessions()
        renamed = False
        updated: list[SessionRecord] = []
        for record in records:
            if record.session_id == session_id:
                record = replace(record, title=title)
                renamed = True
            updated.append(record)
        return renamed and self._write_sessions(updated)

    def delete_session(self, session_id: str) -> bool:
        records = self.sessions()
        remaining = [record for record in records if record.session_id != session_id]
        if len(remaining) == len(records):
            return False
        return self._write_sessions(remaining)

    def _write_sessions(self, records: list[SessionRecord]) -> bool:
        payload = [
            {
                "prompt": item.prompt,
                "state": item.state,
                "started_at": item.started_at,
                "detail": item.detail,
                "input_tokens": item.input_tokens,
                "output_tokens": item.output_tokens,
                "title": item.title,
                "session_id": item.session_id,
            }
            for item in records
        ]
        self._settings.setValue(KEY_SESSIONS, json.dumps(payload, ensure_ascii=False))
        self._settings.sync()
        return self._settings.status() == QSettings.Status.NoError
