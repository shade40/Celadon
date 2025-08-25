import sys

from urllib.parse import urlparse
from argparse import ArgumentParser

import celadon as c

def run(app: str) -> None:
    path = "/"

    if app.startswith(("http://", "https://")):
        url = urlparse(app)
        path = url.path
        router = c.HTTPRouter(f"{url.scheme}://{url.netloc}")

    else:
        file = []
        parts = app.split("/")

        for i, item in enumerate(parts):
            file.append(item)

            if item.endswith(".lua"):
                left = parts[i+1:]
                if len(left):
                    path = "/" + "/".join(left)
                break

        file = "/".join(file)
        router = c.LocalRouter(file)

    app = c.Application(router)

    app.navigate(path)
    app.run()

def serve(router_file: str, port: int) -> None:
    router = c.LocalRouter(router_file)
    router.serve(port)

def main() -> None:
    parser = ArgumentParser("The Celadon application runner.")
    subs = parser.add_subparsers(required=True)

    run_cmd = subs.add_parser("run")
    run_cmd.set_defaults(func=run)
    run_cmd.add_argument("app", help="The application to run. Either the path to a Lua router or the URL to a server.")

    serve_cmd = subs.add_parser("serve")
    serve_cmd.set_defaults(func=serve)
    serve_cmd.add_argument("router_file", help="The path to the Lua router to serve.")
    serve_cmd.add_argument("-p", "--port", default=5555, help="The port to serve on.")

    args = parser.parse_args()

    opts = vars(args)
    func = args.func
    del opts["func"]

    func(**opts)

if __name__ == "__main__":
    main()
