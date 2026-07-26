"""Flask application factory."""

from __future__ import annotations

from typing import Callable, Iterable, Optional

from flask import Flask, jsonify
from flask_cors import CORS

from wp_auto_poster.web.routes import RouteRuntime, register_routes

RouteRuntimeFactory = Callable[[], RouteRuntime]

#: Hostnames the control panel is allowed to be reached on. Anything else is
#: rejected before routing, which blocks DNS-rebinding attacks that would
#: otherwise let a public website reach this loopback-only server.
ALLOWED_HOSTNAMES = frozenset({"localhost", "127.0.0.1", "[::1]", "::1"})


def _default_origins(port: int) -> list:
    return [
        f"http://localhost:{port}",
        f"http://127.0.0.1:{port}",
    ]


def create_app(
    route_runtime_factory: RouteRuntimeFactory,
    import_name: str = __name__,
    template_folder: Optional[str] = None,
    static_folder: Optional[str] = None,
    port: int = 5001,
    allowed_hostnames: Optional[Iterable[str]] = None,
) -> Flask:
    kwargs = {}
    if template_folder:
        kwargs["template_folder"] = template_folder
    if static_folder:
        kwargs["static_folder"] = static_folder

    app = Flask(import_name, **kwargs)

    # Previously this was a bare CORS(app), which let any origin read
    # /api/config — including the WordPress password it used to return.
    CORS(app, origins=_default_origins(port), supports_credentials=False)

    hostnames = frozenset(allowed_hostnames) if allowed_hostnames else ALLOWED_HOSTNAMES

    @app.before_request
    def _reject_foreign_host():
        host = (request_host() or "").split(":")[0].strip().lower()
        if host and host not in hostnames:
            return jsonify({
                "success": False,
                "message": "Host không được phép",
            }), 403
        return None

    @app.after_request
    def _security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    register_routes(app, route_runtime_factory())
    return app


def request_host() -> Optional[str]:
    """Read the request Host header (indirection keeps the factory testable)."""
    from flask import request

    return request.host
