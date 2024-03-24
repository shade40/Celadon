from __future__ import annotations

from typing import Any

from slate import Event

from ..enums import MouseAction
from .widget import Widget


class Slider(Widget):
    style_map = Widget.style_map | {
        state: {"cursor": ""} for state in Widget.state_machine.states
    }

    on_change: Event
    """Called when the slider's value changes.

    Args:
        Value: The new value of the slider.
    """

    cursor: str = "┃"
    rail: str = "─"

    rules = """
    Slider:
        height: 1

        content_style: '.panel1+1'

        /hover|selected:
            fill_style: '@.panel1-1'
        /selected|active:
            cursor_style: '.primary'
    """

    def __init__(
        self,
        *,
        value: float = 0.0,
        end: float = 1.0,
        precision: int = 1,
        **widget_args: Any,
    ) -> None:
        super().__init__(**widget_args)

        self.precision = precision

        self._value = value
        self._end = end

        self.on_change: Event[float] = Event("slider change")

        self.bind("right", self.increase)
        self.bind("left", self.decrease)

    @property
    def value(self) -> float:
        return self._value * self._end

    def increase(self, _: Widget) -> bool:
        self._value = min(round(self._value + 0.1, self.precision), 1.0)
        self.on_change(self.value)

        return True

    def decrease(self, _: Widget) -> bool:
        self._value = max(round(self._value - 0.1, self.precision), 0.0)
        self.on_change(self.value)

        return True

    def _compute_value(self, pos: int) -> float:
        offset = pos - self.position[0]

        if offset == 1:
            return 0

        return max(0.0, min(offset / self.computed_width, 1.0))

    def on_click(self, _: MouseAction, pos: tuple[int, int]) -> bool:
        self._value = self._compute_value(pos[0])
        return True

    def on_drag(self, _: MouseAction, pos: tuple[int, int]) -> bool:
        self._value = self._compute_value(pos[0])
        return True

    def get_content(self) -> list[str]:
        filled = round(self.computed_width * self._value)

        style = self.styles["content"]

        return [
            style((filled - 1) * self.rail)
            + self.styles["cursor"](self.cursor)
            + style((self.computed_width - filled) * self.rail)
        ]
