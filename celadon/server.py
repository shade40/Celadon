import os
import re

from dataclasses import dataclass
from textwrap import dedent
from typing import Any, Callable

from lupa import LuaRuntime, lua_type

_runtime = LuaRuntime()
_runtime.execute("""
function getLocals(level)
    local locals = {}
    local index = 1
    while true do
        local name, value = debug.getlocal(level + 1, index)
        if not name then break end
        locals[name] = value
        index = index + 1
    end
    return locals
end""")

def _inject(func: Callable) -> Callable:
    _runtime.globals()[func.__name__] = func
    return func

@_inject
def fmt(text) -> str:
    text = re.sub(r"(?<!\{)\{(?!\{)", "||<<", text)
    text = re.sub(r"(?<!\})\}(?!\})", "||>>", text)
    text = text.replace("{{", "{").replace("}}", "}")

    text = dedent(text.format(**_runtime.eval("getLocals(2)"))).strip()
    text = text.replace("||<<", "{")
    text = text.replace("||>>", "}")

    return text

def _parse_path(path) -> re.Pattern:
    return re.compile('^' + re.sub(r'{([^/]+)}', r'(?P<\1>[^/]+)', path) + '$')

def _load_router(router) -> dict[str, dict[str, Callable]]:
    loaded = {}

    for key, value in router.items():
        if lua_type(value) == "table":
            value = dict(value)

        if lua_type(value) == "function":
            value = {"GET": value}

        key = _parse_path(key)
        loaded[key] = value

    return loaded

@dataclass
class Response:
    code: int
    headers: dict[str, str]
    text: str

class Server:
    def __init__(self, router: str) -> None:
        @_inject
        def require(path):
            with open(os.path.join(os.path.dirname(router), path)) as f:
                return _runtime.execute(f.read())

        with open(router, "r") as f:
            self.router = _load_router(_runtime.execute(f.read()))

    def request(self, method: str, path: str, data: dict[str, Any], headers: dict[str, str] | None = None) -> Response:
        for pattern, handlers in self.router.items():
            m = pattern.match(path)

            if not m:
                continue

            if method not in handlers:
                raise ValueError(f"invalid method for handler: {method} not in {handlers.keys()}")
                return Response(405, {}, "")

            ctx = _runtime.table(**{
                "path": path,
                "req": _runtime.table(headers=headers or {}),
                "resp": _runtime.table(code=200, headers={}),
            })

            text = handlers[method](ctx, _runtime.table(**m.groupdict()), data)
            return Response(ctx.resp.code, ctx.resp.headers or {}, text)

        else:
            return Response(404, {}, "")

