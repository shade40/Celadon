from typing import Iterable

from .widget import Widget
from .container import Tower


class Dialogue(Tower):
    """A full-screen overlay that displays some content."""

    rules = r"""
    Dialogue:
        consumes_mouse: true
        anchor: screen

        width: 1.0
        height: 1.0

        alignment: [center, center]
        fill_style: '@black*0.6'

        \> Tower:
            consumes_mouse: true

            width: 0.6
            height: 0.5

            alignment: [center, start]
            frame: [padded, verticalouter, padded, verticalouter]

        \*> Text.title:
            alignment: [center, center]
            height: 2
            content_style: bold dim

        \*> Text.body:
            height: null
            overflow: [hide, auto]

        \*> Tower.body:
            gap: 1

        \*> Row.input:
            height: 3
            alignment: [center, end]
    """

    def __init__(self, *children: Widget, **widget_args) -> None:
        self.content = Tower(*children)
        super().__init__(**widget_args)

        super().insert(0, self.content)

    def on_click(self, _, __) -> bool:
        """Destroy dialogue if the outside (dim part) is clicked."""

        self.remove_from_parent()
        return True

    # Redirect all operations to .content

    def insert(self, index: int, widget: Widget) -> None:
        self.content.insert(index, widget)

    def append(self, widget: Widget) -> None:
        self.content.append(widget)

    def extend(self, widgets: Iterable[Widget]) -> None:
        self.content.extend(widgets)

    def remove(self, widget: Widget) -> None:
        self.content.remove(widget)

    def pop(self, index: int) -> Widget:
        return self.content.pop(index)

    def clear(self) -> None:
        self.content.clear()

    def update_children(self, widgets: Iterable[Widget]) -> None:
        self.content.update_children(widgets)

    def replace(self, current: Widget, new: Widget, *, offset: int = 0) -> None:
        self.content.replace(current, new, offset=offset)
