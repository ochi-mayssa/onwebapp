"""Conservative HTML sanitizer for administrator-provided campaign HTML.

Uses a tag/attribute allowlist implemented with the standard library (no extra
dependencies). Anything outside the allowlist is stripped; text content is
always escaped. The result is safe to embed in an email template.
"""
from html import escape
from html.parser import HTMLParser

ALLOWED_TAGS = {
    'p', 'br', 'a', 'strong', 'em', 'b', 'i', 'u', 's', 'ul', 'ol', 'li',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote', 'hr', 'span', 'div',
    'pre', 'code',
}
VOID_TAGS = {'br', 'hr'}
# Elements whose *contents* are dropped entirely (script/style payloads).
SKIP_ELEMENTS = {'script', 'style', 'iframe', 'object', 'embed', 'svg', 'template', 'form'}


def _safe_href(href):
    href = (href or '').strip().lower()
    return href.startswith(('http://', 'https://', 'mailto:', '/'))


class _Sanitizer(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if self._skip_depth:
            if tag in SKIP_ELEMENTS:
                self._skip_depth += 1
            return
        if tag in SKIP_ELEMENTS:
            self._skip_depth = 1
            return
        if tag not in ALLOWED_TAGS:
            return
        if tag in VOID_TAGS:
            self.out.append(f'<{tag}>')
            return
        if tag == 'a':
            href = dict(attrs).get('href', '')
            if _safe_href(href):
                self.out.append(f'<a href="{escape(href, quote=True)}">')
            else:
                self.out.append('<a>')
            return
        self.out.append(f'<{tag}>')

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS and tag in ALLOWED_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self._skip_depth:
            if tag in SKIP_ELEMENTS:
                self._skip_depth = max(0, self._skip_depth - 1)
            return
        if tag in ALLOWED_TAGS and tag not in VOID_TAGS:
            self.out.append(f'</{tag}>')

    def handle_data(self, data):
        if self._skip_depth:
            return
        self.out.append(escape(data))

    def handle_comment(self, data):
        return


def sanitize_campaign_html(html):
    """Return campaign HTML reduced to the safe allowlist (escaped text kept)."""
    if not html:
        return ''
    parser = _Sanitizer()
    parser.feed(html)
    parser.close()
    return ''.join(parser.out)
