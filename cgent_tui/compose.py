"""Prompt composition: positional arguments plus optional piped stdin.

The ``<stdin>`` marker only organizes content; it is not a prompt-injection
boundary. Stdin is read only when it is a pipe or a redirected file, decoded
strictly as UTF-8, and capped at 10 MiB.
"""

import sys
from typing import BinaryIO, Protocol

MAX_STDIN_BYTES = 10 * 1024 * 1024


class PipedStdin(Protocol):
    """Minimal stdin surface the composer needs."""

    def isatty(self) -> bool: ...

    @property
    def buffer(self) -> BinaryIO: ...


STDIN_OPEN = "<stdin>"
STDIN_CLOSE = "</stdin>"


class ComposeError(Exception):
    """Invalid prompt input; maps to exit code 2."""


def read_piped_stdin(stream: PipedStdin | None = None) -> str | None:
    """Read piped stdin, or return None when stdin is an interactive TTY.

    The returned text is guaranteed to be valid decoded text; decoding errors
    and oversized input raise ComposeError instead of producing silent output.
    """
    source: PipedStdin = sys.stdin if stream is None else stream
    try:
        if source.isatty():
            return None
    except (AttributeError, OSError):
        return None
    buffer: BinaryIO = source.buffer
    raw = buffer.read(MAX_STDIN_BYTES + 1)
    if len(raw) > MAX_STDIN_BYTES:
        raise ComposeError(f"stdin exceeds the {MAX_STDIN_BYTES} byte limit")
    try:
        return raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ComposeError(f"stdin is not valid UTF-8: {exc}") from exc


def compose_prompt(prompt: str, stdin_text: str | None) -> str | None:
    """Combine the positional prompt and piped stdin into one prompt.

    Returns None when both are empty. An empty or whitespace-only stdin
    contributes no ``<stdin>`` block.
    """
    parts: list[str] = []
    prompt = prompt.strip()
    if prompt:
        parts.append(prompt)
    stdin_block: str | None = None
    if stdin_text is not None and stdin_text.strip():
        stdin_block = f"{STDIN_OPEN}\n{stdin_text.rstrip()}\n{STDIN_CLOSE}"
        parts.append(stdin_block)
    if not parts:
        return None
    return "\n\n".join(parts)
