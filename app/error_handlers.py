"""Branded HTTP error handlers (PlatformStandards: friendly, consistent errors).

Wire up from the app factory with::

    from app.error_handlers import register_error_handlers

    register_error_handlers(app)

Handlers render ``templates/errors/*.html`` (extending ``base.html``). If template
rendering itself fails (for example the database that feeds base-template context
is down) they fall back to the self-contained static pages in ``static/errors/``
so users never see a bare traceback or a blank page.
"""

from __future__ import annotations

from pathlib import Path

from flask import Response, jsonify, render_template, request

STATIC_ERRORS_DIR = Path(__file__).resolve().parent / "static" / "errors"

_MESSAGES = {
    404: "Page not found.",
    413: "The upload is too large.",
    429: "Too many requests. Please slow down and try again shortly.",
    500: "Internal server error.",
}


def _wants_json() -> bool:
    if request.path.startswith("/api/"):
        return True
    # best_match lists text/html first, so ties resolve to HTML.
    return (
        request.accept_mimetypes.best_match(["text/html", "application/json"])
        == "application/json"
    )


def _static_fallback(status: int) -> Response:
    name = "404.html" if status == 404 else "50x.html"
    body = (STATIC_ERRORS_DIR / name).read_text(encoding="utf-8")
    return Response(body, status=status, mimetype="text/html")


def _respond(status: int, template: str):
    if _wants_json():
        return jsonify(error=_MESSAGES[status]), status
    try:
        return render_template(template, status_code=status), status
    except Exception:  # noqa: BLE001 - never let the error page itself raise
        return _static_fallback(status)


def register_error_handlers(app) -> None:
    """Register 404, 413, 429, and 500 handlers on *app*."""

    @app.errorhandler(404)
    def handle_404(_error):
        return _respond(404, "errors/404.html")

    @app.errorhandler(413)
    def handle_413(_error):
        return _respond(413, "errors/413.html")

    @app.errorhandler(429)
    def handle_429(_error):
        return _respond(429, "errors/429.html")

    @app.errorhandler(500)
    def handle_500(_error):
        return _respond(500, "errors/500.html")
