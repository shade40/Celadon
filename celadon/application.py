from __future__ import annotations

import time

from threading import Thread, Event as ThreadEvent, Lock
from typing import Iterable

from slate import terminal, getch_timeout, feed, Key

from . import xml
from .routers import Router
from .widget import Widget, WidgetFields

import os

DEBUG = os.getenv("DEBUG", None)


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

        deadzone = 10
        term_width, term_height = terminal.size
        term_width += deadzone
        term_height += deadzone

        next_onscreen = set()

        for widget in items:
            if widget.clipped_height < 1 or widget.clipped_width < 1 and 0:
                # print(widget)
                continue

            start, end = widget.outer_rect
            was_onscreen = widget in self._last_onscreen

            if (start[1] > term_height or end[1] < -deadzone or start[0] > term_width or end[0] < -deadzone) and not was_onscreen:
                continue
            

            if not was_onscreen:
                next_onscreen.add(widget)

            onscreen.append(widget)

        if dirty_only:
            onscreen = list(filter(lambda e: e.dirty, onscreen))

        # self._last_onscreen = next_onscreen

        return onscreen


class Application:
    title: str

    pages: dict[str, Page]
    page: Page | None
    current: Application | None = None

    def __init__(self, router: Router, title: str = "") -> None:
        self.pages = {}

        self.router = router

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
        if self._target is None:
            return

        self._target.handle_keyboard(inp)

    def find_all(self, selector: str, context: Widget | None = None) -> Iterable[Widget]:
        if context is None or selector.startswith("#"):
            context = self.page.root

        selector = selector.lstrip("#^")

        for child in [context, *context.parts]:
            if child.eid == selector:
                yield child

    def find(self, selector: str, context: Widget | None = None) -> Widget | None:
        for child in self.find_all(selector, context):
            return child

        return None

    def run(self) -> None:
        if Application.current is not None:
            raise ValueError("another application instance is already running.")

        Application.current = self


        self._is_running = True
        self._last_input = 0

        @terminal.on_resize.append
        def _on_resize(_):
            terminal.clear()
            self._start_render(10)

        with terminal.no_echo(), terminal.alt_buffer():
            self._start_render()

            while self._is_running:
                inp = getch_timeout(0.5, default=None)
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

        Application.current = None

        if self._raised is not None:
            raise self._raised

    def _start_render(self, extra_frames: int = 0):
        if self._current_render_thread and self._current_render_thread.is_alive():
            return

        def _run():
            nonlocal extra_frames

            elapsed = 0
            animation_budget = 1

            while (
                self._is_running
                and (animation_budget + extra_frames > 0 or time.time() - self._last_input < 1 / 15)
            ):
                extra_frames = max(extra_frames - 1, 0)

                widgets = self.page.get_widgets()
                animation_budget = max(
                    [
                        anim.total_duration if anim.loop else anim.duration
                        for widget in widgets
                        for anim in widget.animations
                    ],
                    default=0,
                )

                start = time.perf_counter()

                changes = 0
                lines = []

                for widget in sorted(widgets, key=lambda w: w.layer):
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
                            f"FPS ~ {1 / elapsed:.2f} ({len(widgets)} widgets drawn, {changes:0>4} changes)",
                            cursor=(0, terminal.height - 1),
                        )

                    with terminal.batch():
                        terminal.draw()

                sleep = 1 / 60 - elapsed

                if sleep > 0:
                    time.sleep(sleep)

        with self._render_lock:
            time.time()
            self._current_render_thread = Thread(target=_run)
            self._current_render_thread.start()

    def stop(self) -> None:
        feed(chr(3))
        self._is_running = False

    def add(self, page: Page) -> None:
        self.pages[page.location] = page

    def remove(self, page: Page) -> None:
        del self.pages[page.location]

    def load(self, location: str) -> Page:
        resp = self.router.request("GET", location, {})
        
        if resp.code != 200:
            raise ValueError("problem", resp.code, resp.text)

        page = xml.parse(resp.text)
        return page

    def navigate(self, location: str) -> Page:
        page = None
        cache = True

        if cache:
            page = self.pages.get(location) or None

        if page is None:
            page = self.load(location)

        if page is None:
            raise ValueError()

        self.page = page
        self._target = page.root
        page.root.parent = self


if __name__ == "__main__":
    app = Application("test")

    import celadon as c

    @Widget.from_behaviour(base=c.button)
    def icon_button(widget, fields):
        widget.add_rules(
            """
            frame=frameless,
            width=-1,
            ~background=@black*0.2,

            /selected/
                frame=frameless,
                ~background=@black*0.4,
            """
        )

    @Widget.from_behaviour(base=c.tower)
    def window(widget: Widget, fields: WidgetFields):
        """
        state = State(messages=[])

        @widget.bind
        def compose(self, messages: list[str]) -> Generator[Widget, None, None]:
            for message in messages:
                yield text("- " + message)
        """

        widget.add_rules(
            """
            frame=(rounded;rounded;rounded;rounded),
            width=1.0,
            height=1.0,
            quick_select=self,

            ~frame=.panel1,

            /selected/
                ~frame=.primary
            """
        )

        @widget.add_initializer
        def initialize(self) -> None:
            full_screen = False

            def _full_screen_toggle(self):
                nonlocal full_screen

                window = self.find_ancestor("window")
                full_screen = not full_screen

                if full_screen:
                    window.anchor = c.enums.Anchor.SCREEN
                    window._virtual_width = 0
                    window._virtual_height = 0
                    window.computed_width = 0
                else:
                    window.anchor = c.enums.Anchor.PARENT
                    window._virtual_width = 0
                    window._virtual_height = 0
                    window.computed_width = 0
                    window.build()

            self.append(
                c.row([
                    c.text("Window Title 1.0"),
                    c.row([
                        icon_button("o", _full_screen_toggle),
                        icon_button("x", lambda self: self.find_ancestor(type_name="window").remove_self()),
                    ], rules=["gap=0"]),
                ], rules=[
                    """
                    width=1.0,
                    gap=null,
                    alignment=center,
                    frame=(padded;frameless;padded;frameless),

                    ~background=[dim @.panel1],

                    /parent:selected/
                        ~background=[bold @.primary],
                    """
                ])
            )

            children = [
                c.text("- Hey there de-lilla de-lilla de-lilla"),
                c.text("- Hey there de-lilla"),
                c.text("- Hey there de-lilla de-lilla de-lilla"),
                c.text("- Hey there de-lilla"),
                c.text("- Hey there de-lilla de-lilla de-lilla de-lilla de-lilla"),
                c.button("test1"),
                c.button("test2"),
                c.button("test3"),
            ]

            # for child in children:
            #     self.append(child)

            self.append(c.tower(children=children, rules=["gap=0, height=1.0"]))
            
            self.append(c.row([
                c.text_field("", multiline=True, rules=["width=-1, frame=frameless"]),
            ], rules=[
                """
                width=1.0,
                gap=0,
                frame=(padded;frameless;padded;frameless),

                ~background=@.panel1-2,

                /selected/
                    ~background=@.panel1-2,
                """
            ]))

    # app.add(Page("/", root))
    app.add(Page(
        "/",
        c.root([
            c.row([window(), window()], rules=["width=1.0,height=1.0"]),
            window(),
        ], rules=["frame=frameless, gap=0"]))
    )
    # app.add(Page("/", Root([matrix])))
    app.navigate("/")

    """
    - add kitty input
    - add binding support
    - rethink behavior model? widgets + behaviours? i dont like function widgets
    """

    from zenith import Palette
    from slate import color

    orange = color("#e86100")
    p = Palette(
        orange,
        secondary=orange,
        tertiary=orange,
        panel1=orange,
        panel2=orange,
        namespace="main.",
    )

    # p.alias()
    root = app.page.root

    app.run()
    window = root._fields.children[0].children[0]

    b = c.button("test")

    """
    root.append(b)
    b.build()
    b.state_machine.apply_action("selected")
    b.build()
    import json
    print(json.dumps(b.style_map, indent=2))
    print(json.dumps(list(b._rule_calls.keys()), indent=2))
    """
