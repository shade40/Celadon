# pylint: disable=too-few-public-methods

from __future__ import annotations

from typing import Any, Tuple, Type

__all__ = [
    "Frame",
    "CharTuple",
    "get_frame",
]

CharTuple = Tuple[str, str, str, str]


class Frame:  # pylint: disable=too-many-instance-attributes
    """A set of characters to wrap a widget by."""

    descriptor: tuple[str, str, str] | None = None
    """A list of strings that describes the frame's borders & corners."""

    borders: CharTuple = ("", "", "", "")
    """Left, top, right and bottom border characters."""

    corners: CharTuple = ("", "", "", "")
    """Left-top, right-top, right-bottom and left-bottom border characters."""

    width: int
    """Width of the left and right borders combined."""

    height: int
    """Height of the top and bottom borders combined."""

    outer_horizontal: bool = False
    """Use the parent's fill color (instead of our own) when drawing the sides."""

    outer_vertical: bool = False
    """Use the parent's fill color (instead of our own) when drawing the top & bottom."""

    outer_corner: bool = False
    """Use the parent's fill color (instead of our own) when drawing the corners."""

    def __init__(self) -> None:
        if self.descriptor is not None:
            self.borders, self.corners = self._parse_descriptor()

        assert self.borders is not None and self.corners is not None

        self.width_components = (
            f"'{self.borders[0]}' or ('{self.corners[0]}' + '{self.corners[1]}')"
        )

        self.left, self.top, self.right, self.bottom = self.borders
        (
            self.left_top,
            self.right_top,
            self.right_bottom,
            self.left_bottom,
        ) = self.corners

        self.width = len(self.left + self.right)
        self.height = (self.borders[1] != "") + (self.borders[3] != "")


    def _parse_descriptor(self) -> tuple[CharTuple, CharTuple]:
        """Parses the descriptor into tuples of chartuples."""

        assert self.descriptor is not None
        top, middle, bottom = self.descriptor  # pylint: disable=unpacking-non-sequence

        left_top, top, *_, right_top = list(top)
        left, *_, right = list(middle)
        left_bottom, bottom, *_, right_bottom = list(bottom)

        return (
            (left, top, right, bottom),
            (left_top, right_top, right_bottom, left_bottom),
        )

    @property
    def name(self) -> str:
        """Return the frame class' name."""

        return type(self).__name__

    @classmethod
    def compose(
        cls, sides: tuple[Type[Frame], Type[Frame], Type[Frame], Type[Frame]]
    ) -> Frame:
        """Creates a frame object with borders coming from other frames.

        Args:
            sides: Sides to source from, read in the order left, top, right, bottom.

        Returns:
            A plain Frame object (so no custom name or documentation preview) with the
            given sides.
        """

        borders = []

        frame = cls()

        for i, side in enumerate(sides):
            borders.append(side().borders[i])

        frame.borders = tuple(borders)  # type: ignore
        # frame.corners = borders[1], borders[1], borders[3], borders[3]  # type: ignore
        frame.__init__()  # type: ignore # pylint: disable=unnecessary-dunder-call

        return frame


def get_frame(name: str) -> Type[Frame]:
    """Gets a frame by its name.

    Args:
        name: A case-insensitive frame name.

    Returns:
        The frame class matching the given name.

    Raises:
        ValueError: No frame found with the given name.
    """

    if name is None:
        return Frameless

    frame = {key.lower(): value for key, value in globals().items()}.get(name.lower())

    if frame is not None and issubclass(frame, Frame):
        return frame

    raise ValueError(f"No frame defined with name {name!r}.")


def add_frame_preview(cls: Type[Frame]):
    """Adds a documentation preview to the given class."""

    if cls.descriptor is None:
        return cls

    if cls.__doc__ is None:
        cls.__doc__ = ""

    cls.__doc__ += f"""

Preview:

```
{cls.descriptor[0]}
{cls.descriptor[1]}
{cls.descriptor[2]}
```
"""
    return cls


@add_frame_preview
class ASCII_X(Frame):  # pylint: disable=invalid-name
    """A frame of ASCII characters, with X-s in the corners."""

    descriptor = (
        "X---X",
        "|   |",
        "X---X",
    )


@add_frame_preview
class Light(Frame):
    """A frame with a light outline."""

    descriptor = (
        "┌───┐",
        "│   │",
        "└───┘",
    )


@add_frame_preview
class LightVertical(Frame):
    """A frame with a light outline."""

    borders = ("│", "", "│", "")
    corners = ("", "", "", "")


@add_frame_preview
class Heavy(Frame):
    """A frame with a heavy outline."""

    descriptor = (
        "┏━━━┓",
        "┃   ┃",
        "┗━━━┛",
    )


@add_frame_preview
class Rounded(Frame):
    """A frame with a light outline."""

    descriptor = (
        "╭───╮",
        "│   │",
        "╰───╯",
    )


@add_frame_preview
class Double(Frame):
    """A frame with a double-lined outline."""

    descriptor = (
        "╔═══╗",
        "║   ║",
        "╚═══╝",
    )


@add_frame_preview
class Dashed(Frame):
    """A frame with a dashed outline."""

    descriptor = (
        "┌╌╌╌┐",
        "╎   ╎",
        "└╌╌╌┘",
    )


@add_frame_preview
class HeavyDashed(Frame):
    """A frame with a dashed outline."""

    descriptor = (
        "┏╍╍╍┓",
        "╏   ╏",
        "┗╍╍╍┛",
    )


@add_frame_preview
class Padded(Frame):
    """A frame of spaces."""

    descriptor = (
        "   ",
        "   ",
        "   ",
    )


@add_frame_preview
class Frameless(Frame):
    """A frame of nothing."""

    borders = ("", "", "", "")
    corners = ("", "", "", "")


@add_frame_preview
class HorizontalOuter(Frame):
    """A horizontal McGugan box.

    https://www.willmcgugan.com/blog/tech/post/ceo-just-wants-to-draw-boxes/
    """

    descriptor = (
        "▁▁▁▁▁",
        "▎ x 🮇",
        "▔▔▔▔▔",
    )

    outer_horizontal = True
    outer_corner = True


@add_frame_preview
class VerticalOuter(Frame):
    """A vertical McGugan box.

    https://www.willmcgugan.com/blog/tech/post/ceo-just-wants-to-draw-boxes/
    """

    descriptor = (
        "🮇▔▔▔▔▔▎",
        "🮇  x  ▎",
        "🮇▁▁▁▁▁▎",
    )

    outer_vertical = True
    outer_corner = True
