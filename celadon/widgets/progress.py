from __future__ import annotations

from typing import Any

from .widget import Widget


class Progress(Widget):
    """A simple, non-interactable progress bar."""

    rail: str = "─"
    filled: str = "━"
    show_percentage: bool = True

    style_map = Widget.style_map | {
        state: {"percentage": ""} for state in Widget.state_machine.states
    }

    rules = """
    Progress:
        height: 1

        frame_style: '.panel1'
        content_style: '.primary'

        .minimal:
            show_percentage: false

        .tall:
            rail: '█'
            filled: '█'

            percentage_style: '@.primary .panel1'
            frame_style: '.panel1-1'
    """

    def __init__(self, value: float = 0.0, **widget_args: Any) -> None:
        super().__init__(**widget_args)

        self.value = value

    @property
    def value(self) -> float:
        """Returns the internal value."""

        return self._value

    @value.setter
    def value(self, new: float) -> None:
        """Sets the internal value."""

        self._value = new

    def get_content(self) -> list[str]:
        filled = round(self.computed_width * self.value)

        style = self.styles["content"]

        if not self.show_percentage:
            return [
                self.styles["content"](style(filled * self.filled))
                + self.styles["frame"]((self.computed_width - filled) * self.rail)
            ]

        percentage = f" {self.value * 100:.0f}% "
        filled -= len(percentage)

        return [
            self.styles["content"](filled * self.filled)
            + self.styles["percentage"](percentage)
            + self.styles["frame"]((self.computed_width - filled) * self.rail)
        ]
