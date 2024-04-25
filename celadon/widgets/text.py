from __future__ import annotations

import re
from typing import Any

from zenith import zml_wrap

from ..enums import MouseAction
from .widget import Widget

RE_HYPERLINK_MARKUP = re.compile(r"~([^ \]\[]+)")


class Text(Widget):
    """A widget that displays some static text."""

    wrap: bool = False

    rules = """
    Text, Link:
        width: shrink
        height: shrink
    """

    def __init__(self, content: str, **widget_args: Any) -> None:
        super().__init__(**widget_args)

        self.content = content

        self._wrapped_content = []

        def _wrap_content(_: Widget) -> bool:
            if self.wrap:
                self._wrapped_content = zml_wrap(self.content, width=self._framed_width)
            else:
                self._wrapped_content = self.content.splitlines()

            return True

        self.pre_content += _wrap_content

    def _compute_shrink_width(self) -> int:
        return max(
            (
                sum(len(span) for span in self._parse_markup(line))
                for line in self.content.splitlines()
            ),
            default=0,
        )

    def _compute_shrink_height(self) -> int:
        return len(self._wrapped_content)

    @property
    def selectable_count(self) -> int:
        return 0

    def on_click(self, _: MouseAction, __: tuple[int, int]) -> bool:
        """Clicks the first hyperlink within the text's content."""

        if self.app is None:
            return False

        if (mtch := RE_HYPERLINK_MARKUP.search(self.content)) is not None:
            value = mtch[1]

            self.app.route(value)

        # Never return True, as we don't want the parent to select a widget
        return False

    def get_content(self) -> list[str]:
        return self._wrapped_content

    # Proper linebreaking prototype
    #
    # lines = []
    # usable_width = self.width - self.frame.width - 1
    #
    # for line in self.content.splitlines():
    #     length = 0
    #     buff = ""
    #
    #     for char in line:
    #         if char == "[":
    #             in_tag = True
    #
    #         elif char == "]":
    #             in_tag = False
    #
    #         if length < usable_width and char not in ["\n", "\r"]:
    #             if char != "]" and not in_tag:
    #                 length += 1
    #
    #             buff += char
    #             continue
    #
    #         lines.append(buff)
    #         length = 0
    #         buff = ""
    #
    #     lines.append(buff)
    #
    # return lines
