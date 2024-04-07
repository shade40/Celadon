from __future__ import annotations

from typing import Any, Callable

from slate import Event

from ..enums import MouseAction
from .widget import Widget, wrap_callback


class Button(Widget):
    """A pressable/clickable button."""

    on_submit: Event
    """Called when the Button is clicked/pressed using a primary input (mouse1, return).

    Args:
        self: The instance that sent the event.
    """

    rules = """
    Button:
        content_style: dim
        alignment: [center, center]

        width: shrink
        height: 1

        frame: [heavy, null, heavy, null]

        /idle:
            fill_style: '@.panel1'
            frame_style: .primary+1

        /hover:
            fill_style: '@.panel1+1'
            frame_style: .primary+1

        /selected:
            content_style: dim bold
            fill_style: '@.panel1+1'
            frame_style: .primary+1

        /active:
            fill_style: 'bold @.primary+3'
            frame_style: '.primary+3'

        /disabled:
            fill_style: '@.panel1-2'
            frame_style: .primary-3
            content_style: .panel1+2

        # Variants

        .big:
            height: 3
    """

    def __init__(
        self,
        content: str,
        on_submit: list[Callable[[Button], bool]] | None = None,
        name: str | None = None,
        **widget_args: Any,
    ) -> None:
        """Initializes the button.

        Args:
            content: The content the button should display.
            on_submit: A list of event callbacks to fire when the button submits.
            name: The name to be used in some parents' serialization result.
        """

        super().__init__(**widget_args)

        self._has_timeout = False

        self.content = content
        self.name = name

        self.on_submit = Event("button submit")
        for callback in on_submit or []:
            self.on_submit += callback

        self.bind("return", wrap_callback(self._visual_submit))

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

    def _compute_shrink_width(self) -> int:
        return sum(len(span) for span in self._parse_markup(self.content)) + 4

    def _compute_shrink_height(self) -> int:
        return 1

    def on_click(self, _: MouseAction, __: tuple[int, int]) -> bool:
        """Emits the submit event."""

        self.on_submit(self)

        return True

    def get_content(self) -> list[str]:
        return [self.content]
