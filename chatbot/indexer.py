"""Builds and caches the chatbot's BM25 index over the site's own content."""
import logging
import math
import os
import pickle
import re
import time
from collections import Counter, defaultdict

from django.conf import settings

from .corpus import AUTH, PUBLIC, collect_records, iter_page_sources
from .text_utils import html_to_sections, split_sentences, tokenize

logger = logging.getLogger(__name__)

INDEX_VERSION = 6
INDEX_TTL_SECONDS = 60 * 60 * 12          # rebuild at most every 12 hours
TARGET_CHUNK_CHARS = 520
MAX_CHUNK_CHARS = 1000
MIN_CHUNK_CHARS = 90

# BM25 parameters.
K1 = 1.5
B = 0.75

# Sections that are really navigation furniture rather than copy.
_CHROME_RE = re.compile(r'^[\w &/+\-–—:,.]{0,400}$')


# ── Chunking ───────────────────────────────────────────────────────────────────

def _looks_like_chrome(text):
    """True for link-label runs such as 'Home Articles Research Careers Pricing'.

    Sections are merged per heading, so a heading with several paragraphs arrives
    as one block of text. The test has to be strict: anything with real sentence
    punctuation, or any lowercase connective, is copy and must be kept.
    """
    if not text or len(text) > 200:
        return False
    # Real prose ends sentences. Navigation rarely does.
    if any(mark in text for mark in '.!?;:'):
        return False
    if not _CHROME_RE.match(text):
        return False
    words = text.split()
    if len(words) < 2:
        return True
    if any(len(word) > 14 for word in words):
        return False
    # A menu is a list of labels, so most of them start with a capital.
    capitalised = sum(1 for word in words if word[:1].isupper())
    if capitalised / len(words) < 0.7:
        return False
    # Lowercase words are fine only if they are short connectors.
    return all(len(word) <= 4 or word[:1].isupper() for word in words)


def _split_into_chunks(text, target=TARGET_CHUNK_CHARS, maximum=MAX_CHUNK_CHARS):
    """Group sentences into chunks of roughly ``target`` characters."""
    sentences = split_sentences(text, min_length=1) or [text.strip()]
    chunks = []
    current = ''
    for sentence in sentences:
        if not current:
            current = sentence
        elif len(current) + 1 + len(sentence) <= maximum:
            current = current + ' ' + sentence
        else:
            chunks.append(current)
            current = sentence
        while len(current) >= target:
            chunks.append(current)
            current = ''
    if current:
        chunks.append(current)
    return [c.strip() for c in chunks if len(c.strip()) >= MIN_CHUNK_CHARS] or \
           ([text.strip()] if len(text.strip()) >= 40 else [])


def chunk_page(source_id, title, url, access, markup):
    """Turn one rendered page into indexable chunks."""
    chunks = []
    for heading, body in html_to_sections(markup):
        if _looks_like_chrome(body):
            continue
        for piece in _split_into_chunks(body):
            chunks.append({
                'source_id': source_id,
                'title': title,
                'heading': heading,
                'url': url,
                'access': access,
                'kind': 'page',
                'text': piece,
            })
    return chunks


def chunk_record(source_id, title, url, access, heading, body):
    """Turn one database row into indexable chunks."""
    chunks = []
    if _looks_like_chrome(body):
        return chunks
    for piece in _split_into_chunks(body):
        chunks.append({
            'source_id': source_id,
            'title': title,
            'heading': heading or title,
            'url': url,
            'access': access,
            'kind': 'record',
            'text': piece,
        })
    return chunks


# ── Fetching pages ─────────────────────────────────────────────────────────────

def _crawl_host():
    """Host header for the in-process crawler.

    ``django.test.Client`` sends ``Host: testserver``, which Django only accepts
    while the test runner is running. A real ``manage.py rebuild_chat_index``
    would have every page rejected with DisallowedHost and build an empty index,
    so use a host this deployment already allows.
    """
    for host in getattr(settings, 'ALLOWED_HOSTS', None) or ():
        host = str(host).strip()
        if host and host != '*' and not host.startswith('.'):
            return host
    return 'localhost'


def _superuser_client():
    from django.contrib.auth import get_user_model
    from django.test import Client

    # Never raise on a broken page: outside tests Django hands back a 500
    # response, and the indexer must skip that page rather than blow up the
    # build. Being explicit keeps the behaviour identical under `manage.py test`.
    try:
        client = Client(HTTP_HOST=_crawl_host(), raise_request_exception=False)
    except TypeError:      # older Django without the keyword
        client = Client(HTTP_HOST=_crawl_host())
        client.raise_request_exception = False
    user = get_user_model().objects.filter(
        is_superuser=True, is_active=True
    ).order_by('pk').first()
    if user is None:
        user = get_user_model().objects.filter(is_staff=True, is_active=True).order_by('pk').first()
    if user is not None:
        try:
            client.force_login(user)
        except Exception as exc:
            logger.debug('chatbot index: force_login failed: %s', exc)
    return client


def _fetch_pages():
    """Render every registered page in-process and return ``(url, html)`` pairs.

    The client stays logged in as a superuser throughout so that the pages which
    are normally behind a login still render and can be indexed; access is
    enforced later, per visitor, when results are filtered.
    """
    client = _superuser_client()
    fetched = []
    # Broken pages in the rest of the site are expected during a sweep; record
    # them at debug level instead of dumping tracebacks to the console.
    request_logger = logging.getLogger('django.request')
    previous_level = request_logger.level
    request_logger.setLevel(logging.CRITICAL)
    try:
        for url_name, title, path, access in iter_page_sources():
            try:
                response = client.get(path, follow=False)
            except Exception as exc:
                logger.debug('chatbot index: GET %s raised %s', path, exc)
                continue
            if response.status_code != 200:
                logger.debug('chatbot index: skipping %s (HTTP %s)', path, response.status_code)
                continue
            try:
                markup = response.content.decode('utf-8', 'replace')
            except Exception:
                continue
            fetched.append((url_name, title, path, access, markup))
    finally:
        request_logger.setLevel(previous_level)
    return fetched


# ── Index construction ─────────────────────────────────────────────────────────

def build_index():
    """Collect every source, chunk it, and compute BM25 statistics."""
    chunks = []
    live_paths = set()
    sources = 0
    for url_name, title, path, access, markup in _fetch_pages():
        page_chunks = chunk_page(url_name, title, path, access, markup)
        if page_chunks:
            chunks.extend(page_chunks)
            live_paths.add(path)
            sources += 1

    for source_id, title, path, access, heading, body in collect_records():
        record_chunks = chunk_record(source_id, title, path, access, heading, body)
        if record_chunks:
            chunks.extend(record_chunks)
            live_paths.add(path)
            sources += 1

    postings = defaultdict(dict)
    doc_lengths = []
    for index, chunk in enumerate(chunks):
        tokens = tokenize(chunk['text'])
        if not tokens:
            doc_lengths.append(0)
            continue
        counts = Counter(tokens)
        doc_lengths.append(len(tokens))
        # The heading and title are indexed too, so a question phrased like the
        # section title still finds the passage underneath it.
        for token in tokenize(chunk['heading']):
            counts[token] = counts.get(token, 0) + 2
        for token in tokenize(chunk['title']):
            counts[token] = counts.get(token, 0) + 2
        for token, freq in counts.items():
            postings[token][index] = freq

    total_docs = len(chunks)
    non_empty = [d for d in doc_lengths if d]
    avgdl = (sum(non_empty) / len(non_empty)) if non_empty else 1.0

    return {
        'version': INDEX_VERSION,
        'built_at': time.time(),
        'chunks': chunks,
        'postings': {token: dict(p) for token, p in postings.items()},
        'doc_lengths': doc_lengths,
        'total_docs': total_docs,
        'avgdl': avgdl or 1.0,
        'sources': sources,
        # Pages that actually rendered. Anything absent here 500s, so the
        # chatbot must not link to it.
        'live_paths': sorted(live_paths),
    }


# ── Cache handling ─────────────────────────────────────────────────────────────

def _cache_dir():
    override = getattr(settings, 'CHATBOT_INDEX_DIR', None)
    if override:
        path = str(override)
    else:
        base = getattr(settings, 'BASE_DIR', None) or os.getcwd()
        path = os.path.join(str(base), '.chatbot_index')
    os.makedirs(path, exist_ok=True)
    return path


def _cache_path():
    return os.path.join(_cache_dir(), 'index-%d.pkl' % INDEX_VERSION)


# Unpickling a few hundred chunks on every keystroke would be wasteful, so keep
# the current index in memory too.
_MEMO = {'index': None}


def loaded_index():
    """The in-memory index, loading it from disk once per process if needed."""
    if _MEMO['index'] is None:
        _MEMO['index'] = load_index()
    return _MEMO['index']


def load_index(max_age=INDEX_TTL_SECONDS):
    """Return the cached index, building it if missing, stale, or outdated."""
    # A fresh in-memory index wins: rebuilding and then reading the file back
    # would discard what we just built.
    memo = _MEMO['index']
    if memo is not None and memo.get('version') == INDEX_VERSION:
        if max_age is None or (time.time() - memo.get('built_at', 0)) <= max_age:
            return memo

    path = _cache_path()
    if os.path.exists(path):
        try:
            with open(path, 'rb') as handle:
                index = pickle.load(handle)
            if index.get('version') == INDEX_VERSION:
                if max_age is None or (time.time() - index.get('built_at', 0)) <= max_age:
                    _MEMO['index'] = index
                    return index
        except Exception as exc:
            logger.warning('chatbot index: could not read cache: %s', exc)
    return build_and_save()


def build_and_save():
    started = time.time()
    index = build_index()
    _MEMO['index'] = index
    path = _cache_path()
    try:
        tmp = path + '.tmp'
        with open(tmp, 'wb') as handle:
            pickle.dump(index, handle, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(tmp, path)
    except Exception as exc:
        logger.warning('chatbot index: could not write cache: %s', exc)
    logger.info(
        'chatbot index built: %d chunks from %d sources in %.1fs',
        index['total_docs'], index['sources'], time.time() - started,
    )
    return index


def index_stats(index):
    return {
        'chunks': index.get('total_docs', 0),
        'sources': index.get('sources', 0),
        'terms': len(index.get('postings', {})),
        'built_at': index.get('built_at'),
    }
