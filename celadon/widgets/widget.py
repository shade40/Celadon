from __future__ import annotations

from typing import Callable, Generator, Type

from gunmetal import Event, Span
from zenith.markup import markup_spans, FULL_RESET

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
            "/": {
                "SUBSTATE_ENTER_SCROLLING_X": "/scrolling_x",
                "SUBSTATE_ENTER_SCROLLING_Y": "/scrolling_y",
            },
            "/scrolling_x": {
                "SUBSTATE_EXIT_SCROLLING_X": "/",
            },
            "/scrolling_y": {
                "SUBSTATE_EXIT_SCROLLING_Y": "/",
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
            "fill": "@panel1-3",
            "frame": "panel1+1",
            "content": "text-1",
            "scrollbar_x": "panel1-1",
            "scrollbar_y": "panel1-1",
        },
        "hover": {
            "fill": "@panel1-2",
            "frame": "panel1+1",
            "content": "text",
            "scrollbar_x": "text",
            "scrollbar_y": "text",
        },
        "selected": {
            "fill": "@accent",
            "frame": "panel1+1",
            "content": "text",
            "scrollbar_x": "text",
            "scrollbar_y": "text",
        },
        "active": {
            "fill": "@accent+1",
            "frame": "panel1+1",
            "content": "text",
            "scrollbar_x": "text",
            "scrollbar_y": "text",
        },
        "/scrolling_x": {
            "scrollbar_x": "primary",
        },
        "/scrolling_y": {
            "scrollbar_y": "primary",
        },
    }
    """The style map is the lookup table for the widget's styles at certain states."""

    on_state_change: Event
    """Called when the widget's state changes.

    Args:
        state: The new state.
    """

    scroll: tuple[int, int] = (0, 0)
    """The widget's (horizontal, vertical) scrolling offset."""

    def __init__(
        self, width: int = 1, height: int = 1, frame: Frame | str = "Frameless"
    ) -> None:
        self.on_state_change = self.state_machine.on_change

        self.width = width
        self.height = height

        # These conversions are handled in their properties
        self.frame = frame  # type: ignore
        self.alignment = ("center", "center")  # type: ignore
        self.overflow = ("hide", "hide")  # type: ignore

        self._virtual_width = 0
        self._virtual_height = 0

    @property
    def state(self) -> str:
        """Returns the current state of the widget."""

        return self.state_machine()

    @property
    def styles(self) -> dict[str, Callable[[str], str]]:
        """Returns a dictionary of style keys to markup callables."""

        def _get_style_function(style: str, fill: str) -> Callable[[str], str]:
            def _style(item: str) -> str:
                return f"[{fill}{style}]{item}"

            return _style

        styles = self.style_map[self.state.split("/")[0]].copy()

        if "/" in self.state:
            key = "/" + self.state.split("/")[-1]

            if key in self.style_map:
                styles |= self.style_map[key].items()

        output = {}
        fill = styles["fill"]

        if fill != "":
            fill += " "

        for key, style in styles.items():
            if key == "fill":
                continue

            output[key] = _get_style_function(style, fill)

        return output

    @property
    def frame(self) -> Frame:
        """Returns and sets the current frame."""

        return self._frame

    @frame.setter
    def frame(self, new: str | Type[Frame]) -> None:
        if isinstance(new, str):
            new = get_frame(new)

        assert not isinstance(new, str)
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

        assert isinstance(new[0], Alignment) and isinstance(new[1], Alignment)
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

        assert isinstance(new[0], Overflow) and isinstance(new[1], Overflow)
        self._overflow = new

    @staticmethod
    def _parse_markup(markup: str) -> tuple[Span, ...]:
        """Parses some markup into a span of tuples.

        This also handles (ignores) zenith's FULL_RESET spans.
        """

        return tuple(span for span in markup_spans(markup) if span is not FULL_RESET)

    def _add_scrollbars(  # pylint: disable=too-many-arguments
        self,
        lines: list[tuple[Span, ...]],
        width: int,
        height: int,
        scrollbar_x: bool,
        scrollbar_y: bool,
    ) -> None:
        """Adds scrollbars to the given lines."""

        if scrollbar_x:
            buff = "".join(
                list(
                    _build_scrollbar(
                        *self.frame.scrollbars[0],
                        size=width - scrollbar_y,
                        current=self.scroll[0] / max(self._virtual_width - width, 1),
                        ratio=width / self._virtual_width,
                    )
                )
            )

            lines[-1] = tuple(
                markup_spans(self.styles["scrollbar_x"](buff + " " * scrollbar_y))
            )

        if scrollbar_y:
            chars = list(
                _build_scrollbar(
                    *self.frame.scrollbars[1],
                    size=height - scrollbar_x,
                    current=self.scroll[1] / max(self._virtual_height - height, 1),
                    ratio=height / self._virtual_height,
                )
            )

            for i, line in enumerate(lines):
                if i >= height - scrollbar_x:
                    break

                span = line[-1]

                lines[i] = (  # type: ignore
                    *line[:-1],
                    span.mutate(text=span.text[:-1]),
                    *(markup_spans(self.styles["scrollbar_y"](chars[i]))),
                )

    def _apply_frame(self, lines: list[tuple[Span, ...]], width: int) -> None:
        """Adds frame characters around the given lines."""

        def _style(item) -> tuple[Span, ...]:
            return self._parse_markup(self.styles["frame"](item))

        left_top, right_top, right_bottom, left_bottom = self.frame.corners
        left, top, right, bottom = self.frame.borders

        for i, line in enumerate(lines):
            lines[i] = (*_style(left), *line, *_style(right))

        if left_top + top + right_top != "":
            lines.insert(
                0, (*_style(left_top), *_style(top * width), *_style(right_top))
            )

        if left_bottom + bottom + right_bottom != "":
            lines.append(
                (*_style(left_bottom), *_style(bottom * width), *_style(right_bottom))
            )

    def _horizontal_align(self, line: tuple[Span, ...], width: int) -> tuple[Span, ...]:
        """Aligns a tuple of spans horizontally, using `self.alignment[0]`."""

        length = sum(len(span.text) for span in line)
        diff = width - length

        if line in [tuple(), (Span(""),)]:
            return self._parse_markup(self.styles["content"](diff * " "))

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

    def _vertical_align(self, lines: list[tuple[Span, ...]], height: int) -> None:
        """Aligns a list of tuples of spans vertically, using `self.alignment[1]`.

        Note that this mutates `lines`.
        """

        available = height - len(lines)
        alignment = self.alignment[1]
        filler = self._parse_markup(self.styles["content"](" "))

        if alignment is Alignment.START:
            lines.extend([filler] * available)
            return

        if alignment is Alignment.CENTER:
            top, extra = divmod(available, 2)
            bottom = top + extra

            for _ in range(top):
                lines.insert(0, filler)

            lines.extend([filler] * bottom)
            return

        for _ in range(available):
            lines.insert(0, filler)

    def _slice_line(
        self, line: tuple[Span, ...], start: int, end: int
    ) -> tuple[tuple[Span, ...], int]:
        """Slices a line into the given width.

        Returns:
            A tuple of (sliced_line, virtual_width).
        """

        width = end - start
        virt = sum(len(span) for span in line)

        line_list = []

        before_start = 0
        occupied = 0

        for span in line:
            length = len(span)

            before_start += length
            if before_start < start:
                continue

            new = span[max(start - (before_start - length), 0) :]
            length = len(new)

            line_list.append(new)

            occupied += length

            if occupied > width:
                break

        width_diff = max(occupied - width, 0)

        if width_diff > 0 and len(line_list) > 0:
            for i, span in enumerate(reversed(line_list)):
                length = len(span)

                new = span[:-width_diff]
                width_diff -= length - len(new)

                line_list[-i - 1] = new

                if width_diff <= 0:
                    break

        if not line_list:
            line_list.extend(self._parse_markup(self.styles["content"](" ")))

        occupied = sum(len(span) for span in line_list)

        if occupied < width:
            end = line_list[-1]

            line_list[-1] = end.mutate(text=end.text + (width - occupied) * " ")

        return tuple(line_list), virt

    def handle_keyboard(self, key: str) -> bool:
        ...

    def handle_mouse(self, action: MouseAction, position: tuple[int, int]) -> bool:
        ...

    def get_content(self) -> list[str]:
        """Gets the dynamic content for this widget."""

        raise NotImplementedError

    def build(self) -> list[tuple[Span, ...]]:
        """Builds the strings that represent the widget."""

        def _clamp_scroll(scroll: int, dim: int, virt: int) -> int:
            return max(min(scroll, virt - dim + 3 * (virt >= dim)), 0)

        width = max(self.width - self.frame.width, 0)
        height = max(self.height - self.frame.height, 0)

        self.scroll = (
            _clamp_scroll(self.scroll[0], self.width, self._virtual_width),
            _clamp_scroll(self.scroll[1], self.height, self._virtual_height),
        )

        content_style = self.styles["content"]

        lines: list[tuple[Span, ...]] = [
            self._parse_markup(content_style(line)) for line in self.get_content()
        ]

        self._virtual_height = len(lines)

        if self._virtual_height > height:
            lines = lines[self.scroll[1] : self.scroll[1] + height]

            if len(lines) < height:
                lines.extend([(Span(""),)] * (height - len(lines)))

        # Handle alignment
        self._vertical_align(lines, height)

        for i, line in enumerate(lines):
            lines[i] = self._horizontal_align(line, width)

        lines_and_widths = [
            self._slice_line(line, self.scroll[0], self.scroll[0] + width)
            for line in lines
        ]

        self._virtual_width = max(lines_and_widths, key=lambda item: item[1])[1]
        lines = [line for line, _ in lines_and_widths]

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
