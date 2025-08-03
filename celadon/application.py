from __future__ import annotations

import time

from threading import Thread, Event as ThreadEvent, Lock

from slate import terminal, getch, getch_timeout, feed, Key

from .widget import Widget
from .enums import MouseAction

import os
DEBUG = os.getenv("DEBUG", None)


def _parse_mouse_input(key: Key) -> tuple[MouseAction, tuple[int, int]] | None:
    inp = str(key)

    if not inp.startswith("mouse:"):
        return None

    # TODO: This ignores stacked events and only handles the last one. Shouldn't be an
    # issue, but look out.
    inp = inp.rsplit("mouse:", maxsplit=1)[-1]

    action, position = inp.split("@")
    parts = position.split(";")

    if len(parts) != 2:
        return None

    return MouseAction(action), (int(parts[0]), int(parts[1]))


class Page:
    location: str
    root: Widget

    def __init__(self, location: str, root: Widget | None = None) -> None:
        self.location = location
        self.root = root
        self._last_onscreen = set()

    def get_widgets(self, dirty_only: bool = False) -> list[Widget]:
        items = [self.root, *self.root.parts]
        return items
        onscreen = []

        term_width, term_height = terminal.size
        # next_onscreen = set()

        for widget in items:
            """
            if widget.clipped_height < 1 or widget.clipped_width < 1:
                print(widget)
                continue

            start, end = widget.outer_rect
            was_onscreen = widget in self._last_onscreen

            if (start[1] > term_height or end[1] < 0 or start[0] > term_width or end[0] < 0) and not was_onscreen:
                continue
            

            if not was_onscreen:
                next_onscreen.add(widget)
            """

            onscreen.append(widget)

        if dirty_only:
            onscreen = list(filter(lambda e: e.dirty, onscreen))

        # self._last_onscreen = next_onscreen

        return onscreen


class Application:
    title: str

    pages: dict[str, Page]
    page: Page | None

    def __init__(self, title: str = "", pages: list[Page] | None = None) -> None:
        self.pages = {}

        for page in pages or []:
            self.add(page)

        self._draw_thread = None
        self._is_running = False
        self._raised = None

        self._target = None

        # Threading for render abortion
        self._current_render_thread = None
        self._render_abort_event = ThreadEvent()
        self._render_lock = Lock()
        self._last_lines = []

    def process_input(self, inp: Key) -> None:
        mouse_event = _parse_mouse_input(inp)

        if mouse_event is None:
            if self._target is None:
                return

            self._target.handle_keyboard(inp)

    def run(self) -> None:
        target_frametime = 1 / 60

        self._is_running = True
        self._last_input = 0

        @terminal.on_resize.append
        def _on_resize(_):
            terminal.clear()
            self._start_render(10)

        with terminal.no_echo(), terminal.alt_buffer():
            self._start_render()

            while self._is_running:
                inp = getch_timeout(0.1, default=None)
                if inp is None:
                    # Fetch terminal size to send any update events
                    _ = terminal.size
                    continue
                self._last_input = time.time()

                if inp == "ctrl-c":
                    self.stop()
                    break

                if inp == "ctrl-l":
                    terminal.clear()
                    self._start_render()
                    continue

                try:
                    self.process_input(inp)

                except Exception as exc:
                    self._raised = exc
                    self.stop()
                    break

                self._start_render()

            if self._current_render_thread and self._current_render_thread.is_alive():
                self._render_abort_event.set()
                self._current_render_thread.join()

        if self._raised is not None:
            raise self._raised

    def _start_render(self, extra_frames: int = 0):
        if self._current_render_thread and self._current_render_thread.is_alive():
            return

        def _run():
            nonlocal extra_frames

            elapsed = 0
            animation_budget = 1

            while self._is_running and animation_budget + extra_frames > 0 or time.time() - self._last_input < 1/15:
                extra_frames = max(extra_frames-1, 0)

                widgets = self.page.get_widgets()
                animation_budget = max(
                    [
                        anim.total_duration if anim.loop else anim.duration
                        for widget in widgets
                        for anim in widget.animations
                    ], default=0
                )

                start = time.perf_counter()

                changes = 0
                lines = []

                for widget in widgets:
                    origin = widget.clipped_position

                    widget_lines = []

                    for i, line in enumerate(widget.build()):
                        widget_lines.append(((origin[0], origin[1] + i), line))

                    lines.extend(widget_lines)

                elapsed = time.perf_counter() - start

                with self._render_lock:
                    if lines != self._last_lines:
                        changes = terminal.write_bulk(lines)
                        self._last_lines = lines.copy()

                    if DEBUG:
                        terminal.write(
                            f"FPS ~ {1/elapsed:.2f} ({len(widgets)} widgets drawn, {changes:0>4} changes)",
                            cursor=(0, terminal.height-1)
                        )

                    with terminal.batch():
                        terminal.draw()

                sleep = 1/60 - elapsed

                if sleep > 0:
                    time.sleep(sleep)

        with self._render_lock:
            thread_start = time.time()
            self._current_render_thread = Thread(target=_run)
            self._current_render_thread.start()

    def stop(self) -> None:
        feed(chr(3))
        self._is_running = False

    def add(self, page: Page) -> None:
        self.pages[page.location] = page

    def remove(self, page: Page) -> None:
        del self.pages[page.location]

    # Overwrite-able
    # No-op in default impl because pages must be defined before load,
    # but celx loads them
    def load(self, location: str) -> Page: ...

    def navigate(self, location: str) -> Page:
        page = None
        cache = True

        if cache:
            page = self.pages[location] or None

        if page is None:
            page = self.load(page)

        if page is None:
            raise ValueError()

        self.page = page
        self._target = page.root
        page.root.parent = self


if __name__ == "__main__":

    def jump_behaviour(widget: Widget):
        state = {"active": True}

        offset = 0
        original = None
        frames = 0

        from math import sin, pi

        def _jump(_):
            nonlocal offset, original, frames

            if not state["active"]:
                return

            offset = int(sin(frames / 60 * 2 * pi) * 10)
            widget.offset = 30, 12 + offset

            frames += 1
            widget.dirty = True

        widget.on_build_start += _jump

        def _pause(args):
            _, key = args

            if key != " ":
                return

            state["active"] = not state["active"]

        widget.on_key += _pause

    import sys

    from celadon import (
        Alignment,
        Anchor,
        Animation,
        Button,
        Cursor,
        Matrix,
        Overflow,
        Root,
        Row,
        Slider,
        Text,
        TextField,
        Tower,
        enums,
        frames,
    )

    def header(widget: Widget):
        widget.add_rules(
            "width=1.0, alignment=center",
            #"anchor=screen",
            #"offset=(0.5;0)",
        )

        anim = Animation(duration=30, loop=False)
        background_rule = None
        
        @anim.on_frame.append
        def step_anim(args):
            nonlocal background_rule

            anim, self = args

            if background_rule is not None:
                self.remove_rules(background_rule)

            background_rule = f"~background=@.primary-3*{anim.frame % 60 / 60}"
            self.add_rules(background_rule)

        # widget.animations.append(anim)

        @widget.add_initializer
        def initialize(self, initial_label: str) -> None:
            self.label = Text(initial_label)
            self.append(self.label)

    Header = Widget.create_type("Header", source=Tower, behaviours=[header])

    def message_box(widget: Widget):
        widget.add_rules("min_width=-1, width=1.0")

        @widget.add_initializer
        def initialize(self, message: str) -> None:
            t = Text(message, rules=[
                """
                frame=light,
                width_offset=2,
                alignment=center,

                /selected/
                    frame=double,
                """
            ])
            t.inert = False
            self.append(t)

        @widget.on_build_start.append
        def determine_side(self) -> None:
            if not isinstance(self.parent, Widget):
                return

            idx = self.parent.children.index(self)
            self.alignment = (
                (Alignment.START, Alignment.START)
                if idx % 2 else
                (Alignment.END, Alignment.START)
            )

    MessageBox = Widget.create_type("MessageBox", source=Tower, behaviours=[message_box])
        
    messages = []
    for i in range(50):
        messages.append(MessageBox(message="My third message My third message My third message"))

    root = Root(
        [
            Tower(messages, rules=["width=1.0, height=1.0"]),
            TextField(
                "Test",
                binds={
                    "return": lambda *_: sys.exit(1)
                },
                rules=[
                    """
                    height=-1,
                    frame=(frameless;verticalouter;frameless;verticalouter),

                    ~background=@.panel1-2,
                    ~frame=gray,

                    /selected/
                        ~background=@.panel1-2,
                    """
                ]
            ),
            Header(initial_label="[bold]OpenerCode", rules=[
                """
                anchor=screen,
                max_width=50,
                offset=(0.5;0),

                ~background=@.primary-2*0.3,
                """
            ]),
        ],
        rules=[
            "alignment=(start;end), gap=0",
        ]
    )


    anim = Animation(duration=60, loop=True)
    last_pos = None

    @anim.on_frame.append
    def step(args):
        global last_pos

        def _get_square(origin):
            for y in range(3):
                for x in range(3):
                    yield (origin[0] + x, origin[1] + y)

        anim, self = args

        if last_pos is not None:
            for (x, y) in last_pos:

                for (x, y) in _get_square((x, y)):
                    matrix._data[y][x] = None

        x = int(anim.frame % anim.total_duration / anim.total_duration * (terminal.width - 3))
        y = 0

        last_pos = []

        for i in range(5):
            offset = int((terminal.height * 2 - 5) / 4 * i)

            last_pos.append((x, y+offset))

            for (ix, iy) in _get_square((x, y + offset)):
                matrix._data[iy][ix] = "red"


    matrix = Matrix(terminal.width, terminal.height * 2)
    matrix.animations.append(anim)

    app = Application()

    app.add(Page("/", root))
    # app.add(Page("/", Root([matrix])))
    app.navigate("/")

    """
    - add kitty input
    - add binding support
    - rethink behavior model? widgets + behaviours? i dont like function widgets
    """

    app.run()
    print(root.children[1].overflow)
