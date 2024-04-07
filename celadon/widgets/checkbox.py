from __future__ import annotations

from typing import Any, Callable

from slate import Event

from ..enums import MouseAction
from .button import Button
from .widget import Widget, wrap_callback


class Checkbox(Widget):
    """A button-like widget for checkboxes."""

    content: str
    checked: bool = False
    indicators: tuple[str, str] = ("□", "▣")

    on_change: Event
    """Called when the Checkbox's value changed.

    Args:
        self: The Checkbox that sent the event. Use `self.checked` to get current state.
    """

    style_map = Button.style_map | {
        state: {"indicator": ""} for state in Button.state_machine.states
    }

    # TODO: Add a form of inheritance to YAML styling
    rules = """
    Checkbox:
        content_style: dim

        height: 1
        width: shrink

        /idle:
            frame_style: .primary+1

        /hover:
            fill_style: '@.panel1-2'
            frame_style: .primary+1

        /selected:
            content_style: dim bold
            fill_style: '@.panel1-1'
            frame_style: .primary+1

        /active:
            fill_style: '@.primary+3'
            frame_style: '.panel1'
            indicator_style: 'dim'
    """

    def __init__(
        self,
        content: str,
        checked: bool = False,
        name: str | None = None,
        on_change: list[Callable[[Checkbox], bool]] | None = None,
        **widget_args: Any,
    ) -> None:
        super().__init__(**widget_args)

        self._has_timeout = False

        self.content = content
        self.checked = checked
        self.name = name

        self.on_change = Event("checkbox changed")

        for event in on_change or []:
            self.on_change += event

        self.bind("return", wrap_callback(self._visual_submit))

    def _visual_submit(self) -> bool:
        """Animates the active state when the button is submitted using a keyboard."""

        if self._has_timeout:
            return False

        self.checked = not self.checked
        self.state_machine.apply_action("CLICKED")

        self._has_timeout = True
        self.app.timeout(
            150,
            lambda: (
                self.state_machine.apply_action("RELEASED_KEYBOARD"),
                setattr(self, "_has_timeout", False),  # type: ignore
            ),
        )

        return self.on_change(self.checked)

    def _compute_shrink_width(self) -> int:
        return len(f" {self.indicators[self.checked]} {self.content} ")

    def _compute_shrink_height(self) -> int:
        return 1

    def on_click(self, _: MouseAction, __: tuple[int, int]) -> bool:
        """Toggles checked & emits the change event."""

        self.checked = not self.checked
        self.on_change(self.checked)

        return True

    def serialize(self) -> dict[str, Any]:
        if self.name is None:
            raise ValueError(f"field {self!r} cannot be serialized without a name.")

        return {self.name: self.checked}

    def get_content(self) -> list[str]:
        indicator = self.styles["indicator"](self.indicators[self.checked]) + "[/]"

        return [f" {indicator} {self.content} "]
