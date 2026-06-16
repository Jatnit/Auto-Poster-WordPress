"""Flask application factory."""

from __future__ import annotations

from typing import Callable, Optional

from flask import Flask
from flask_cors import CORS

from wp_auto_poster.web.routes import RouteRuntime, register_routes


RouteRuntimeFactory = Callable[[], RouteRuntime]


def create_app(
    route_runtime_factory: RouteRuntimeFactory,
    import_name: str = __name__,
    template_folder: Optional[str] = None,
    static_folder: Optional[str] = None,
) -> Flask:
    kwargs = {}
    if template_folder:
        kwargs["template_folder"] = template_folder
    if static_folder:
        kwargs["static_folder"] = static_folder

    app = Flask(import_name, **kwargs)
    CORS(app)
    register_routes(app, route_runtime_factory())
    return app
