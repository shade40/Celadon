from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Generator, Type

from gunmetal import Event, Span
from zenith.markup import markup_spans, FULL_RESET

from ..enums import Alignment, Overflow, MouseAction
from ..frames import Frame, get_frame
from ..style_map import StyleMap
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

    if thumb_end >= size - 1:
        thumb_end = size
        thumb_start = thumb_end - thumb_length - offset

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
                "RELEASED": "idle",
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

    style_map = StyleMap(
        {
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
                "scrollbar_x": "panel1-1",
                "scrollbar_y": "panel1-1",
            },
            "selected": {
                "fill": "@accent",
                "frame": "panel1+1",
                "content": "text",
                "scrollbar_x": "panel1-1",
                "scrollbar_y": "panel1-1",
            },
            "active": {
                "fill": "@primary-3",
                "frame": "panel1+1",
                "content": "text-3",
                "scrollbar_x": "panel1-1",
                "scrollbar_y": "panel1-1",
            },
            "/scrolling_x": {
                "scrollbar_x": "primary",
            },
            "/scrolling_y": {
                "scrollbar_y": "primary",
            },
        }
    )
    """The style map is the lookup table for the widget's styles at certain states."""

    on_state_change: Event
    """Called when the widget's state changes.

    Args:
        state: The new state.
    """

    scroll: tuple[int, int] = (0, 0)
    """The widget's (horizontal, vertical) scrolling offset."""

    position: tuple[int, int] = (0, 0)
    """The widget's (horizontal, vertical) position."""

    def __init__(
        self,
        *args,
        width: int = 1,
        height: int = 1,
        frame: Frame | str = "Frameless",
        alignment: tuple[str | Alignment, str | Alignment] = ("center", "center"),
        overflow: tuple[str | Overflow, str | Overflow] = ("auto", "auto"),
        **kwargs,
    ) -> None:
        self.on_state_change = self.state_machine.on_change

        self.width = width
        self.height = height
        self.state_machine = deepcopy(self.state_machine)

        # These conversions are handled in their properties
        self.frame = frame  # type: ignore
        self.alignment = alignment  # type: ignore
        self.overflow = overflow  # type: ignore

        self._virtual_width = 0
        self._virtual_height = 0

        self._set_annotated_fields(args, kwargs)

        self.setup()

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

    def _set_annotated_fields(
        self, args: tuple[str, ...], kwargs: dict[str, Any]
    ) -> None:
        fields = self.__annotations__
        fields.update(**{key: getattr(self, key, None) for key in fields})

        for key, value in zip(fields.keys(), args):
            if key in kwargs:
                raise ValueError(
                    f"Annotated field {key!r} got multiple values: "
                    + f"({value!r}, {kwargs[key]!r}."
                )

            fields[key] = value

        fields.update(**kwargs)
        self.__dict__.update(**fields)

    def _parse_markup(self, markup: str) -> tuple[Span, ...]:
        """Parses some markup into a span of tuples.

        This also handles (ignores) zenith's FULL_RESET spans.
        """

        content_style = self.styles["content"]("")[1:-1]

        # Replace full unsetters with full unsetter + content style
        markup = markup.replace("/", "/ " + content_style)

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

        width = max(width, self._virtual_width)
        length = sum(len(span.text) for span in line)
        diff = width - length

        style = self.styles["content"]

        if line in [tuple(), (Span(""),)]:
            return self._parse_markup(style(diff * " "))

        alignment = self.alignment[0]

        if alignment is Alignment.START:
            return (*line[:-1], line[-1].mutate(text=line[-1].text + diff * " "))

        if alignment is Alignment.CENTER:
            end, extra = divmod(diff, 2)
            start = end + extra

            # Return padding as a single span instead of (start, content, end)
            # when content is " " (filler lines)
            if "".join(span.text for span in line) == " ":
                return self._parse_markup(style((start + end) * " "))

            return (
                *self._parse_markup(style(start * " ")),
                line[0],
                *line[1:],
                *self._parse_markup(style(end * " ")),
            )

        if alignment is Alignment.END:
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
    ) -> tuple[Span, ...]:
        """Slices a line into the given width."""

        width = end - start

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
                new = span[:-width_diff]
                width_diff -= len(span) - len(new)

                line_list[-i - 1] = new

                if width_diff <= 0:
                    break

        if not line_list:
            line_list.extend(self._parse_markup(self.styles["content"](" ")))

        occupied = sum(len(span) for span in line_list)

        if occupied < width:
            end = line_list[-1]

            line_list[-1] = end.mutate(text=end.text + (width - occupied) * " ")

        return tuple(line_list)

    def _apply_mouse_state(self, action: MouseAction) -> None:
        """Applies a state change action based on mouse input."""

        value = action.value

        if "click" in value:
            self.state_machine.apply_action("CLICKED")
            return

        if "hover" in value:
            self.state_machine.apply_action("HOVERED")
            return

        if "release" in value:
            self.state_machine.apply_action("RELEASED")
            return

    def setup(self) -> None:
        """Called at the end of __init__ to do custom set up."""

    def contains(self, position: tuple[int, int]) -> bool:
        """Determines whether this widget contains the given position."""

        rect = self.position, (
            self.position[0] + self.width,
            self.position[1] + self.height,
        )

        (left, top), (right, bottom) = rect

        return left < position[0] <= right and top < position[1] <= bottom

    def handle_keyboard(self, key: str) -> bool:
        ...

    def handle_mouse(self, action: MouseAction, position: tuple[int, int]) -> bool:
        self._apply_mouse_state(action)

        def _get_names(action: MouseAction) -> tuple[str, ...]:
            if action.value in ["hover", "release"]:
                return (action.value,)

            parts = action.value.split("_")

            # left click & right click or drag
            if parts[0] in ["left", "right"]:
                return (action.value, parts[1])

            if parts[0] == "shift":
                return (action.value, f"shift_{parts[1]}", parts[1])

            if parts[0] == "ctrl":
                return (action.value, f"ctrl_{parts[1]}", parts[1])

            # scrolling
            return (action.value, parts[0])

        possible_names = _get_names(action)

        for name in possible_names:
            if hasattr(self, f"on_{name}"):
                handle = getattr(self, f"on_{name}")

                if name.count("_") > 0:
                    handle(position)
                    return True

                handle(action, position)
                return True

        # Always return True for hover, even if no specific handler is found
        return action is MouseAction.HOVER

    def get_content(self) -> list[str]:
        """Gets the dynamic content for this widget."""

        raise NotImplementedError

    def build(self) -> list[tuple[Span, ...]]:
        """Builds the strings that represent the widget."""

        width = max(self.width - self.frame.width, 0)
        height = max(self.height - self.frame.height, 0)

        def _should_scroll(real: int, virt: int) -> bool:
            return real / max(virt, 1) <= 1.0

        def _clamp_scrolls() -> int:
            x_bar = _should_scroll(width, self._virtual_width)
            y_bar = _should_scroll(height, self._virtual_height)

            return (
                max(min(self.scroll[0], self._virtual_width - width + x_bar), 0),
                max(min(self.scroll[1], self._virtual_height - height + y_bar), 0),
            )

        self.scroll = _clamp_scrolls()

        content_style = self.styles["content"]

        lines: list[tuple[Span, ...]] = [
            self._parse_markup(content_style(line)) for line in self.get_content()
        ]

        self._virtual_height = len(lines)
        self._virtual_width = max(sum(len(span) for span in line) for line in lines)

        # Clip into vertical size
        if self._virtual_height > height:
            lines = lines[self.scroll[1] : self.scroll[1] + height]

            if len(lines) < height:
                lines.extend([(Span(""),)] * (height - len(lines)))

        # Handle alignment
        self._vertical_align(lines, height)

        for i, line in enumerate(lines):
            lines[i] = self._horizontal_align(line, width)

        # Clip into horizontal size
        lines = [
            self._slice_line(line, self.scroll[0], self.scroll[0] + width)
            for line in lines
        ]

        # Determine whether scrollbars should be shown
        scrollbar_x = self.overflow[0] is Overflow.SCROLL or (
            self.overflow[0] is Overflow.AUTO
            and _should_scroll(width, self._virtual_width)
        )

        scrollbar_y = self.overflow[1] is Overflow.SCROLL or (
            self.overflow[1] is Overflow.AUTO
            and _should_scroll(height, self._virtual_height)
        )

        # Composite together frame + content + scrollbar
        self._add_scrollbars(
            lines,
            width,
            height,
            scrollbar_x,
            scrollbar_y,
        )

        self._apply_frame(lines, width)

        return lines
