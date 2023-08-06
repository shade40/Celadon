from __future__ import annotations

import re
import sys
import importlib.util
from dataclasses import dataclass, field
from threading import Thread
from time import perf_counter, sleep
from typing import Any, Callable
from pathlib import Path
from yaml import safe_load

from slate import Terminal, getch, Event, terminal as slt_terminal
from slate.core import BEGIN_SYNCHRONIZED_UPDATE, END_SYNCHRONIZED_UPDATE

from .widgets import Widget, widget_types
from .enums import MouseAction
from .state_machine import deep_merge
from .style_map import StyleMap
from .widgets import Widget

__all__ = [
    "Selector",
    "Application",
    "Page",
]


def _parse_mouse_input(inp: str) -> tuple[MouseAction, tuple[int, int]] | None:
    if not inp.startswith("mouse:"):
        return None

    # TODO: This ignores stacked events and only handles the last one. Shouldn't be an
    # issue, but look out.
    inp = inp.split("mouse:")[-1]

    action, position = inp.split("@")
    parts = position.split(";")

    if len(parts) != 2:
        return None

    return MouseAction(action), (int(parts[0]), int(parts[1]))


def _flatten(widget: Widget) -> list[Widget]:
    items = [widget]

    for child in widget.drawables():
        if child is widget:
            continue

        items.extend(_flatten(child))

    return items


def _load_rules(source: str) -> dict[Selector, Rulebook]:
    """Loads a set of rule declarations from YAML.

    Nested get inserted into the parent's key, so:

    ```yaml
    Button:
        height: 1
        frame: lightvertical

        /idle:
            content_style: primary-1
    ```

    would become:

    ```json
    {
        "Button": {
            "height": 1,
            "frame": "lightvertical",
        },
        "Button/idle": {
            "content_style": "primary-1",
        }
    }
    ```

    You can customize where the insertion takes place by marking it with an `&`. For
    example:

    ```yaml
    .fill:
        height: 1

        Progressbar&:
            height: 3
    ```

    becomes:

    ```json
    {
        ".fill": {
            "height": 1,
        },
        "Progressbar.fill": {
            "height": 3,
        }
    }
    ```

    Returns:
        A flattened dictionary of `{selector: {rules...}}`.
    """

    source_data = safe_load(source)

    if source_data is None:
        return {}

    outer = {}

    def _flatten(data: dict[str, Any], prefix: str = "") -> dict:
        inner = {}

        for key, value in data.items():
            if isinstance(value, dict):
                if "&" not in key:
                    key = f"&{key}"

                key = key.replace("&", prefix)

                for part in key.split(","):
                    outer[part.lstrip()] = _flatten(value, prefix=part)

                continue

            if isinstance(value, list):
                value = tuple(value)

            inner[key] = value

        return inner

    _flatten(source_data)

    return outer


RE_QUERY = re.compile(
    r"^([A-Z][\w\|]+)?(#[a-z0-9@\-]+)?((?:\.[a-z0-9@\-]+)*)?(\/[\w\|]+)?$"
)


@dataclass(frozen=True)
class Selector:
    """
    Element#<id>.<variant1>.<variant2>/<substate>

    Button#logo.inactive/hover

    #logo.inactive/hover
    """

    query: str

    elements: tuple[Type[Widget], ...] = (Widget,)
    eid: str | None = None
    groups: tuple[str, ...] = tuple()
    states: tuple[str, ...] | None = None

    direct_parent: Selector | None = None
    indirect_parent: Selector | None = None
    forced_score: int | None = None

    def __str__(self) -> str:
        if self.direct_parent is not None:
            return f"{self.direct_parent} > {self.query}"

        if self.indirect_parent is not None:
            return f"{self.indirect_parent} > {self.query}"

        return self.query

    @classmethod
    def parse(
        cls,
        query: str,
        direct_parent: Selector | None = None,
        indirect_parent: Selector | None = None,
        forced_score: int | None = None,
    ) -> Selector:
        """Parses a query into a selector."""

        if " > " in query:
            left, right = query.split(" > ")
            return Selector.parse(right, direct_parent=Selector.parse(left))

        if " *> " in query:
            left, right = query.split(" *> ")
            return Selector.parse(right, indirect_parent=Selector.parse(left))

        if query == "*":
            return cls(
                query,
                (Widget,),
                direct_parent=direct_parent,
                indirect_parent=indirect_parent,
            )

        mtch = RE_QUERY.match(query)

        if mtch is None:
            # TODO: Add pretty errors
            raise ValueError(f"Wtf is {query}???")

        elements_str, eid, groups_str, states = mtch.groups()

        if elements_str is None:
            elements = (Widget,)
        else:
            elements = tuple(
                widget_types[element] for element in elements_str.split("|")
            )

        eid = (eid or "").lstrip("#") or None
        groups = tuple(groups_str.split(".")[1:])

        if states is not None:
            states = tuple(states.lstrip("/").split("|"))

        return cls(
            query=query,
            elements=elements,
            eid=eid,
            groups=groups,
            states=states,
            direct_parent=direct_parent,
            indirect_parent=indirect_parent,
            forced_score=forced_score,
        )

    def matches(self, widget: Widget) -> int:
        score = 0

        if self.direct_parent is not None:
            if isinstance(widget.parent, Application):
                return 0

            elif widget.parent is None:
                return 0

            score += self.direct_parent.matches(widget.parent)

            if score == 0:
                return 0

        if self.indirect_parent is not None:
            if isinstance(widget.parent, Application):
                return 0

            item = widget
            count = 0

            while True:
                count += 1
                parent = item.parent

                if isinstance(parent, Application):
                    return 0

                score += self.indirect_parent.matches(parent)

                if score != 0:
                    score -= count * 10
                    break

                item = parent

        if self.query == "*":
            return score + 100

        type_matches = isinstance(widget, self.elements)
        eid_matches = self.eid is None or self.eid == widget.eid
        group_matches = all(group in widget.groups for group in self.groups)
        state_matches = self.states is None or any(
            widget.state.endswith(state) for state in self.states
        )

        if not (type_matches and eid_matches and group_matches and state_matches):
            return 0

        if self.forced_score is not None:
            return self.forced_score

        score = (
            (eid_matches - (self.eid is None)) * 1000
            + (group_matches - (len(self.groups) == 0)) * 500
            + ((state_matches - (self.states is None)) * 250)
            - (self.elements == (Widget,))
            + type_matches
        ) * type_matches

        return score


# TODO
Rulebook = Any

BuilderType = Callable[[Any, ...], "Page"]


class Page:
    children: list[Widget]
    _rules: dict[Selector, Rulebook]

    def __init__(
        self,
        *children: Widget,
        name: str | None = None,
        route_name: str | None = None,
        builder: BuilderType | None = None,
    ) -> None:
        self.name = name
        self.route_name = route_name
        self._children = []
        self._rules = {}
        self._encountered_types: list[type] = []
        self._builder = builder

        self.extend(children)

    def __iadd__(self, widget: Any) -> Page:
        if not isinstance(widget, Widget):
            raise TypeError(f"Can only add Widgets (not {widget!r}) to Page")

        self.append(widget)

        return self

    def __iter__(self) -> Iterable[Widget]:
        return iter(self._children)

    def _init_widget(self, widget: Widget) -> None:
        if type(widget) not in self._encountered_types:
            for child in widget.drawables():
                for selector, rule in _load_rules(child.rules).items():
                    self.rule(selector, **rule)

                self._encountered_types.append(type(child))

        widget.parent = self

    def build(self, *args: Any, **kwargs: Any) -> Page:
        if self._builder is None:
            if len(args) + len(kwargs):
                raise ValueError(
                    f"Page {self!r} takes no arguments, got {args=!r}, {kwargs!r}."
                )

                return self

        return self._builder(*args, **kwargs)

    def append(self, widget: Widget) -> None:
        self._init_widget(widget)
        self._children.append(widget)

    def extend(self, widgets: Iterable[Widget]) -> None:
        for widget in widgets:
            self._init_widget(widget)
            self.append(widget)

    def insert(self, index: int, widget: Widget) -> None:
        self._init_widget(widget)
        self._children.insert(index, widget)

    def remove(self, widget: Widget) -> None:
        self._init_widget(widget)
        self._children.remove(widget)

    def pop(self, index: int) -> Widget:
        self._init_widget(widget)
        widget = self._children.pop(index)

        return widget

    def clear(self) -> None:
        for widget in self._children:
            self.remove(widget)

    def update(self, widgets: Iterable[Widget]) -> None:
        self.clear()
        self.extend(widgets)

    # True if anything changed
    def apply_rules(self) -> bool:
        drawables = []
        for widget in self._children:
            drawables.extend(widget.drawables())

        applicable_rules = None

        for widget in drawables:
            new_attrs = {}
            new_style_map = StyleMap()

            if not widget.query_changed():
                continue

            applicable_rules = [
                (sel, sel.matches(widget), rule) for sel, rule in self._rules.items()
            ]

            for sel, score, (attrs, style_map) in sorted(
                applicable_rules, key=lambda item: item[1]
            ):
                if score == 0:
                    continue

                new_attrs.update(**attrs)
                new_style_map |= style_map

            widget.update(new_attrs, new_style_map)

        return applicable_rules is not None

    def find_all(self, query: str) -> Generator[Widget, None, None]:
        if isinstance(query, Selector):
            selector = query
        else:
            selector = Selector.parse(query)

        for widget in self._children:
            for child in widget.drawables():
                if selector.matches(child):
                    yield child

    def find(self, query: str) -> Widget | None:
        for widget in self.find_all(query):
            return widget

        return None

    def rule(self, query: str | Selector, base: bool = False, **rules: str) -> Selector:
        style_map = {}
        attrs = {}

        for key, value in rules.copy().items():
            if not key.endswith("_style"):
                attrs[key] = value
            else:
                style_map[key.removesuffix("_style")] = value

        if isinstance(query, Selector):
            selector = query
        else:
            selector = Selector.parse(query, forced_score=(1 if base else None))

        if selector not in self._rules:
            self._rules[selector] = (attrs, style_map)
            return selector

        # Merge existing rules for the same selector
        old_attrs, old_style_map = self._rules[selector]
        deep_merge(old_attrs, attrs)
        deep_merge(old_style_map, style_map)

        return selector


# Everything currently handling Application._widgets
# will handle Application.page.children instead.
#
# When drawing, we'll draw page.children first, then our children.
class Application(Page):
    children: list[Widget]  # For constantly visible, overlay-type widgets

    _pages: list[Page]
    _page: Page | None

    def __init__(
        self, name: str, framerate: int = 60, terminal: Terminal | None = None
    ) -> None:
        super().__init__(name=name, route_name="/")

        self.on_frame_drawn = Event("Frame Drawn")
        self.on_page_added = Event("Page Added")

        self._pages = []
        self._page = None
        self._mouse_target: Widget | None = None
        self._framerate = 60
        self._terminal = terminal or slt_terminal

        self._is_running = False
        self._is_paused = False

    def __enter__(self) -> None:
        Widget.app = self

        return self

    def __exit__(
        self,
        exc_type: Type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if exc is not None:
            raise exc

        self.run()

    def __iadd__(self, page: Any) -> Application:
        if not isinstance(page, Page):
            raise TypeError(f"Can only add pages (not {widget!r}) to App")

        self.append(page)

        return self

    def __iter__(self) -> Iterable[Widget]:
        return iter(self._pages)

    def _draw_loop(self) -> None:
        frametime = 1 / self._framerate

        clear = self._terminal.clear
        write = self._terminal.write
        draw = self._terminal.draw
        on_frame_drawn = self.on_frame_drawn

        while self._is_running:
            if self._is_paused:
                sleep(frametime)

            start = perf_counter()
            clear()

            self.apply_rules()
            self._page.apply_rules()

            for widget in [*self._page, *self._children]:
                widget.compute_dimensions(self._terminal.width, self._terminal.height)

                for child in widget.drawables():
                    origin = child.position

                    for i, line in enumerate(child.build()):
                        write(line, cursor=(origin[0], origin[1] + i))

            draw()

            if on_frame_drawn:
                on_frame_drawn()
                on_frame_drawn.clear()

            elapsed = perf_counter() - start

            if elapsed < frametime:
                sleep(frametime)

    def _set_default_rules(self, widget: Widget) -> None:
        for child in _flatten(widget):
            for state in child.state_machine.states:
                self.rule(
                    child.as_query() + f"/{state}",
                    **{
                        f"{key}_style": value
                        for key, value in child.style_map[state].items()
                    },
                    base=True,
                )

            self.rule(
                child.as_query(),
                **child.as_config(),
                base=True,
            )

    @property
    def page(self) -> Page:
        return self._page

    def build_from(self, path: str | Path) -> None:
        if not isinstance(path, Path):
            path = Path(path)

        for item in path.iterdir():
            if item.suffix == ".py":
                with open(item, "r") as file:
                    code = compile(file.read(), item.name, "exec")

                package_name = item.parent.parent.stem + "." + item.parent.stem

                globs = globals().copy()
                globs["__name__"] = f"{package_name}.{item.stem}"
                globs["__package__"] = package_name

                exec(code, globs)

                if not "get" in globs:
                    continue

                page = globs["get"](self)

                page.name = globs.get(
                    "DISPLAY_NAME", item.stem.replace("_", " ").title()
                )
                page.route_name = item.stem

                self.append(page)

    def find_all(self, query: str) -> Generator[Widget, None, None]:
        selector = Selector.parse(query)

        if self.page is not None:
            yield from self.page.find_all(selector)

        for widget in self._children:
            for child in widget.drawables():
                if selector.matches(child):
                    yield child

    def rule(self, query: str | Selector, base: bool = False, **rules: str) -> Selector:
        if isinstance(query, Selector):
            selector = query

        else:
            selector = Selector.parse(query, forced_score=1 if base else None)

        for page in self._pages:
            page.rule(selector, base=base, **rules)

        super().rule(selector, base=base, **rules)
        return selector

    # Make sure to add our rules to the page's, and set our terminal
    def append(self, page: Page) -> None:
        if page.name is None or page.route_name is None:
            raise ValueError(
                "Pages must have both `name` and `route_name`,"
                f" got {page.name=!r}, {page.route_name=!r}"
            )

        for selector, rule in self._rules.items():
            page.rule(selector, rule)

        for widget in page:
            self._set_default_rules(widget)

        self._pages.append(page)
        self.on_page_added()

    # Maybe something like `pin` makes more sense? See above.
    def add_widget(self, widget: Widget) -> None:
        super().append(widget)

    def route(self, destination: str) -> None:
        for page in self._pages:
            if page.route_name == destination:
                break

        else:
            raise ValueError(f"No page with route {destination!r}.")

        self._page = page
        self._terminal.set_title(f"{self.name} - {page.name}")

    def process_input(self, inp: str) -> bool:
        if (event := _parse_mouse_input(inp)) is not None:
            action, position = event

            if (
                self._mouse_target is not None
                and action is MouseAction.HOVER
                and not self._mouse_target.contains(position)
            ):
                self._mouse_target.handle_mouse(MouseAction.LEFT_RELEASE, position)

            for widget in reversed([*self._page, *self._children]):
                if not widget.contains(position):
                    continue

                if widget.handle_mouse(action, position):
                    if self._mouse_target not in [widget, None]:
                        self._mouse_target.handle_mouse(
                            MouseAction.LEFT_RELEASE, position
                        )

                    self._mouse_target = widget
                    return True

        if self._mouse_target is not None:
            self._mouse_target.handle_mouse(
                MouseAction.LEFT_RELEASE, self._mouse_target.position
            )

        if len(self._children) == 0:
            return False

        return self._children[0].handle_keyboard(inp)

    def run(self) -> None:
        self._is_running = True

        raised: Exception | None = None

        for widget in self._children:
            self._set_default_rules(widget)

        if self._page is None:
            self.route("index")

        terminal = self._terminal

        with terminal.report_mouse(), terminal.no_echo(), terminal.alt_buffer():
            thread = Thread(name=f"{self.name} draw", target=self._draw_loop)
            thread.start()

            while self._is_running:
                inp = getch()

                if self._is_paused:
                    continue

                if inp == chr(3):
                    self.stop()
                    break

                try:
                    self.process_input(inp)

                except Exception as exc:
                    self.stop()
                    raised = exc
                    break

            thread.join()

        if raised is not None:
            raise raised

    # TODO: Expand this to clear screen (wait for frame to finish)
    def pause(self) -> None:
        self._is_paused = True

    def resume(self) -> None:
        self._is_paused = False

    # Look into piping into stdin / force quitting blocking read early
    def stop(self) -> None:
        self._is_running = False
