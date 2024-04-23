from __future__ import annotations

from io import StringIO
from contextlib import contextmanager

from celadon import Application, Page, Tower, Row, Text, Widget

from slate import Span, Terminal, Color
from zenith import zml_get_spans


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


def test_widget_slice_line() -> None:
    w = Widget()

    spans = zml_get_spans("[blue]tes[@red]t[/ blue] content")
    sliced = w._slice_line(spans, 0, 3)
    assert sliced == (Span("tes", reset_after=True, foreground=Color(rgb=(0, 0, 255))),)


def test_widget_selection() -> None:
    w = Widget()
    assert w._selected_index is None
    assert w.state == "idle"

    w.select(1)
    assert w._selected_index == 0
    assert w.selected is w
    assert w.state == "selected"

    target = Widget()

    w = Tower(Widget(), Widget(), target, Widget())

    w.select(0)
    assert w._selected_index is None

    w.select(3)
    assert w._selected_index == 3
    assert w.selected is target

    nested_target = Widget()
    target = Tower(Widget(), nested_target, Widget())
    outer_target = Widget()
    w = Tower(Widget(), outer_target, target, Widget())

    w.select(4)
    assert w.selected is target
    assert w.selected.selected is nested_target
    assert w.state == "selected"

    w.select(2)
    assert w.selected is outer_target
    assert w.state == "selected"
