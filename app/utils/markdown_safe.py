"""Sanitized markdown rendering for user-provided content."""

import bleach
import markdown as md_lib

ALLOWED_TAGS = [
    'p', 'br', 'strong', 'em', 'u', 'h1', 'h2', 'h3', 'h4',
    'ul', 'ol', 'li', 'a', 'code', 'pre', 'blockquote', 'hr',
]
ALLOWED_ATTRIBUTES = {'a': ['href', 'title', 'rel']}
ALLOWED_PROTOCOLS = ['http', 'https', 'mailto']


def render_markdown(text):
    """Convert markdown to sanitized HTML."""
    if not text or not str(text).strip():
        return ''
    raw_html = md_lib.markdown(
        str(text),
        extensions=['extra', 'nl2br', 'sane_lists'],
        output_format='html5',
    )
    return bleach.clean(
        raw_html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        strip=True,
    )


def strip_markdown_plain(text, max_len=500):
    """Plain text for in-world / bot messages."""
    if not text:
        return ''
    html = render_markdown(text)
    plain = bleach.clean(html, tags=[], strip=True)
    plain = ' '.join(plain.split())
    if max_len and len(plain) > max_len:
        return plain[: max_len - 3] + '...'
    return plain
