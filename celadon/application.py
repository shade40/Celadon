# pylint: disable=too-many-lines

from __future__ import annotations

import re
from dataclasses import dataclass
from threading import Thread
from time import perf_counter, sleep
from typing import Any, Callable, Iterator, Iterable, Type, overload
from types import TracebackType
from pathlib import Path
from yaml import safe_load

from slate import Terminal, getch, Event, terminal as slt_terminal, feed, Key

from .widgets import Widget, handle_mouse_on_children
from .enums import MouseAction
from .state_machine import deep_merge
from .style_map import StyleMap

__all__ = [
    "Selector",
    "Application",
    "Page",
]

DEFAULT_RULES = """
.fill:
    width: null
    height: null

.fill-width:
    width: null

.fill-height:
    height: null

.center:
    alignment: [center, center]

.overflow-scroll:
    overflow: [scroll, scroll]

.overflow-auto:
    overflow: [auto, auto]

.overflow-hide:
    overflow: [hide, hide]
"""


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


def _flatten(widget: Widget) -> list[Widget]:
    items = [widget]

    for child in widget.drawables():
        if child is widget:
            continue

        items.extend(_flatten(child))

    return items


def _load_rules(source: str) -> dict[str, dict[str, Any]]:
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

    def _flatten(data: dict[str, Any], prefix: str = "") -> dict[str, Any]:
        inner = {}

        for key, value in data.items():
            if isinstance(value, dict):
                if key.startswith((">", "*>")):
                    key = " " + key

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
class Selector:  # pylint: disable=too-many-instance-attributes
    """The object used to query widgets.

    Basic syntax is:

        WidgetType#id.group1.group2/state1|state2

    ...where `WidgetType` is necessary if an id is given, everything else is optional.

    You can also test for hierarchy, e.g.:

        # Direct hierarchy (ParentType > WidgetType.class1)
        ParentType > WidgetType.class1

        # Indirect hierarchy (ParentType > OtherParent > WidgetType.class1)
        ParentType *> WidgetType.class1

    Finally, you can use `*` to indicate 'any' in hierarchal matches:

        # WidgetType#id that is the child of any widget (all of them, so don't do this)
        * > WidgetType#id

        # Any widget whos direct parent is WidgetType#id
        WidgetType#id > *
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
        """Parses a query into a selector.

        Args:
            query: The query to parse.
            direct_parent: Direct parent to test for, obtained by parsing
                `direct_parent > query`.
            indirect_parent: Direct parent to test for, obtained by parsing
                `indirect_parent *> query`.
            forced_score:A score to use when a selector matches the rule, instead of the
                score the selector calculates.

        Returns:
            The obtained selector.
        """
        # TODO: Add support for multi-hierarchy
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
                ("Widget",),
                forced_score=forced_score,
                direct_parent=direct_parent,
                indirect_parent=indirect_parent,
            )

        mtch = RE_QUERY.match(query)

        if mtch is None:
            raise ValueError(
                f"incorrect syntax {query!r}, use 'WidgetType#id.class/type'"
            )

        elements_str, eid, groups_str, states = mtch.groups()
        elements_str = elements_str or ""

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

    def matches(  # pylint: disable=too-many-return-statements, too-many-branches
        self, widget: Widget | "Page"
    ) -> int:
        """Determines how well this selector matches the widget.

        Returns:
            A score calculated as:

                (
                    (eid_matches * 1000)
                    + (group_matches * 500)
                    + (state_matches * 250)
                    + (type_matches * 100)
                )

            When optional parts are ommitted (like groups), they are excluded from the
            calculation.
        """

        score = 0

        if self.direct_parent is not None:
            if isinstance(widget.parent, Application):
                return 0

            if widget.parent is None:
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

                if parent is None:
                    return 0

                score += self.indirect_parent.matches(parent)

                if score != 0:
                    score -= count * 10
                    break

                item = parent

        if self.query == "*":
            return score + 100

        type_matches = self.elements == ("",) or any(
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


BuilderType = Callable[..., "Page"]


class Page:  # pylint: disable=too-many-instance-attributes
    """A Page of an application.

    It contains some children, and a set of rules it applies to them.
    """

    parent: "Application"
    children: list[Widget]
    _rules: dict[Selector, tuple[dict[str, Any], dict[str, Any]]]

    def __init__(
        self,
        *children: Widget,
        name: str = "Index",
        route_name: str = "index",
        builder: BuilderType | None = None,
        rules: str = "",
    ) -> None:
        self.name = name
        self.route_name = route_name
        self._children: list[Widget] = []
        self._rules = {}
        self._encountered_types: list[type] = []
        self._builder = builder
        self._rules_changed = True

        self._init_rules = rules

        self.extend(children)

    def __iadd__(self, widget: Any) -> Page:
        """Shorthand for `.append(widget)`."""

        if not isinstance(widget, Widget):
            raise TypeError(f"Can only add Widgets (not {widget!r}) to Page")

        self.append(widget)

        return self

    def __iter__(self) -> Iterator[Widget]:
        """Shorthand for `iter(._children)`."""

        return iter(self._children)

    def __len__(self) -> int:
        """Shorthand for `len(._children)`."""

        return len(self._children)

    @overload
    def __getitem__(self, item: int) -> Widget:
        ...

    @overload
    def __getitem__(self, item: slice) -> list[Widget]:
        ...

    def __getitem__(self, item):
        """Shorthand for `._children[item]`."""

        return self._children[item]

    def _init_widget(self, widget: Widget) -> None:
        """Initializes a widget.

        This loads the widget's rules if it hasn't encountered the same type before,
        and sets its parent to self.
        """

        if type(widget) not in self._encountered_types:
            for child in widget.drawables():
                self.load_rules(child.rules, score=None)
                self._encountered_types.append(type(child))

        widget.parent = self

    def build(self, *args: Any, **kwargs: Any) -> Page:
        """Applies the builder function.

        Might be removed in the future.
        """

        if self._builder is None:
            if len(args) + len(kwargs):
                raise ValueError(
                    f"Page {self!r} takes no arguments, got {args=!r}, {kwargs!r}."
                )

            return self

        return self._builder(*args, **kwargs)

    def append(self, widget: Widget) -> None:
        """Initializes & adds a widget to the Page.

        Analogous to `list.append`.
        """

        self._init_widget(widget)
        self._children.append(widget)

    def extend(self, widgets: Iterable[Widget]) -> None:
        """Extends the page by the given widgets.

        Analogous to `list.extend`.
        """

        for widget in widgets:
            self._init_widget(widget)
            self.append(widget)

    def insert(self, index: int, widget: Widget) -> None:
        """Inserts a widget into the page.

        Analogous to `list.insert`.
        """

        self._init_widget(widget)
        self._children.insert(index, widget)

    def remove(self, widget: Widget) -> None:
        """Removes a widget from the page.

        Analogous to `list.remove`.
        """

        self._init_widget(widget)
        self._children.remove(widget)

    def pop(self, index: int) -> Widget:
        """Pops a widget from the page.

        Analogous to `list.pop`.
        """

        widget = self._children.pop(index)

        return widget

    def clear(self) -> None:
        """Removes all widgets.

        Analogous to `list.clear`.
        """

        for widget in self._children:
            self.remove(widget)

    def update(self, widgets: Iterable[Widget]) -> None:
        """Clears all widgets then adds everything given.

        Analogous to `list.update`.
        """

        self.clear()
        self.extend(widgets)

    def load_rules(
        self,
        rules: str | None = None,
        score: int | None = None,
        load_init_rules: bool = False,
    ) -> None:
        """Loads the given YAML rules.

        Args:
            rules: The YAML to load.
            score: A score to use when a selector matches the rule, instead of the score
                the selector calculates.
            load_init_rules: If set, will ignore rules and use the rules passed in
                during `__init__`.

        Either `rules` or `load_init_rules` must be set.
        """

        if rules is None and not load_init_rules:
            raise TypeError("must provide rules to load.")

        if load_init_rules:
            rules = self._init_rules

        assert rules is not None

        for selector, rule in _load_rules(rules).items():
            self.rule(selector, **rule, score=score)

    def apply_rules(self) -> bool:
        """Applies the page's rules to the widgets.

        Returns:
            Whether any rules were applied, e.g. whether there was any change.
        """

        drawables: list[Widget] = []

        for widget in self._children:
            drawables.extend(widget.drawables())

        applicable_rules = None

        rules_changed = self._rules_changed

        for widget in drawables:
            new_attrs: dict[str, Any] = {}
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

    def find_all(self, query: str | Selector) -> Iterator[Widget]:
        """Finds all widgets in the page matching the given query."""

        selector: Selector

        if isinstance(query, Selector):
            selector = query
        else:
            selector = Selector.parse(query)

        for widget in self._children:
            for child in widget.drawables():
                if selector.matches(child):
                    yield child

    def find(self, query: str | Selector) -> Widget | None:
        """Finds the first widget in the page matching the given query."""

        for widget in self.find_all(query):
            return widget

        return None

    def rule(
        self, query: str | Selector, score: int | None = None, **rules: str
    ) -> Selector:
        """Creates a new rule that matches query, and applies rules on matches.

        Args:
            query: The query that will be matched against.
            score: A score to use when a selector matches the rule, instead of the score
                the selector calculates.
            rules: The rules to apply to every matching widget.

        Returns:
            The selector used for matching.
        """

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


class Application(Page):  # pylint: disable=too-many-instance-attributes
    """A page to rule them all.

    The primary interface to run Celadon applications. It maintains a list of pages,
    between which it can navigate using routing. Only one page can be displayed at a
    time, but it is possible to create constant overlays by adding widgets directly to
    the Application instance, instead of a page.
    """

    children: list[Widget]  # For constantly visible, overlay-type widgets

    _pages: list[Page]
    _page: Page | None

    def __init__(
        self, name: str, framerate: int = 60, terminal: Terminal | None = None
    ) -> None:
        """Initializes the Application.

        Args:
            name: The name of the app. Used for the terminal's title bar.
            framerate: The target framerate. Note that this isn't very closely
                maintained.
            terminal: A terminal instance to use.
        """

        super().__init__(name=name, route_name="/")

        self.on_frame_drawn = Event("frame drawn")
        self.on_page_added = Event("page added")

        self._pages = []
        self._page = None
        self._mouse_target: Widget | None = None
        self._hover_target: Widget | None = None
        self._framerate = framerate
        self._terminal = terminal or slt_terminal

        self._is_running = False
        self._is_paused = False
        self._raised: Exception | None = None
        self._timeouts: list[tuple[Callable[[], Any], int | float]] = []

        _ = self.terminal.foreground_color
        _ = self.terminal.background_color

    def __enter__(self) -> Application:
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
        """Shorthand for `.append(page)`."""

        if not isinstance(page, Page):
            raise TypeError(f"Can only add pages (not {page!r}) to App")

        self.append(page)

        return self

    def __iter__(self) -> Iterator[Page]:  # type: ignore
        """Shorthand for `iter(._pages)`."""

        return iter(self._pages)

    def _draw_loop(self) -> None:  # pylint: disable=too-many-locals
        """The display & timing loop of the Application, run as a thread."""

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

                for widget in [*self._page, *self._children]:  # type: ignore
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

                eliminated = []

                for i, (callback, timeout) in enumerate(self._timeouts):
                    timeout -= elapsed * 1000

                    if timeout <= 0:
                        callback()

                        eliminated.append(i)
                        continue

                    self._timeouts[i] = (callback, timeout)

                for i in eliminated:
                    self._timeouts.pop(i)

        except Exception as exc:  # pylint: disable=broad-exception-caught
            self.stop()
            self._raised = exc

    @property
    def page(self) -> Page | None:
        """Returns the current page."""

        return self._page

    @property
    def terminal(self) -> Terminal:
        """Returns the in-use terminal instance."""

        return self._terminal

    def timeout(self, delay_ms: int, callback: Callable[[], Any]) -> None:
        """Sets up a non-blocking timeout.

        Args:
            delay_ms: The delay (in milliseconds) before the callback is executed.
            callback: The callback to execute when the delay is up.
        """

        self._timeouts.append((callback, delay_ms))

    def build_from(self, path: str | Path) -> None:
        """Builds an application from a given path.

        Likely removed in the future.
        """

        if not isinstance(path, Path):
            path = Path(path)

        for item in path.iterdir():
            if item.suffix == ".py":
                with open(item, "r", encoding="utf-8") as file:
                    code = compile(file.read(), item.name, "exec")

                package_name = item.parent.parent.stem + "." + item.parent.stem

                globs = globals().copy()
                globs["__name__"] = f"{package_name}.{item.stem}"
                globs["__package__"] = package_name

                exec(code, globs)  # pylint: disable=exec-used

                if not "get" in globs:
                    continue

                page = globs["get"](self)

                page.name = globs.get(
                    "DISPLAY_NAME", item.stem.replace("_", " ").title()
                )
                page.route_name = item.stem

                self.append(page)

    def find_all(self, query: str | Selector) -> Iterator[Widget]:
        selector = query

        if isinstance(query, str):
            selector = Selector.parse(query)

        assert isinstance(selector, Selector)

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

    def append(self, page: Page) -> None:  # type: ignore # pylint: disable=arguments-renamed
        """Adds a page."""

        if page.name is None or page.route_name is None:
            raise ValueError(
                "Pages must have both `name` and `route_name`,"
                f" got {page.name=!r}, {page.route_name=!r}"
            )

        rules: dict[str, Any] = {}

        # God compelled me to right this,,,
        # May he compel me to clean  it up.
        #
        for key, value in self._rules.items():
            rules.update(
                **{
                    key.query: {
                        **value[0],
                        **{sel + "_style": val for sel, val in value[1].items()},
                    }
                }
            )

        for selector, rule in rules.items():
            page.rule(selector, **rule)

        page.parent = self

        self._pages.append(page)
        page.load_rules(load_init_rules=True)
        self.on_page_added()

        if self._mouse_target is None and len(page) > 0:
            self._mouse_target = page[0]

    def pin(self, widget: Widget) -> None:
        """Pins a widget to the application.

        Pinning means the app will always be displayed & on top, regardless of the
        current page.

        Analogous to `Page.append(self, widget)`.
        """

        super().append(widget)

    def apply_rules(self) -> bool:
        page_applied = False

        if self._page is not None:
            page_applied |= self._page.apply_rules()

        return page_applied | super().apply_rules()

    def route(self, destination: str) -> None:
        """Routes to a new page."""

        for page in self._pages:
            if page.route_name == destination:
                break

        else:
            raise ValueError(f"No page with route {destination!r}.")

        self._page = page
        self._terminal.set_title(f"{self.name} - {page.name}")

    def process_input(self, inp: Key) -> bool:
        """Processes input.

        Returns:
            Whether the input could be handled.
        """

        event = _parse_mouse_input(inp)

        if event is None:
            if self._mouse_target is not None:
                return self._mouse_target.handle_keyboard(inp)

            return False

        result, _, mouse_target, hover_target = handle_mouse_on_children(
            *event,
            self._mouse_target,
            self._hover_target,
            reversed([*self._page, *self._children]),
        )

        # We need to keep `_mouse_target` to handle keyboard inputs
        self._hover_target = hover_target

        if result:
            return True

        return False

    def run(self) -> None:
        """Runs the application.

        This function will block until the application halts.
        """

        self._is_running = True

        if self._page is None:
            self.route("index")

        self.load_rules(DEFAULT_RULES)
        terminal = self._terminal

        with terminal.report_mouse(), terminal.no_echo(), terminal.alt_buffer():
            thread = Thread(name=f"{self.name} draw", target=self._draw_loop)
            thread.start()

            while self._is_running:
                inp = getch()

                if self._is_paused:
                    continue

                if inp == "ctrl-c":
                    self.stop()
                    break

                try:
                    self.process_input(inp)

                except Exception as exc:  # pylint: disable=broad-exception-caught
                    self.stop()
                    self._raised = exc
                    break

            thread.join()

        self._terminal.set_title(None)

        if self._raised is not None:
            raise self._raised

    # TODO: Expand this to clear screen (wait for frame to finish)
    def pause(self) -> None:
        """Pauses the app."""

        self._is_paused = True

    def resume(self) -> None:
        """Resumes the app."""

        self._is_paused = False

    def stop(self) -> None:
        """Stops the application."""

        feed(chr(3))
        self._is_running = False
