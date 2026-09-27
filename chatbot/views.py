from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.urls import reverse, NoReverseMatch
from django.utils.html import escape
import json
import re
import uuid

from .models import ChatSession, ChatMessage
from .knowledge_base import KNOWLEDGE_BASE, GENERAL_RESPONSES, PAGE_TITLES
from .corpus import access_for_url_name, user_can_read
from .text_utils import split_sentences, tokenize
from . import search as site_search

_WORD_RE = re.compile(r'[a-z0-9]+')

# Word boundaries matter here: plain substring matching made
# "do you offer internships?" start with "hi" and reply with a greeting.
GREETING_RE = re.compile(
    r'\b(hi|hello|hey|hiya|yo|greetings|good\s+(morning|afternoon|evening))\b')
THANKS_RE = re.compile(
    r'\b(thanks|thank\s+you|thankyou|thx|cheers|appreciate(\s+it)?|grateful)\b')

# The four pages the chatbot offers when it has nothing better to say.
STARTER_SUGGESTIONS = [
    {'title': 'What is OnWebApp?', 'content': 'Learn about the platform'},
    {'title': 'What services do you offer?', 'content': 'See our services'},
    {'title': 'How much does it cost?', 'content': 'Check pricing'},
    {'title': 'How does automation work?', 'content': 'Learn about RPA & BPA'},
]


def chatbot_view(request):
    return render(request, 'chatbot/chatbot.html')


def _resolve(url_name):
    """Turn a URL name like 'home:about' into a real path, or None."""
    if not url_name:
        return None
    try:
        return reverse(url_name)
    except NoReverseMatch:
        return None


def _page_is_live(path):
    """True unless the index knows this path is broken.

    Several routes in this project still point at templates that do not exist,
    so they resolve but return HTTP 500. The index records which pages actually
    rendered, and the bot must never send a visitor to one of the broken ones.
    """
    try:
        known = site_search.loaded_index().get('live_paths')
    except Exception:
        return True
    if not known:
        return True
    return path in known


def _page_links(page_key, section=None, extra_url_names=(), user=None):
    """Build the list of clickable page links returned alongside an answer."""
    links = []
    seen = set()

    def add(url_name):
        path = _resolve(url_name)
        if not path or path in seen or not _page_is_live(path):
            return
        if not user_can_read(user, access_for_url_name(url_name)):
            return
        seen.add(path)
        title = next(
            (page['title'] for page in KNOWLEDGE_BASE.values() if page.get('url') == url_name),
            PAGE_TITLES.get(url_name, url_name.split(':')[-1].replace('_', ' ').title())
        )
        links.append({'title': title, 'url': path})

    page = KNOWLEDGE_BASE.get(page_key or '', {})
    add(page.get('url'))
    if section:
        add(section.get('url'))
    for url_name in extra_url_names:
        add(url_name)

    return links


def _retrieval_links(links):
    """Shape index hits into the link objects the front end expects."""
    out = []
    seen = set()
    for link in links or []:
        path = link.get('url')
        if not path or path in seen or not _page_is_live(path):
            continue
        seen.add(path)
        out.append({'title': link.get('title') or link.get('label') or 'this page',
                    'url': path})
    return out


def _chips(labels, content=None):
    return [{'title': label, 'content': content or label} for label in labels if label]


def _resolve_suggestions(suggestions):
    """Swap URL names in follow-up chips for real paths, dropping any that fail."""
    resolved = []
    for suggestion in suggestions:
        item = dict(suggestion)
        if 'url' in item:
            path = _resolve(item['url'])
            if path and _page_is_live(path):
                item['url'] = path
            else:
                item.pop('url')
        resolved.append(item)
    return resolved


@csrf_exempt
def get_suggestions(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        data = json.loads(request.body)
        user_message_text = escape(data.get('message', '').strip())
        session_id = data.get('session_id')

        if not session_id:
            session_id = str(uuid.uuid4())
        session, _ = ChatSession.objects.get_or_create(session_id=session_id)
        if request.user.is_authenticated and not session.user:
            session.user = request.user
            session.save()

        ChatMessage.objects.create(
            session=session, sender='USER', content=user_message_text
        )

        reply, suggestions, links = generate_response(
            user_message_text, session, request.user
        )

        ChatMessage.objects.create(
            session=session, sender='BOT', content=reply
        )

        return JsonResponse({
            'reply': reply,
            'suggestions': suggestions,
            'links': links,
            'session_id': session.session_id
        })

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        print(f"[!] Chatbot Error: {e}")
        return JsonResponse({'error': 'Something went wrong.'}, status=500)


# ── Navbar site search ──────────────────────────────────────────────────────
# Backed by the same index the chatbot answers from, so the search box needs no
# crawling of its own and results are filtered to what the visitor may read.

SEARCH_MIN_CHARS = 2
SEARCH_DROPDOWN_LIMIT = 8
SEARCH_PAGE_LIMIT = 25
SEARCH_HIT_LIMIT = 60


def _search_snippet(text, query, max_chars=150):
    """A short excerpt, preferring the sentence that matches the query best."""
    terms = set(tokenize(query))
    best, best_score = '', -1
    for sentence in split_sentences(text):
        overlap = len(terms & set(tokenize(sentence)))
        if overlap > best_score:
            best, best_score = sentence, overlap
    snippet = ' '.join((best or text).split())
    if len(snippet) > max_chars:
        snippet = snippet[:max_chars].rsplit(' ', 1)[0] + '…'
    return snippet


def _search_results(query, user, limit=SEARCH_DROPDOWN_LIMIT):
    """Best matching pages for ``query``, best first and one entry per page."""
    hits, _index = site_search.search(query, user=user, limit=SEARCH_HIT_LIMIT)
    results, seen = [], set()
    for score, chunk in hits:
        if score <= 0:
            break
        url = chunk.get('url', '')
        if not url or url in seen or not _page_is_live(url):
            continue
        seen.add(url)
        results.append({
            'title': chunk.get('title') or url,
            'url': url,
            'heading': chunk.get('heading', ''),
            'snippet': _search_snippet(chunk.get('text', ''), query),
        })
        if len(results) >= limit:
            break
    return results


def site_search_api(request):
    """Typeahead endpoint behind the navbar search box."""
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    query = (request.GET.get('q') or '').strip()
    if len(query) < SEARCH_MIN_CHARS:
        return JsonResponse({'query': query, 'results': []})
    return JsonResponse({
        'query': query,
        'results': _search_results(query, request.user),
    })


def search_page(request):
    """Full results page, for 'view all results' in the dropdown."""
    query = (request.GET.get('q') or '').strip()
    results = []
    if len(query) >= SEARCH_MIN_CHARS:
        results = _search_results(query, request.user, limit=SEARCH_PAGE_LIMIT)
    return render(request, 'chatbot/search.html', {
        'query': query,
        'results': results,
        'results_length': len(results),
    })


def search_knowledge_base(message):
    message_lower = message.lower()
    best_match = None
    best_key = None
    best_score = 0

    for page_key, page_data in KNOWLEDGE_BASE.items():
        for section in page_data['sections']:
            score = 0
            for keyword in section['topic']:
                if keyword in message_lower:
                    score += len(keyword)
            if score > best_score:
                best_score = score
                best_match = section
                best_key = page_key

    return best_key, best_match


def _curated_match(message):
    """Find a curated answer, but only on whole specific words.

    Substring matching made this bot answer "do you offer internships?" with the
    post-launch support paragraph, because "offer" appears inside "support".
    Requiring whole words of at least five characters keeps the hand-written
    answers for the questions they were written for.
    """
    lowered = message.lower()
    words = set(_WORD_RE.findall(lowered))
    best = (None, None, 0)
    for page_key, page_data in KNOWLEDGE_BASE.items():
        for section in page_data['sections']:
            strength = 0
            for keyword in section['topic']:
                keyword = keyword.lower()
                if len(keyword) < 5:
                    continue
                if ' ' in keyword:
                    if keyword in lowered:
                        strength += 2
                elif keyword in words:
                    strength += 1
            if strength > best[2]:
                best = (page_key, section, strength)
    return best


def _order_reply(message_lower, session, user):
    """Order and production tracking, which needs a login or an order number."""
    if not any(w in message_lower for w in ['order', 'production', 'progress']):
        return None
    if not (user and getattr(user, 'is_authenticated', False)) and not session.user_id:
        return (
            "Please log in to your account to check order and production status.",
            _resolve_suggestions([{'title': 'Contact Support', 'content': 'Talk to our team',
                                    'url': 'contact:contact'}]),
            _page_links('contact', user=user),
        )
    match_id = re.search(r'#?(\d+)', message_lower)
    if not match_id:
        return (
            "Please provide an Order ID (for example, 'progress for #123') so I can look it up.",
            [],
            [],
        )
    return (
        f"I couldn't reach the ERP adapter for order #{match_id.group(1)}. "
        "Our team can pull the live status for you.",
        _resolve_suggestions([{'title': 'Contact Support', 'content': 'Request order status',
                                'url': 'contact:contact'}]),
        _page_links('contact', extra_url_names=('home:erp_service',), user=user),
    )


def generate_response(message, session, user=None):
    """Answer any question about the site.

    Order of preference: small talk, then a hand-written answer when the visitor
    used the exact wording it was written for, then the site-wide index. The
    index is what lets the bot talk about any page, not just the curated set.
    """
    message_lower = message.lower()
    user = user or getattr(session, 'user', None)

    # ── Greetings ──
    # Only when the message actually opens with one, or is very short: "hi-tech"
    # and "hi" inside another word are not greetings.
    if GREETING_RE.match(message_lower) or (
            len(_WORD_RE.findall(message_lower)) <= 2 and GREETING_RE.search(message_lower)):
        return (
            GENERAL_RESPONSES['greeting'],
            _resolve_suggestions(STARTER_SUGGESTIONS),
            _page_links('home', extra_url_names=('services:index', 'payments:plans',
                                                 'home:rpa_bpa'), user=user),
        )

    # ── Thanks ──
    if THANKS_RE.search(message_lower):
        return (
            GENERAL_RESPONSES['thanks'],
            [
                {'title': 'Services', 'content': 'What else we offer', 'url': 'services:index'},
                {'title': 'Pricing', 'content': 'Check our plans', 'url': 'payments:plans'},
            ],
            [],
        )

    # ── Explicit "show me the page / where is this" ──
    if any(w in message_lower for w in ['where can i', 'show me', 'link to', 'page for',
                                        'go to', 'read more', 'find more']):
        page_key, match = search_knowledge_base(message)
        if match:
            links = _page_links(page_key, match, extra_url_names=('contact:contact',),
                                user=user)
            if links:
                titles = ', '.join(l['title'] for l in links)
                return (
                    f"{GENERAL_RESPONSES['link_help']} {titles}.",
                    [{'title': 'Ask something else', 'content': 'What else can I help with?'}],
                    links,
                )

    # ── A curated answer the visitor clearly asked for ──
    page_key, match, strength = _curated_match(message)
    if match and strength >= 1:
        follow_ups = _resolve_suggestions(_get_follow_ups(message_lower))
        return match['answer'], follow_ups, _page_links(page_key, match, user=user)

    # ── Order / production tracking ──
    order = _order_reply(message_lower, session, user)
    if order:
        return order

    # ── Anything else: search the whole site ──
    result = site_search.answer(message, user=user)
    links = _retrieval_links(result['links'])
    if result['confidence'] != 'none':
        suggestions = _chips(result['suggestions'])
        if not suggestions:
            suggestions = _resolve_suggestions(_get_follow_ups(message_lower))
        return result['response'], suggestions, links

    # ── Nothing confident in the index; fall back to a curated answer ──
    if match:
        return (match['answer'],
                _resolve_suggestions(_get_follow_ups(message_lower)),
                _page_links(page_key, match, user=user))

    return (
        result['response'],
        _resolve_suggestions(STARTER_SUGGESTIONS),
        links or _page_links('home', extra_url_names=('home:automation_home',
                                                      'services:index', 'contact:contact'),
                             user=user),
    )


def _get_follow_ups(message_lower):
    follow_ups = []

    if any(w in message_lower for w in ['rpa', 'robotic', 'automate', 'automation']):
        follow_ups = [
            {'title': 'What is BPA?', 'content': 'Learn about Business Process Automation', 'url': 'home:rpa_bpa'},
            {'title': 'Intelligent Automation', 'content': 'AI-powered automation', 'url': 'home:rpa_bpa'},
            {'title': 'Website Automation', 'content': 'Browser, UI and service automation', 'url': 'home:automation_home'},
        ]
    elif any(w in message_lower for w in ['bpa', 'business process']):
        follow_ups = [
            {'title': 'What is RPA?', 'content': 'Learn about Robotic Process Automation', 'url': 'home:rpa_bpa'},
            {'title': 'Workflow Builder', 'content': 'Build your own workflows', 'url': 'home:rpa_bpa'},
            {'title': 'Benefits', 'content': 'Why automate?'},
        ]
    elif any(w in message_lower for w in ['web development', 'website', 'web app']):
        follow_ups = [
            {'title': 'ERP Integration', 'content': 'Connect enterprise systems', 'url': 'home:erp_service'},
            {'title': 'Our Process', 'content': 'How we work', 'url': 'home:about'},
            {'title': 'Tech Stack', 'content': 'React, Django, Node.js', 'url': 'home:web_development'},
        ]
    elif any(w in message_lower for w in ['pricing', 'cost', 'plan', 'price']):
        follow_ups = [
            {'title': 'See Our Plans', 'content': 'Basic, Pro and Enterprise', 'url': 'payments:plans'},
            {'title': 'Our Services', 'content': 'What you get', 'url': 'services:index'},
        ]
    elif any(w in message_lower for w in ['integration', 'connect', 'api']):
        follow_ups = [
            {'title': '50+ Connectors', 'content': 'Shopify, Stripe, Salesforce', 'url': 'integration:integration_homepage'},
            {'title': 'ERP Sync', 'content': 'ERPNext, SAP, Odoo', 'url': 'home:erp_service'},
            {'title': 'IoT Integration', 'content': 'Connect devices', 'url': 'services:iot_integration'},
        ]
    elif any(w in message_lower for w in ['ai', 'artificial intelligence', 'predictive']):
        follow_ups = [
            {'title': 'Content Generation', 'content': 'AI-powered content'},
            {'title': 'Predictive Insights', 'content': 'Behavior prediction'},
            {'title': 'AI Workflows', 'content': 'Intelligent automation', 'url': 'home:rpa_bpa'},
        ]
    elif any(w in message_lower for w in ['monitoring', 'uptime', 'alerts']):
        follow_ups = [
            {'title': 'Platform Monitoring', 'content': 'Uptime and performance', 'url': 'platform_monitoring:hub'},
            {'title': 'Task Scheduler', 'content': 'Run tasks on schedule', 'url': 'platform_monitoring:task_scheduler'},
        ]
    else:
        follow_ups = [
            {'title': 'Services', 'content': 'What we offer', 'url': 'services:index'},
            {'title': 'Pricing', 'content': 'Check our plans', 'url': 'payments:plans'},
            {'title': 'Contact', 'content': 'Talk to our team', 'url': 'contact:contact'},
        ]

    return follow_ups
