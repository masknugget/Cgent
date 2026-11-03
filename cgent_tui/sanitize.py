"""Sanitization for untrusted text shown in the interactive terminal UI.

Agent output, tool names and errors, and server diagnostics are untrusted.
The TUI never renders them through ANSI-parsing APIs; this helper strips the
control characters that could smuggle terminal escape sequences into the
display layer. Newlines and tabs are preserved.

The non-interactive ``run`` stdout path is a script data channel and
intentionally does not sanitize; callers consume it as plain data.
"""

_ALLOWED_CONTROL_CHARS = {"\n", "\t"}


def sanitize_display_text(text: str) -> str:
    """Remove C0/C1 control characters (including ESC) from display text."""
    return "".join(
        char
        for char in text
        if (ord(char) >= 0x20 or char in _ALLOWED_CONTROL_CHARS) and not (0x7F <= ord(char) <= 0x9F)
    )
