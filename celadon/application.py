from __future__ import annotations

import re
from dataclasses import dataclass, field
from threading import Thread
from time import perf_counter, sleep

from celadon.widgets import Widget
from slate import Terminal, getch, Event
from slate.core import BEGIN_SYNCHRONIZED_UPDATE, END_SYNCHRONIZED_UPDATE

from . import widgets
from .enums import MouseAction
from .widgets import Widget, Tower
from .state_machine import deep_merge
from .style_map import StyleMap


__all__ = [
    "Selector",
    "Application",
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
                getattr(widgets, element) for element in elements_str.split("|")
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

        if not (eid_matches and group_matches and state_matches):
            return 0

        if self.forced_score is not None:
            return self.forced_score

        score = (
            (eid_matches - (self.eid is None)) * 1000
            + (group_matches - (len(self.groups) == 0)) * 500
            + ((state_matches - (self.states is None)) * 250)
            * (type_matches - (self.elements == (Widget,)))
        )

        return score


class Application:
    def __init__(
        self, name: str, *, terminal: Terminal | None = None, target_frames: int = 60
    ) -> None:
        self.on_frame_ready = Event("Frame Ready")
        self.terminal = terminal or Terminal()

        self._name = name
        self._is_active = False
        self._target_frames = target_frames
        self._widgets: list[Widget] = []
        self._mouse_target: Widget | None = None
        self._rules: dict[
            Selector,
            dict[
                str,
                tuple[
                    dict[str, DimensionSpec | AlignmentSetting | OverflowSetting],
                    dict[str, str],
                ],
            ],
        ] = {}

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

    def __iadd__(self, other: object) -> None:
        if not isinstance(other, Widget):
            raise TypeError(f"Can only add widgets to apps, not {type(other)!r}.")

        self.add(other)

        return self

    def _update_and_apply_rules(self) -> None:
        drawables = []
        for widget in self._widgets:
            drawables.extend(widget.drawables())

        for widget in drawables:
            new_attrs = {}
            new_style_map = StyleMap()

            if not widget.query_changed():
                continue

            applicable_rules = [
                (sel.matches(widget), rule) for sel, rule in self._rules.items()
            ]

            for score, (attrs, style_map) in sorted(
                applicable_rules, key=lambda item: item[0]
            ):
                if score == 0:
                    continue

                new_attrs.update(**attrs)
                new_style_map |= style_map

            widget.update(new_attrs, new_style_map)

    def _draw_loop(self) -> None:
        frametime = 1 / self._target_frames

        clear = self.terminal.clear
        write = self.terminal.write
        draw = self.terminal.draw
        frame_ready = self.on_frame_ready

        while self._is_active:
            start = perf_counter()
            clear()

            self._update_and_apply_rules()

            for widget in self._widgets:
                widget.compute_dimensions(self.terminal.width, self.terminal.height)

                for child in widget.drawables():
                    origin = child.position

                    for i, line in enumerate(child.build()):
                        write(line, cursor=(origin[0], origin[1] + i))

            draw()

            if frame_ready:
                frame_ready()
                frame_ready.clear()

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


    def select(self, query: str) -> Selector:
        """Creates a new selector and returns it."""

        return Selector.parse(query)

    def find_all(self, query: str) -> Generator[Widget, None, None]:
        """Finds all widgets that are selected by a query."""

        # matching = [sel for sel in self._rules sel.query == query]

        # if len(matching) > 0:
        #     selector = matching[0]

        # else:
        selector = Selector.parse(query)

        for widget in self._widgets:
            for child in widget.drawables():
                if selector.matches(child):
                    yield child

    def find(self, query: str) -> Widget | None:
        """Finds the first widget that is selected by a query."""

        for widget in self.find_all(query):
            return widget

        return None

    def rule(self, query: str, base: bool = False, **rules: str) -> Selector:
        """Applies some styling rules for the given query."""

        style_map = {}
        attrs = {}
        for key, value in rules.copy().items():
            if not key.endswith("_style"):
                attrs[key] = value
            else:
                style_map[key.removesuffix("_style")] = value

        selector = Selector.parse(query, forced_score=(1 if base else None))

        if selector not in self._rules:
            self._rules[selector] = ({}, {})

        old_attrs, old_style_map = self._rules[selector]
        deep_merge(old_attrs, attrs)
        deep_merge(old_style_map, style_map)

        return selector

    def process_input(self, inp: str) -> bool:
        if (event := _parse_mouse_input(inp)) is not None:
            action, position = event

            if (
                self._mouse_target is not None
                and action is MouseAction.HOVER
                and not self._mouse_target.contains(position)
            ):
                self._mouse_target.handle_mouse(MouseAction.LEFT_RELEASE, position)

            for widget in reversed(self._widgets):
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

        if len(self._widgets) == 0:
            return False

        return self._widgets[0].handle_keyboard(inp)

    def add(self, widget: Widget) -> None:
        self._widgets.append(widget)
        widget.parent = self

    def run(self) -> None:
        self._is_active = True

        exception: Exception | None = None

        for widget in self._widgets:
            self._set_default_rules(widget)

        terminal = self.terminal

        with terminal.report_mouse(), terminal.no_echo(), terminal.alt_buffer():
            terminal.set_title(self._name)

            thread = Thread(name=f"{self._name}_draw", target=self._draw_loop)
            thread.start()

            while self._is_active:
                inp = getch()

                if inp == chr(3):
                    self._is_active = False
                    break

                try:
                    self.process_input(inp)

                except Exception as exc:
                    self._is_active = False
                    exception = exc
                    break

            thread.join()

        if exception is not None:
            raise exception

    def stop(self) -> None:
        self._is_active = False
