# pylint: disable=too-many-lines

from __future__ import annotations

import re
from dataclasses import dataclass
from threading import Thread
from time import perf_counter, sleep
from types import TracebackType
from typing import Any, Callable, Iterable, Iterator, Type, overload

from slate import Color, Event, Key, Terminal, color, feed, getch
from slate import terminal as slt_terminal
from yaml import safe_load
from zenith import Palette

from .enums import MouseAction
from .state_machine import deep_merge
from .style_map import StyleMap
from .widgets import Container, Widget, handle_mouse_on_children, Slider

__all__ = [
    "load_rules",
    "Selector",
    "Application",
    "Page",
]

DEFAULT_RULES = """
.fill:
    width: null
    height: null

.w-fill:
    width: null

.h-fill:
    height: null

.start:
    alignment: [start, start]

.center:
    alignment: [center, center]

.end:
    alignment: [end, end]

.of-scroll:
    overflow: [scroll, scroll]

.of-auto:
    overflow: [auto, auto]

.of-hide:
    overflow: [hide, hide]
"""


class _TerminalWrapper:
    def __init__(self) -> None:
        self.eid = 0
        self.parent = None

    @property
    def groups(self) -> tuple[str, ...]:
        """Returns the current color space."""

        return (slt_terminal.color_space.value.replace("_", "-"),)

    def query_changed(self) -> bool:
        """Our query (currently) never changes at runtime."""

        return False

    def update(self, _: dict[str, Any], __: dict[str, str]) -> None:
        """No-op"""


_terminal_wrapper = _TerminalWrapper()


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


def load_rules(source: str) -> dict[str, dict[str, Any]]:
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
                key = key.replace(r"\>", ">").replace(r"\*>", "*>")

                if key.startswith((">", "*>")):
                    key = " " + key

                if "&" not in key:
                    key = f"&{key}"

                key = key.replace("&", prefix)

                for part in key.split(","):
                    key = part.lstrip()
                    if key not in outer:
                        outer[key] = {}

                    outer[part.lstrip()].update(_flatten(value, prefix=part))

                continue

            if isinstance(value, list):
                value = tuple(value)

            inner[key] = value

        return inner

    _flatten(source_data)

    return outer


RE_QUERY = re.compile(
    r"^([A-Z][\w\|]+)?(#[a-z0-9@\-]+)?((?:\.[a-z0-9@\-]+)*)?(\/[\w\|\-]+)?$"
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
            return f"{self.indirect_parent} *> {self.query}"

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
            forced_score: A score to use when a selector matches the rule, instead of the
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

        if elements_str == "Terminal":
            elements_str = "_TerminalWrapper"

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

    def _match_parent(
        self, widget: Widget | "Page" | _TerminalWrapper, direct: bool = True
    ) -> int:
        """Walks up the widget's parent tree and tries to match each.

        Args:
            widget: The widget whos parents we are looking at.
            direct: If set, we will only walk up for one node, and use `direct_parent`
                instead of `indirect_parent`.
        """

        # Match Terminal.<color-space> *> queries
        if (
            self.indirect_parent is not None
            and not direct
            and "_TerminalWrapper" in self.indirect_parent.elements
        ):
            return self.indirect_parent.matches(_terminal_wrapper)

        if widget.parent is None:
            return 0

        parent = widget.parent

        while hasattr(parent, "parent") and parent.parent is not None:
            if direct:
                # Both are checked to be non-null at call site.
                return self.direct_parent.matches(parent)  # type: ignore

            if score := self.indirect_parent.matches(parent):  # type: ignore
                return score

            parent = parent.parent

        return 0

    # TODO: We should have a Protocol to describe common actions between these classes.
    def matches(  # pylint: disable=too-many-return-statements, too-many-branches
        self, widget: Widget | "Page" | _TerminalWrapper
    ) -> int:
        """Determines how well this selector matches the widget.

        Returns:
            A score calculated as:

                (
                    (eid_matches * 1000)
                    + (group_matches * 500 + len(groups) * 100)
                    + (state_matches * 250)
                    + (type_matches * 100)
                )

            When optional parts are ommitted (like groups), they are excluded from the
            calculation. However, when these are provided the widget _must_ have
            matching attributes, otherwise the function will return 0.
        """

        is_palette = self.elements == ("Palette",)

        if self.query == "*":
            return 10

        if (
            not is_palette
            and type(widget).__name__ not in self.elements
            and self.elements != ("",)
        ):
            return 0

        score = 100

        if self.direct_parent is not None and self._match_parent(widget) == 0:
            return 0

        if (
            self.indirect_parent is not None
            and self._match_parent(widget, direct=False) == 0
        ):
            return 0

        if is_palette:
            return score + 100

        if self.eid is not None:
            if isinstance(widget, Widget) and widget.eid == self.eid:
                score += 1000

            else:
                return 0

        if self.groups:
            if isinstance(widget, (Widget, _TerminalWrapper)) and all(
                group in widget.groups for group in self.groups
            ):
                score += 500 + 100 * len(self.groups)

            else:
                return 0

        if self.states is not None:
            if isinstance(widget, Widget) and any(
                widget.state.endswith(state) for state in self.states
            ):
                score += 250

            else:
                return 0

        return self.forced_score or score


BuilderType = Callable[..., "Page"]


class Page:  # pylint: disable=too-many-instance-attributes
    """A Page of an application.

    It contains some children, and a set of rules it applies to them.
    """

    parent: "Application"
    children: list[Widget]
    _rules: dict[Selector, tuple[dict[str, Any], dict[str, Any]]]

    _builtin_rules: dict[Selector, tuple[dict[str, Any], dict[str, Any]]]
    _user_rules: dict[Selector, tuple[dict[str, Any], dict[str, Any]]]

    def __init__(
        self,
        *children: Widget,
        title: str = "",
        route_name: str = "/",
        builder: BuilderType | None = None,
        rules: str = "",
    ) -> None:
        if not route_name.startswith("/"):
            raise ValueError(f"route names must start with a slash, got {route_name!r}")

        self.title = title
        self.route_name = route_name
        self._palettes: dict[str, Palette] = {}
        self._children: list[Widget] = []
        self._builtin_rules = {}
        self._user_rules = {}
        self._encountered_types: list[type] = []
        self._builder = builder
        self._rules_changed = True

        self.load_rules(DEFAULT_RULES, _builtin=True)
        self.load_rules(rules)

        # Always load slider rules for scrollbars
        self._init_widget(Slider())

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

    @property
    def _rules(self) -> dict[str, Any]:
        """Returns {**builtin_rules, **user_rules}."""

        rules = {**self._builtin_rules}
        keys = [*rules]

        for sel, value in self._user_rules.items():
            if sel in keys:
                attrs, style_map = rules[sel]

                deep_merge(attrs, value[0])
                deep_merge(style_map, value[1])
                continue

            rules[sel] = value

        return rules

    def _init_widget(self, widget: Widget) -> None:
        """Initializes a widget.

        This loads the widget's rules if it hasn't encountered the same type before,
        and sets its parent to self.
        """

        for child in widget.drawables():
            if type(child) in self._encountered_types:
                continue

            self.load_rules(child.rules, _builtin=True)
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
        rules: str,
        score: int | None = None,
        _builtin: bool = False,
    ) -> None:
        """Loads the given YAML rules.

        Args:
            rules: The YAML to load.
            score: A score to use when a selector matches the rule, instead of the score
                the selector calculates.
        """

        for selector, rule in load_rules(rules).items():
            self.rule(selector, **rule, score=score, _builtin=_builtin)

    def apply_rules(self) -> bool:
        """Applies the page's rules to the widgets.

        Returns:
            Whether any rules were applied, e.g. whether there was any change.
        """

        drawables: list[Widget] = []

        for widget in self._children:
            drawables.extend(widget.drawables())

        applicable_rules = None

        for target in [_terminal_wrapper] + drawables:
            new_attrs: dict[str, Any] = {}
            new_style_map = StyleMap()

            if not self._rules_changed and not target.query_changed():
                continue

            applicable_rules = [
                (sel, score, rule)
                for sel, rule in self._rules.items()
                if (score := sel.matches(target)) != 0
            ]

            for sel, score, (attrs, style_map) in sorted(
                applicable_rules, key=lambda item: item[1]
            ):
                # TODO: This redefines palettes every time we encounter them, which is
                #       quite wasteful!
                if sel.elements == ("Palette",):
                    namespace = sel.query.split(">")[-1].removeprefix("Palette/")

                    if namespace == "Palette":
                        continue

                    for key, value in attrs.items():
                        if isinstance(value, Color):
                            continue

                        attrs[key] = color(value)

                    if namespace in self._palettes:
                        palette = self._palettes[namespace]

                        palette.update(**attrs)
                        palette.alias(ignore_already_aliased=True)

                    else:
                        palette = Palette(**attrs, namespace=namespace + ".")

                        self._palettes[namespace] = palette
                        palette.alias()

                    continue

                new_attrs.update(**attrs)
                new_style_map |= style_map

            target.update(new_attrs, new_style_map)

        self._rules_changed = False

        return applicable_rules is not None

    def find_all(
        self, query: str | Selector, scope: Container | None = None
    ) -> Iterator[Widget]:
        """Finds all widgets in the page matching the given query."""

        selector: Selector

        if isinstance(query, Selector):
            selector = query
        else:
            selector = Selector.parse(query)

        children = self._children if scope is None else scope.children

        for widget in children:
            for child in widget.drawables():
                if selector.matches(child):
                    yield child

    def find(
        self, query: str | Selector, scope: Container | None = None
    ) -> Widget | None:
        """Finds the first widget in the page matching the given query."""

        for widget in self.find_all(query, scope):
            return widget

        return None

    def rule(
        self,
        query: str | Selector,
        score: int | None = None,
        _builtin: bool = False,
        **rules: str,
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

        rules_container = self._builtin_rules if _builtin else self._user_rules

        self._rules_changed = True

        for key, value in rules.copy().items():
            if not key.endswith("_style"):
                attrs[key] = value
            else:
                style_map[key[: -len("_style")]] = value

        if isinstance(query, Selector):
            selector = query
        else:
            selector = Selector.parse(query, forced_score=score)

        if selector not in rules_container:
            rules_container[selector] = (attrs, style_map)
            return selector

        # Merge existing rules_container for the same selector
        old_attrs, old_style_map = rules_container[selector]
        deep_merge(old_attrs, attrs)
        deep_merge(old_style_map, style_map)

        return selector

    def dump_rules_applied_to(self, widget: Widget) -> dict[Selector, int]:
        out = {}

        for sel, rule in self._rules.items():
            score = sel.matches(widget)

            if score == 0:
                continue

            out[sel] = (sel.matches(widget), rule)

        return out


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
        self,
        title: str,
        framerate: int = 60,
        terminal: Terminal | None = None,
        fps_sample: int = 60,
    ) -> None:
        """Initializes the Application.

        Args:
            name: The name of the app. Used for the terminal's title bar.
            framerate: The target framerate. Note that this isn't very closely
                maintained.
            terminal: A terminal instance to use.
        """

        self._pages = []
        super().__init__(title=title, route_name="/")

        self.on_frame_drawn: Event[Application] = Event("frame drawn")
        self.on_page_added: Event[Page] = Event("page added")
        self.on_page_changed: Event[Page] = Event("page changed")

        self.fps = 0
        self.fps_sample = fps_sample

        self._page = None
        self._mouse_target: Widget | None = None
        self._hover_target: Widget | None = None
        self._framerate = framerate
        self._terminal = terminal or slt_terminal

        self._is_running = False
        self._is_paused = False
        self._raised: Exception | None = None
        self._timeouts: list[tuple[Callable[[], Any], int | float]] = []

        self._should_draw = True

        def _on_terminal_resize(_: tuple[int, int]) -> bool:
            self._should_draw = True

            return True

        self._terminal.on_resize += _on_terminal_resize

        _ = self.terminal.foreground_color
        _ = self.terminal.background_color

        Widget.app = self

    def __enter__(self) -> Application:
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

    def _draw_loop(  # pylint: disable=too-many-locals, too-many-nested-blocks
        self,
    ) -> None:
        """The display & timing loop of the Application, run as a thread."""

        frametime = 1 / self._framerate

        clear = self._terminal.clear
        write = self._terminal.write
        draw = self._terminal.draw

        on_frame_drawn = self.on_frame_drawn

        elapsed = 1.0
        framerates = []
        fps_sample = self.fps_sample

        try:
            while self._is_running:
                did_draw = False

                if self._is_paused:
                    sleep(frametime)

                start = perf_counter()
                width, height = self._terminal.size

                if self.apply_rules() or self._should_draw:
                    clear()

                    items = sorted(  # type: ignore
                        [*self._page, *self._children],
                        key=lambda w: w.layer,
                    )

                    for widget in items:
                        widget.compute_dimensions(width, height)

                        for child in widget.drawables():
                            origin = child.clipped_position

                            for i, line in enumerate(child.build()):
                                write(line, cursor=(origin[0], origin[1] + i))

                    self._should_draw = False
                    did_draw = True

                write(str(self.fps), cursor=self._terminal.origin)
                draw()

                on_frame_drawn(self)
                on_frame_drawn.clear()

                # Calculate & manage FPS
                elapsed = perf_counter() - start

                if did_draw:
                    framerates.append(1 / elapsed)

                if elapsed < frametime:
                    sleep(frametime - elapsed)

                fps_framecount = len(framerates)
                if fps_framecount > fps_sample:
                    framerates.pop(0)

                self.fps = round(sum(framerates) / min(fps_framecount, fps_sample))

                # Handle timeouts
                eliminated = []

                elapsed = perf_counter() - start

                for i, (callback, timeout) in enumerate(self._timeouts):
                    timeout -= elapsed * 1000

                    if timeout <= 0:
                        callback()

                        eliminated.append(i)
                        self._should_draw = True
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

    def timeout(
        self, delay_ms: int, callback: Callable[[], Any]
    ) -> tuple[Callable[[], Any], int | float]:
        """Sets up a non-blocking timeout.

        Args:
            delay_ms: The delay (in milliseconds) before the callback is executed.
            callback: The callback to execute when the delay is up.
        """

        item = (callback, delay_ms)
        self._timeouts.append(item)
        return item

    def clear_timeout(self, timeout: tuple[Callable[[], Any], int | float]) -> None:
        """Clears a previously added timeout.

        Args:
            timeout: The timeout object obtained when calling `timeout()`.
        """

        if timeout not in self._timeouts:
            raise ValueError("cannot remove non-registered timeout {timeout!r}")

        self._timeouts.remove(timeout)

    def find_all(
        self, query: str | Selector, scope: Container | None = None
    ) -> Iterator[Widget]:
        selector = query

        if isinstance(query, str):
            selector = Selector.parse(query)

        assert isinstance(selector, Selector)

        if self.page is not None:
            yield from self.page.find_all(selector, scope)

        yield from super().find_all(query, scope)

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

        if page.title is None or page.route_name is None:
            raise ValueError(
                "Pages must have both `title` and `route_name`,"
                f" got {page.title=!r}, {page.route_name=!r}"
            )

        rules: dict[str, Any] = {}

        # God compelled me to write this,,,
        # May he compel me to clean  it up.
        #
        for key, value in self._user_rules.items():
            rules.update(
                **{
                    str(key): {
                        **value[0],
                        **{sel + "_style": val for sel, val in value[1].items()},
                    }
                }
            )

        for selector, rule in rules.items():
            page.rule(selector, **rule)

        page.parent = self

        self._pages.append(page)
        self.on_page_added(page)

        if self._mouse_target is None and len(page) > 0:
            self._mouse_target = page[0]

    def remove(self, widget: Widget) -> None:
        super().remove(widget)

        if self._mouse_target is widget and self.page is not None:
            self._mouse_target = self.page[0]

    def pin(self, widget: Widget) -> None:
        """Pins a widget to the application.

        Pinning means the app will always be displayed & on top, regardless of the
        current page.

        Analogous to `Page.append(self, widget)`.
        """

        super().append(widget)
        self._mouse_target = widget

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
        self.on_page_changed(page)

        if page.route_name == "/":
            self._terminal.set_title(f"{self.title}")

        else:
            self._terminal.set_title(f"{self.title} - {page.title}")

        self.apply_rules()

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

        result, *_, hover_target = handle_mouse_on_children(
            *event,
            self._mouse_target,
            self._hover_target,
            reversed([*self._page, *self._children]),  # type: ignore
        )

        # We need to keep (not update) `_mouse_target` to handle keyboard inputs
        self._hover_target = hover_target

        return result

    def run(self) -> None:
        """Runs the application.

        This function will block until the application halts.
        """

        self._is_running = True

        if self._page is None:
            self.route("/")

        terminal = self._terminal

        with terminal.report_mouse(), terminal.no_echo(), terminal.alt_buffer():
            thread = Thread(name=f"{self.title}.draw", target=self._draw_loop)
            thread.start()

            while self._is_running:
                inp = getch()

                if self._is_paused:
                    continue

                if inp == "ctrl-c":
                    self.stop()
                    break

                self._should_draw = True

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
