import pytest
from gunmetal import Span

from celadon import Alignment, Overflow, Widget, frames

EMPTY_STYLEMAP = {
    "idle": {
        "fill": "",
        "frame": "",
        "content": "",
        "scrollbar_x": "",
        "scrollbar_y": "",
    },
    "hover": {
        "fill": "",
        "frame": "",
        "content": "",
        "scrollbar_x": "",
        "scrollbar_y": "",
    },
    "selected": {
        "fill": "",
        "frame": "",
        "content": "",
        "scrollbar_x": "",
        "scrollbar_y": "",
    },
    "active": {
        "fill": "",
        "frame": "",
        "content": "",
        "scrollbar_x": "",
        "scrollbar_y": "",
    },
}


class TextWidget(Widget):
    style_map = EMPTY_STYLEMAP

    def __init__(self, text: str) -> None:
        self.text = text

        super().__init__(width=20, height=5, frame="ASCII_X", overflow=("hide", "hide"))

    def get_content(self) -> list[str]:
        return self.text.splitlines()


class ScrollingWidget(Widget):
    style_map = EMPTY_STYLEMAP

    def __init__(self) -> None:
        super().__init__(width=20, height=20, frame="Light", overflow=("hide", "hide"))

        self.overflow = ("scroll", "scroll")

    def get_content(self) -> list[str]:
        return [
            "".join(str(i)[-1] for i in range(self.width + 10))
            for _ in range(self.height + 10)
        ]


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


def _print_widget(lines: list[tuple[Span]]) -> str:
    return "\n" + ",\n".join(
        "(" + ", ".join(map(repr, map(str, line))) + ")" for line in lines
    )


def test_widget_alignments():
    w = TextWidget("start-start")
    w.alignment = ("start", "start")

    assert (output := w.build()) == _as_spans(
        [
            ("X", "------------------", "X"),
            ("|", "start-start       ", "|"),
            ("|", "                  ", "|"),
            ("|", "                  ", "|"),
            ("X", "------------------", "X"),
        ]
    ), _print_widget(output)

    w = TextWidget("center-end")
    w.alignment = (Alignment.CENTER, Alignment.END)

    assert (output := w.build()) == _as_spans(
        [
            ("X", "------------------", "X"),
            ("|", "                  ", "|"),
            ("|", "                  ", "|"),
            ("|", "    ", "center-end", "    ", "|"),
            ("X", "------------------", "X"),
        ]
    ), _print_widget(output)

    w = TextWidget("end-center")
    w.alignment = ("end", "center")

    assert w.build() == _as_spans(
        [
            ("X", "------------------", "X"),
            ("|", "                  ", "|"),
            ("|", "        end-center", "|"),
            ("|", "                  ", "|"),
            ("X", "------------------", "X"),
        ]
    )


def test_widget_scrollbars():
    w = ScrollingWidget()

    assert (output := w.build()) == _as_spans(
        [
            ("┌", "──────────────────", "", "┐"),
            ("│", "01234567890123456", "█", "│"),
            ("│", "01234567890123456", "█", "│"),
            ("│", "01234567890123456", "█", "│"),
            ("│", "01234567890123456", "█", "│"),
            ("│", "01234567890123456", "█", "│"),
            ("│", "01234567890123456", "█", "│"),
            ("│", "01234567890123456", "█", "│"),
            ("│", "01234567890123456", "█", "│"),
            ("│", "01234567890123456", "█", "│"),
            ("│", "01234567890123456", "█", "│"),
            ("│", "01234567890123456", "█", "│"),
            ("│", "01234567890123456", " ", "│"),
            ("│", "01234567890123456", " ", "│"),
            ("│", "01234567890123456", " ", "│"),
            ("│", "01234567890123456", " ", "│"),
            ("│", "01234567890123456", " ", "│"),
            ("│", "01234567890123456", " ", "│"),
            ("│", "▅▅▅▅▅▅▅▅▅▅▅       ", "", "│"),
            ("└", "──────────────────", "", "┘"),
        ],
    ), _print_widget(output)

    w.overflow = ("hide", "scroll")

    assert (output := w.build()) == _as_spans(
        [
            ("┌", "──────────────────", "", "┐"),
            ("│", "01234567890123456", "█", "│"),
            ("│", "01234567890123456", "█", "│"),
            ("│", "01234567890123456", "█", "│"),
            ("│", "01234567890123456", "█", "│"),
            ("│", "01234567890123456", "█", "│"),
            ("│", "01234567890123456", "█", "│"),
            ("│", "01234567890123456", "█", "│"),
            ("│", "01234567890123456", "█", "│"),
            ("│", "01234567890123456", "█", "│"),
            ("│", "01234567890123456", "█", "│"),
            ("│", "01234567890123456", "█", "│"),
            ("│", "01234567890123456", " ", "│"),
            ("│", "01234567890123456", " ", "│"),
            ("│", "01234567890123456", " ", "│"),
            ("│", "01234567890123456", " ", "│"),
            ("│", "01234567890123456", " ", "│"),
            ("│", "01234567890123456", " ", "│"),
            ("│", "01234567890123456", " ", "│"),
            ("└", "──────────────────", "", "┘"),
        ],
    ), _print_widget(output)

    w.overflow = ("scroll", "hide")

    assert (output := w.build()) == _as_spans(
        [
            ("┌", "──────────────────", "", "┐"),
            ("│", "012345678901234567", "│"),
            ("│", "012345678901234567", "│"),
            ("│", "012345678901234567", "│"),
            ("│", "012345678901234567", "│"),
            ("│", "012345678901234567", "│"),
            ("│", "012345678901234567", "│"),
            ("│", "012345678901234567", "│"),
            ("│", "012345678901234567", "│"),
            ("│", "012345678901234567", "│"),
            ("│", "012345678901234567", "│"),
            ("│", "012345678901234567", "│"),
            ("│", "012345678901234567", "│"),
            ("│", "012345678901234567", "│"),
            ("│", "012345678901234567", "│"),
            ("│", "012345678901234567", "│"),
            ("│", "012345678901234567", "│"),
            ("│", "012345678901234567", "│"),
            ("│", "▅▅▅▅▅▅▅▅▅▅▅       ", "│"),
            ("└", "──────────────────", "┘"),
        ],
    ), _print_widget(output)

    w.overflow = (Overflow.SCROLL, Overflow.SCROLL)
    w.scroll = (15, 0)

    assert (output := w.build()) == _as_spans(
        [
            ("┌", "──────────────────", "┐"),
            ("│", "34567890123456789", "█", "│"),
            ("│", "34567890123456789", "█", "│"),
            ("│", "34567890123456789", "█", "│"),
            ("│", "34567890123456789", "█", "│"),
            ("│", "34567890123456789", "█", "│"),
            ("│", "34567890123456789", "█", "│"),
            ("│", "34567890123456789", "█", "│"),
            ("│", "34567890123456789", "█", "│"),
            ("│", "34567890123456789", "█", "│"),
            ("│", "34567890123456789", "█", "│"),
            ("│", "34567890123456789", "█", "│"),
            ("│", "34567890123456789", " ", "│"),
            ("│", "34567890123456789", " ", "│"),
            ("│", "34567890123456789", " ", "│"),
            ("│", "34567890123456789", " ", "│"),
            ("│", "34567890123456789", " ", "│"),
            ("│", "34567890123456789", " ", "│"),
            ("│", "       ▅▅▅▅▅▅▅▅▅▅ ", "│"),
            ("└", "──────────────────", "┘"),
        ],
    ), _print_widget(output)

    w.scroll = (25, 20)

    assert (output := w.build()) == _as_spans(
        [
            ("┌", "──────────────────", "┐"),
            ("│", "34567890123456789", " ", "│"),
            ("│", "34567890123456789", " ", "│"),
            ("│", "34567890123456789", " ", "│"),
            ("│", "34567890123456789", " ", "│"),
            ("│", "34567890123456789", " ", "│"),
            ("│", "34567890123456789", " ", "│"),
            ("│", "34567890123456789", " ", "│"),
            ("│", "34567890123456789", "█", "│"),
            ("│", "34567890123456789", "█", "│"),
            ("│", "34567890123456789", "█", "│"),
            ("│", "34567890123456789", "█", "│"),
            ("│", "34567890123456789", "█", "│"),
            ("│", "34567890123456789", "█", "│"),
            ("│", "34567890123456789", "█", "│"),
            ("│", "34567890123456789", "█", "│"),
            ("│", "34567890123456789", "█", "│"),
            ("│", "34567890123456789", "█", "│"),
            ("│", "       ▅▅▅▅▅▅▅▅▅▅ ", "│"),
            ("└", "──────────────────", "┘"),
        ]
    ), _print_widget(output)


def test_widget_framing():
    w = ScrollingWidget()
    w.overflow = ("hide", "hide")
    w.width = 20
    w.height = 5

    w.frame = "Frameless"
    output = w.build()

    assert ["".join(map(str, line)) for line in output] == [
        "01234567890123456789",
        "01234567890123456789",
        "01234567890123456789",
        "01234567890123456789",
        "01234567890123456789",
    ], _print_widget(output)

    w.frame = frames.Light
    output = w.build()

    assert ["".join(map(str, line)) for line in output] == [
        "┌──────────────────┐",
        "│012345678901234567│",
        "│012345678901234567│",
        "│012345678901234567│",
        "└──────────────────┘",
    ], _print_widget(output)


def test_widget_no_default_content():
    w = Widget()

    with pytest.raises(NotImplementedError):
        w.get_content()


def test_widget_inline_markup():
    class MarkupWidget(Widget):
        style_map = EMPTY_STYLEMAP

        def get_content(self) -> list[str]:
            return ["This is normal [bold 141]but this ain't [yellow]and this is"]

    w = MarkupWidget(width=20, height=5, frame="ASCII_X", overflow=("hide", "hide"))

    assert (output := w.build()) == _as_spans(
        [
            ("X", "------------------", "X"),
            ("|", "                  ", "|"),
            (
                "|",
                "This is normal ",
                Span("but", bold=True, foreground="38;5;141"),
                "|",
            ),
            ("|", "                  ", "|"),
            ("X", "------------------", "X"),
        ]
    ), _print_widget(output)


def test_widget_styling():
    class SubStateWidget(TextWidget):
        state_machine = TextWidget.state_machine.copy(
            add_transitions={
                "/": {
                    "SUBSTATE_ENTER_CHECKED": "/checked",
                    "SUBSTATE_ENTER_WEIRD": "/weird",
                },
                "/checked": {
                    "SUBSTATE_EXIT_CHECKED": "/",
                },
                "/weird": {
                    "SUBSTATE_EXIT_WEIRD": "/",
                    "SUBSTATE_ENTER_CHECKED": "/checked",
                },
            }
        )

        style_map = TextWidget.style_map | {
            "/checked": {
                "content": "red",
                "frame": "bold red",
            }
        }

    w = SubStateWidget("Alma")
    w.alignment = ("start", "start")

    assert w.build() == _as_spans(
        [
            ("X", "------------------", "X"),
            ("|", "Alma              ", "|"),
            ("|", "                  ", "|"),
            ("|", "                  ", "|"),
            ("X", "------------------", "X"),
        ]
    )

    w.state_machine.apply_action("SUBSTATE_ENTER_WEIRD")

    assert w.build() == _as_spans(
        [
            ("X", "------------------", "X"),
            ("|", "Alma              ", "|"),
            ("|", "                  ", "|"),
            ("|", "                  ", "|"),
            ("X", "------------------", "X"),
        ]
    )

    w.state_machine.apply_action("SUBSTATE_ENTER_CHECKED")

    styles = {key: value("item") for key, value in w.styles.items()}

    assert styles == {
        "content": "[red]item",
        "frame": "[bold red]item",
        "scrollbar_x": "[]item",
        "scrollbar_y": "[]item",
    }

    assert w.build() == _as_spans(
        [
            (
                Span("X", bold=True, foreground="38;2;255;0;0"),
                Span("------------------", bold=True, foreground="38;2;255;0;0"),
                Span("X", bold=True, foreground="38;2;255;0;0"),
            ),
            (
                Span("|", bold=True, foreground="38;2;255;0;0"),
                Span("Alma              ", foreground="38;2;255;0;0"),
                Span("|", bold=True, foreground="38;2;255;0;0"),
            ),
            (
                Span("|", bold=True, foreground="38;2;255;0;0"),
                Span("                  ", foreground="38;2;255;0;0"),
                Span("|", bold=True, foreground="38;2;255;0;0"),
            ),
            (
                Span("|", bold=True, foreground="38;2;255;0;0"),
                Span("                  ", foreground="38;2;255;0;0"),
                Span("|", bold=True, foreground="38;2;255;0;0"),
            ),
            (
                Span("X", bold=True, foreground="38;2;255;0;0"),
                Span("------------------", bold=True, foreground="38;2;255;0;0"),
                Span("X", bold=True, foreground="38;2;255;0;0"),
            ),
        ]
    )


def test_widget_auto_scrollbar():
    w = TextWidget("Small")
    w.overflow = ("auto", "auto")

    assert (output := w.build()) == _as_spans(
        [
            ("X", "------------------", "X"),
            ("|", "                  ", "|"),
            ("|", "       ", "Small", "      ", "|"),
            ("|", "                  ", "|"),
            ("X", "------------------", "X"),
        ]
    ), _print_widget(output)

    w.text = "this is going to be too long"

    assert (output := w.build()) == _as_spans(
        [
            ("X", "------------------", "X"),
            ("|", "                  ", "|"),
            ("|", "this is going to b", "|"),
            ("|", "############------", "|"),
            ("X", "------------------", "X"),
        ]
    ), _print_widget(output)

    w.text = "too tall\n" * 10

    assert (output := w.build()) == _as_spans(
        [
            ("X", "------------------", "X"),
            ("|", "     ", "too tall", "    ", "#", "|"),
            ("|", "     ", "too tall", "    ", "|", "|"),
            ("|", "     ", "too tall", "    ", "|", "|"),
            ("X", "------------------", "X"),
        ]
    ), _print_widget(output)

    w.text = "this is going to be too long\n" * 10

    assert (output := w.build()) == _as_spans(
        [
            ("X", "------------------", "X"),
            ("|", "this is going to ", "#", "|"),
            ("|", "this is going to ", "|", "|"),
            ("|", "###########------ ", "|"),
            ("X", "------------------", "X"),
        ]
    ), _print_widget(output)
