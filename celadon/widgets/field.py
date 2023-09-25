from typing import Any
from string import printable, punctuation, whitespace

from slate import Key

from ..enums import MouseAction
from .widget import Widget

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

        /idle|hover|active:
            frame_style: ui.primary-1

        /hover:
            fill_style: '@ui.panel1-2'

        /selected:
            content_style: ''
            frame_style: ui.primary-1
            cursor_style: '@ui.panel1+3'
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

        self._value_length = len(value)

        super().__init__(**widget_args)

    def move_cursor(self, x: int = 0, y: int = 0) -> None:
        """Moves the cursor by the given x and y coordinates."""

        self.cursor = min(self.cursor[0] + x, self._value_length), self.cursor[1] + y

    def on_click(self, _: MouseAction, __: tuple[int, int]) -> bool:
        """Allows the widget to be selected on click."""

        return True

    def handle_keyboard(self, key: Key) -> bool:
        binds = super().handle_keyboard(key)

        if key == "left":
            self.move_cursor(x=-1)
            return True

        if key == "right":
            self.move_cursor(x=1)
            return True

        x = self.cursor[0]
        left, right = self.value[:x], self.value[x:]

        if key == "backspace":
            if x == 0:
                return False

            self.value = left[:-1] + right
            self._value_length -= 1

            self.move_cursor(x=-1)
            return True

        if key == "ctrl-backspace":
            self.value = right
            change = len(left)

            self._value_length -= change
            self.move_cursor(x=-change)
            return True

        if key == "alt-backspace":
            distance = 0

            for distance, char in enumerate(reversed(left)):
                if char in DELIMITERS:
                    if distance == 0:
                        continue

                    break

            else:
                distance = len(left)

            self.value = left[:-distance] + right
            self.move_cursor(x=-distance)
            return True

        if key in PRINTABLE:
            self.value = left + str(key) + right
            self._value_length += 1

            self.move_cursor(x=1)
            return True

        return binds

    def serialize(self) -> dict[str, Any]:
        if self.name is None:
            raise ValueError(f"field {self!r} cannot be serialized without a name.")

        return {self.name: self.value}

    def get_content(self) -> list[str]:
        x = self.cursor[0]

        value = self.value or self.placeholder

        if not value:
            return [" " + self.styles["cursor"](" ") + "[/] "]

        style = self.styles["placeholder" if not self.value else "content"]

        left, right = value[:x], value[x + 1 :]

        cursor = " "

        if x < len(value):
            cursor = value[x]

        return [" " + style(left) + self.styles["cursor"](cursor) + style(right) + " "]
