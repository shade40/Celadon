from enum import Enum

__all__ = [
    "Alignment",
    "Overflow",
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
