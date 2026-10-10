from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.urls import reverse, NoReverseMatch
from django.utils.html import escape
from django.conf import settings
from urllib.parse import quote
import json
import re
import uuid

from .models import CallRequest, ChatLead, ChatMessage, ChatSession
from .knowledge_base import KNOWLEDGE_BASE, GENERAL_RESPONSES, PAGE_TITLES
from .corpus import access_for_url_name, user_can_read
from .intents import INTENTS
from .text_utils import split_sentences, tokenize
from . import conversation
from . import page_context
from . import search as site_search
from django.utils import timezone

_WORD_RE = re.compile(r'[a-z0-9]+')

# Word boundaries matter here: plain substring matching made
# "do you offer internships?" start with "hi" and reply with a greeting.
GREETING_RE = re.compile(
    r'\b(hi|hello|hey|hiya|yo|greetings|good\s+(morning|afternoon|evening))\b')
THANKS_RE = re.compile(
    r'\b(thanks|thank\s+you|thankyou|thx|cheers|appreciate(\s+it)?|grateful)\b')

# Asking for a person. Kept deliberately narrow: every alternative here is a
# phrase that only makes sense when the visitor wants to stop reading and talk
# to someone. "talk about pricing" and "call the API" must not match.
HUMAN_RE = re.compile(
    r'\b(?:talk|speak|chat)\s+(?:to|with)\s+(?:a\s+|an\s+|the\s+|my\s+)?'
    r'(?:human|person|people|agent|representative|rep|specialist|advisor|consultant|'
    r'expert|someone|somebody|real\s+(?:human|person|agent)|actual\s+(?:human|person))\b'
    r'|\b(?:call|ring|phone|dial)\s+(?:me\s+back|back|us\s+back|me\s+now|us\s+now|'
    r'me|us|the\s+team|someone)\b'
    r'|\b(?:human|live|real|actual)\s+(?:agent|person|human|representative|help)\b'
    r'|\b(?:call\s*cent(?:er|re)|call\s+desk|(?:support|sales|hot)\s+'
    r'(?:line|desk|number))\b'
    r'|\bcontact\s+(?:the\s+)?(?:support|sales|service)\s+team\b'
    r'|\bconnect\s+me\s+(?:to|with)\s+(?:the\s+|a\s+)?'
    r'(?:support|team|sales|agent|human|person|someone|advisor)\b'
    # "need a manager" escalates, "need a manager dashboard" is a product
    # question, so the word has to end there.
    r'|\b(?:want|need|like)\s+(?:to\s+)?(?:a\s+|the\s+|my\s+)?'
    r'(?:manager|supervisor)(?!\s+\w)'
    r'|\b(?:talk|speak|complain|escalate)\s+(?:to|with)?\s*(?:a\s+|the\s+|my\s+)?'
    r'(?:manager|supervisor|boss)\b'
    r'|\bescalat(?:e|ed|es|ing|ion)\b'
    r'|\brequest\s+(?:a\s+)?(?:call\s*back|callback)\b'
    r'|\btransfer\s+me\b')

# "Tell me more", pricing, quotes and demos. These read like site questions but
# are really about the visitor's own project, so a page link is not the end of
# the answer: a person should be one click away from here. Kept to phrases that
# only make sense for a project enquiry, so "explain how the RPA engine works"
# (a documentation question the index answers well) is not dragged into it.
DETAILS_RE = re.compile(
    r'\b(?:more|extra|further|additional)\s+'
    r'(?:details?|information|info|context|background)\b'
    r'|\b(?:tell|show|give|explain|elaborate)\s+(?:us\s+|me\s+)?more\b'
    r'|\b(?:details?|information|info)\s+(?:about|on|for|regarding)\b'
    r'|\b(?:how\s+much|what\s+(?:does|will|would)\s+it\s+cost)\b'
    r'|\b(?:pricing|prices?|costs?|quotes?|quotations?|estimates?|proposals?)\b'
    r'|\b(?:demos?|demonstrations?|free\s+trials?|trials?)\b'
    r'|\bbook\s+a\s+(?:call|consultation|meeting|demo)\b'
    r'|\bget\s+(?:started|going)\b'
    r'|\bi\s*(?:\'m|am)\s+interested\b')

# The four pages the chatbot offers when it has nothing better to say.
STARTER_SUGGESTIONS = [
    {'title': 'What is OnWebApp?', 'content': 'Learn about the platform'},
    {'title': 'What services do you offer?', 'content': 'See our services'},
    {'title': 'How much does it cost?', 'content': 'Check pricing'},
    {'title': 'How does automation work?', 'content': 'Learn about RPA & BPA'},
]

# Always offered alongside a handoff so the visitor is never stuck on "no".
HUMAN_SUGGESTION = {
    'title': 'Still stuck? Talk to a person',
    'content': 'Connect me with the team',
}

CALL_CENTER_WHATSAPP_TEXT = (
    'Hi, I was using the OnWebApp site guide and would like to speak to someone.'
)

# Sentences to splice into the escalation reply. Lowercasing the button label
# does not produce English ("call us now is the quickest way"), so each channel
# carries its own phrasing.
_CHANNEL_PHRASES = {
    'call': 'call us',
    'chat': 'message us on WhatsApp',
    'form': 'send us a message',
}


def _join_phrases(phrases):
    if len(phrases) == 1:
        return phrases[0]
    if len(phrases) == 2:
        return f'{phrases[0]} or {phrases[1]}'
    return ', '.join(phrases[:-1]) + f', or {phrases[-1]}'


def wants_human(message):
    """True when the visitor is asking for a person, not for an answer.

    Single source of truth for the escalation decision: the reply builder and
    the queue writer both call this, so a request can never answer with a page
    link while also never reaching an agent.
    """
    lowered = (message or '').lower()
    if not HUMAN_RE.search(lowered):
        return False
    # "hello, call me" still escalates: only a message that is nothing but a
    # greeting is not asking for a person.
    return not GREETING_RE.fullmatch(lowered.strip(' \t\n\r.!,'))


def should_offer_human(message):
    """True when this turn should offer the visitor a way to reach a person.

    Three cases only, and each of them is a question a bot should not be left
    to answer alone:

    * they asked for a person, or mentioned the call centre directly;
    * they asked for details, pricing, a quote or a demo;
    * the bot could not answer, which is handled where the fallback happens.

    Everything else gets no button at all. A "Call" button under every single
    answer is read as part of the furniture and then ignored exactly when it
    matters.
    """
    lowered = (message or '').lower()
    return wants_human(lowered) or bool(DETAILS_RE.search(lowered))


def _call_center():
    """Normalised call centre config, with every field a plain string."""
    cfg = getattr(settings, 'CALL_CENTER', None) or {}
    return {
        'enabled': bool(cfg.get('ENABLED', True)),
        'phone': (cfg.get('PHONE') or '').strip(),
        'phone_display': (cfg.get('PHONE_DISPLAY') or cfg.get('PHONE') or '').strip(),
        'whatsapp': (cfg.get('WHATSAPP') or '').strip(),
        'email': (cfg.get('EMAIL') or '').strip(),
        'hours': (cfg.get('HOURS') or '').strip(),
    }


def _call_center_actions():
    """Clickable channels for reaching a person, skipping unconfigured ones.

    Returns nothing at all when the feature is switched off or no channel is
    usable, so the caller can fall back to a plain "get in touch" answer
    instead of rendering a row of dead buttons.
    """
    cfg = _call_center()
    if not cfg['enabled']:
        return []

    actions = []

    phone_digits = re.sub(r'[^\d+]', '', cfg['phone'])
    if phone_digits:
        actions.append({
            'label': 'Call us now',
            'detail': cfg['phone_display'],
            'url': 'tel:' + phone_digits,
            'icon': 'fas fa-phone',
            'kind': 'call',
        })

    whatsapp_digits = re.sub(r'[^\d]', '', cfg['whatsapp'])
    if whatsapp_digits:
        actions.append({
            'label': 'WhatsApp us',
            'detail': cfg['whatsapp'],
            'url': f'https://wa.me/{whatsapp_digits}'
                   f'?text={quote(CALL_CENTER_WHATSAPP_TEXT)}',
            'icon': 'fab fa-whatsapp',
            'kind': 'chat',
        })

    contact_path = _resolve('contact:contact')
    if contact_path and _page_is_live(contact_path):
        actions.append({
            'label': 'Send a message',
            'detail': cfg['email'] or None,
            'url': contact_path + '?from=chat',
            'icon': 'fas fa-envelope',
            'kind': 'form',
        })

    return actions


def _contact_fallback_links(user=None):
    """Contact page links for an escalation, even if the search index is stale.

    _page_links drops any path the crawl index has not marked live. That is the
    right call when recommending a page, but wrong here: an escalation with no
    link and no buttons is exactly the dead end this feature exists to prevent.
    """
    links = _page_links('contact', user=user)
    if links:
        return links

    path = _resolve('contact:contact')
    if path and user_can_read(user, access_for_url_name('contact:contact')):
        return [{'title': PAGE_TITLES.get('contact:contact', 'Contact Us'), 'url': path}]
    return []


def _handoff_reply(user=None):
    """Escalation copy. Says what is actually available, never a dead end."""
    cfg = _call_center()
    actions = _call_center_actions()

    if not actions:
        # (reply, suggestions, links, actions)
        return (
            "I can pass this to the team. Use the Contact page and someone will "
            "get back to you as soon as possible.",
            [],
            _contact_fallback_links(user=user),
            [],
        )

    if len(actions) == 1:
        lead = f"Of course - {_CHANNEL_PHRASES.get(actions[0]['kind'], 'get in touch')} is the quickest way to reach us."
    else:
        phrases = [_CHANNEL_PHRASES.get(a['kind'], 'get in touch') for a in actions]
        lead = f"Of course - you can {_join_phrases(phrases)}."

    hours = f" Our team is available {cfg['hours']}." if cfg['hours'] else ''

    return (
        f"{lead} I'll pass on the context of this chat so you don't have to "
        f"repeat yourself.{hours}",
        [],
        [],
        actions,
    )


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

    Lives in :mod:`chatbot.search` now so the page-context layer can ask the
    same question without importing this module; kept as a alias here because
    the reply builder calls it in a dozen places.
    """
    return site_search.page_is_live(path)


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


def _open_call_request(request, session, message, channels):
    """Put an explicit request for a person into the call centre queue.

    One ticket per chat session. Asking again after it was resolved reopens the
    same ticket rather than piling up duplicates, and the original escalation
    time is kept so the queue still shows how long this visitor has been waiting.
    """
    user = request.user if getattr(request, 'user', None) and request.user.is_authenticated else None
    reason = ' '.join(message.split())[:200]
    # `channels` is a list of clickable actions; the ticket only remembers which
    # kind of channel the visitor picked first, not the button payload.
    channel = channels[0]['kind'] if channels else ''

    ticket, created = CallRequest.objects.get_or_create(
        session=session,
        defaults={
            'requested_by': user,
            'reason': reason,
            'channel': channel,
            'escalated_at': timezone.now(),
        },
    )

    if not created:
        changed = []
        if ticket.status == CallRequest.STATUS_RESOLVED:
            ticket.status = CallRequest.STATUS_NEW
            ticket.resolved_at = None
            ticket.assigned_to = None
            ticket.assigned_at = None
            changed += ['status', 'resolved_at', 'assigned_to', 'assigned_at']
        # A repeat request is new information: refresh the reason and re-stamp
        # the wait so a reopened ticket sorts to the top of the queue.
        ticket.reason = reason
        ticket.channel = channel or ticket.channel
        if user and not ticket.requested_by_id:
            ticket.requested_by = user
            changed.append('requested_by')
        changed += ['reason', 'channel']
        ticket.save(update_fields=changed + ['updated_at'])

    return ticket


def _call_request_payload(ticket):
    """What the visitor's widget is allowed to know about their own ticket."""
    if not ticket:
        return {'escalated': False, 'status': None, 'waiting': None}
    return {
        'escalated': True,
        'status': ticket.status,
        'waiting': ticket.waiting_label,
    }


@csrf_exempt
def session_status(request):
    """Let a waiting visitor receive the agent's replies.

    Identified by session_id, the same opaque token the widget already sends and
    stores, and it only ever returns messages for that one session. The
    transcript itself is not exposed; an agent can post into the conversation,
    and the visitor sees those messages appear.
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    session_id = (request.GET.get('session_id') or '').strip()
    if not session_id or len(session_id) > 100:
        return JsonResponse({'error': 'Missing session'}, status=400)

    try:
        since = float(request.GET.get('since') or 0)
    except (TypeError, ValueError):
        since = 0

    session = ChatSession.objects.filter(session_id=session_id).first()
    if not session:
        return JsonResponse({'messages': [], 'status': None, 'escalated': False})

    ticket = CallRequest.objects.filter(session=session).first()
    if not ticket:
        return JsonResponse({'messages': [], 'status': None, 'escalated': False})

    agent_messages = []
    for message in session.messages.filter(sender=ChatMessage.SENDER_AGENT):
        if message.timestamp.timestamp() > since:
            agent_messages.append({
                'id': message.pk,
                'sender': 'AGENT',
                'content': message.content,
                'timestamp': message.timestamp.isoformat(),
                'agent': message.agent_label(),
            })

    return JsonResponse({
        'messages': agent_messages,
        'now': timezone.now().isoformat(),
        **_call_request_payload(ticket),
    })


@csrf_exempt
def get_suggestions(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        data = json.loads(request.body)
        # The engine reads the visitor's own words: apostrophes are characters,
        # not entities, and ``i'm interested`` must still be recognised. Only
        # the copy stored in the transcript is escaped.
        raw_message = (data.get('message') or '').strip()
        user_message_text = escape(raw_message)
        session_id = data.get('session_id')

        if not session_id:
            session_id = str(uuid.uuid4())
        session, _ = ChatSession.objects.get_or_create(session_id=session_id)
        if request.user.is_authenticated and not session.user:
            session.user = request.user
            session.save()

        # Where the visitor is reading from. The guide's answer, its
        # suggestions and the questions it asks all depend on it.
        conversation.remember_page(session, data.get('page'))

        ChatMessage.objects.create(
            session=session, sender='USER', content=user_message_text
        )

        handoff = []
        flags = {}

        reply, suggestions, links = generate_response(
            raw_message, session, request.user, actions=handoff, flags=flags
        )

        # After a detour the pending qualification question rides along with
        # whatever answer the visitor did get, so the flow never stalls. When
        # the turn carries its own structured payload the front end renders the
        # question itself instead.
        pending = flags.get('pending_question')
        if pending and not flags.get('structured'):
            reply = f"{reply.rstrip()} {pending}"

        ChatMessage.objects.create(
            session=session, sender='BOT', content=reply
        )
        # Conversation state only ever lives on the session: page, stage,
        # answers. Nothing here is sent back to the visitor.
        session.save()

        # The same answer, cut into renderable pieces so the bubble can show
        # paragraphs or a list instead of one dense block of text.
        reply_parts, reply_format = site_search.split_answer(reply)

        # The way to reach a person is offered only on the turns that need one:
        # they asked for a person or for details, or the bot could not answer.
        # ENABLED switches off the channels, not the queue, so a switched-off
        # call centre must not put a "Call" button on the page either.
        offer_call = bool(flags.get('offer_call')) and _call_center()['enabled']

        # Handoff buttons ride along with the answer so a reply that says "let me
        # get you someone" is never a promise without a button behind it.
        if offer_call and not handoff:
            handoff = _call_center_actions()

        # Only an explicit "get me a person" opens a ticket. The bot's
        # low-confidence fallback also offers a person, and that must not fill
        # the call centre with every unanswered question. The same raw text the
        # reply was built from decides, so the two can never disagree.
        ticket = None
        if wants_human(raw_message):
            ticket = _open_call_request(request, session, raw_message, handoff)

        return JsonResponse({
            'reply': reply,
            'reply_parts': reply_parts,
            'reply_format': reply_format,
            'suggestions': suggestions,
            'links': links,
            'actions': handoff,
            'offer_call': offer_call,
            'call': _call_request_payload(ticket),
            # Everything beyond the words: intent, stage, recommendations and
            # the summary block. None on turns the conversation engine let the
            # normal answer pipeline handle.
            'structured': flags.get('structured'),
            'session_id': session.session_id
        })

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        print(f"[!] Chatbot Error: {e}")
        return JsonResponse({'error': 'Something went wrong.'}, status=500)


def _json_body(request):
    """The decoded request body, or None when it is not valid JSON."""
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return None
    return body if isinstance(body, dict) else None


def _authenticated_user(request):
    user = getattr(request, 'user', None)
    return user if user and user.is_authenticated else None


@csrf_exempt
def page_context_view(request):
    """What the guide should say on the page it is embedded in.

    The widget calls this on load with the path it is sitting on and gets back
    a welcome line, the page's own second sentence, the questions worth
    suggesting there and any call to action
    the page carries — every URL resolved against the real URL table and
    filtered for the visitor's access level and the index's live pages. When a
    session id travels with it the page is remembered, so the very first
    message already knows where the visitor is reading from.
    """
    if request.method == 'GET':
        path = request.GET.get('path') or ''
        session_id = request.GET.get('session_id') or ''
    elif request.method == 'POST':
        body = _json_body(request)
        if body is None:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        path = body.get('path') or ''
        session_id = body.get('session_id') or ''
    else:
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    context = page_context.resolve_context(path, user=_authenticated_user(request))

    session_id = str(session_id).strip()[:100]
    if session_id:
        session = ChatSession.objects.filter(session_id=session_id).first()
        if session:
            conversation.remember_page(
                session, {'path': context.get('path'), 'title': context.get('title')})
            session.save(update_fields=['state', 'updated_at'])

    return JsonResponse(context)


@csrf_exempt
def request_lead(request):
    """The visitor confirmed: hand this conversation to the team as a lead.

    Everything in the summary comes from answers they actually gave — the
    transcript is stored as-is on the session, and the row is written once per
    session so a double click updates it instead of queueing duplicates. The
    same handover also opens a form ticket, which is how the queue learns there
    is a person waiting behind it.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    body = _json_body(request)
    if body is None:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    session_id = str(body.get('session_id') or '').strip()[:100]
    session = ChatSession.objects.filter(session_id=session_id).first() \
        if session_id else None
    if not session:
        return JsonResponse({'error': 'Unknown session'}, status=400)

    state = conversation.load_state(session)
    intent = state.get('intent') or ''
    if intent not in INTENTS:
        # Nothing has been said yet, so there is no summary to hand over and
        # nothing to qualify a call about.
        return JsonResponse(
            {'error': 'There is not enough in this chat to hand over yet.'},
            status=400)

    fields = conversation.lead_fields(state)
    summary = conversation.team_summary(state)

    lead, created = ChatLead.objects.get_or_create(
        session=session,
        defaults={'intent': fields['intent'], 'solution': fields['solution'],
                  'contact': fields['contact'], 'summary': summary,
                  'data': fields['data']},
    )
    changed = []
    for name in ('intent', 'solution', 'contact'):
        if getattr(lead, name) != fields[name]:
            setattr(lead, name, fields[name])
            changed.append(name)
    if lead.summary != summary:
        lead.summary = summary
        changed.append('summary')
    if lead.data != fields['data']:
        lead.data = fields['data']
        changed.append('data')
    if changed:
        lead.save(update_fields=changed + ['updated_at'])

    state['stage'] = 'ready'
    state['lead_submitted'] = True
    session.state = state
    session.save()

    reply = (
        "Thank you - your request is with the team. I have passed on this "
        "conversation along with the summary above, so there is no need to "
        "repeat anything. Someone will get back to you."
    )

    # The press and its confirmation are written once, on the first submission:
    # a double click must not leave the agent reading the confirmation twice.
    if created:
        label = str(body.get('label') or '').strip()[:200]
        if not label:
            label = 'Request a consultation'
        # The button press is the visitor's own line, so it belongs in the
        # transcript the agent reads - they will see what was asked for.
        ChatMessage.objects.create(
            session=session, sender='USER', content=escape(label))
        ChatMessage.objects.create(session=session, sender='BOT', content=reply)

    ticket = _open_call_request(
        request, session,
        f"Consultation requested - {lead.solution or lead.intent}",
        [{'kind': 'form'}],
    )

    reply_parts, reply_format = site_search.split_answer(reply)
    return JsonResponse({
        'reply': reply,
        'reply_parts': reply_parts,
        'reply_format': reply_format,
        'summary': conversation.lead_summary(state),
        'lead': {
            'intent': lead.intent,
            'solution': lead.solution,
            'summary': lead.summary,
            'status': lead.status,
            'created': created,
        },
        'call': _call_request_payload(ticket),
        'session_id': session.session_id,
    })


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


def _order_reply(message_lower, session, user, flags=None):
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
    # The bot cannot reach the ERP adapter itself, so this is one of the turns
    # where the visitor needs a person rather than a better answer.
    if flags is not None:
        flags['offer_call'] = True
    return (
        f"I couldn't reach the ERP adapter for order #{match_id.group(1)}. "
        "Our team can pull the live status for you.",
        _resolve_suggestions([{'title': 'Contact Support', 'content': 'Request order status',
                                'url': 'contact:contact'}]),
        _page_links('contact', extra_url_names=('home:erp_service',), user=user),
    )


def generate_response(message, session, user=None, actions=None, flags=None):
    """Answer any question about the site.

    Order of preference: small talk, then the conversation engine — which
    turns a stated requirement into a recommendation, a qualification and a
    summary the visitor can hand over — then a hand-written answer when the
    visitor used the exact wording it was written for, then the site-wide
    index. The index is what lets the bot talk about any page, not just the
    curated set.

    ``message`` is the visitor's raw text; escaping belongs to the transcript,
    not to the reasoning. ``actions`` is an optional list that collects the
    live-agent buttons for this turn. It is filled in place rather than
    returned, so the three-tuple result that callers and tests already unpack
    stays unchanged. ``flags`` is filled in the same way and carries
    ``offer_call`` (whether this turn should show a way to reach a person),
    ``structured`` (the conversation layer's payload) and ``pending_question``
    (an unanswered qualification question worth re-offering).
    """
    message_lower = message.lower()
    user = user or getattr(session, 'user', None)

    if should_offer_human(message) and flags is not None:
        flags['offer_call'] = True

    # ── Asking for a person ──
    # Checked before everything else so "I want to talk to someone about pricing"
    # reaches a human instead of an answer about pricing.
    if wants_human(message_lower):
        reply, suggestions, links, handoff = _handoff_reply(user=user)
        if actions is not None:
            actions.extend(handoff)
        return reply, suggestions, links

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

    # ── Understand, recommend, qualify, convert ──
    # The guide's own flow: a stated requirement or an explicit ask turns the
    # answer into a recommendation and then one useful question at a time. It
    # sits after the small talk and page-link turns so those keep their exact
    # behaviour, and before the curated answers so a real project brief is
    # qualified rather than answered with a paragraph. Returning None means
    # "not my turn" and the pipeline below runs unchanged.
    turn = conversation.handle_turn(message, session, user=user, flags=flags)
    if turn is not None:
        return turn

    # ── A curated answer the visitor clearly asked for ──
    page_key, match, strength = _curated_match(message)
    if match and strength >= 1:
        follow_ups = _resolve_suggestions(_get_follow_ups(message_lower))
        return match['answer'], follow_ups, _page_links(page_key, match, user=user)

    # ── Order / production tracking ──
    order = _order_reply(message_lower, session, user, flags=flags)
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
        if flags is not None:
            flags['offer_call'] = True
        return (match['answer'],
                _resolve_suggestions(_get_follow_ups(message_lower) + [HUMAN_SUGGESTION]),
                _page_links(page_key, match, user=user))

    # Last resort: say it does not know, but never leave the visitor without a
    # way to reach a person. This is where "the bot was useless" moments land,
    # so the button is offered whether or not they asked for one.
    if flags is not None:
        flags['offer_call'] = True
    if actions is not None and _call_center_actions():
        actions.extend(_call_center_actions())

    return (
        result['response'],
        _resolve_suggestions(STARTER_SUGGESTIONS + [HUMAN_SUGGESTION]),
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
