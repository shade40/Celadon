from __future__ import annotations

from typing import Any

from slate import Event

from ..enums import MouseAction
from .widget import Widget, to_widget_space, wrap_callback


class Slider(Widget):
    """A clickable and draggable slider."""

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
    Slider,VerticalSlider:
        content_style: '.panel1'
        cursor_style: '.panel1+1'

        /selected|hover:
            fill_style: '@.panel1-2'

        /selected|active:
            cursor_style: '.primary'

        /disabled:
            cursor_style: .panel1-1
            content_style: .panel1-1

        .-scroll-x:
            rail: " "
            cursor: "▅"

        .-scroll-y:
            rail: " "
            cursor: "█"

    Slider:
        height: 1
        width: null

    VerticalSlider:
        height: null
        width: 1
    """

    def __init__(
        self,
        *,
        value: float = 0.0,
        scale: float = 1.0,
        precision: int = 1,
        cursor_size: int = 1,
        name: str | None = None,
        **widget_args: Any,
    ) -> None:
        """Initializes a Slider.

        Args:
            value: The internal value (0.0-1.0) to start at.
            scale: The factor to scale the internal value by (`value = _value * scale`).
            precision: The rounding precision used in `increase` & `decrease` to avoid
                floating point errors.
            name: The name used when serializing this widget.
        """

        super().__init__(**widget_args)

        self._value = value
        self._scale = scale

        self.precision = precision
        self.name = name
        self.cursor_size = cursor_size

        self.on_change: Event[float] = Event("slider change")

        # TODO: These can be directional with class-body definitions
        self.bind("right", wrap_callback(self.increase))
        self.bind("left", wrap_callback(self.decrease))

        self._grab_offset = 0

    @property
    def value(self) -> float:
        """Returns the internal state of progress bar scaled to the end factor."""

        return self._value * self._scale

    @value.setter
    def value(self, new: float) -> None:
        self._value = new

    def serialize(self) -> dict[str, Any]:
        if self.name is None:
            raise ValueError(f"slider {self!r} cannot be serialized without a name.")

        return {self.name: self.value}

    # TODO: This docstring fucking sucks lol
    def _get_value(self, offset: int) -> float:
        """Gets the fractional value at the given widget offset."""

        x = to_widget_space((offset, 0), self)[0]
        return max(0.0, min((x - self._grab_offset) / self.computed_width, 1.0))

    def increase(self, amount: float = 0.1) -> bool:
        """Increases the progress bar by the given amount."""

        self._value = min(round(self._value + amount, self.precision), 1.0)
        self.on_change(self.value)

        return True

    def decrease(self, amount: float = 0.1) -> bool:
        """Decreases the progress bar by the given amount."""

        self._value = max(round(self._value - amount, self.precision), 0.0)
        self.on_change(self.value)

        return True

    def on_click(self, _: MouseAction, pos: tuple[int, int]) -> bool:
        cursor = round(self.computed_width * self._value)
        self._grab_offset = to_widget_space(pos, self)[0] - cursor

        # Click outside of cursor bar, so we recenter around it
        if not (0 <= self._grab_offset < cursor + self.cursor_size):
            self._grab_offset = self.cursor_size // 2

        self._value = self._get_value(pos[0])
        self.on_change(self.value)

        return True

    def on_drag(self, _: MouseAction, pos: tuple[int, int]) -> bool:
        self._value = self._get_value(pos[0])
        self.on_change(self.value)

        return True

    def _build(self, dimension: int) -> list[str]:
        start = min(round(dimension * self._value), dimension - self.cursor_size)

        style = self.styles["content"]

        return [
            *[style(self.rail) for _ in range(start)],
            *[self.styles["cursor"](self.cursor) for _ in range(self.cursor_size)],
            *[style(self.rail) for _ in range(dimension - start - self.cursor_size)],
        ]

    def get_content(self) -> list[str]:
        return ["".join(self._build(self.computed_width))]


class VerticalSlider(Slider):
    cursor: str = "━"
    rail: str = "│"

    # TODO: This docstring fucking sucks lol
    def _get_value(self, offset: int) -> float:
        """Gets the fractional value at the given widget offset."""

        x = to_widget_space((0, offset), self)[1]
        return max(0.0, min((x - self._grab_offset) / self.computed_height, 1.0))

    def on_click(self, _: MouseAction, pos: tuple[int, int]) -> bool:
        cursor = round(self.computed_height * self._value)
        self._grab_offset = to_widget_space(pos, self)[1] - cursor

        # Click outside of cursor bar, so we recenter around it
        if not (0 <= self._grab_offset < cursor + self.cursor_size):
            self._grab_offset = self.cursor_size // 2

        self._value = self._get_value(pos[1])
        self.on_change(self.value)

        return True

    def on_drag(self, _: MouseAction, pos: tuple[int, int]) -> bool:
        self._value = self._get_value(pos[1])
        self.on_change(self.value)

        return True

    def get_content(self) -> list[str]:
        return self._build(self.computed_height)
