from string import printable, punctuation, whitespace
from typing import Any

from slate import Key

from ..enums import MouseAction
from .widget import Widget, to_widget_space

PRINTABLE = [*printable]
DELIMITERS = {*whitespace, *punctuation}


class Field(Widget):
    """A text field."""

    style_map = Widget.style_map | {
        state: {"cursor": "", "placeholder": ""}
        for state in Widget.state_machine.states
    }

    rules = """
    Field:
        frame: [heavy, null, null, null]
        height: 1

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

            distance = 0

            for distance, char in enumerate(reversed(left)):
                if char in DELIMITERS:
                    if distance == 0:
                        continue

                    break

            else:
                distance = len(left)

            self.set_line(y, left[:-distance] + right)

            self.move_cursor(x=-distance)
            return True

        if key == "return":
            if not self.multiline:
                return True

            lines = self.value.split("\n")

            if cursor != "":
                right = left[-1] + right
                left = left[:-1]

            if len(lines) > y + 1:
                lines[y + 1] = right + lines[y + 1]
            else:
                lines.append(right)

            lines[y] = left
            self.value = "\n".join(lines)

            self.move_cursor(x=-self.cursor[0], y=1)
            return True

        if key in PRINTABLE:
            self.set_line(y, left + str(key) + right)

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
            return [" " + self.styles["cursor"](" ") + "[/] "]

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
