from enum import Enum

__all__ = [
    "Alignment",
    "Overflow",
    "MouseAction",
]


class Alignment(Enum):
    """An enum used to select alignment strategy."""

    START = "start"
    """Align to the start of the area (left or top)."""

    CENTER = "center"
    """Align to centered in the area."""

    END = "end"
    """Align to the end of the area (right or bottom)."""


class Anchor(Enum):
    """An enum to determine a widget's positioning strategy."""

    NONE = "none"
    """Use flow-vise arrangement."""

    PARENT = "parent"
    """Position at parent.position + self.offset."""

    SCREEN = "screen"
    """Position at terminal.origin + self.offset."""


class Overflow(Enum):
    """An enum used to select overflow strategy."""

    HIDE = "hide"
    """Hide scrollbar for overflowing content."""

    SCROLL = "scroll"
    """Display scrollbar for overflowing content."""

    AUTO = "auto"
    """Display scrollbar only when there is overflowing content."""


class Direction(Enum):
    """An enum used for selecting layout direction."""

    HORIZONTAL = "horizontal"
    """Flow content horizontally."""

    VERTICAL = "vertical"
    """Flow content vertically."""


class MouseAction(Enum):
    """A humonculous enumeration of mouse actions."""

    LEFT_CLICK = "left_click"
    LEFT_RELEASE = "left_release"
    RIGHT_CLICK = "right_click"
    RIGHT_RELEASE = "right_release"
    SHIFT_LEFT_CLICK = "shift_left_click"
    SHIFT_LEFT_RELEASE = "shift_left_release"
    SHIFT_RIGHT_CLICK = "shift_right_click"
    SHIFT_RIGHT_RELEASE = "shift_right_release"
    OPTION_LEFT_CLICK = "option_left_click"
    OPTION_LEFT_RELEASE = "option_left_release"
    OPTION_RIGHT_CLICK = "option_right_click"
    OPTION_RIGHT_RELEASE = "option_right_release"
    SHIFT_OPTION_LEFT_CLICK = "shift_option_left_click"
    SHIFT_OPTION_LEFT_RELEASE = "shift_option_left_release"
    SHIFT_OPTION_RIGHT_CLICK = "shift_option_right_click"
    SHIFT_OPTION_RIGHT_RELEASE = "shift_option_right_release"
    CTRL_LEFT_CLICK = "ctrl_left_click"
    CTRL_LEFT_RELEASE = "ctrl_left_release"
    CTRL_RIGHT_CLICK = "ctrl_right_click"
    CTRL_RIGHT_RELEASE = "ctrl_right_release"
    SHIFT_CTRL_LEFT_CLICK = "shift_ctrl_left_click"
    SHIFT_CTRL_LEFT_RELEASE = "shift_ctrl_left_release"
    SHIFT_CTRL_RIGHT_CLICK = "shift_ctrl_right_click"
    SHIFT_CTRL_RIGHT_RELEASE = "shift_ctrl_right_release"
    CTRL_OPTION_LEFT_CLICK = "ctrl_option_left_click"
    CTRL_OPTION_LEFT_RELEASE = "ctrl_option_left_release"
    CTRL_OPTION_RIGHT_CLICK = "ctrl_option_right_click"
    CTRL_OPTION_RIGHT_RELEASE = "ctrl_option_right_release"
    SHIFT_CTRL_OPTION_LEFT_CLICK = "shift_ctrl_option_left_click"
    SHIFT_CTRL_OPTION_LEFT_RELEASE = "shift_ctrl_option_left_release"
    SHIFT_CTRL_OPTION_RIGHT_CLICK = "shift_ctrl_option_right_click"
    SHIFT_CTRL_OPTION_RIGHT_RELEASE = "shift_ctrl_option_right_release"
    LEFT_DRAG = "left_drag"
    RIGHT_DRAG = "right_drag"
    HOVER = "hover"
    SHIFT_LEFT_DRAG = "shift_left_drag"
    SHIFT_RIGHT_DRAG = "shift_right_drag"
    SHIFT_HOVER = "shift_hover"
    OPTION_LEFT_DRAG = "option_left_drag"
    OPTION_RIGHT_DRAG = "option_right_drag"
    OPTION_HOVER = "option_hover"
    SHIFT_OPTION_LEFT_DRAG = "shift_option_left_drag"
    SHIFT_OPTION_RIGHT_DRAG = "shift_option_right_drag"
    SHIFT_OPTION_HOVER = "shift_option_hover"
    CTRL_LEFT_DRAG = "ctrl_left_drag"
    CTRL_RIGHT_DRAG = "ctrl_right_drag"
    CTRL_HOVER = "ctrl_hover"
    SHIFT_CTRL_LEFT_DRAG = "shift_ctrl_left_drag"
    SHIFT_CTRL_RIGHT_DRAG = "shift_ctrl_right_drag"
    SHIFT_CTRL_HOVER = "shift_ctrl_hover"
    CTRL_OPTION_LEFT_DRAG = "ctrl_option_left_drag"
    CTRL_OPTION_RIGHT_DRAG = "ctrl_option_right_drag"
    CTRL_OPTION_HOVER = "ctrl_option_hover"
    SHIFT_CTRL_OPTION_LEFT_DRAG = "shift_ctrl_option_left_drag"
    SHIFT_CTRL_OPTION_RIGHT_DRAG = "shift_ctrl_option_right_drag"
    SHIFT_CTRL_OPTION_HOVER = "shift_ctrl_option_hover"
    SCROLL_UP = "scroll_up"
    SCROLL_DOWN = "scroll_down"
    SCROLL_LEFT = "scroll_left"
    SCROLL_RIGHT = "scroll_right"
    SHIFT_SCROLL_UP = "shift_scroll_up"
    SHIFT_SCROLL_DOWN = "shift_scroll_down"
    SHIFT_SCROLL_LEFT = "shift_scroll_left"
    SHIFT_SCROLL_RIGHT = "shift_scroll_right"
    OPTION_SCROLL_UP = "option_scroll_up"
    OPTION_SCROLL_DOWN = "option_scroll_down"
    OPTION_SCROLL_LEFT = "option_scroll_left"
    OPTION_SCROLL_RIGHT = "option_scroll_right"
    SHIFT_OPTION_SCROLL_UP = "shift_option_scroll_up"
    SHIFT_OPTION_SCROLL_DOWN = "shift_option_scroll_down"
    SHIFT_OPTION_SCROLL_LEFT = "shift_option_scroll_left"
    SHIFT_OPTION_SCROLL_RIGHT = "shift_option_scroll_right"
    CTRL_SCROLL_UP = "ctrl_scroll_up"
    CTRL_SCROLL_DOWN = "ctrl_scroll_down"
    CTRL_SCROLL_LEFT = "ctrl_scroll_left"
    CTRL_SCROLL_RIGHT = "ctrl_scroll_right"
    SHIFT_CTRL_SCROLL_UP = "shift_ctrl_scroll_up"
    SHIFT_CTRL_SCROLL_DOWN = "shift_ctrl_scroll_down"
    SHIFT_CTRL_SCROLL_LEFT = "shift_ctrl_scroll_left"
    SHIFT_CTRL_SCROLL_RIGHT = "shift_ctrl_scroll_right"
    CTRL_OPTION_SCROLL_UP = "ctrl_option_scroll_up"
    CTRL_OPTION_SCROLL_DOWN = "ctrl_option_scroll_down"
    CTRL_OPTION_SCROLL_LEFT = "ctrl_option_scroll_left"
    CTRL_OPTION_SCROLL_RIGHT = "ctrl_option_scroll_right"
    SHIFT_CTRL_OPTION_SCROLL_UP = "shift_ctrl_option_scroll_up"
    SHIFT_CTRL_OPTION_SCROLL_DOWN = "shift_ctrl_option_scroll_down"
    SHIFT_CTRL_OPTION_SCROLL_LEFT = "shift_ctrl_option_scroll_left"
    SHIFT_CTRL_OPTION_SCROLL_RIGHT = "shift_ctrl_option_scroll_right"
