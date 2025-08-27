import string

from functools import partial, lru_cache
from typing import Any, Callable, TypeVar

from slate import Key, Event, Span, terminal, Color
from zenith import zml_escape

from . import frames
from .enums import Alignment, Direction, Anchor, Overflow, QuickSelect
from .widget import Widget, _apply_style, _compute, WidgetFields

PRINTABLE_LIST = [*string.printable]

__all__ = [
    "button",
    "container",
    "cursor",
    "matrix",
    "root",
    "row",
    "slider",
    "text",
    "text_field",
    "tower",
]

BEHAVIOURS = {}

def behaviour(func: Callable[[Widget, WidgetFields], None]) -> Callable[[Widget, WidgetFields], None]:
    BEHAVIOURS[func.__name__] = func

    return func

def _gather_qs_self_children(widgets: list[Widget]) -> list[Widget]:
    output = []

    for widget in widgets:
        if widget.quick_select is QuickSelect.SELF:
            output.append(widget)
            continue

        active_children = getattr(widget, "active_children", [])

        if widget.quick_select is QuickSelect.CONTENTS and active_children is not None:
            output.extend(_gather_qs_self_children(active_children))
            continue

    return output


def _find_word_end(line: str, direction: int = 1) -> int:
    """Returns the distance from the next word boundary."""

    # Consistent with unix shell behaviour:
    # * Always delete first char, then remove any non-punctuation
    # Note that the exact behaviour isn't standardized:
    # * Python repl: until change in letter+digit & punctuation
    # * Unix shells: only removes letter+digit
    word_chars = string.ascii_letters + string.digits

    if direction == -1:
        strip_line = line.rstrip(word_chars)
    else:
        strip_line = line.lstrip(word_chars)

    return -direction * (len(strip_line) - len(line)) + direction


@Widget.from_behaviour()
@behaviour
def text(widget: Widget, fields: WidgetFields):
    widget.inert = True

    for state in widget.style_map.keys():
        if state == "*":
            continue
        widget.style_map[state]["content"] = "opaque"

    @widget.add_initializer
    def initialize(self, text: str) -> list[str]:
        fields.define_public(text=text)

    @widget.bind
    def get_contents(self) -> list[str]:
        return [fields.text]


@Widget.from_behaviour()
@behaviour
def button(widget: Widget, fields: WidgetFields):
    widget.on_submit: Event[Widget] = Event("on submit")

    widget.add_rules(
        """
        width_offset=2,
        alignment=(center;start),
        frame=(double;frameless;double;frameless),

        ~frame=.primary-1,
        ~background=@.panel1-1,

        /selected/
            ~content=[],
            ~background=@white,
            ~frame=white,
        """
    )

    @widget.add_initializer
    def initialize(
        self, label: str, submit_callback: Callable[[Widget], bool | None] | None = None
    ) -> list[str]:
        fields.define_public(label=label)

        if submit_callback is not None:
            self.on_submit += submit_callback

    @widget.bind
    def get_contents(self):
        return [f"[dim]{self.qs_hint + ' ' if self.qs_hint else ''}[/dim]" + fields.label]

    @widget.on_key.append
    def submit(args):
        self, key = args

        if key in [" ", "return"]:
            self.on_submit(self)


@behaviour
def container(direction: Direction, widget: Widget, fields: WidgetFields) -> dict[str, Any]:
    widget.width = -1
    widget.height = -1
    widget.quick_select = QuickSelect.CONTENTS

    for state in widget.style_map.keys():
        if state == "*":
            continue

        widget.style_map[state]["content"] = ""

    @widget.add_initializer
    def initialize(self, children: list[Widget] | None = None) -> list[str]:
        fields.define_public(gap=1)

        fields.define_readonly(
            children=[],
            active_children=[],
            selected=None,
            direction=direction,
        )

        fields.define_private(
            qs_offset=1,
            qs_shown=False,
        )

        widget.qs_binds = {}

        for child in children or []:
            self.append(child)

    @widget.bind
    def append(self, el: Widget) -> None:
        fields.children.append(el)
        self._init_widget(el)

    @widget.bind
    def remove(self, el: Widget) -> None:
        fields.children.remove(el)

    @widget.bind
    def replace(self, original: Widget, replacement: Widget) -> None:
        idx = fields.children.index(original)
        self.remove(original)
        self.insert(idx, replacement)

    @widget.bind
    def insert(self, idx: int, widget: Widget) -> None:
        fields.children.insert(idx, widget)
        self._init_widget(widget)

    @widget.bind
    def replace_children(self, new: list[Widget]) -> None:
        fields.children = new

        for child in new:
            self._init_widget(child)

    @widget.bind
    def _init_widget(self, el: Widget):
        el.parent = self

        # Build once to assign correct shrink sizing
        el.build()

        if el.inert:
            return

        offset = fields.qs_offset

        if el.quick_select is QuickSelect.CONTENTS:
            for i, child in enumerate(_gather_qs_self_children(el.active_children)):
                offset = fields.qs_offset + i
                self.qs_binds[offset] = child
                child.qs_bind = offset

        elif el.quick_select is QuickSelect.SELF:
            self.qs_binds[offset] = el
            el.qs_bind = offset

        else:
            raise NotImplementedError(f"wtf is {el.quick_select!r}")

        fields.qs_offset = offset + 1

    @widget.state_machine.on_action.append
    def cascade_selected_state(action: str):
        if "SELECTED" not in action:
            return

        if action == "UNSELECTED" and fields.selected is not None:
            fields.selected.state_machine.apply_action(action)

        if action == "SELECTED" and len(fields.active_children) == 1 and widget.quick_select == QuickSelect.CONTENTS:
            fields.selected = fields.active_children[0]

        if fields.selected is not None:
            fields.selected.state_machine.apply_action(action)

    @widget.on_key.append
    def handle_selection(args) -> bool:
        self, key = args

        if fields.selected is not None and fields.selected.handle_keyboard(key):
            return True

        if key == "escape" and fields.selected is not None:
            fields.selected.state_machine.apply_action("UNSELECTED")
            fields.selected = None

            return True

        key_str = str(key)

        if key_str.isdigit() and (bound := self.qs_binds.get(int(key_str))):
            if fields.selected is not None:
                fields.selected.state_machine.apply_action("UNSELECTED")

            fields.selected = bound
            bound.state_machine.apply_action("SELECTED")
            self.state_machine.apply_action("SELECTED")
            return True

        return False

    @widget.on_build_start.append
    def set_active_children(self):
        fields.active_children = [child for child in fields.children if not child.inert]
        self.inert = all(child.inert for child in fields.children)

    @widget.on_build_start.append
    def arrange(self):
        def _align(alignment, available):
            available = max(available, 0)
            if available == 1:
                return 0, 0
            if alignment == Alignment.CENTER:
                return divmod(available, 2)
            if alignment == Alignment.END:
                return available, 0
            return 0, 0

        def _is_fill(widget_child, horizontal):
            if horizontal:
                return widget_child.width is None or (
                    isinstance(widget_child.width, float) and widget_child.width > 0
                )
            return widget_child.height is None or (
                isinstance(widget_child.height, float) and widget_child.height > 0
            )

        def _compute_offset(offset, negative):
            if isinstance(offset, float):
                return int(negative * max(offset, 0))

            if offset < 0:
                return negative + offset

            return offset

        x, y = self.position
        x -= self.scroll[0]
        y -= self.scroll[1]
        parent_anchor = x, y

        x += 1 if self.frame.left else 0
        y += 1 if self.frame.top else 0

        children = fields.children

        if not children:
            self.parts = []
            return

        available_width = max(
            self._framed_width, self._virtual_width
        ) - self.has_scrollbar(1) - self.width_offset
        available_height = max(
            self._framed_height, self._virtual_height
        ) - self.has_scrollbar(0) - self.height_offset

        direction = fields.direction
        is_horizontal = direction == Direction.HORIZONTAL

        fill_children = []
        non_fill_children = []

        for child in children:
            if child.anchor in [Anchor.SCREEN, Anchor.PARENT]:
                child.compute_dimensions(terminal.width, terminal.height)

                if child.anchor is Anchor.SCREEN:
                    context = terminal.size
                    origin = (0, 0)

                elif child.anchor is Anchor.PARENT:
                    context = self.computed_width, self.computed_height
                    origin = parent_anchor

                else:
                    raise NotImplementedError(
                        f"not sure how to handle anchor: {child.anchor}"
                    )

                x_offset = _compute_offset(
                    child.offset[0], context[0] - child.computed_width
                )
                y_offset = _compute_offset(
                    child.offset[1], context[1] - child.computed_height
                )

                child.position = (
                    origin[0] + x_offset,
                    origin[1] + y_offset,
                )
                continue

            if _is_fill(child, is_horizontal):
                fill_children.append(child)

            else:
                if child.width == -1 or child.height == -1:
                    child._last_state = None
                    child.build()
                child.compute_dimensions(available_width, available_height)
                non_fill_children.append(child)

        if is_horizontal:
            used_space = sum(child.computed_width for child in non_fill_children)
            gap = _compute(fields.gap, available_width - used_space)
            used_space += gap * max(len(children) - 1, 0)
            remaining_space = max(available_width - used_space, 0)
        else:
            used_space = sum(child.computed_height for child in non_fill_children)
            gap = _compute(fields.gap, available_height - used_space)
            used_space += gap * max(len(children) - 1, 0)
            remaining_space = max(available_height - used_space, 0)

        # Distribute remaining space among fill children
        if fill_children:
            fill_size, fill_remainder = divmod(remaining_space, len(fill_children))
            for i, child in enumerate(fill_children):
                if child.width == -1 or child.height == -1:
                    child._last_state = None
                    child.build()
                extra = 1 if i < fill_remainder else 0
                if is_horizontal:
                    child.compute_dimensions(fill_size + extra, available_height)
                else:
                    child.compute_dimensions(available_width, fill_size + extra)

        # Second pass: position all children
        all_children = []
        current_x, current_y = x, y

        # Calculate total content size for alignment
        if is_horizontal:
            total_content_width = sum(
                child.computed_width for child in children
            ) + gap * max(len(children) - 1, 0)
            content_align_x, content_align_x_extra = _align(
                self.alignment[0], available_width - total_content_width
            )
            current_x += content_align_x + content_align_x_extra
        else:
            total_content_height = sum(
                child.computed_height for child in children
            ) + gap * max(len(children) - 1, 0)
            content_align_y, content_align_y_extra = _align(
                self.alignment[1], available_height - total_content_height
            )
            current_y += content_align_y + content_align_y_extra

        s_start, s_end = [list(val) for val in self.inner_rect]

        for child in children:
            all_children.extend([child, *child.parts])

            if child.anchor is not Anchor.NONE:
                continue

            if is_horizontal:
                align_y, align_y_extra = _align(
                    self.alignment[1], available_height - child.computed_height + self.height_offset
                )

                child.position = (current_x, current_y + align_y + align_y_extra)
                current_x += child.computed_width + gap
            else:
                align_x, align_x_extra = _align(
                    self.alignment[0], available_width - child.computed_width + self.width_offset
                )

                child.position = (current_x + align_x + align_x_extra, current_y)
                current_y += child.computed_height + gap

            clip_start, clip_end = [0, 0], [0, 0]

            c_start, c_end = child.outer_rect

            if c_start[0] < s_start[0]:
                clip_start[0] = s_start[0] - c_start[0]

            if c_start[1] < s_start[1]:
                clip_start[1] = s_start[1] - c_start[1]

            if s_end[0] < c_end[0]:
                clip_end[0] = c_end[0] - s_end[0]

            if s_end[1] < c_end[1]:
                clip_end[1] = c_end[1] - s_end[1]

            child.clip(clip_start, clip_end)

        self.parts = [*all_children]

        bar_x, bar_y = self.scrollbars

        if self.has_scrollbar(0):
            self.parts.append(bar_x)

        if self.has_scrollbar(1):
            self.parts.append(bar_y)

        # Update virtual dimensions based on children
        non_anchored = [child for child in children if child.anchor is Anchor.NONE]

        if is_horizontal:
            total_width = sum(
                child.computed_width for child in non_anchored
            ) + gap * max(len(non_anchored) - 1, 0)
            max_height = max(
                (child.computed_height for child in non_anchored), default=1
            )
            self._virtual_width = total_width
            self._virtual_height = max_height
        else:
            max_width = max((child.computed_width for child in non_anchored), default=1)
            total_height = sum(
                child.computed_height for child in non_anchored
            ) + gap * max(len(non_anchored) - 1, 0)
            self._virtual_width = max_width
            self._virtual_height = total_height

    @widget.bind
    def build(self, fillchar: str = " "):
        lines = Widget.build(self, fillchar)

        if not len(lines):
            return lines

        qs_content = None

        if not self.inert and self.qs_bind is not None:
            show = False
            parent = self.parent

            while isinstance(parent, Widget):
                if parent.quick_select is QuickSelect.SELF:
                    show = parent.state_machine() == "selected" and parent.selected is None
                    break

                if parent.is_root():
                    show = parent.selected is None
                    break

                parent = parent.parent

            fields.qs_shown = show

            if show:
                qs_content = f"{self.qs_bind}"
                sp = Span(qs_content, dim=True)

                first_line = lines[0]

                truncated = []
                goal = len(qs_content)
                current = 0

                for i, span in enumerate(first_line):
                    new = current + len(span)

                    if new > goal:
                        cut = span[len(span) - (new - goal):]
                        if len(cut):
                            truncated.append(cut)
                        break

                    current = new

                lines[0] = (sp, *truncated, *first_line[i+1:])

        return lines

    @widget.bind
    def get_contents(self) -> list[str]:
        return [self._virtual_width * " "] * self._virtual_height

    def autoscroll():
        if fields.selected is None:
            return

        sel = fields.selected
        w, h = sel.computed_width, sel.computed_height
        clips = sel.viewport_offsets
        csx, csy = clips[0]
        cex, cey = clips[1]

        sx, sy = widget.scroll
        if cey > csy:
            widget.scroll = (sx + cex, sy + cey)
        elif csy > cey:
            widget.scroll = (sx - csx, sy - csy)

    @widget.bind
    def serialize(self) -> dict[str, Any]:
        output = {}

        for w in self.children:
            if not hasattr(w, "serialize"):
                continue

            output = {**output, **w.serialize()}

        return output


tower = Widget.create_type("tower", behaviours=[partial(container, Direction.VERTICAL)])
row = Widget.create_type("row", behaviours=[partial(container, Direction.HORIZONTAL)])


@Widget.from_behaviour()
@behaviour
def slider(widget: Widget, fields: WidgetFields):
    widget.add_rules(
        """
        ~content=.panel1-2,
        ~frame=.panel1-1,
        overflow=hide,

        /selected/
            ~content=.panel1+1,
            ~frame=.primary,
        """
    )

    @widget.add_initializer
    def initialize(
        self,
        value: float = 0.5,
        thumb_size: int = 1,
        resolution: float = None,
        chars: tuple[str, str] = ("─", "█"),
        vertical: bool = False,
    ) -> None:
        self.value = value
        self.on_change = Event("on_change")

        fields.define_public(
            resolution=resolution,
            thumb_size=thumb_size,
            vertical=vertical,
            rail=chars[0],
            thumb=chars[1],
        )

        if fields.vertical:
            self.width = 1
            self.height = None
            self.frame = frames.Frame.compose(
                (frames.Frameless, frames.Light, frames.Frameless, frames.Light)
            )
        else:
            self.width = None
            self.height = 1
            self.frame = frames.Frame.compose(
                (frames.Light, frames.Frameless, frames.Light, frames.Frameless)
            )

    @widget.on_key.append
    def handle_cursor(args) -> bool:
        self, key = args

        up, down = [["arrow-left", "arrow-up"], ["arrow-down", "arrow-right"]]
        resolution = fields.resolution or 1 / self._framed_width
        original = self.value

        if key in up:
            self.value -= resolution

        elif key in down:
            self.value += resolution

        elif key in [str(r) for r in range(10)]:
            start = 0
            self.value = 0

            while round(self.value, 3) <= 1.0:
                self.value += resolution
                num = str(key)
                contents = "".join(self.get_contents())

                if num == "0":
                    if contents.endswith(num):
                        break
                    else:
                        continue

                if num + fields.rail not in contents:
                    break

        else:
            return False

        self.value = max(0, self.value)
        self.value = min(self.value, 1)
        self.value = round(self.value, 3)

        self.on_change(self)

        return True

    @widget.bind
    def _get_hint_positions(self):
        if fields.vertical:
            size = self._framed_height - fields.thumb_size
        else:
            size = self._framed_width - fields.thumb_size
            
        total = size + fields.thumb_size
        available_space = total - 10
        base_gap = available_space // 9
        remainder = available_space % 9
        
        positions = {}
        current_pos = 0
        positions[current_pos] = 1
        
        for number in [2, 3, 4, 5, 6, 7, 8, 9, 0]:
            gap_size = base_gap + (1 if remainder > 0 else 0)
            if remainder > 0:
                remainder -= 1
            current_pos += 1 + gap_size
            positions[current_pos] = number

        return positions

    @widget.bind
    def get_contents(self):
        thumb_char = fields.thumb.replace("\\", "")

        if fields.vertical:
            size = self._framed_height - fields.thumb_size
        else:
            size = self._framed_width - fields.thumb_size

        start = int(size * self.value)
        styles = self.get_styles()

        thumb_chars = [thumb_char] * fields.thumb_size

        if self.qs_hint != "":
            thumb_chars[fields.thumb_size // 2] = f"[invert dim]{self.qs_hint}[/invert /dim]"

        rail = size * fields.rail

        if self.state_machine() == "selected":
            rail = ""
            positions = self._get_hint_positions()
            total = size + fields.thumb_size
            
            for i in range(total):
                rail += str(positions[i]) if i in positions else fields.rail

        line = [
            *[styles["content"](rail[:start])],
            *styles["frame"]("".join(thumb_chars)),
            *[styles["content"](rail[start - size:])],
        ]

        if fields.vertical:
            return line

        return ["".join(line)]


@Widget.from_behaviour()
@behaviour
def cursor(widget: Widget, fields: WidgetFields):
    widget.add_rules(
        """
        ~content=.panel1-1,

        /selected/
            ~content=[.primary bold],
        """
    )

    @widget.add_initializer
    def initialize(self, value: tuple[int, int] = (0, 0)):
        self.value = value

        fields.define_private(
            is_capturing=False,
            last_key=None,
        )

    @widget.bind
    def get_contents(self) -> list[str]:
        styles = self.get_styles()

        def _style(char, key):
            if fields.last_key == key:
                return styles["content"](char)

            return styles["frame"](char)

        center = _style("o", None) if fields.is_capturing else _style(".", None)
        up = _style("ʌ", "up")
        left = _style("<", "left")
        right = _style(">", "right")
        down = _style("v", "down")

        return [
            f"   {up}  ",
            f"[opaque] {left} {center} {right} ",
            f"   {down}  ",
        ]

    @widget.on_key.append
    def handle(args):
        self, key = args

        if key == " ":
            fields.is_capturing = not fields.is_capturing
            return True

        if not fields.is_capturing:
            fields.last_key = None
            return False

        if key not in ("arrow-left", "arrow-right", "arrow-up", "arrow-down"):
            return False

        x = self.value[0]
        y = self.value[1]

        if "left" in key:
            x -= 0.1
        elif "right" in key:
            x += 0.1
        elif "up" in key:
            y -= 0.1
        elif "down" in key:
            y += 0.1

        fields.last_key = key

        original = (x, y)
        self.value = (max(min(x, 1), 0), max(min(y, 1), 0))

        self.on_change(self)

        return True

@Widget.from_behaviour()
@behaviour
def text_field(widget: Widget, fields: WidgetFields):
    widget.width = 1.0
    widget.overflow = (Overflow.AUTO, Overflow.AUTO)

    widget.add_rules(
        """
        ~cursor=[],

        /selected/
            ~cursor=@white,
        """
    )

    @widget.add_initializer
    def initialize(self, value: str = "", placeholder: str = "", multiline: bool = False):
        self.value = value

        fields.define_public(
            placeholder=placeholder,
            multiline=multiline,
        )

        fields.define_readonly(
            cursor=(0, 0),
            cursor_line=("", "", ""),
        )

        fields.define_private(
            cursor_column_hint=0,
            lines=[],
        )

        self._eval_lines()

    @widget.bind
    def _eval_lines(self) -> None:
        fields.lines = self.value.split("\n")

        x, y = fields.cursor
        line = fields.lines[y]

        left, right = line[:x], line[x + 1 :]
        cursor = line[x] if x < len(line) else ""
        fields.cursor_line = left, cursor, right

    @widget.bind
    def move_cursor(
        self, dx: int = 0, dy: int = 0, absolute: bool = False, smart: bool = False
    ) -> bool:
        cx, cy = fields.cursor
        reset_hint = False

        if absolute:
            x, y = dx, dy

        else:
            if smart:
                if dx < 0 and cx == 0 and 0 < cy <= len(fields.lines):
                    cx = 0
                    dx = len(fields.lines[cy - 1])
                    dy -= 1

                    reset_hint = True

                elif (
                    0 < dx
                    and cx == len(fields.lines[cy])
                    and dy == 0
                    and cy < len(fields.lines) - 1
                ):
                    cx = 0
                    dx = 0
                    dy += 1

                    fields.cursor_column_hint = 0
                    reset_hint = True

            x = max(cx + dx, fields.cursor_column_hint)
            y = cy + dy

        y = max(0, min(len(fields.lines) - 1, y))

        line = fields.lines[y]

        x = max(0, min(len(line), x))

        if reset_hint:
            fields.cursor_column_hint = 0
        else:
            fields.cursor_column_hint = max(fields.cursor_column_hint, x)

        fields.cursor = (x, y)
        self._eval_lines()

        return fields.cursor != (cx, cy)

    @widget.bind
    def set_line(self, y: int, line: str) -> None:
        self.value = "\n".join(
            [
                *fields.lines[:y],
                line,
                *fields.lines[y + 1 :],
            ]
        )

        self._eval_lines()

    @widget.bind
    def delete_trailing_newline(self) -> None:
        """Deletes a newline from the end of the current line.

        No-op when y == 0.
        """

        x, y = fields.cursor

        if y == 0:
            return

        line = fields.lines[y - 1]
        left, right = line[:x], line[x + 1 :]
        cursor = line[x] if x < len(line) else ""

        fields.lines[y - 1] += fields.lines[y]
        fields.lines.pop(y)

        self.value = "\n".join(fields.lines)

        self.scroll = (self.scroll[0], self.scroll[1] - 1)
        self.move_cursor(dy=-1, dx=len(left + cursor + right))
        self._eval_lines()

    @widget.on_key.append
    def handle_input(args) -> bool:
        self, key = args

        if key == "left":
            fields.cursor_column_hint = 0
            return self.move_cursor(dx=-1, smart=True)

        if key == "right":
            fields.cursor_column_hint = 0
            return self.move_cursor(dx=1, smart=True)

        if key == "up":
            return self.move_cursor(dy=-1, smart=True)

        if key == "down":
            return self.move_cursor(dy=1, smart=True)

        if key == "ctrl-up":
            return self.move_cursor(dx=fields.cursor[0], dy=0, absolute=True)

        if key == "ctrl-down":
            return self.move_cursor(
                dx=fields.cursor[0], dy=len(fields.lines) - 1, absolute=True
            )

        x, y = fields.cursor
        left, cursor, right = fields.cursor_line

        if key == "alt-left":
            return self.move_cursor(dx=_find_word_end(left, direction=-1))

        if key == "alt-right":
            return self.move_cursor(dx=_find_word_end(right + " "))

        if key == "ctrl-left":
            return self.move_cursor(0, y, absolute=True)

        if key == "ctrl-right":
            return self.move_cursor(len(left + cursor + right), y, absolute=True)

        if key == "backspace":
            if x == 0:
                self.delete_trailing_newline()
                self.rebuild_ancestry()
                return True

            self.set_line(y, left[: -max(1, len(cursor))] + cursor + right)

            fields.cursor_column_hint = 0
            self.move_cursor(dx=-1)
            return True

        if key == "ctrl-backspace":
            if x == 0:
                self.delete_trailing_newline()
                return True

            self.set_line(y, cursor + right)
            change = len(left)

            fields.cursor_column_hint = 0
            self.move_cursor(dx=-change)
            return True

        if key == "alt-backspace":
            if x == 0:
                self.delete_trailing_newline()
                return True

            distance = _find_word_end(left, direction=-1)

            self.set_line(y, left[:distance] + cursor + right)
            fields.cursor_column_hint = 0
            self.move_cursor(dx=distance)

            return True

        if key == "return":
            if not fields.multiline:
                return True

            lines = fields.lines

            if cursor != "":
                right = cursor + right

            lines[y] = left

            if len(lines) > y + 1:
                lines.insert(y + 1, right)
            else:
                lines.append(right)

            self.value = "\n".join(lines)
            fields.cursor_column_hint = 0
            self.move_cursor(dx=-fields.cursor[0], dy=1)

            self.rebuild_ancestry()
            return True

        if key in PRINTABLE_LIST:
            self.set_line(y, left + str(key) + cursor + right)
            self.move_cursor(dx=1)
            return True

    @widget.bind
    def get_contents(self) -> list[str]:
        value = self.value or fields.placeholder
        styles = self.get_styles()
        frame_style = styles["frame"]
        content_style = styles["content"]
        cursor_style = styles["cursor"]

        if not value:
            return [self.qs_hint + content_style("") + cursor_style(" ") + "[/]" + content_style(" ")]

        if self.value == "":
            content_style = frame_style

        left, cursor, right = (
            zml_escape(part.replace("\\", "⧵")) for part in fields.cursor_line
        )

        if cursor == "":
            cursor = " "

        lines = [zml_escape(line) for line in fields.lines]
        y = fields.cursor[1]

        styled_cursor_line = (
            self.qs_hint
            + content_style(left)
            + cursor_style(cursor)
            + "[/]"
            + content_style(right)
            + " "
        )

        return [
            *(f"{line}" for line in lines[:y]),
            styled_cursor_line,
            *(f"{line}" for line in lines[y + 1 :]),
        ]


# @Widget.from_behaviour()
def matrix(widget: Widget):
    @widget.add_initializer
    def initialize(self, cols: int = 10, rows: int = 10, dense: bool = True):
        self.cols = cols
        self.rows = rows
        self.dense = dense
        self.cursor = (0, 0)
        self._checkerboard = []
        self._data: list[list[Color]] = []

        for y in range(self.rows):
            line = []

            for x in range(self.cols):
                line.append("main.panel1-3" if (x + y % 2) % 2 else "main.panel1-1")

            self._checkerboard.append(line)
            self._data.append([None] * self.cols)

    @lru_cache
    def _color_from_style(style: str | Callable) -> Color:
        if not callable(style):
            raw = style
            style = lambda x: f"[{raw}]{x}[/]"

        span = _apply_style(" ", style)[0]

        return span.foreground or span.background

    @widget.on_key.append
    def move_cursor(args) -> bool:
        self, key = args

        cx, cy = self.cursor

        if key == "arrow-up":
            cy -= 1
        elif key == "arrow-down":
            cy += 1
        elif key == "arrow-left":
            cx -= 1
        elif key == "arrow-right":
            cx += 1
        elif key == "return":
            current = self._data[cy][cx]
            self._data[cy][cx] = None if current else "white"
        else:
            return False

        og = self.cursor
        self.cursor = (
            max(0, min(cx, self.cols - 1)),
            max(0, min(cy, self.rows - 1)),
        )

        return self.cursor != og

    @widget.bind
    def get_contents(self) -> list[str]:
        styles = self.get_styles()

        lines = []

        for y in range(self.rows):
            line = []
            for x in range(self.cols):
                if self.cursor == (x, y) and self.state_machine() == "selected":
                    color = Color.white().darken(5)
                else:
                    color = _color_from_style(
                        self._data[y][x] or self._checkerboard[y][x]
                    )

                line.append(color.hex)

            if not self.dense:
                lines.append("".join(f"[@{bg}] [/]" for bg in line))
                continue

            if y % 2:
                lines.append("".join(f"[@{bg} {fg}]▄[/]" for fg, bg in zip(line, last)))

            else:
                last = line

        return lines


@Widget.from_behaviour(base=tower)
@behaviour
def root(widget: Widget, fields: WidgetFields):
    widget.add_rules(
        """
        anchor=screen,
        position=(0;0),
        alignment=center,
        overflow=auto,
        quick_select=self,

        layer=-1,
        """
    )

    widget.width = 1.0
    widget.height = 1.0

    @terminal.on_resize.append
    def _resize(size):
        widget.scroll = (0, 0)
        widget.compute_dimensions(*size)

    _resize((terminal.width, terminal.height))

    @widget.on_build_start.append
    def always_select(self):
        widget.state_machine.apply_action("SELECTED")
