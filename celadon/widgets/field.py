import string
from typing import Any, Iterator

from slate import Key

from ..enums import MouseAction
from .widget import Widget, to_widget_space

PRINTABLE = [*string.printable]


class Field(Widget):
    """A text field."""

    style_map = Widget.style_map | {
        state: {"cursor": "", "placeholder": ""}
        for state in Widget.state_machine.states
    }

    rules = """
    Field:
        overflow: [auto, auto]
        width: fill
        height: shrink

        frame: [heavy, null, null, null]

        placeholder_style: 'dim italic'
        frame_style: .primary-1

        /hover:
            fill_style: '@.panel1-2'

        /selected|active:
            content_style: ''
            cursor_style: '@.panel1+3'

        /disabled:
            frame_style: .primary-3
    """

    def __init__(
        self,
        value: str = "",
        placeholder: str = "",
        multiline: bool = False,
        name: str | None = None,
        **widget_args,
    ) -> None:
        self.value = value
        self.placeholder = placeholder
        self.multiline = multiline
        self.name = name

        self.cursor = (0, 0)

        super().__init__(**widget_args)

    def _get_cursorline(self, x_offset=0, y_offset=0) -> tuple[str, str, str]:
        """Gets the line (left, cursor, right) at the current cursor + given offset."""
        x, y = self.cursor
        x += x_offset
        y += y_offset

        line = self.value.split("\n")[y]

        left, right = line[:x], line[x + 1 :]
        cursor = line[x] if x < len(line) else ""

        return left, cursor, right

    def _find_word_end(self, line: str, direction: int = 1) -> int:
        """Returns the distance from the next word boundary."""

        # Consistent with unix shell behaviour:
        # * Always delete first char, then remove any non-punctuation
        # Note that the exact behaviour isn't standardized:
        # * Python repl: until change in letter+digit & punctionation
        # * Unix shells: only removes letter+digit
        word_chars = string.ascii_letters + string.digits

        if direction == -1:
            strip_line = line.rstrip(word_chars)
        else:
            strip_line = line.lstrip(word_chars)

        return -direction * (len(strip_line) - len(line)) + direction

    def _compute_shrink_width(self) -> int:
        return max(*[len(line) for line in self.value.split("\n")], 8) + 4

    def _compute_shrink_height(self) -> int:
        return max(len(self.value.split("\n")), 1)

    def move_cursor(self, x: int = 0, y: int = 0) -> None:
        """Moves the cursor by the given x and y coordinates."""

        self.set_cursor(self.cursor[0] + x, self.cursor[1] + y)

    def set_cursor(self, x: int = 0, y: int = 0) -> None:
        """Sets the cursor to the given coordinates and clamps them."""

        lines = self.value.split("\n")
        y = max(0, min(len(lines) - 1, y))

        line = lines[y]
        x = max(0, min(len(line), x))

        self.cursor = x, y

    def on_click(self, _: MouseAction, pos: tuple[int, int]) -> bool:
        """Allows the widget to be selected on click."""

        x, y = to_widget_space(pos, self)
        # Account for padding on the left
        self.set_cursor(x - 1, y)

        return True

    def set_line(self, y: int, line: str) -> None:
        """Sets the line at the given y index."""

        lines = self.value.split("\n")

        self.value = "\n".join(
            [
                *lines[:y],
                line,
                *lines[y + 1 :],
            ]
        )

    def delete_trailing_newline(self) -> None:
        """Deletes a newline from the end of the current line.

        No-op when y == 0.
        """

        y = self.cursor[1]

        if y == 0:
            return

        parts = self._get_cursorline(y_offset=-1)

        lines = self.value.split("\n")
        lines[y - 1] += lines[y]
        lines.pop(y)

        self.value = "\n".join(lines)

        self.move_cursor(y=-1, x=len("".join(parts)))

    def handle_keyboard(self, key: Key) -> bool:
        binds = super().handle_keyboard(key)

        # TODO: Properly handle markup in field value
        if str(key) in "[]":
            return True

        if key == "left":
            self.move_cursor(x=-1)
            return True

        if key == "right":
            self.move_cursor(x=1)
            return True

        if key == "up":
            self.move_cursor(y=-1)
            return True

        if key == "down":
            self.move_cursor(y=1)
            return True

        x, y = self.cursor

        left, cursor, right = self._get_cursorline()

        if key == "alt-left":
            self.move_cursor(x=self._find_word_end(left, direction=-1))
            return True

        if key == "alt-right":
            self.move_cursor(x=self._find_word_end(right + " "))
            return True

        if key == "ctrl-left":
            self.set_cursor(0, y)
            return True

        if key == "ctrl-right":
            self.set_cursor(len(left + cursor + right), y)
            return True

        left += cursor

        if key == "backspace":
            if x == 0:
                self.delete_trailing_newline()
                return True

            self.set_line(y, left[: -1 - len(cursor)] + cursor + right)

            self.move_cursor(x=-1)
            return True

        if key == "ctrl-backspace":
            if x == 0:
                self.delete_trailing_newline()
                return True

            self.set_line(y, cursor + right)
            change = len(left) - 1

            self.move_cursor(x=-change)
            return True

        if key == "alt-backspace":
            if x == 0:
                self.delete_trailing_newline()
                return True

            distance = self._find_word_end(left, direction=-1)

            self.set_line(y, left[:distance] + right)
            self.move_cursor(x=distance)

            return True

        if key == "return":
            if not self.multiline:
                return True

            lines = self.value.split("\n")

            if cursor != "":
                right = left[-1] + right
                left = left[:-1]

            lines[y] = left

            if len(lines) > y + 1:
                lines.insert(y + 1, right)
            else:
                lines.append(right)

            self.value = "\n".join(lines)

            self.move_cursor(x=-self.cursor[0], y=1)
            return True

        if key in PRINTABLE:
            left = left.removesuffix(cursor)
            self.set_line(y, left + str(key) + cursor + right)

            self.move_cursor(x=1)
            return True

        return binds

    def serialize(self) -> dict[str, Any]:
        if self.name is None:
            raise ValueError(f"field {self!r} cannot be serialized without a name.")

        return {self.name: self.value}

    def get_content(self) -> list[str]:
        value = self.value or self.placeholder

        if not value:
            return [" " + self.styles["cursor"](" ") + " "]

        content_style = self.styles["content"]
        cursor_style = self.styles["cursor"]

        if self.value == "":
            content_style = self.styles["placeholder"]

            if self._selected_index is None:
                cursor_style = content_style

        style = self.styles["placeholder" if not self.value else "content"]
        left, cursor, right = self._get_cursorline()
        if cursor == "":
            cursor = " "

        lines = self.value.split("\n")
        y = self.cursor[1]

        return [
            *(f" {line} " for line in lines[:y]),
            (
                " "
                + content_style(left)
                + cursor_style(cursor)
                + content_style(right)
                + " "
            ),
            *(f" {line} " for line in lines[y + 1 :]),
        ]
