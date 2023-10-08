from __future__ import annotations

from io import StringIO
from contextlib import contextmanager

from celadon import Application, Page, Tower, Row, Text, Widget

from slate import Span, Terminal


class SizedTerminal(Terminal):
    stream = StringIO()

    @property
    def size(self) -> tuple[int, int]:
        return 80, 24

    @contextmanager
    def no_echo(self):
        try:
            yield
        finally:
            pass


def _format_lines(lines: list[tuple[Span]]) -> str:
    return "\n" + ",\n".join(
        "(" + ", ".join(map(repr, map(str, line))) + ")" for line in lines
    )


def _as_spans(text: list[tuple[str]]) -> list[tuple[Span]]:
    def _to_span(item: str | Span) -> Span:
        if isinstance(item, Span):
            return item

        return Span(item)

    output = []
    length = len(text)

    for i, line in enumerate(text):
        output.append(tuple(map(_to_span, filter(lambda item: item != "", line))))

    return output


def apply_rules(widget: Widget, rules: str | None = None) -> Widget:
    with Application("Test Runner", terminal=SizedTerminal()) as app:
        app.rule(
            "*",
            content_style="",
            frame_style="",
            fill_style="",
            scrollbar_x_style="",
            scrollbar_y_style="",
        )

        app += Page(Tower(widget), rules=(rules or ""))
        app.timeout(0, lambda: app.stop())

    return widget


def test_widget_alignment() -> None:
    w = apply_rules(
        Text("hello"),
        """
    Text:
        width: 20
        height: 5

        frame: ascii_x
    """,
    )

    w.alignment = ["start", "start"]

    assert (output := w.build()) == _as_spans(
        [
            ("X", "------------------", "X"),
            ("|", "hello             ", "|"),
            ("|", "                  ", "|"),
            ("|", "                  ", "|"),
            ("X", "------------------", "X"),
        ]
    ), _format_lines(output)

    w.alignment = ["center", "center"]

    assert (output := w.build()) == _as_spans(
        [
            ("X", "------------------", "X"),
            ("|", "                  ", "|"),
            ("|", "       ", "hello", "      ", "|"),
            ("|", "                  ", "|"),
            ("X", "------------------", "X"),
        ]
    ), _format_lines(output)

    w.alignment = ["start", "end"]

    assert (output := w.build()) == _as_spans(
        [
            ("X", "------------------", "X"),
            ("|", "                  ", "|"),
            ("|", "                  ", "|"),
            ("|", "hello             ", "|"),
            ("X", "------------------", "X"),
        ]
    ), _format_lines(output)


def test_widget_scrolling() -> None:
    w = apply_rules(
        Text(
            "\n".join("".join(map(lambda i: str(i % 10), range(20))) for _ in range(20))
        ),
        """
        Text:
            width: 20
            height: 10
            overflow: [scroll, scroll]

            frame: ascii_x
        """,
    )

    assert (output := w.build()) == _as_spans(
        [
            ("X", "------------------", "X"),
            ("|", "01234567890123456", "#", "|"),
            ("|", "01234567890123456", "#", "|"),
            ("|", "01234567890123456", "#", "|"),
            ("|", "01234567890123456", "|", "|"),
            ("|", "01234567890123456", "|", "|"),
            ("|", "01234567890123456", "|", "|"),
            ("|", "01234567890123456", "|", "|"),
            ("|", "################- ", "|"),
            ("X", "------------------", "X"),
        ]
    ), _format_lines(output)

    w.scroll_to(y=-1)

    assert (output := w.build()) == _as_spans(
        [
            ("X", "------------------", "X"),
            ("|", "01234567890123456", "|", "|"),
            ("|", "01234567890123456", "|", "|"),
            ("|", "01234567890123456", "|", "|"),
            ("|", "01234567890123456", "|", "|"),
            ("|", "01234567890123456", "|", "|"),
            ("|", "01234567890123456", "#", "|"),
            ("|", "01234567890123456", "#", "|"),
            ("|", "################- ", "|"),
            ("X", "------------------", "X"),
        ]
    ), _format_lines(output)

    w.scroll_to(x=5, y=7)

    assert (output := w.build()) == _as_spans(
        [
            ("X", "------------------", "X"),
            ("|", "34567890123456789", "|", "|"),
            ("|", "34567890123456789", "|", "|"),
            ("|", "34567890123456789", "#", "|"),
            ("|", "34567890123456789", "#", "|"),
            ("|", "34567890123456789", "#", "|"),
            ("|", "34567890123456789", "|", "|"),
            ("|", "34567890123456789", "|", "|"),
            ("|", "-################ ", "|"),
            ("X", "------------------", "X"),
        ]
    ), _format_lines(output)
