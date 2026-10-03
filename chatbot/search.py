"""Query the site index and compose a grounded, extractive answer.

There is no language model here. The answer is always text that already exists
in a page or database record, so the bot cannot invent facts about the company.
"""
import logging
import math
import re

from .corpus import user_can_read
from .indexer import B, K1, load_index, loaded_index
from .text_utils import STOPWORDS, split_sentences, tokenize, trim_to_sentence

__all__ = ['answer', 'search', 'split_answer', 'load_index', 'loaded_index']

# List markers the curated answers use, so "1." and "-" are both recognised.
LIST_MARKER = re.compile(r'^(?:[-*\u2022]|\d+[.)])\s+')

logger = logging.getLogger(__name__)

# A hit must clear this score to be trusted enough to answer from.
MIN_SCORE = 1.1
STRONG_SCORE = 3.0
# A word appearing in more than this share of chunks is treated as generic and
# cannot, on its own, justify an answer.
DISTINCTIVE_DF = 0.15
# Keep the answer short; the chatbot renders one message bubble.
MAX_ANSWER_SENTENCES = 3
MAX_ANSWER_CHARS = 480
MAX_LINKS = 3
MAX_SUGGESTIONS = 4

_WORD_RE = re.compile(r"[a-z0-9][a-z0-9'+#.-]*")


def _idf(index, token):
    """Inverse document frequency, floored so no term is ever worthless."""
    total = index.get('total_docs') or 1
    docs = (index.get('postings') or {}).get(token) or {}
    df = len(docs)
    return math.log(1 + (total - df + 0.5) / (df + 0.5))


def _idf_weights(index, query_tokens):
    weights = {}
    for token in set(query_tokens):
        docs = (index.get('postings') or {}).get(token) or {}
        df_ratio = len(docs) / (index.get('total_docs') or 1)
        # Generic words ("website", "blog", "service") must not outvote rare ones
        # ("scraping", "ux") when picking the sentence that answers the question,
        # but they still need to count for something.
        weights[token] = _idf(index, token) * (0.3 if df_ratio > 0.35 else 1.0)
    return weights


def _content_words(text):
    """Question words with stopwords removed, in order, still readable."""
    words = []
    for word in _WORD_RE.findall((text or '').lower()):
        word = word.strip('.-')
        if len(word) >= 2 and word not in STOPWORDS:
            words.append(word)
    return words


def _phrase_bonus(query, text_norm, heading_norm, title_norm):
    """Reward contiguous matches of the question's meaningful words.

    Without this, "what is web 4.0?" matches any page that happens to say "web"
    twice, and the passage that actually explains Web 4.0 loses.
    """
    words = _content_words(query)
    if len(words) < 2:
        return 0.0
    whole = _normalise(' '.join(words))
    if not whole:
        return 0.0
    if whole in heading_norm:
        return 6.0
    if whole in title_norm:
        return 5.0
    if whole in text_norm:
        return 5.0
    # Count adjacent word pairs: "security testing", "ux ui", "link analyzer".
    bonus = 0.0
    for first, second in zip(words, words[1:]):
        if first in text_norm and second in text_norm:
            bonus += 0.6
    return min(bonus, 1.5)


def _bm25(index, query_tokens, weights=None):
    """Classic Okapi BM25 over the cached postings."""
    postings = index.get('postings') or {}
    doc_lengths = index.get('doc_lengths') or []
    total = index.get('total_docs') or 0
    avgdl = index.get('avgdl') or 1.0
    if not postings or not total:
        return {}

    scores = {}
    for token in set(query_tokens):
        docs = postings.get(token)
        if not docs:
            continue
        df = len(docs)
        # Ignore terms that appear in nearly everything: they carry no signal.
        if df / total > 0.65:
            continue
        idf = math.log(1 + (total - df + 0.5) / (df + 0.5))
        if weights is not None:
            idf *= weights.get(token, 1.0)
        for doc_id, freq in docs.items():
            length = doc_lengths[doc_id] if doc_id < len(doc_lengths) else avgdl
            norm = freq * (K1 + 1) / (freq + K1 * (1 - B + B * (length / avgdl)))
            scores[doc_id] = scores.get(doc_id, 0.0) + idf * norm
    return scores


def _normalise(text):
    return re.sub(r'[^a-z0-9]+', ' ', (text or '').lower()).strip()


def search(query, user=None, limit=MAX_LINKS, index=None):
    """Return the best readable chunks for ``query`` as ``(score, chunk)`` pairs."""
    index = index or load_index()
    query_tokens = tokenize(query)
    if not query_tokens:
        return [], index

    weights = _idf_weights(index, query_tokens)
    raw = _bm25(index, query_tokens, weights)
    if not raw:
        return [], index

    chunks = index['chunks']
    scored = []
    for doc_id, score in raw.items():
        chunk = chunks[doc_id]
        if not user_can_read(user, chunk.get('access', 'public')):
            continue
        text_norm = _normalise(chunk['text'])
        heading_norm = _normalise(chunk.get('heading', ''))
        title_norm = _normalise(chunk.get('title', ''))
        url_norm = _normalise(chunk.get('url', '').replace('/', ' '))

        # Contiguous matches of the question's own words beat scattered ones.
        score += _phrase_bonus(query, text_norm, heading_norm, title_norm)
        # A heading written in the same words as the question is a strong hint.
        heading_overlap = weights and sum(
            weights.get(t, 0.0) for t in set(query_tokens) & set(tokenize(chunk['heading'])))
        if heading_overlap:
            score += 0.3 * heading_overlap
        for word in _content_words(query):
            if word in url_norm:
                score += 0.75
                break
        # Slight preference for body copy over short navigational fragments.
        score *= 1.0 if len(chunk['text']) >= 120 else 0.9
        scored.append((score, chunk))

    scored.sort(key=lambda item: (-item[0], item[1]['source_id']))
    return scored[:limit], index


def _best_sentences(text, query_tokens, max_sentences=MAX_ANSWER_SENTENCES,
                    max_chars=MAX_ANSWER_CHARS, weights=None):
    """Pick the most relevant, readable sentences from a passage."""
    return _rank_sentences([(0, s) for s in split_sentences(text, min_length=25)],
                           query_tokens, max_sentences, max_chars, weights)


def _rank_sentences(candidates, query_tokens, max_sentences, max_chars, weights=None):
    """Rank ``(chunk_position, sentence)`` pairs against the question.

    Words are weighted by inverse document frequency, so a sentence mentioning
    "scraping" outranks one that merely says "web" five times.
    """
    weights = weights or {}
    query_set = set(query_tokens)
    if not query_set:
        query_set = set(query_tokens)
    total_weight = sum(weights.get(t, 1.0) for t in query_set) or 1.0
    ranked = []
    for position, sentence in candidates:
        tokens = set(tokenize(sentence))
        if not tokens:
            continue
        shared = query_set & tokens
        if not shared and position:
            continue
        weight = sum(weights.get(t, 1.0) for t in shared)
        coverage = weight / total_weight
        # Favour sentences that answer the question, and the opening sentence
        # of a passage, which usually states the topic.
        position_bonus = 0.4 if position == 0 else 0.0
        length_penalty = 0.0 if 40 <= len(sentence) <= 220 else 0.2
        ranked.append((coverage * 3 + weight * 0.1 + position_bonus - length_penalty,
                       position, sentence))
    if not ranked:
        return ''
    ranked.sort(key=lambda item: (-item[0], item[1]))

    chosen = sorted(ranked[:max_sentences], key=lambda item: item[1])
    answer = ' '.join(sentence for _, _, sentence in chosen)
    if len(answer) > max_chars:
        answer = answer[:max_chars]
    return trim_to_sentence(answer)


def _page_answer(index, source_id, query_tokens, max_sentences=MAX_ANSWER_SENTENCES,
                 max_chars=MAX_ANSWER_CHARS, weights=None):
    """Answer from the best sentences anywhere on the winning page.

    Scoring picks the right *page* far more reliably than it picks the right
    500-character *chunk*, so once a page wins we let its own text decide which
    sentences actually address the question.
    """
    candidates = []
    for position, chunk in enumerate(index['chunks']):
        if chunk['source_id'] != source_id:
            continue
        for sentence in split_sentences(chunk['text'], min_length=25):
            candidates.append((position, sentence))
    if not candidates:
        return ''
    return _rank_sentences(candidates, query_tokens, max_sentences, max_chars, weights)


def _dedupe_sources(hits):
    """One entry per page/record, ordered by the best hit for that source."""
    seen = set()
    unique = []
    for score, chunk in hits:
        key = chunk['source_id']
        if key in seen:
            continue
        seen.add(key)
        unique.append((score, chunk))
    return unique


def _suggestion_label(chunk):
    heading = (chunk.get('heading') or '').strip()
    if heading and heading.lower() != (chunk.get('title') or '').strip().lower():
        return heading
    return chunk.get('title', '')


def _matches_are_confident(index, query_tokens, score, chunk):
    """Refuse to guess when the question and the passage barely overlap.

    A question is only answerable if at least one of its *distinctive* words --
    the ones that appear in only a small fraction of the corpus -- is actually
    present. That is what stops "do you offer internships?" from happily
    quoting a paragraph about 30 days of post-launch support.
    """
    if score < MIN_SCORE:
        return False

    total = index.get('total_docs') or 1
    postings = index.get('postings') or {}
    query_set = set(query_tokens)
    if not query_set:
        return False

    chunk_tokens = set(tokenize(chunk['heading'])) | set(tokenize(chunk['text']))
    matched = distinctive = distinctive_matched = 0
    for token in query_set:
        docs = postings.get(token)
        if docs:
            matched += 1
            df_ratio = len(docs) / total
        else:
            df_ratio = 0.0
        if df_ratio <= DISTINCTIVE_DF:
            distinctive += 1
            if token in chunk_tokens:
                distinctive_matched += 1

    if distinctive and distinctive_matched == 0:
        return False
    coverage = matched / len(query_set)
    if coverage >= 0.5:
        return True
    return coverage >= 0.34 and score >= STRONG_SCORE


def _answer_is_on_topic(response, query_tokens, index):
    """The answer must actually mention one of the question's specific words.

    Ranking can pick the right *page* while `_rank_sentences` settles on an
    introductory sentence that never says the thing being asked about. This is
    the last guard against answering with generic marketing copy.
    """
    if not response:
        return False
    response_tokens = set(tokenize(response))
    total = index.get('total_docs') or 1
    postings = index.get('postings') or {}
    for token in set(query_tokens):
        docs = postings.get(token)
        df_ratio = (len(docs) / total) if docs else 0.0
        if df_ratio <= 0.3 and token in response_tokens:
            return True
    # Every question word was generic; fall back to any overlap at all.
    return bool(response_tokens & set(query_tokens))


def answer(query, user=None, index=None, max_links=MAX_LINKS):
    """Build a grounded answer for ``query`` from content the user may read.

    Returns a dict with ``response``, ``links``, ``suggestions`` and ``hits``.
    """
    index = index or load_index()
    query_tokens = tokenize(query)
    if not query_tokens:
        return _fallback(query, [], index, 'no_query')

    weights = _idf_weights(index, query_tokens)
    pool, index = search(query, user, limit=24, index=index)
    if not pool:
        return _fallback(query, [], index, 'no_hits')

    unique = _dedupe_sources(pool)
    # Try the best-ranked pages in turn until one yields an answer that is both
    # confidently matched and actually about the thing that was asked.
    chosen = chosen_response = None
    for score, chunk in unique[:4]:
        if not _matches_are_confident(index, query_tokens, score, chunk):
            continue
        response = _page_answer(index, chunk['source_id'], query_tokens, weights=weights)
        if chosen is None and response:
            chosen, chosen_response = (score, chunk), response
        if response and _answer_is_on_topic(response, query_tokens, index):
            chosen, chosen_response = (score, chunk), response
            break

    if chosen is None:
        return _fallback(query, unique, index, 'low_confidence')

    top_score, top_chunk = chosen
    response = chosen_response
    if not response:
        response = _page_answer(index, top_chunk['source_id'], query_tokens,
                                max_sentences=1, weights=weights)
    if not response:
        return _fallback(query, unique, index, 'empty_passage')

    # A second passage on a different page can complete the answer.
    if len(response) < 220:
        for score, chunk in pool[1:]:
            if chunk['source_id'] == top_chunk['source_id']:
                continue
            if score < top_score * 0.55:
                break
            extra = _best_sentences(chunk['text'], query_tokens, max_sentences=1,
                                    weights=weights)
            if extra and extra not in response:
                response = response + ' ' + extra
            if len(response) >= 220:
                break

    links = _build_links(_dedupe_sources(pool), max_links)
    suggestions = _build_suggestions(index, pool, top_chunk, links, query_tokens)
    return {
        'response': response,
        'links': links,
        'suggestions': suggestions,
        'hits': [{'title': c['title'], 'heading': c['heading'], 'url': c['url'],
                  'access': c.get('access', 'public')}
                 for _, c in _dedupe_sources(pool)[:max_links]],
        'confidence': 'high' if top_score >= STRONG_SCORE else 'medium',
    }


def _build_links(unique_hits, max_links):
    """One reference per distinct page, in descending relevance order."""
    links = []
    seen = set()
    for _, chunk in unique_hits:
        if len(links) >= max_links:
            break
        if chunk['url'] in seen:
            continue
        seen.add(chunk['url'])
        label = chunk.get('heading') or chunk.get('title') or 'this page'
        title = chunk.get('title') or label
        links.append({
            'label': label if len(label) <= 80 else title,
            'title': title,
            'url': chunk['url'],
        })
    return links


def _build_suggestions(index, pool, top_chunk, links, query_tokens):
    """Follow-up questions: other sections of the winning page, then rivals.

    Headings on the same page make the best suggestions because they are the
    other things that page explains, and the visitor can click straight to them.
    """
    suggestions = []
    seen = set()
    link_titles = {l['title'] for l in links}

    def add(label):
        label = (label or '').strip()
        if not label or len(label) < 4 or len(label) > 90:
            return False
        key = label.lower()
        if key in seen:
            return False
        seen.add(key)
        suggestions.append(label)
        return True

    # Sibling sections on the winning page.
    for chunk in index['chunks']:
        if len(suggestions) >= MAX_SUGGESTIONS:
            break
        if chunk['source_id'] != top_chunk['source_id']:
            continue
        heading = chunk.get('heading') or ''
        if not heading or heading == top_chunk.get('heading'):
            continue
        if not set(tokenize(heading)):
            continue
        add(heading)

    # Then the strongest other pages, by their title.
    for _, chunk in pool:
        if len(suggestions) >= MAX_SUGGESTIONS:
            break
        if chunk['source_id'] == top_chunk['source_id']:
            continue
        if chunk.get('title') in link_titles:
            continue
        add(chunk.get('title', ''))
    return suggestions


def split_answer(response):
    """Break a finished answer into the pieces the UI should render.

    The chat shows one bubble per answer, so a 400-character run-on paragraph is
    hard to scan in a 380px column. An answer written as a list keeps its list
    structure; anything else is split on sentence boundaries. Not one word of
    the answer changes, and reassembling the pieces reproduces the original, so
    this can never drift from ``reply``.

    Returns ``(parts, format)`` where format is ``'bullets'`` or ``'paragraphs'``.
    """
    response = (response or '').strip()
    if not response:
        return [], 'paragraphs'

    lines = [line.strip() for line in response.splitlines() if line.strip()]
    marked = [line for line in lines if LIST_MARKER.match(line)]
    # Every line marked, or a marked run of two or more after an unmarked lead.
    # A lone "- " after prose is a dash in a sentence, not a list.
    has_list = bool(marked) and (
        len(marked) == len(lines)
        or (len(marked) == len(lines) - 1 and len(marked) >= 2)
    )
    if has_list:
        head = [] if LIST_MARKER.match(lines[0]) else [lines[0]]
        return head + [LIST_MARKER.sub('', line) for line in marked], 'bullets'

    sentences = split_sentences(response, min_length=1)
    return (sentences or [response]), 'paragraphs'


def _fallback(query, unique_hits, index, reason):
    """No trustworthy passage. Offer the closest pages instead of inventing."""
    links = _build_links(unique_hits, MAX_LINKS)
    suggestions = [chunk.get('title', '') for _, chunk in unique_hits[:MAX_SUGGESTIONS]]
    if reason == 'no_query':
        response = ("Tell me what you would like to know about OnWebApp — for example "
                    "its services, pricing, automation, ERP, SEO tools, or community forums.")
    elif reason == 'no_hits':
        response = ("I could not find anything about that in the OnWebApp site. "
                    "You can explore the main areas below or ask me to describe a service.")
    else:
        response = ("I do not have a confident answer for that yet. I could not find a page "
                    "that covers it directly, so I would rather point you to something related "
                    "than guess.")
    return {
        'response': response,
        'links': links,
        'suggestions': [s for s in dict.fromkeys(suggestions) if s],
        'hits': [],
        'confidence': 'none',
        'reason': reason,
    }
