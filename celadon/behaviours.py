import string

from functools import partial
from typing import Any, Callable, Iterator

from slate import Event, Span, terminal
from zenith import zml_escape

from .enums import Alignment, Direction, Anchor, QuickSelect
from .widget import Widget, _compute, WidgetFields

PRINTABLE_LIST = [*string.printable]

__all__ = [
    "Button",
    "Container",
    "Root",
    "Row",
    "Slider",
    "Text",
    "TextField",
    "Tower",
]


def bind(func: Callable) -> Callable:
    func._is_bound = True
    return func


def subscribe(event_name: str) -> Callable:
    def _decorate(func: Callable):
        func._event_name = event_name
        return func

    return _decorate


BEHAVIOURS = {}


def behaviour(cls: type) -> type:
    BEHAVIOURS[cls.__name__] = cls

    binds = {}
    subscribers = {}

    data = {}
    for typ in (*reversed(cls.__bases__), cls):
        data.update(typ.__dict__)

    for key, value in data.items():
        if not callable(value):
            continue

        if getattr(value, "_is_bound", False):
            binds[key] = value
            continue

        if (event := getattr(value, "_event_name", None)) is not None:
            if event not in subscribers:
                subscribers[event] = []

            subscribers[event].append(value)
            continue

    @partial(setattr, cls, "__init__")
    def __init__(self, widget: Widget, fields: WidgetFields) -> None:
        self.target = widget
        self.fields = fields

        self.binds = ...
        self.subscribed = subscribers
        for name, handlers in subscribers.items():
            event = getattr(self.target, name, None)

            if event is None:
                raise ValueError("unknown event {name!r} in {type(self).__name__!r}.")

            for handler in handlers:
                event.append(partial(handler, self))

    @partial(setattr, cls, "__iter__")
    def __iter__(self) -> Iterator:
        yield from (self.target, self.fields)

    return cls


@behaviour
class Text:
    target: Widget
    fields: WidgetFields

    def setup(self, text: str) -> None:
        target, fields = self
        fields.define_public(text=text)
        target.inert = True

        for state in target.style_map.keys():
            if state == "*":
                continue
            target.style_map[state]["content"] = "opaque"

    @bind
    def get_contents(self) -> list[str]:
        return [self.fields.text]


text = Widget.create_type("text", behaviours=[Text])


@behaviour
class Button:
    target: Widget
    fields: WidgetFields

    def setup(self, label: str, on_submit: Callable[[Widget], bool] | None = None) -> None:
        self.target.add_default_rules(
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

        self.fields.define_public(
            label=label,
            on_submit=Event("on button submit"),
        )

        if on_submit is not None:
            self.fields.on_submit += on_submit

    @bind
    def get_contents(self):
        hint = self.target.qs_hint + " " if self.target.qs_hint else ""

        return [f"[dim]{hint}[/dim]" + self.fields.label]

    @subscribe("on_key")
    def submit(self, args):
        _, key = args

        if key in [" ", "return"]:
            self.fields.on_submit(self)


button = Widget.create_type("button", behaviours=[Button])


@behaviour
class Container:
    target: Widget
    fields: WidgetFields
    direction = Direction.VERTICAL

    def setup(self, children: list[Widget] | None = None) -> None:
        target, fields = self
        self.target.add_default_rules("""
            width=-1,
            height=-1,
            quick_select=contents,
        """)

        for state in target.style_map.keys():
            if state == "*":
                continue

            target.style_map[state]["content"] = ""

        fields.define_public(gap=1)

        fields.define_readonly(
            children=[],
            active_children=[],
            selected=None,
            direction=self.direction,
        )

        fields.define_private(
            qs_offset=1,
            qs_shown=False,
            qs_binds={},
        )

        for child in children or []:
            self.append(child)

        @self.target.state_machine.on_action.append
        def cascade_selected_state(action: str):
            if "SELECTED" not in action:
                return

            if action == "UNSELECTED" and fields.selected is not None:
                fields.selected.state_machine.apply_action(action)

            if (
                action == "SELECTED"
                and len(fields.active_children) == 1
                and target.quick_select == QuickSelect.CONTENTS
            ):
                fields.selected = fields.active_children[0]

            if fields.selected is not None:
                fields.selected.state_machine.apply_action(action)

    def _gather_qs_self_children(self, widgets: list[Widget]) -> list[Widget]:
        output = []

        for widget in widgets:
            if widget.quick_select is QuickSelect.SELF:
                output.append(widget)
                continue

            active_children = getattr(widget, "active_children", [])

            if (
                widget.quick_select is QuickSelect.CONTENTS
                and active_children is not None
            ):
                output.extend(self._gather_qs_self_children(active_children))
                continue

        return output

    @bind
    def _init_widget(self, el: Widget):
        target, fields = self
        el.parent = target

        # Build once to assign correct shrink sizing
        el.build()

        if el.inert:
            return

        offset = fields.qs_offset

        if el.quick_select is QuickSelect.CONTENTS:
            for i, child in enumerate(
                self._gather_qs_self_children(el.active_children)
            ):
                offset = fields.qs_offset + i
                fields.qs_binds[offset] = child
                child.qs_bind = offset

        elif el.quick_select is QuickSelect.SELF:
            fields.qs_binds[offset] = el
            el.qs_bind = offset

        else:
            raise NotImplementedError(f"wtf is {el.quick_select!r}")

        fields.qs_offset = offset + 1

    @bind
    def append(self, el: Widget) -> None:
        self.fields.children.append(el)
        self._init_widget(el)

    @bind
    def remove(self, el: Widget) -> None:
        self.fields.children.remove(el)

    @bind
    def replace(self, original: Widget, replacement: Widget) -> None:
        idx = self.fields.children.index(original)
        self.target.remove(original)
        self.target.insert(idx, replacement)

    @bind
    def insert(self, idx: int, widget: Widget) -> None:
        self.fields.children.insert(idx, widget)
        self._init_widget(widget)

    @bind
    def replace_children(self, new: list[Widget]) -> None:
        self.fields.children = new

        for child in new:
            self._init_widget(child)

    @subscribe("on_key")
    def handle_selection(self, args) -> bool:
        target, fields = self
        self, key = args

        if fields.selected is not None and fields.selected.handle_keyboard(key):
            return True

        if key == "escape" and fields.selected is not None:
            fields.selected.state_machine.apply_action("UNSELECTED")
            fields.selected = None

            return True

        key_str = str(key)

        if key_str.isdigit() and (bound := fields.qs_binds.get(int(key_str))):
            if fields.selected is not None:
                fields.selected.state_machine.apply_action("UNSELECTED")

            fields.selected = bound
            bound.state_machine.apply_action("SELECTED")
            target.state_machine.apply_action("SELECTED")
            return True

        return False

    def arrange(self):
        target, fields = self

        fields.active_children = [child for child in fields.children if not child.inert]
        target.inert = all(child.inert for child in fields.children)

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

        x, y = target.position
        x -= target.scroll[0]
        y -= target.scroll[1]
        parent_anchor = x, y

        x += 1 if target.frame.left else 0
        y += 1 if target.frame.top else 0

        children = fields.children

        if not children:
            target.parts = []
            return

        available_width = (
            max(target._framed_width, target._virtual_width)
            - target.has_scrollbar(1)
            - target.width_offset
        )
        available_height = (
            max(target._framed_height, target._virtual_height)
            - target.has_scrollbar(0)
            - target.height_offset
        )

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
                    context = target.computed_width, target.computed_height
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
                target.alignment[0], available_width - total_content_width
            )
            current_x += content_align_x + content_align_x_extra
        else:
            total_content_height = sum(
                child.computed_height for child in children
            ) + gap * max(len(children) - 1, 0)
            content_align_y, content_align_y_extra = _align(
                target.alignment[1], available_height - total_content_height
            )
            current_y += content_align_y + content_align_y_extra

        s_start, s_end = [list(val) for val in target.inner_rect]

        for child in children:
            all_children.extend([child, *child.parts])

            if child.anchor is not Anchor.NONE:
                continue

            if is_horizontal:
                align_y, align_y_extra = _align(
                    target.alignment[1],
                    available_height - child.computed_height + target.height_offset,
                )

                child.position = (current_x, current_y + align_y + align_y_extra)
                current_x += child.computed_width + gap
            else:
                align_x, align_x_extra = _align(
                    target.alignment[0],
                    available_width - child.computed_width + target.width_offset,
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

        target.parts = [*all_children]

        bar_x, bar_y = target.scrollbars

        if target.has_scrollbar(0):
            target.parts.append(bar_x)

        if target.has_scrollbar(1):
            target.parts.append(bar_y)

        # Update virtual dimensions based on children
        non_anchored = [child for child in children if child.anchor is Anchor.NONE]

        if is_horizontal:
            total_width = sum(
                child.computed_width for child in non_anchored
            ) + gap * max(len(non_anchored) - 1, 0)
            max_height = max(
                (child.computed_height for child in non_anchored), default=1
            )
            target._virtual_width = total_width
            target._virtual_height = max_height
        else:
            max_width = max((child.computed_width for child in non_anchored), default=1)
            total_height = sum(
                child.computed_height for child in non_anchored
            ) + gap * max(len(non_anchored) - 1, 0)
            target._virtual_width = max_width
            target._virtual_height = total_height

    @bind
    def build(self, fillchar: str = " "):
        target, fields = self

        lines = Widget.build(target, fillchar)
        target.arrange()

        if not len(lines):
            return lines

        qs_content = None

        if not target.inert and target.qs_bind is not None:
            show = False
            parent = target.parent

            while isinstance(parent, Widget):
                if parent.quick_select is QuickSelect.SELF:
                    show = (
                        parent.state_machine() == "selected" and parent.selected is None
                    )
                    break

                if parent.is_root():
                    show = parent.selected is None
                    break

                parent = parent.parent

            fields.qs_shown = show

            if show:
                qs_content = f"{target.qs_bind}"
                sp = Span(qs_content, dim=True)

                first_line = lines[0]

                truncated = []
                goal = len(qs_content)
                current = 0

                for i, span in enumerate(first_line):
                    new = current + len(span)

                    if new > goal:
                        cut = span[len(span) - (new - goal) :]
                        if len(cut):
                            truncated.append(cut)
                        break

                    current = new

                lines[0] = (sp, *truncated, *first_line[i + 1 :])

        return lines

    @bind
    def get_contents(self) -> list[str]:
        target, fields = self
        return [target._virtual_width * " "] * target._virtual_height

    @bind
    def autoscroll(self):
        target, fields = self

        if fields.selected is None:
            return

        sel = fields.selected
        _w, _h = sel.computed_width, sel.computed_height
        clips = sel.viewport_offsets
        csx, csy = clips[0]
        cex, cey = clips[1]

        sx, sy = target.scroll
        if cey > csy:
            target.scroll = (sx + cex, sy + cey)
        elif csy > cey:
            target.scroll = (sx - csx, sy - csy)

    @bind
    def serialize(self) -> dict[str, Any]:
        target, fields = self
        output = {}

        for w in fields.children:
            if not hasattr(w, "serialize"):
                continue

            output = {**output, **w.serialize()}

        return output


@behaviour
class Tower(Container):
    direction = Direction.VERTICAL


tower = Widget.create_type("tower", behaviours=[Tower])


@behaviour
class Row(Container):
    direction = Direction.HORIZONTAL


row = Widget.create_type("row", behaviours=[Row])


@behaviour
class Slider:
    target: Widget
    fields: WidgetFields

    def setup(
        self,
        value: float = 0.5,
        thumb_size: int = 1,
        resolution: float = None,
        chars: tuple[str, str] = ("─", "█"),
        vertical: bool = False,
    ) -> None:
        target, fields = self
        target.add_default_rules(
            """
            ~content=.panel1-2,
            ~frame=.panel1-1,
            overflow=hide,

            /selected/
                ~content=.panel1+1,
                ~frame=.primary,
            """
        )

        fields.define_public(
            resolution=resolution,
            thumb_size=thumb_size,
            vertical=vertical,
            rail=chars[0],
            thumb=chars[1],
            on_change=Event("on slider change"),
        )

        target.value = value

        if fields.vertical:
            target.add_default_rules("""
                width=1,
                height=null,
                frame=(frameless;light;frameless;light)
            """)

        else:
            target.add_default_rules("""
                width=null,
                height=1,
                frame=(light;frameless;light;frameless)
            """)

    @subscribe("on_key")
    def handle_cursor(self, args) -> bool:
        target, fields = self
        self, key = args

        up, down = [["arrow-left", "arrow-up"], ["arrow-down", "arrow-right"]]
        resolution = fields.resolution or 1 / target._framed_width

        if key in up:
            target.value -= resolution

        elif key in down:
            target.value += resolution

        elif key in [str(r) for r in range(10)]:
            target.value = 0

            while round(self.value, 3) <= 1.0:
                self.value += resolution
                num = str(key)
                contents = "".join(
                    ["".join(line) for line in target.get_contents(raw=True)]
                ).strip()

                if num == "0":
                    if not contents.endswith(num):
                        break
                    else:
                        continue

                if num + fields.rail not in contents:
                    break

        else:
            return False

        target.value = max(0, target.value)
        target.value = min(target.value, 1)
        target.value = round(target.value, 3)

        fields.on_change(self)

        return True

    def _get_hint_positions(self):
        target, fields = self
        if fields.vertical:
            size = target._framed_height - fields.thumb_size
        else:
            size = target._framed_width - fields.thumb_size

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

    @bind
    def get_contents(self, raw: bool = False):
        target, fields = self
        thumb_char = fields.thumb.replace("\\", "")

        if fields.vertical:
            size = target._framed_height - fields.thumb_size
        else:
            size = target._framed_width - fields.thumb_size

        start = int(size * target.value)
        styles = target.get_styles()

        if raw:
            for k, v in styles.items():
                styles[k] = lambda x: x

        thumb_chars = [thumb_char] * fields.thumb_size

        if target.qs_hint != "":
            thumb_chars[fields.thumb_size // 2] = (
                f"[invert dim]{target.qs_hint}[/invert /dim]"
            )

        rail = size * fields.rail

        if target.state_machine() == "selected":
            rail = ""
            positions = self._get_hint_positions()
            total = size + fields.thumb_size

            for i in range(total):
                rail += str(positions[i]) if i in positions else fields.rail

        line = [
            *[styles["content"](char) for char in rail[:start]],
            *[styles["frame"](char) for char in thumb_chars],
            *[styles["content"](char) for char in rail[start - size :]],
        ]

        if fields.vertical:
            return line

        return ["".join(line)]


slider = Widget.create_type("slider", behaviours=[Slider])


@behaviour
class TextField:
    target: Widget
    fields: WidgetFields

    def setup(self, value: str = "", placeholder: str = "", multiline: bool = False):
        self.target.add_default_rules(
            """
            width=1.0,
            overflow=auto,

            ~cursor=[],

            /selected/
                ~cursor=@white,
            """
        )

        self.value = value

        self.fields.define_public(
            placeholder=placeholder,
            multiline=multiline,
        )

        self.fields.define_readonly(
            cursor=(0, 0),
            cursor_line=("", "", ""),
        )

        self.fields.define_private(
            cursor_column_hint=0,
            lines=[],
        )

        self._eval_lines()

    @staticmethod
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

    @bind
    def _eval_lines(self) -> None:
        target, fields = self

        fields.lines = target.value.split("\n")

        x, y = fields.cursor
        line = fields.lines[y]

        left, right = line[:x], line[x + 1 :]
        cursor = line[x] if x < len(line) else ""
        fields.cursor_line = left, cursor, right

    @bind
    def move_cursor(
        self, dx: int = 0, dy: int = 0, absolute: bool = False, smart: bool = False
    ) -> bool:
        target, fields = self

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

    @bind
    def set_line(self, y: int, line: str) -> None:
        target, fields = self

        target.value = "\n".join(
            [
                *fields.lines[:y],
                line,
                *fields.lines[y + 1 :],
            ]
        )

        target._eval_lines()

    @bind
    def delete_trailing_newline(self) -> None:
        """Deletes a newline from the end of the current line.

        No-op when y == 0.
        """
        target, fields = self

        x, y = fields.cursor

        if y == 0:
            return

        line = fields.lines[y - 1]
        left, right = line[:x], line[x + 1 :]
        cursor = line[x] if x < len(line) else ""

        fields.lines[y - 1] += fields.lines[y]
        fields.lines.pop(y)

        target.value = "\n".join(fields.lines)

        target.scroll = (target.scroll[0], target.scroll[1] - 1)
        target.move_cursor(dy=-1, dx=len(left + cursor + right))
        target._eval_lines()

    @subscribe("on_key")
    def handle_input(self, args) -> bool:
        target, fields = self
        _, key = args

        if key == "left":
            fields.cursor_column_hint = 0
            return target.move_cursor(dx=-1, smart=True)

        if key == "right":
            fields.cursor_column_hint = 0
            return target.move_cursor(dx=1, smart=True)

        if key == "up":
            return target.move_cursor(dy=-1, smart=True)

        if key == "down":
            return target.move_cursor(dy=1, smart=True)

        if key == "ctrl-up":
            return target.move_cursor(dx=fields.cursor[0], dy=0, absolute=True)

        if key == "ctrl-down":
            return target.move_cursor(
                dx=fields.cursor[0], dy=len(fields.lines) - 1, absolute=True
            )

        x, y = fields.cursor
        left, cursor, right = fields.cursor_line

        if key == "alt-left":
            return target.move_cursor(dx=self._find_word_end(left, direction=-1))

        if key == "alt-right":
            return target.move_cursor(dx=self._find_word_end(right + " "))

        if key == "ctrl-left":
            return target.move_cursor(0, y, absolute=True)

        if key == "ctrl-right":
            return target.move_cursor(len(left + cursor + right), y, absolute=True)

        if key == "backspace":
            if x == 0:
                target.delete_trailing_newline()
                target.rebuild_ancestry()
                return True

            target.set_line(y, left[: -max(1, len(cursor))] + cursor + right)

            fields.cursor_column_hint = 0
            target.move_cursor(dx=-1)
            return True

        if key == "ctrl-backspace":
            if x == 0:
                target.delete_trailing_newline()
                return True

            target.set_line(y, cursor + right)
            change = len(left)

            fields.cursor_column_hint = 0
            target.move_cursor(dx=-change)
            return True

        if key == "alt-backspace":
            if x == 0:
                target.delete_trailing_newline()
                return True

            distance = self._find_word_end(left, direction=-1)

            target.set_line(y, left[:distance] + cursor + right)
            fields.cursor_column_hint = 0
            target.move_cursor(dx=distance)

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

            target.value = "\n".join(lines)
            fields.cursor_column_hint = 0
            target.move_cursor(dx=-fields.cursor[0], dy=1)

            target.rebuild_ancestry()
            return True

        if key in PRINTABLE_LIST:
            target.set_line(y, left + str(key) + cursor + right)
            target.move_cursor(dx=1)
            return True

    @bind
    def get_contents(self) -> list[str]:
        target, fields = self

        value = target.value or fields.placeholder
        styles = target.get_styles()
        frame_style = styles["frame"]
        content_style = styles["content"]
        cursor_style = styles["cursor"]

        if not value:
            return [
                target.qs_hint
                + content_style("")
                + cursor_style(" ")
                + "[/]"
                + content_style(" ")
            ]

        if target.value == "":
            content_style = frame_style

        left, cursor, right = (
            zml_escape(part.replace("\\", "⧵")) for part in fields.cursor_line
        )

        if cursor == "":
            cursor = " "

        lines = [zml_escape(line) for line in fields.lines]
        y = fields.cursor[1]

        styled_cursor_line = (
            target.qs_hint
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


text_field = Widget.create_type("text_field", behaviours=[TextField])


@behaviour
class Root:
    target: Widget
    fields: WidgetFields

    @subscribe("on_init")
    def post_init(self, target) -> None:
        target.add_default_rules(
            """
            anchor=screen,
            position=(0;0),
            alignment=center,
            overflow=auto,
            quick_select=self,

            layer=-1,
            """
        )

        target.width = 1.0
        target.height = 1.0

        @terminal.on_resize.append
        def _resize(size):
            target.scroll = (0, 0)
            target.compute_dimensions(*size)

        _resize((terminal.width, terminal.height))

    @subscribe("on_build_start")
    def always_select(self, target):
        target.state_machine.apply_action("SELECTED")


root = Widget.create_type("root", behaviours=[Tower, Root])
