import os

from dataclasses import dataclass
from functools import partial
from enum import Enum
from typing import Any, Callable

from lupa import LuaRuntime

from .xml import parse
from .behaviours import behaviour
from .widget import Widget, WidgetFields

def init_runtime() -> LuaRuntime:
    return LuaRuntime()

NO_VALUE = object()

runtime = init_runtime()

def _get_namespace(widget: Widget, getter: Callable, setter: Callable) -> ...:
    with open(os.path.join(os.path.dirname(__file__), "builtins.lua"), "r") as f:
        builtins = runtime.execute(f.read())

    return runtime.eval("""
        function(this, widget, w_get, w_set)
            local setfenv = function(fn, env)
                if type(fn) ~= "function" then
                    return fn
                end

                local i = 1
                while true do
                    local name = debug.getupvalue(fn, i)
                    if name == "_ENV" then
                        debug.upvaluejoin(fn, i, (function()
                            return env
                        end), 1)
                        break
                    elseif not name then
                        break
                    end

                    i = i + 1
                end

                return fn
            end

            local listeners = {}
            local owned_keys = {}

            local meta = setmetatable(
                {
                    copy = function()
                        local copy = {}

                        for k, v in pairs(this) do
                            copy[k] = v
                        end

                        return copy
                    end,

                    listeners = listeners,
                    owned_keys = owned_keys,

                    on_change = function(k, cb)
                        local owner, _ = table.unpack(w_get(k))

                        if owner == nil then
                            error("no owner for variable '" .. k .. "'")
                        end

                        if owner.lua.listeners[k] == nil then
                            owner.lua.listeners[k] = {}
                        end

                        table.insert(owner.lua.listeners[k], function(v)
                            this.eval_in_scope(cb, v)
                        end)
                    end,
                },
                {
                    __index = function(t, k)
                        if k == "app" then
                            return widget.app
                        end

                        if this[k] ~= nil then
                            return this[k]
                        end

                        local owner, val = table.unpack(w_get(k))

                        if owner ~= nil then
                            return val
                        end

                        return nil
                    end,

                    __newindex = function(t, k, v)
                        if this[k] ~= nil then
                            this[k] = v

                            if listeners[k] ~= nil then
                                for _, cb in ipairs(listeners[k]) do
                                    if not pcall(cb, v) then
                                        -- TODO: Handle errors on app level
                                        print('error')
                                    end
                                end
                            end
                            return
                        end

                        local owner, val = table.unpack(w_get(k))

                        if k == val then
                            return
                        end

                        if owner ~= nil then
                            w_set(owner, k, v)
                        else
                            this[k] = v
                            table.insert(owned_keys, k)
                            return
                        end
                    end,
                }
            )

            local scheduled = {}

            this.schedule_eval = function(func)
                table.insert(scheduled, func)
            end

            this.eval_in_scope = function(wrapper, ...)
                local args = {...}
                local envd = setfenv(wrapper, meta)

                return envd(table.unpack(args))
            end

            this.eval_scheduled = function()
                for _, func in ipairs(scheduled) do
                    this.eval_in_scope(func)
                end
            end

            return meta
        end
    """)(builtins, widget, getter, setter)

@behaviour
def lua_behaviour(widget: Widget, fields: WidgetFields) -> Widget | None:
    def _get(key: str) -> Any:
        parent = widget.parent

        i = 0
        while isinstance(parent, Widget):
            if hasattr(parent, "lua"):
                vals = parent.lua.owned_keys.values()

                if key in vals:
                    return runtime.table(parent, parent.lua.copy()[key])

            parent = parent.parent
            i += 1

        return runtime.table(None, None)

    def _set(owner: Widget, key: str, value: Any) -> Widget | None:
        owner.lua[key] = value

    @widget.add_initializer
    def initialize(self):
        fields.define_readonly(lua=_get_namespace(widget, _get, _set))

class _HTTPMethod(Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"

class _IncludeMethod(Enum):
    WIDGET = "WIDGET"
    DATA = "DATA"

class _SwapMethod(Enum):
    BEFORE = "BEFORE"
    TARGET = "TARGET"
    AFTER = "AFTER"
    IN = "IN"

def _data_resolver(arg: str, cast_type: type = str):
    def _resolve(widget) -> str:
        if not arg[0] == arg[-1] == "`":
            return cast_type(arg)

        func = runtime.eval(f"function() return {arg.strip('`')} end")
        result = widget.lua.eval_in_scope(func)

        return cast_type(result)

    return _resolve

def _include_resolver(method: _IncludeMethod, arg: str):
    if method is _IncludeMethod.DATA:
        return _data_resolver(arg, dict)

    def _resolve(widget) -> Widget:
        selector = _data_resolver(arg)(widget)
        return widget.app.find(selector, context=widget)

    return _resolve

def _swap_resolver(method: _SwapMethod, arg: str):
    def _resolve(widget, content: Widget) -> None:
        selector = _data_resolver(arg)(widget)
        target = widget.app.find(selector, context=widget)

        parent = target.parent

        if method is _SwapMethod.TARGET:
            parent.replace(target, content)
        elif method is _SwapMethod.IN:
            target.replace_children([content])
        elif method is _SwapMethod.BEFORE:
            parent.insert(parent.children.index(target), content)
        elif method is _SwapMethod.AFTER:
            parent.insert(parent.children.index(target) + 1, content)

    return _resolve

def _empty_resolver(widget: Widget) -> None:
    return None

@dataclass
class HQLResult:
    method: _HTTPMethod
    endpoint: Callable[[Widget], str]
    headers: dict[str, str]
    includes: list[tuple[_IncludeMethod, Callable[[], Widget | dict[str, str]]]]
    swap: tuple[_SwapMethod, Callable[[], Widget]]

    def __call__(self, widget: Widget) -> None:
        endpoint = self.endpoint(widget)
        if endpoint is None:
            raise RuntimeError("why is endpoint none?")

        headers = self.headers(widget) or {}
        data = {}

        for gather in self.includes:
            result = gather(widget)

            if isinstance(result, Widget):
                result = result.serialize()

            data.update(result)

        resp = widget.app.router.request(self.method.value, endpoint, data, headers=headers)
        resp_widget = parse(resp.text)

        self.swap(widget, resp_widget)

    @classmethod
    def parse(cls, query: str) -> 'HQLResult':
        statements = []

        statement = []
        args = []
        token = ""

        in_code = False

        for i, char in enumerate(query):
            if char == "`":
                token += char
                in_code = not in_code
                continue

            if in_code:
                token += char
                continue

            if char.strip() == "":
                if len(token):
                    statement.append(token)
                token = ""
                continue

            if char in ";!":
                if len(token):
                    statement.append(token)

                statements.append(statement)
                statement = []

                token = ""

                if char == ";":
                    continue
                else:
                    break

            if char == ",":
                continue

            token += char
        
        method = _empty_resolver
        endpoint = _empty_resolver
        headers = _empty_resolver
        includes = []
        swap = _empty_resolver

        for keyword, *data in statements:
            if keyword in [e.name for e in _HTTPMethod]:
                method = _HTTPMethod(keyword)
                endpoint = _data_resolver(*data, str)
                continue

            if keyword == "HEADERS":
                headers = _data_resolver(*data, dict)
                continue

            if keyword in ["SWAP", "INCLUDE"]:
                if keyword == "SWAP":
                    enum = _SwapMethod 
                    default = _SwapMethod.TARGET
                    resolver = _swap_resolver

                else:
                    enum = _IncludeMethod
                    default = _IncludeMethod.WIDGET
                    resolver = _include_resolver

                parts = []

                i = 0
                length = len(data)
                result = []

                while True:
                    if i > length - 1:
                        break

                    arg = data[i]
                    
                    if arg in [e.name for e in enum]:
                        result.append(resolver(enum(arg), data[i+1]))
                        i += 2
                        continue

                    result.append(resolver(default, arg))
                    i += 1

                if keyword == "SWAP":
                    swap = result[0]

                else:
                    includes = result

        return HQLResult(method, endpoint, headers, includes, swap)
