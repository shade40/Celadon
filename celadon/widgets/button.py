from __future__ import annotations

from typing import Any

from slate import Event, EventCallback

from ..enums import MouseAction
from .widget import Widget

SEMANTIC_STYLES = """
        .{base}:
            /idle|hover:
                frame_style: ui.{base}

            /selected:
                frame_style: ui.{base}

            /active:
                frame_style: ui.panel1-2
                fill_style: '@ui.{base}+3'
"""


class Button(Widget):
    """A pressable/clickable button."""

    on_submit: Event
    """Called when the Button is clicked/pressed using a primary input (mouse1, return).

    Args:
        self: The instance that sent the event.
    """

    rules = f"""
    Button:
        content_style: dim
        alignment: [center, center]

        height: 1
        frame: [heavy, null, heavy, null]

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
            frame: frameless

        # Variants

        .big:
            height: 3

    {SEMANTIC_STYLES.format(base="success")}
    {SEMANTIC_STYLES.format(base="warning")}
    {SEMANTIC_STYLES.format(base="error")}
    """

    def __init__(
        self,
        content: str,
        on_submit: list[EventCallback] | None = None,
        **widget_args: Any,
    ) -> None:
        """Initializes the button.

        Args:
            content: The content the button should display.
            on_submit: A list of event callbacks to fire when the button submits.
            route: On click, it routes the application to a new page. Likely removed
                in the future.
        """

        super().__init__(**widget_args)

        self._has_timeout = False

        self.content = content
        self.width = sum(len(span) for span in self._parse_markup(self.content)) + 4

        self.on_submit = Event("button submit")
        for callback in on_submit or []:
            self.on_submit += callback

        self.bind("return", self._visual_submit)

    def _visual_submit(self) -> bool:
        """Animates the active state when the button is submitted using a keyboard."""

        if self._has_timeout:
            return False

        self.state_machine.apply_action("CLICKED")

        self._has_timeout = True
        self.app.timeout(
            150,
            lambda: (
                self.state_machine.apply_action("RELEASED_KEYBOARD"),
                setattr(self, "_has_timeout", False),  # type: ignore
            ),
        )

        return self.on_submit(self)

    def on_click(self, _: MouseAction, __: tuple[int, int]) -> bool:
        """Emits the submit event."""

        self.on_submit(self)

        return True

    def get_content(self) -> list[str]:
        return [self.content]
