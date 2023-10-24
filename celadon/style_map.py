from __future__ import annotations

from copy import deepcopy

from .state_machine import deep_merge


class StyleMap(dict):
    """A dictionary that is deep-merged when using the | (or) operator."""

    def __or__(self, other: object) -> StyleMap:
        if not isinstance(other, (dict, StyleMap)):
            raise TypeError(
                "Can only merge a StyleMap with a dict or another StyleMap,"
                f" not {type(other)!r}."
            )

        # if "*" in other:
        #     for key in

        return StyleMap(deep_merge(deepcopy(self), other))
