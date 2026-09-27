"""Text extraction, tokenisation and sentence utilities for the chatbot index."""
import html
import re
from html.parser import HTMLParser

# ── HTML → text ────────────────────────────────────────────────────────────────

# Tags whose content is never page copy.
_SKIP_TAGS = frozenset((
    'script', 'style', 'noscript', 'svg', 'template', 'iframe', 'canvas',
    'head', 'nav', 'footer', 'form', 'button', 'select', 'option',
))
# Class-name fragments that mark site chrome rather than content.
_SKIP_CLASSES = frozenset((
    'topbar', 'navbar', 'breadcrumb', 'offcanvas', 'cookie-banner', 'chatbot',
))
_HEADING_TAGS = frozenset(('h1', 'h2', 'h3', 'h4', 'h5', 'h6'))
# Tags that end a run of text. Everything between one of these and the next is
# treated as a single block, which keeps a navigation list from being glued onto
# the paragraph above it.
_FLUSH_TAGS = frozenset((
    'p', 'li', 'td', 'th', 'blockquote', 'pre', 'figcaption', 'dd', 'dt', 'summary',
))
_VOID_TAGS = frozenset((
    'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link',
    'meta', 'param', 'source', 'track', 'wbr',
))


class _SectionExtractor(HTMLParser):
    """Walks rendered HTML and emits ``(heading, text)`` sections."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.sections = []
        self._heading = ''
        self._buffer = []
        self._heading_parts = []
        self._skip_stack = []          # tags of the skip region we are inside
        self._in_heading = False

    # -- helpers ---------------------------------------------------------
    def _flush(self):
        block = _clean(' '.join(self._buffer))
        self._buffer = []
        if not block:
            return
        # One entry per block. Merging every paragraph under a heading glued
        # navigation runs onto the real copy, which then survived the
        # link-run filter in the indexer.
        self.sections.append((self._heading, [block]))

    @property
    def _skipping(self):
        return bool(self._skip_stack)

    # -- HTMLParser API --------------------------------------------------
    def handle_starttag(self, tag, attrs):
        if tag in ('body', 'html'):
            # New document body: recover from any unbalanced skip region.
            self._skip_stack = []
        if tag in _VOID_TAGS:
            if not self._skipping and tag in _BLOCK_TAGS:
                self._buffer.append('\n')
            return
        if self._skipping:
            self._skip_stack.append(tag)
            return
        classes = (dict(attrs).get('class') or '').split()
        if tag in _SKIP_TAGS or any(
            token in name for token in _SKIP_CLASSES for name in classes
        ):
            self._skip_stack = [tag]
            return
        if tag in _HEADING_TAGS:
            self._flush()
            self._in_heading = True
            self._heading_parts = []
        elif tag in _FLUSH_TAGS:
            self._flush()
            self._buffer.append('\n')
        elif tag in _BLOCK_TAGS:
            self._buffer.append('\n')

    def handle_endtag(self, tag):
        if self._skipping:
            if tag in self._skip_stack:
                # Close out this tag and anything left open inside it, so a
                # mis-nested document does not swallow the rest of the page.
                index = len(self._skip_stack) - 1 - self._skip_stack[::-1].index(tag)
                del self._skip_stack[index:]
            return
        if tag in _HEADING_TAGS and self._in_heading:
            self._in_heading = False
            heading = _clean(''.join(self._heading_parts))
            if heading and len(heading) <= 140:
                self._heading = heading
        elif tag in _FLUSH_TAGS:
            self._flush()
        elif tag in _BLOCK_TAGS:
            self._buffer.append('\n')

    def handle_startendtag(self, tag, attrs):
        if tag in _BLOCK_TAGS and not self._skipping:
            self._buffer.append('\n')

    def handle_data(self, data):
        if self._skipping:
            return
        if self._in_heading:
            self._heading_parts.append(data)
        else:
            self._buffer.append(data)

    def close(self):
        super().close()
        self._flush()
        return self.sections


_BLOCK_TAGS = frozenset((
    'p', 'div', 'section', 'article', 'header', 'main', 'ul', 'ol', 'li',
    'table', 'tr', 'td', 'th', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'br',
    'hr', 'blockquote', 'pre', 'figure', 'figcaption', 'dl', 'dt', 'dd',
))


def _clean(value):
    value = (value or '').replace('\u00a0', ' ').replace('\u200b', '')
    return re.sub(r'\s+', ' ', value).strip()


def html_to_sections(markup):
    """Split rendered HTML into ``(heading, text)`` sections."""
    if not markup:
        return []
    parser = _SectionExtractor()
    try:
        parser.feed(markup)
        parser.close()
    except Exception as exc:  # never let one malformed page break the index
        import logging
        logging.getLogger(__name__).debug('html_to_sections failed: %s', exc)
        return []
    return [(heading, ' '.join(lines)) for heading, lines in parser.sections]


_TAG_RE = re.compile(r'<[^>]+>')


def clean_plain_text(value):
    """Normalise text that came from a database field rather than from HTML."""
    if not value:
        return ''
    return _clean(html.unescape(_TAG_RE.sub(' ', value)))


# ── Tokenisation ───────────────────────────────────────────────────────────────

STOPWORDS = frozenset("""
a about above after again against all also am an and any are aren as at be because been before being
below between both but by can cannot could couldn did didn do does doesn doing don down during each
few for from further had hadn has hasn have haven having he her here hers herself him himself his how
i if in into is isn it its itself just let me more most mustn my myself no nor not of off on once only
or other ought our ours ourselves out over own same shan she should shouldn so some such than that the
their theirs them themselves then there these they this those through to too under until up very was
wasn we were weren what when where which while who whom why will with won would wouldn you your yours
yourself yourselves get got make made use used using new one two three
do does did done offer offers offering support supports want wants wanted need needs needed
like likes liked tell tells explain describes describe provide provides
much many lot lots thing things stuff way ways type types kind kinds
""".split())

_WORD_RE = re.compile(r"[a-z0-9][a-z0-9'+#-]*")


def _stem(word):
    """Very light suffix stripping so plurals and gerunds match their base."""
    if len(word) > 4 and word.endswith('ies'):
        return word[:-3] + 'y'
    if len(word) > 4 and word.endswith('ses'):
        return word[:-2]
    if len(word) > 3 and word.endswith('s') and not word.endswith(('ss', 'us', 'is')):
        return word[:-1]
    if len(word) > 5 and word.endswith('ing'):
        stem = word[:-3]
        if len(stem) > 2 and stem[-1] == stem[-2] and stem[-1] not in 'lsz':
            stem = stem[:-1]
        return stem
    if len(word) > 4 and word.endswith('ed'):
        stem = word[:-2]
        if len(stem) > 2 and stem[-1] == stem[-2] and stem[-1] not in 'lsz':
            stem = stem[:-1]
        return stem
    return word


def tokenize(value):
    """Lowercase word tokens with stopwords and light stemming applied."""
    tokens = []
    for raw in _WORD_RE.findall((value or '').lower()):
        if len(raw) < 2 or raw in STOPWORDS:
            continue
        token = _stem(raw)
        if len(token) < 2 or token in STOPWORDS:
            continue
        tokens.append(token)
    return tokens


# ── Sentences ──────────────────────────────────────────────────────────────────

_SENTENCE_RE = re.compile(r'(?<=[.!?])\s+(?=[A-Z0-9"“(])')
_MIN_SENTENCE = 20


def split_sentences(text, min_length=_MIN_SENTENCE):
    """Split a passage into sentences, keeping only substantial ones."""
    if not text:
        return []
    return [s.strip() for s in _SENTENCE_RE.split(text) if len(s.strip()) >= min_length]


def trim_to_sentence(text):
    """Drop a trailing fragment so answers never end mid-sentence."""
    text = (text or '').strip()
    if not text:
        return ''
    if text[-1] in '.!?"”\')':
        return text
    sentences = split_sentences(text, min_length=_MIN_SENTENCE)
    if sentences:
        return ' '.join(sentences)
    cut = max(text.rfind('. '), text.rfind('! '), text.rfind('? '))
    if cut > 40:
        return text[:cut + 1].strip()
    return text + '.'
