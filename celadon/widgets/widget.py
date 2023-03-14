from __future__ import annotations

from typing import Callable, Generator, Type

from zenith.markup import markup, markup_spans
from gunmetal import Event, Span

from ..enums import Alignment, Overflow
from ..frames import Frame, get_frame
from ..state_machine import StateMachine

__all__ = [
    "Widget",
]


def _build_scrollbar(
    rail: str, thumb: str, size: int, current: float, ratio: float
) -> Generator[str, None, None]:
    """Builds the characters for a scrollbar.

    Args:
        rail: The character used for the 'rail' of the scrollbar.
        thumb: The character used for the 'thumb' of the scrollbar.
        size: The total available size for the scrollbar to follow.
        current: The current value/position of the scrollbar, 0-1.
        ratio: The visible ('viewport') size divided by the total ('virtual') size.

    Yields:
        `rail` or `thumb`, depending on which character comes next, a total of `size`
        times.
    """

    thumb_length = int(size * ratio)
    move_area = size - thumb_length

    thumb_center = int(current * move_area)
    half_thumb, offset = divmod(thumb_length, 2)
    thumb_center += half_thumb

    thumb_start = thumb_center - half_thumb
    thumb_end = thumb_center + half_thumb + offset

    for i in range(size):
        if thumb_start <= i <= thumb_end:
            yield thumb
            continue

        yield rail


class Widget:  # pylint: disable=too-many-instance-attributes
    """This is a docstring."""

    state_machine = StateMachine(
        states=("idle", "hover", "selected", "active"),
        transitions={
            "idle": {
                "HOVERED": "hover",
                "SELECTED": "selected",
                "CLICKED": "active",
            },
            "hover": {
                "UNHOVERED": "idle",
                "SELECTED": "selected",
                "CLICKED": "active",
            },
            "selected": {
                "UNSELECTED": "idle",
                "CLICKED": "active",
            },
            "active": {
                "RELEASED": "idle",
            },
        },
    )
    """The state machine keeps track of the current state of the widget.

    It has a tuple of possible states, and a mapping of:

        {current_state: {action: resulting_state, ...}

    ...that are used for state-transitions.
    """

    style_map = {
        "idle": {
            "fill": "panel+1",
            "border": "accent",
            "content": "text",
        },
        "hover": {
            "fill": "panel+2",
            "border": "accent",
            "content": "text",
        },
        "selected": {
            "fill": "accent",
            "border": "panel+2",
            "content": "text",
        },
        "active": {
            "fill": "accent+1",
            "border": "panel",
            "content": "text",
        },
    }
    """The style map is the lookup table for the widget's styles at certain states."""

    on_state_change: Event
    """Called when the widget's state changes.

    Args:
        state: The new state.
    """

    frame: Frame
    """The frame drawn around the widget."""

    scroll: tuple[int, int] = (0, 0)
    """The widget's (horizontal, vertical) scrolling offset."""

    def __init__(
        self, width: int = 1, height: int = 1, frame: Frame | str = "Frameless"
    ) -> None:
        self.on_state_change = self.state_machine.on_change

        self.width = width
        self.height = height
        self.frame = frame
        self.alignment = ("center", "center")
        self.overflow = ("hide", "hide")

        self._virtual_width = 0
        self._virtual_height = 0

    @property
    def state(self) -> str:
        """Returns the current state of the widget."""

        return self.state_machine()

    @property
    def styles(self) -> dict[str, Callable[[str], str]]:
        """Returns a dictionary of style keys to markup callables."""

        return {
            key: lambda item: markup("[{value}]{item}")
            for key, value in self.style_map[self.state]
        }

    @property
    def frame(self) -> Frame:
        """Returns and sets the current frame."""

        return self._frame

    @frame.setter
    def frame(self, new: str | Type[Frame]) -> None:
        if isinstance(new, str):
            new = get_frame(new)

        self._frame = new()

    @property
    def alignment(self) -> tuple[Alignment, Alignment]:
        """Returns and sets the current alignment settings.

        Args:
            new: A tuple of either two strings (start, center, end) or two alignment
                constants.
        """

        return self._alignment

    @alignment.setter
    def alignment(self, new: tuple[Alignment, Alignment] | tuple[str, str]) -> None:
        """Sets the alignment setting."""

        if not all(isinstance(item, Alignment) for item in new):
            new = Alignment(new[0]), Alignment(new[1])

        self._alignment = new

    @property
    def overflow(self) -> tuple[Overflow, Overflow]:
        """Returns and sets the current overflow settings.

        Args:
            new: A tuple of either two strings (start, center, end) or two alignment
                constants.
        """

        return self._overflow

    @overflow.setter
    def overflow(self, new: tuple[Overflow, Overflow] | tuple[str, str]) -> None:
        """Sets the overflow setting."""

        if not all(isinstance(item, Overflow) for item in new):
            new = Overflow(new[0]), Overflow(new[1])

        self._overflow = new

    def _add_scrollbars(  # pylint: disable=too-many-arguments
        self,
        lines: list[tuple[Span]],
        width: int,
        height: int,
        scrollbar_x: bool,
        scrollbar_y: bool,
    ) -> None:
        """Adds scrollbars to the given lines."""

        if scrollbar_x:
            virtual = max(1, self._virtual_width)

            buff = "".join(
                list(
                    _build_scrollbar(
                        *self.frame.scrollbars[0],
                        size=width - scrollbar_y,
                        current=self.scroll[0] / virtual,
                        ratio=width / virtual,
                    )
                )
            )

            lines[-1] = (Span(buff + " " * scrollbar_y),)

        if scrollbar_y:
            virtual = max(1, self._virtual_height)

            chars = list(
                _build_scrollbar(
                    *self.frame.scrollbars[1],
                    size=height - scrollbar_x,
                    current=self.scroll[1] / virtual,
                    ratio=height / virtual,
                )
            )

            for i, line in enumerate(lines):
                if i >= height - scrollbar_x:
                    break

                span = line[-1]

                lines[i] = (
                    *line[:-1],
                    span.mutate(text=span.text[:-1]),
                    Span(chars[i]),
                )

    def _apply_frame(self, lines: list[tuple[Span]], width: int) -> None:
        """Adds frame characters around the given lines."""

        left_top, right_top, right_bottom, left_bottom = self.frame.corners
        left, top, right, bottom = self.frame.borders

        for i, line in enumerate(lines):
            lines[i] = (Span(left), *line, Span(right))

        if left_top + top + right_top != "":
            lines.insert(0, (Span(left_top), Span(top * width), Span(right_top)))

        if left_bottom + bottom + right_bottom != "":
            lines.append((Span(left_bottom), Span(bottom * width), Span(right_bottom)))

    def _horizontal_align(self, line: tuple[Span], width: int) -> tuple[Span]:
        """Aligns a tuple of spans horizontally, using `self.alignment[0]`."""

        length = sum(len(span.text) for span in line)
        diff = width - length
        alignment = self.alignment[0]

        if alignment is Alignment.START:
            return (*line[:-1], line[-1].mutate(text=line[-1].text + diff * " "))

        if alignment is Alignment.CENTER:
            span = line[0]
            end, extra = divmod(diff, 2)
            start = end + extra

            return (
                span.mutate(text=start * " " + span.text + end * " "),
                *line[1:],
            )

        span = line[0]

        return (span.mutate(text=diff * " " + span.text), *line[1:])

    def _vertical_align(self, lines: list[tuple[Span]], height: int) -> None:
        """Aligns a list of tuples of spans vertically, using `self.alignment[1]`.

        Note that this mutates `lines`.
        """

        available = height - len(lines)
        alignment = self.alignment[1]
        filler = Span("")

        if alignment is Alignment.START:
            lines.extend([(filler,)] * available)
            return

        if alignment is Alignment.CENTER:
            top, extra = divmod(available, 2)
            bottom = top + extra

            for _ in range(top):
                lines.insert(0, (filler,))

            lines.extend([(filler,)] * bottom)
            return

        for _ in range(available):
            lines.insert(0, (filler,))

    def handle_keyboard(self, key: str) -> bool:
        ...

    def handle_mouse(self, action: MouseAction, position: tuple[int, int]) -> bool:
        ...

    def get_content(self) -> list[str]:
        """Gets the dynamic content for this widget."""

        raise NotImplementedError

    def build(self) -> list[str]:
        """Builds the strings that represent the widget."""

        width = max(self.width - self.frame.width, 0)
        height = max(self.height - self.frame.height, 0)

        lines: list[tuple[Span]] = [list(markup_spans(l)) for l in self.get_content()]

        self._virtual_height = len(lines)

        if self._virtual_height > height:
            lines = lines[self.scroll[1] : self.scroll[1] + height]

            if len(lines) < height:
                lines.extend([(Span(""),)] * (height - len(lines)))

        # Handle alignment
        self._vertical_align(lines, height)

        for i, line in enumerate(lines):
            lines[i] = self._horizontal_align(line, width)

        # Trim spans horizontally to fit within width
        for i, line in enumerate(lines):
            occupied = 0
            new_line = []

            for span in line:
                occupied += len(span.text)

                if occupied > width:
                    start = self.scroll[0]
                    end = start + (width - occupied)

                    if end >= 0:
                        end = None

                    span = span[start:end]

                    if len(span) < width:
                        span = span.mutate(text=span.text + " " * (width - len(span)))

                new_line.append(span)

            self._virtual_width = max(self._virtual_width, occupied)

            lines[i] = tuple(new_line)

        self.scroll = (
            min(self.scroll[0], self._virtual_width - 1),
            min(self.scroll[1], self._virtual_height - 1),
        )

        # Composite together frame + content + scrollbar
        self._add_scrollbars(
            lines,
            width,
            height,
            self.overflow[0] is Overflow.SCROLL,
            self.overflow[1] is Overflow.SCROLL,
        )

        self._apply_frame(lines, width)

        return lines
