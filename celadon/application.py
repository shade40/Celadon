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

    elements: tuple[str, ...] = tuple()
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
            return Selector.parse(
                right, direct_parent=Selector.parse(left), forced_score=forced_score
            )

        if " *> " in query:
            left, right = query.split(" *> ")
            return Selector.parse(
                right, indirect_parent=Selector.parse(left), forced_score=forced_score
            )

        if query == "*":
            return cls(
                query,
                (Widget,),
                forced_score=forced_score,
                direct_parent=direct_parent,
                indirect_parent=indirect_parent,
            )

        mtch = RE_QUERY.match(query)

        if mtch is None:
            # TODO: Add pretty errors
            raise ValueError(f"Wtf is {query}???")

        elements_str, eid, groups_str, states = mtch.groups()

        elements = tuple(elements_str.split("|"))
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

        type_matches = any(
            type(widget).__name__ == element for element in self.elements
        )

        if isinstance(widget, Page):
            eid_matches = 0
            group_matches = 0
            state_matches = 0

        else:
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
            + (1 - (self.elements == (Widget,))) * type_matches * 100
        ) * type_matches

        return score


# TODO
Rulebook = Any

BuilderType = Callable[[Any, ...], "Page"]


class Page:
    parent: "Application"
    children: list[Widget]
    _rules: dict[Selector, Rulebook]

    def __init__(
        self,
        *children: Widget,
        name: str = "Index",
        route_name: str = "index",
        builder: BuilderType | None = None,
        rules: str | None = None,
    ) -> None:
        self.name = name
        self.route_name = route_name
        self._children = []
        self._rules = {}
        self._encountered_types: list[type] = []
        self._builder = builder
        self._rules_changed = True

        if rules is not None:
            self.load_rules(rules)

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
                self.load_rules(child.rules, score=None)
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

    def load_rules(self, rules: str, score: int | None = None) -> None:
        for selector, rule in _load_rules(rules).items():
            self.rule(selector, **rule, score=score)

    # True if anything changed
    def apply_rules(self) -> bool:
        drawables = []
        for widget in self._children:
            drawables.extend(widget.drawables())

        applicable_rules = None

        rules_changed = self._rules_changed

        for widget in drawables:
            new_attrs = {}
            new_style_map = StyleMap()

            if not rules_changed and not widget.query_changed():
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

        self._rules_changed = False

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

    def rule(
        self, query: str | Selector, score: int | None = None, **rules: str
    ) -> Selector:
        style_map = {}
        attrs = {}

        self._rules_changed = True

        for key, value in rules.copy().items():
            if not key.endswith("_style"):
                attrs[key] = value
            else:
                style_map[key.removesuffix("_style")] = value

        if isinstance(query, Selector):
            selector = query
        else:
            selector = Selector.parse(query, forced_score=score)

        if selector not in self._rules:
            self._rules[selector] = (attrs, style_map)
            return selector

        # Merge existing rules for the same selector
        old_attrs, old_style_map = self._rules[selector]
        deep_merge(old_attrs, attrs)
        deep_merge(old_style_map, style_map)

        return selector


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
        self._framerate = framerate
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

        try:
            while self._is_running:
                if self._is_paused:
                    sleep(frametime)

                start = perf_counter()
                clear()

                self.apply_rules()

                for widget in [*self._page, *self._children]:
                    widget.compute_dimensions(
                        self._terminal.width, self._terminal.height
                    )

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

        except Exception as exc:
            self.stop()
            self._raised = exc

    def _set_default_rules(self, widget: Widget) -> None:
        for child in _flatten(widget):
            for state in child.state_machine.states:
                self.rule(
                    child.as_query() + f"/{state}",
                    **{
                        f"{key}_style": value
                        for key, value in child.style_map[state].items()
                    },
                    score=1,
                )

            self.rule(
                child.as_query(),
                **child.as_config(),
                score=1,
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

    def rule(
        self, query: str | Selector, score: int | None = None, **rules: str
    ) -> Selector:
        if isinstance(query, Selector):
            selector = query

        else:
            selector = Selector.parse(query, forced_score=score)

        for page in self._pages:
            page.rule(selector, score=score, **rules)

        super().rule(selector, score=score, **rules)
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

        page.parent = self

        self._pages.append(page)
        self.on_page_added()

    # Maybe something like `pin` makes more sense? See above.
    def add_widget(self, widget: Widget) -> None:
        super().append(widget)

    def apply_rules(self) -> bool:
        return self._page.apply_rules() + super().apply_rules()

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

                    self.apply_rules()

                    self._mouse_target = widget

                    # After release, send an extra hover event if the widget contains
                    # the mouse.
                    if "release" in action.value:
                        widget.handle_mouse(MouseAction.HOVER, position)

                    return True

            else:
                if self._mouse_target is not None:
                    self._mouse_target.handle_mouse(
                        MouseAction.LEFT_RELEASE, self._mouse_target.position
                    )

        if self._mouse_target is None:
            return False

        self._mouse_target.handle_keyboard(inp)

    def run(self) -> None:
        self._is_running = True

        self._raised: Exception | None = None

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
                    self._raised = exc
                    break

            thread.join()

        if self._raised is not None:
            raise self._raised

    # TODO: Expand this to clear screen (wait for frame to finish)
    def pause(self) -> None:
        self._is_paused = True

    def resume(self) -> None:
        self._is_paused = False

    # Look into piping into stdin / force quitting blocking read early
    def stop(self) -> None:
        self._is_running = False
