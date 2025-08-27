import json
import os
import re
import requests
import sqlite3 as py_sqlite3

from dataclasses import dataclass
from functools import partial
from http.server import HTTPServer, BaseHTTPRequestHandler
from textwrap import dedent
from typing import Any, Callable, Protocol, Iterable
from urllib.parse import parse_qs, urlparse, urljoin

from lupa import LuaRuntime, lua_type

INJECTED = {}

def _inject(func: Callable) -> Callable:
    INJECTED[func.__name__] = func
    return func

@_inject
def fmt(lua: LuaRuntime, text) -> str:
    text = re.sub(r"(?<!\{)\{(?!\{)", "||<<", text)
    text = re.sub(r"(?<!\})\}(?!\})", "||>>", text)
    text = text.replace("{{", "{").replace("}}", "}")

    text = dedent(text.format(**lua.eval("getLocals(2)"))).strip()
    text = text.replace("||<<", "{")
    text = text.replace("||>>", "}")

    return text

@_inject
def sqlite3(lua: LuaRuntime, path: str):
    conn = py_sqlite3.connect(path)
    conn.row_factory = py_sqlite3.Row

    cursor = conn.cursor()

    def _exec(sql: str, data: Iterable[Any] | None = None):
        data = data or []

        cursor.execute(sql, data)
        conn.commit()

    def _query(sql: str, data: Iterable[Any] | None = None) -> list[dict[str, Any]]:
        data = data or []

        res = cursor.execute(sql, data)
        return lua.table(*[dict(r) for r in res.fetchall()])

    return {
        "exec": _exec,
        "query": _query,
    }


def _parse_path(path) -> re.Pattern:
    return re.compile('^' + re.sub(r'{([^/]+)}', r'(?P<\1>[^/]+)', path) + '$')

def _load_routes(router) -> dict[str, dict[str, Callable]]:
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

class Router(Protocol):
    def request(self, method: str, path: str, data: dict[str, Any], headers: dict[str, str] | None = None) -> Response:
        ...

class LocalRouter:
    def __init__(self, router: str) -> None:
        self.file = router

    def _get_runtime(self) -> LuaRuntime:
        lua = LuaRuntime()

        lua.execute("""
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

        @_inject
        def require(lua: LuaRuntime, path: str):
            with open(os.path.join(os.path.dirname(self.file), path)) as f:
                return lua.execute(f.read())

        glob = lua.globals()

        for key, value in INJECTED.items():
            glob[key] = partial(value, lua)

        with open(os.path.join(os.path.dirname(__file__), "builtins.lua"), "r") as f:
            builtins = lua.execute(f.read())

        for key, value in builtins.items():
            glob[key] = value

        return lua

    def request(self, method: str, path: str, data: dict[str, Any], headers: dict[str, str] | None = None) -> Response:
        lua = self._get_runtime()

        with open(self.file, "r") as f:
            content = f.read()
            routes = _load_routes(lua.execute(content))

        for pattern, handlers in routes.items():
            m = pattern.match(path)

            if not m:
                continue

            if method not in handlers:
                raise ValueError(f"invalid method for handler: {method} not in {handlers.keys()}")
                return Response(405, {}, "")

            ctx = lua.table(**{
                "path": path,
                "req": lua.table(headers=headers or {}),
                "resp": lua.table(code=200, headers={}),
            })

            text = handlers[method](ctx, lua.table(**m.groupdict()), lua.table(**data))
            return Response(ctx.resp.code, ctx.resp.headers or {}, text)

        else:
            return Response(404, {}, "")

    def serve(self, port: int = 5555) -> None:
        router_ref = self
        
        class RequestHandler(BaseHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                self.router = router_ref
                super().__init__(*args, **kwargs)
            
            def _handle_request(self):
                def _parse_formdata(query) -> dict[str, str]:
                    return {k: v[0] if len(v) == 1 else v for k, v in parse_qs(query).items()}

                try:
                    method = self.command
                    path = urlparse(self.path).path
                    data = {}
                    
                    if method in ['GET', 'DELETE']:
                        query = urlparse(self.path).query
                        if query:
                            data = _parse_formdata(query)
                    
                    elif method in ['POST', 'PUT', 'PATCH']:
                        content_length = int(self.headers.get('Content-Length', 0))
                        if content_length > 0:
                            body = self.rfile.read(content_length).decode('utf-8')
                            
                            # Try to parse as JSON first
                            content_type = self.headers.get('Content-Type', '')
                            if 'application/json' in content_type:
                                try:
                                    data = json.loads(body)
                                except json.JSONDecodeError:
                                    data = {}
                            elif 'application/x-www-form-urlencoded' in content_type:
                                data = _parse_formdata(query)
                            else:
                                # Default to form data parsing
                                try:
                                    data = _parse_formdata(query)
                                except:
                                    data = {'body': body}
                    
                    response = self.router.request(method, path, data, dict(self.headers))
                    self.send_response(response.code)
                    
                    for key, value in response.headers.items():
                        self.send_header(key, value)
                    self.end_headers()
                    
                    if response.text:
                        self.wfile.write(response.text.encode('utf-8'))
                
                except Exception as e:
                    print(e)
                    self.send_response(500)
                    self.end_headers()
                    self.wfile.write(f"Internal Server Error: {str(e)}".encode('utf-8'))
            
            def do_GET(self):
                self._handle_request()
            
            def do_POST(self):
                self._handle_request()
            
            def do_PUT(self):
                self._handle_request()
            
            def do_PATCH(self):
                self._handle_request()
            
            def do_DELETE(self):
                self._handle_request()
        
        httpd = HTTPServer(('localhost', port), RequestHandler)
        print(f"Server running on http://localhost:{port}")

        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            httpd.shutdown()

class HTTPRouter:
    def __init__(self, url: str) -> None:
        if not url.startswith(("http://", "https://")):
            url = "http://" + url

        self.url = url

    def request(self, method: str, path: str, data: dict[str, Any], headers: dict[str, str] | None = None) -> Response:
        if path.startswith(('http://', 'https://')):
            url = path
        elif path.startswith('//'):
            url = path
        else:
            url = urljoin(self.url, path)
        
        request_kwargs = {
            'headers': { "CELX_REQUEST": "true", **(headers or {}) },
            'timeout': 30
        }
        
        if method.upper() in ['GET', 'DELETE']:
            if data:
                request_kwargs['params'] = data
        else:
            if isinstance(data, (dict, list)):
                request_kwargs['json'] = data
                if 'Content-Type' not in request_kwargs['headers']:
                    request_kwargs['headers']['Content-Type'] = 'application/json'
            else:
                request_kwargs['data'] = data
        
        try:
            response = requests.request(method.upper(), url, **request_kwargs)
            response_headers = dict(response.headers)
            
            return Response(
                code=response.status_code,
                headers=response_headers,
                text=response.text
            )
        
        except requests.exceptions.RequestException as e:
            return Response(
                code=500,
                headers={},
                text=f"Request failed: {str(e)}"
            )

