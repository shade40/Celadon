from typing import Any

from slate import Event, EventCallback

from ..enums import MouseAction
from .button import Button
from .widget import Widget


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
        "idle": {
            "indicator": "",
        },
        "hover": {
            "indicator": "",
        },
        "selected": {
            "indicator": "",
        },
        "active": {
            "indicator": "",
        },
    }

    rules = """
    Checkbox:
        content_style: dim

        height: 1

        /idle:
            fill_style: '@ui.panel1'
            frame_style: ui.primary+1

        /hover:
            fill_style: '@ui.panel1+1'
            frame_style: ui.primary+1

        /selected:
            content_style: dim bold
            fill_style: '@ui.panel1+1'
            frame_style: ui.primary+1

        /active:
            fill_style: '@ui.primary+3'
            frame_style: 'ui.panel1-2'
            indicator_style: 'dim'
    """

    def __init__(
        self,
        content: str,
        checked: bool = False,
        on_change: list[EventCallback] | None = None,
        **widget_args: Any,
    ) -> None:
        super().__init__(**widget_args)

        self._has_timeout = False

        self.content = content
        self.checked = checked

        self.on_change = Event("checkbox changed")

        for event in on_change or []:
            self.on_change += event

        self.bind("return", self._visual_submit)

    def _visual_submit(self) -> None:
        """Animates the active state when the button is submitted using a keyboard."""

        if self._has_timeout:
            return

        self.checked = not self.checked
        self.state_machine.apply_action("CLICKED")

        self._has_timeout = True
        self.app.timeout(
            150,
            lambda: (
                self.state_machine.apply_action("RELEASED_KEYBOARD"),
                setattr(self, "_has_timeout", False),
            ),
        )

        return self.on_change(self)

    def on_click(self, action: MouseAction, __: tuple[int, int]) -> None:
        """Toggles checked & emits the change event."""

        self.checked = not self.checked
        self.on_change(self.checked)

    def get_content(self) -> None:
        indicator = self.styles["indicator"](self.indicators[self.checked]) + "[/]"

        return [f" {indicator} {self.content} "]
