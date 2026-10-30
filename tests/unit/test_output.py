from cgent.execution.output import OutputWindow


def test_output_window_keeps_complete_small_output() -> None:
    window = OutputWindow(10)
    window.add(b"hello")

    assert window.render() == "hello"
    assert not window.truncated


def test_output_window_keeps_head_and_tail_when_truncated() -> None:
    window = OutputWindow(10)
    window.add(b"0123456789abcdefghij")

    rendered = window.render()
    assert rendered.startswith("01234")
    assert rendered.endswith("fghij")
    assert "[10 bytes truncated]" in rendered
    assert window.truncated
    assert window.total_bytes == 20
