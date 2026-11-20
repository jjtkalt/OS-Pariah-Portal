"""Build absolute portal URLs from configured portal_url (not request Host)."""

from flask import url_for

from app.utils.db import get_dynamic_config


def absolute_portal_url(endpoint, **values):
    """Return an absolute URL rooted at the configured portal_url.

    Avoids Host / X-Forwarded-Host poisoning of emailed and discovery links.
    Falls back to Flask's _external=True only when portal_url cannot be built.
    """
    base = (get_dynamic_config("portal_url") or "").rstrip("/")
    path = url_for(endpoint, **values)
    if base and path.startswith("/"):
        return f"{base}{path}"
    if base and not path.startswith("http"):
        return f"{base}/{path.lstrip('/')}"
    return url_for(endpoint, _external=True, **values)
