import re

from copy import deepcopy
from functools import partial
from lxml.etree import Element, fromstring
from typing import Callable, Any

from .application import Page
from .behaviours import BEHAVIOURS
from .widget import Widget, WIDGET_TYPES
from . import lua

RE_LUA_START = re.compile("<lua[^>]*>")

def _sanitize_xml(text: str) -> str:
    lua_start = RE_LUA_START.finditer(text)

    output = ""
    start, end = (0, 0)

    for start in lua_start:
        span = start.span()
        output += text[end:span[1]]

        sli = text[span[1]:]

        for i, char in enumerate(sli):
            if char == "<" and sli[i:i+6] == "</lua>":
                end = span[1] + i
                break

            if char == ">":
                char = "&gt;"

            elif char == "<":
                char = "&lt;"

            output += char

    if end < len(text):
        output += text[end:]

    return output

def parse(text: str) -> Page | Widget | None:
    text = _sanitize_xml(text)

    root = fromstring(text)

    if root.tag == "page":
        return _parse_page(root)

    return _parse_widget(root)

CUSTOM_WIDGETS = {}
 
def _parse_page(root: Element) -> Page:
    if "location" not in root.attrib:
        raise ValueError("no location passed for page.")

    root_widget = None

    for child in root.getchildren():
        if child.tag == "widget":
            tag, contents, behaviour = _parse_widget_decl(child)

            WIDGET_TYPES[tag] = behaviour 
            CUSTOM_WIDGETS[tag] = contents
            continue

        # TODO: Handle non-widgets like complib
        root_widget = _parse_widget(child)
        root_widget.build()

        for w in [root_widget, *root_widget.parts]:
            w.lua.eval_scheduled()


    page = Page(root.attrib["location"], root_widget)

    return page

def _parse_widget(root: Element) -> Widget:
    tag = root.tag.replace("-", "_")

    attrib = {**root.attrib}

    if tag in CUSTOM_WIDGETS:
        replacement = deepcopy(CUSTOM_WIDGETS[tag])
        overwrite_rules = attrib.get("rules", "")

        attrib["rules"] = ",".join(
            [
                r for r in
                [replacement.attrib.get("rules"), f"/idle/ {overwrite_rules}"]
                if r is not None
            ]
        )

        if "rules" in replacement.attrib:
            del replacement.attrib["rules"]

        attrib = {**attrib, **replacement.attrib}

        slot = replacement.find(".//_slot")

        if slot is not None:
            parent = slot.getparent()
            [*parent].index(slot)
            parent.remove(slot)

            for i, child in enumerate(root.getchildren()):
                parent.append(child)

            if root.text is not None:
                parent.text = root.text

        replacement.tag = tag
        root = replacement

    if "rules" in attrib:
        attrib["rules"] = [attrib["rules"]]

    parsed_attrib = {}
    event_handlers = {}

    for key, value in attrib.items():
        key = key.replace("-", "_")

        if key.startswith("on_"):
            value = value.strip()

            if value.startswith(":"):
                event_handlers[key] = lua.HQLResult.parse(value[1:])
                continue

            event_handlers[key] = lua.runtime.eval(f"function(self) {value} end")
            continue

        if key == "include":
            value = [
                beh for beh in
                [
                    BEHAVIOURS.get(name.strip())
                    for name in value.split(",")
                ]
                if beh is not None
            ]

        parsed_attrib[key] = value

    if root.text is None or root.text.strip() == "":
        widget = WIDGET_TYPES[tag](**parsed_attrib)
    else:
        widget = WIDGET_TYPES[tag](root.text.strip(), **parsed_attrib)

    for child in root.getchildren():
        if child.tag == "lua":
            text = _parse_lua(child)
            widget.lua.schedule_eval(lua.runtime.eval(f"function() {text} end"))
            continue

        widget.append(_parse_widget(child))

    for name, handler in event_handlers.items():
        event = getattr(widget, name, None)

        if event is None:
            raise ValueError(f"{widget} has no event {name!r}.")

        event.append(partial(widget.lua.eval_in_scope, handler))

    return widget

def _parse_lua(root: Element) -> None:
    text = (root.text or "").replace("&lt;", "<").replace("&gt;", ">")

    return text

def _parse_widget_decl(root: Element) -> tuple[str, Element, Callable[[Any, ...], Widget]]:
    name = root.attrib["name"].replace("-", "_")

    behaviours = [
        BEHAVIOURS[e.strip()]
        for e in root.attrib.get("behaviours", "").split(",") if e != ""
    ]

    children = root.getchildren()

    if len(children) != 1:
        raise ValueError("custom widgets declarations must have exactly 1 child.")

    source = WIDGET_TYPES[children[0].tag]

    behaviour = Widget.create_type(name, behaviours, source)

    return name, children[0], behaviour
