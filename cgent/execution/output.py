"""A bounded head/tail byte window for streaming process output."""


class OutputWindow:
    def __init__(self, max_bytes: int) -> None:
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        self._head_limit = max_bytes // 2
        self._tail_limit = max_bytes - self._head_limit
        self._head = bytearray()
        self._tail = bytearray()
        self._total_bytes = 0

    @property
    def truncated(self) -> bool:
        return self._total_bytes > self._head_limit + self._tail_limit

    @property
    def total_bytes(self) -> int:
        return self._total_bytes

    def add(self, data: bytes) -> None:
        self._total_bytes += len(data)
        remaining = data
        if len(self._head) < self._head_limit:
            count = min(self._head_limit - len(self._head), len(remaining))
            self._head.extend(remaining[:count])
            remaining = remaining[count:]
        if remaining:
            self._tail.extend(remaining)
            if len(self._tail) > self._tail_limit:
                del self._tail[: len(self._tail) - self._tail_limit]

    def render(self) -> str:
        head = bytes(self._head).decode("utf-8", errors="replace")
        tail = bytes(self._tail).decode("utf-8", errors="replace")
        if not self.truncated:
            return head + tail
        omitted = self._total_bytes - len(self._head) - len(self._tail)
        return f"{head}\n... [{omitted} bytes truncated] ...\n{tail}"
