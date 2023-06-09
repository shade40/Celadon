from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from ..application import Page

from .container import Row
from .button import Button


def index_first(page: "Page") -> int:
    if page.route_name == "index":
        return 0

    return ord(page.route_name[0])


class Nav(Row):
    def __init__(
        self, sort_key: Callable[["Page"], int] = index_first, **widget_args
    ) -> None:
        super().__init__(**widget_args)

        self.sort_key = sort_key
        self.app.on_page_added += self._update_pages

        self._selection_set = False

    def _update_pages(self) -> None:
        self._selection_set = False
        self.clear()

        for page in sorted(self.app, key=self.sort_key):
            button = Button(page.name, route=page.route_name)

            self.append(button)

    def get_content(self) -> list[str]:
        if not self._selection_set:
            for button in self.children:
                if button.content == self.app.page.name:
                    button.groups = ("selected",)
                    break

                if "selected" in button.groups:
                    button.remove_group("selected")

        return super().get_content()
