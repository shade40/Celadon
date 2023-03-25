from enum import Enum

__all__ = [
    "Alignment",
    "Overflow",
    "MouseAction",
]


class Alignment(Enum):
    START = "start"
    """Align to the start of the area (left or top)."""

    CENTER = "center"
    """Align to centered in the area."""

    END = "end"
    """Align to the end of the area (right or bottom)."""


class Overflow(Enum):
    HIDE = "hide"
    """Hide scrollbar for overflowing content."""

    SCROLL = "scroll"
    """Display scrollbar for overflowing content."""

    AUTO = "auto"
    """Display scrollbar only when there is overflowing content."""


class MouseAction(Enum):
    LEFT_CLICK = "left_click"
    RIGHT_CLICK = "right_click"
    CTRL_LEFT_CLICK = "ctrl_left_click"
    CTRL_RIGHT_CLICK = "ctrl_right_click"
    LEFT_RELEASE = "left_release"
    RIGHT_RELEASE = "right_release"
    LEFT_DRAG = "left_drag"
    RIGHT_DRAG = "right_drag"
    CTRL_LEFT_DRAG = "ctrl_left_drag"
    CTRL_RIGHT_DRAG = "ctrl_right_drag"
    HOVER = "hover"
    SHIFT_HOVER = "shift_hover"
    CTRL_HOVER = "ctrl_hover"
    SCROLL_UP = "scroll_up"
    SCROLL_DOWN = "scroll_down"
    SCROLL_RIGHT = "scroll_right"
    SCROLL_LEFT = "scroll_left"
    SHIFT_SCROLL_UP = "shift_scroll_up"
    SHIFT_SCROLL_DOWN = "shift_scroll_down"
    CTRL_SCROLL_UP = "ctrl_scroll_up"
    CTRL_SCROLL_DOWN = "ctrl_scroll_down"
