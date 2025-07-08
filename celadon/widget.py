from __future__ import annotations

import re
import uuid
from copy import deepcopy
from functools import lru_cache
from typing import TYPE_CHECKING, Any, Callable, Type

from slate import Event, Span, Key
from slate.span import EMPTY_SPAN
from zenith.markup import zml_get_spans, zml_pre_process, preserve_escapes, FULL_RESET

from .enums import Alignment, Anchor, Overflow
from .frames import Frame, get_frame
from .state_machine import StateMachine

if TYPE_CHECKING:
    from .application import Application

__all__ = ["Widget"]


def _compute(spec: int | float | None, hint: int) -> int:
    if isinstance(spec, float):
        return int(spec * hint)

    if spec is None:
        return hint

    if isinstance(spec, int):
        return spec

    raise ValueError(f"invalid dimension spec {spec!r} - must be float, int or None")


RE_FULL_UNSETTER = re.compile(r"(?<=\[)[^\]]*(\/) ")

def _apply_style(line: str, style: Callable[[str], str]) -> tuple[Span, ...]:
    raw_style = style("")

    line = RE_FULL_UNSETTER.sub("/ " + raw_style, line)
    line = zml_pre_process(preserve_escapes(style(line)))

    return tuple(
        span for span in zml_get_spans(line) if span is not FULL_RESET
    )


class Widget:
    position: tuple[int, int]
    width: int | float | None
    height: int | float | None
    computed_width: int
    computed_height: int
    layer: int
    parent: "Container" | None
    app: "Application"
    state_machine: StateMachine
    parts: list[Widget]
    palette: str
    inert: bool

    @classmethod
    def create_type(cls, name: str, behaviours: list[Callable[Widget]]) -> Callable[[Any, ...], Widget]:
        def _construct(*args, eid: str | None = None, **kwargs) -> Widget:
            w = Widget(eid=eid, type_name=name)

            if len(args) and len(w.initializers):
                raise ValueError(
                    "please only use keyword arguments in multi-initializer widget construction"
                    + " to avoid inconsistent behaviour."
                )

            for setup in behaviours:
                setup(w)

            for init in w.initializers:
                code = init.__code__
                arg_names = [arg for arg in code.co_varnames[:code.co_argcount] if arg != "self"]

                if len(args):
                    for k, v in zip(arg_names, args):
                        kwargs[k] = v

                init(**{k: v for k, v in kwargs.items() if k in arg_names})

            w.on_init(w)
            return w

        return _construct

    def bind(self, function: Callable) -> Callable:
        bound = function.__get__(self, self.__class__)
        setattr(self, function.__name__, bound)

        return bound

    def add_initializer(self, function: Callable) -> Callable:
        self.initializers.append(self.bind(function))

        return function

    def add_behaviour(self, behaviour: Callable[[Widget], dict[str, Any]]) -> None:
        behaviour(self)

    def __init__(self, *, eid: str | None = None, type_name: str = "Widget") -> None:
        self.eid = eid or str(uuid.uuid4())
        self.type_name = type_name

        self.position = (0, 0)
        self.width = -1
        self.height = -1
        self.computed_width = 1
        self.computed_height = 1
        self.scroll = (0, 0)
        self.layer = 0
        self.parent = None
        self.parts = []
        self.dirty = True
        self.inert = False

        self.anchor = Anchor.NONE
        self.offset = (0, 0)

        self.palette = "main"
        
        self.initializers = []

        self.state_machine = StateMachine(
            states=("idle", "hover", "selected", "active", "disabled"),
            transitions={
                "idle": {
                    "DISABLED": "disabled",
                    "HOVERED": "hover",
                    "SELECTED": "selected",
                    "CLICKED": "active",
                },
                "hover": {
                    "DISABLED": "disabled",
                    "RELEASED": "idle",
                    "SELECTED": "selected",
                    "CLICKED": "active",
                },
                "selected": {
                    "DISABLED": "disabled",
                    "UNSELECTED": "idle",
                    "CLICKED": "active",
                },
                "active": {
                    "DISABLED": "disabled",
                    "RELEASED": "idle",
                    "RELEASED_KEYBOARD": "selected",
                },
                "disabled": {
                    "ENABLED": "idle",
                },
            },
        )

        self.style_map = {
            "idle": {
                "background": "",
                "frame": ".panel1-2",
                "content": ".text",
                "scrollbar_x": "@.panel1-2",
                "scrollbar_y": "@.panel1-2",
            },
            "selected": {
                "background": "",
                "frame": ".panel1+2",
                "content": ".text bold",
                "scrollbar_x": "@.panel1-2",
                "scrollbar_y": "@.panel1-2",
            },
            "hover": {
                "background": "",
                "frame": ".panel1+1",
                "content": ".text",
                "scrollbar_x": "@.panel1-2",
                "scrollbar_y": "@.panel1-2",
            },
            "active": {
                "background": "",
                "frame": ".panel1+2",
                "content": ".text",
                "scrollbar_x": "@.panel1-2",
                "scrollbar_y": "@.panel1-2",
            },
            "disabled": {
                "background": "",
                "frame": ".panel1-1",
                "content": ".text-1",
                "scrollbar_x": "@.panel1-3",
                "scrollbar_y": "@.panel1-3",
            }
        }

        self.frame = get_frame(None)()
        self.alignment = (Alignment.START, Alignment.START)
        self.overflow = (Overflow.HIDE, Overflow.HIDE)
     
        self._cached_styles = [None, None]

        self._virtual_width = 0
        self._virtual_height = 0
        self._clip_start = (0, 0)
        self._clip_end = (0, 0)
        self._last_build = None
        
        self.on_init: Event[Widget] = Event("on init")

        self.on_content_start: Event[Widget] = Event("pre content")
        self.on_content: Event[Widget] = Event("post content")
        self.on_build_start: Event[Widget] = Event("pre build")
        self.on_build: Event[Widget] = Event("post build")

        self.on_key: Event[Widget, Key] = Event("on key pressed")
        self.on_mouse: Event[Widget, MouseAction, tuple[int, int]] = Event("on mouse action")

        self.state_machine.on_change += lambda *_: self.set_dirty()

    def __str__(self) -> str:
        return self.type_name

    def __repr__(self) -> str:
        return f"{self.type_name}"

    @property
    def _framed_width(self) -> int:
        return max(self.computed_width - self.frame.width, 0)

    @property
    def _framed_height(self) -> int:
        return max(self.computed_height - self.frame.height, 0)

    @lru_cache(1024)
    def _parse_markup(self, markup: str) -> tuple[Span, ...]:
        markup = zml_pre_process(preserve_escapes(markup))
        return tuple(zml_get_spans(markup))

    @property
    def clipped_position(self) -> tuple[int, int]:
        return (
            self.position[0] + self._clip_start[0],
            self.position[1] + self._clip_start[1],
        )

    def get_styles(self, raw: bool = False) -> dict[str, Callable[[str], str] | str]:
        # if self._cached_styles[raw] is not None:
        #    return self._cached_styles[raw]

        palette = self.palette

        def _fill_palette(style: str) -> str:
            words = []

            for word in style.split(" "):
                if not (word.startswith(".") or word.startswith("@.")):
                    words.append(word)
                    continue

                alpha = ""

                if "*" in word:
                    word, alpha = word.split("*")
                    alpha = "*" + alpha

                words.append(word.replace(".", palette + ".", 1) + alpha)

            return " ".join(words)

        values = self.style_map[self.state_machine()].copy() or {}

        if values == {}:
            return {}

        background = values.get("background", "")
        parent = self.parent

        while background == "" and isinstance(parent, Widget):
            background = parent.get_styles(raw=True)["background"]
            parent = parent.parent

        background = _fill_palette(background)
        styles = { "background": background if raw else lambda text, bg=background: f"[{bg}]{text}[/bg]" }

        for name, style in values.items():
            if name == "background":
                continue

            style = background + " " + _fill_palette(style)

            if raw:
                styles[name] = style
            else:
                styles[name] = lambda text, style=style: f"[{style}]{text}[/fg]"

        self._cached_styles[raw] = styles

        return styles

    def _vertical_truncate(self, lines: list[tuple[Span, ...]], height: int) -> list[tuple[Span, ...]]:
        if self._virtual_height > height:
            lines = lines[self.scroll[1] : self.scroll[1] + height]
            if len(lines) < height:
                lines.extend([(EMPTY_SPAN,)] * (height - len(lines)))
        return lines

    def _vertical_align(self, lines: list[tuple[Span, ...]], height: int, fillchar: str) -> None:
        alignment = self.alignment[1]
        available = height - len(lines)

        styles = self.get_styles()
        filler = _apply_style(fillchar, styles["content"])

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

    def _horizontal_align(self, line: tuple[Span, ...], width: int, fillchar: str) -> tuple[Span, ...]:
        alignment = self.alignment[0]
        width = max(width, self._virtual_width)
        length = sum(len(span) for span in line)
        diff = width - length

        style = self.get_styles()["content"]

        if line in [tuple(), (Span(""),)]:
            return _apply_style(diff * fillchar, style)

        if alignment is Alignment.START:
            return (*line[:-1], line[-1].mutate(text=line[-1].text + diff * fillchar))

        if alignment is Alignment.CENTER:
            end, extra = divmod(diff, 2)
            start = end + extra

            if "".join(span.text for span in line) == " ":
                return _apply_style((start + end) * fillchar, style)

            return (
                *_apply_style(start * fillchar, style),
                line[0],
                *line[1:],
                *_apply_style(end * fillchar, style),
            )

        if alignment is Alignment.END:
            span = line[0]
            return (span.mutate(text=diff * fillchar + span.text), *line[1:])

        raise NotImplementedError(f"Unknown alignment {alignment!r}.")

    @lru_cache(1024)
    def _horizontal_truncate(
        self, line: tuple[Span, ...], start: int, end: int
    ) -> tuple[Span, ...]:
        if end is None:
            end = len(line) - 1

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

            if length == 0:
                continue

            line_list.append(new)
            occupied += length

            if occupied > width:
                break

        width_diff = max(occupied - width, 0)
        empty = []

        if width_diff > 0 and len(line_list) > 0:
            for i, span in enumerate(reversed(line_list)):
                new = span[:-width_diff]
                width_diff -= len(span) - len(new)

                if len(new) == 0:
                    empty.append(-i - 1)
                else:
                    line_list[-i - 1] = new

                if width_diff <= 0:
                    break

        for offset, i in enumerate(empty):
            line_list.pop(i - offset)

        if not line_list:
            line_list.extend([Span(" ")])

        occupied = sum(len(span) for span in line_list)

        if occupied < width:
            suffix = line_list[-1]
            line_list[-1] = suffix.mutate(text=suffix.text + (width - occupied) * " ")

        return tuple(line_list)

    def _apply_frame(self, lines: list[tuple[Span, ...]], width: int) -> None:
        frame_style = self.get_styles()["frame"]

        left_top, right_top, right_bottom, left_bottom = self.frame.corners
        left, top, right, bottom = self.frame.borders

        for i, line in enumerate(lines):
            lines[i] = (
                *_apply_style(left, frame_style),
                *line,
                *_apply_style(right, frame_style),
            )

        if left_top + top + right_top != "":
            lines.insert(
                0,
                (
                    *_apply_style(left_top or (left != "") * top, frame_style),
                    *_apply_style(top * width, frame_style),
                    *_apply_style(right_top or (right != "") * top, frame_style),
                ),
            )

        if left_bottom + bottom + right_bottom != "":
            lines.append(
                (
                    *_apply_style(left_bottom or (left != "") * bottom, frame_style),
                    *_apply_style(bottom * width, frame_style),
                    *_apply_style(right_bottom or (right != "") * bottom, frame_style),
                )
            )

    def _apply_clip(self, lines: list[tuple[Span, ...]]) -> list[tuple[Span, ...]]:
        lines = [
            self._horizontal_truncate(line,
                self._clip_start[0],
                self.computed_width - self._clip_end[0]
            )
            for line in lines
        ]

        lines = lines[self._clip_start[1] :]

        if self._clip_end[1] > 0:
            lines = lines[: -self._clip_end[1]]

        return lines

    def _update_scrollbars(self, width: int, height: int) -> None:
        ...

    def set_dirty(self, value: bool = True):
        self.dirty = value

        if value:
            self._cached_styles = [None, None]

    def handle_keyboard(self, key: Key) -> bool:
        return self.on_key((self, key))

    def handle_mouse(self, action: MouseAction, position: tuple[int, int]) -> bool:
        self.on_mouse((self, action, position))

    def get_contents(self) -> list[str]:
        return []

    def is_root(self) -> bool:
        return self.parent is not None and not isinstance(self.parent, Widget)

    def build(self, fillchar: str = " ") -> list[str]:
        self.on_build_start(self)

        width = self._framed_width
        height = self._framed_height

        def _clamp_scrolls() -> tuple[int, int]:
            x_bar = width < self._virtual_width
            y_bar = height < self._virtual_height

            return (
                max(min(self.scroll[0], self._virtual_width - width + x_bar), 0),
                max(min(self.scroll[1], self._virtual_height - height + y_bar), 0),
            )

        self.scroll = _clamp_scrolls()

        self.on_content_start(self)
        content = self.get_contents()
        self.on_content(self)

        styles = self.get_styles()

        lines: list[tuple[Span, ...]] = [
            _apply_style(line, styles["content"]) for line in content
        ]

        self._virtual_height = len(lines) or 1
        self._virtual_width = max(
            (sum(len(span) for span in line) for line in lines), default=1
        )

        lines = self._vertical_truncate(lines, height)
        self._vertical_align(lines, height, fillchar)

        for i, line in enumerate(lines):
            lines[i] = self._horizontal_align(line, width, fillchar)

        lines = [
            self._horizontal_truncate(line,
                self.scroll[0],
                self.scroll[0] + width
            )
            for line in lines
        ]

        self._apply_frame(lines, width)

        if len(lines) > self.computed_height:
            lines = lines[: self.computed_height]

        lines = self._apply_clip(lines)

        self._update_scrollbars(width, height)

        self.on_build(self)

        self._last_build = lines

        if (
            self._clip_start[0] + self._clip_end[0] >= self.computed_width
            or self._clip_start[1] + self._clip_end[1] >= self.computed_height
        ):
            return []

        return lines

    def compute_dimensions(self, available_width: int, available_height: int) -> None:
        if self.width == -1:
            self.computed_width = self._virtual_width + self.frame.width
        else: 
            self.computed_width = _compute(self.width, available_width)

        if self.height == -1:
            self.computed_height = self._virtual_height + self.frame.height
        else:
            self.computed_height = _compute(self.height, available_height)

    def clip(self, start: tuple[int, int], end: tuple[int, int]) -> None:
        self._clip_start = start
        self._clip_end = end
