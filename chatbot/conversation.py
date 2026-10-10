"""Conversation state, qualification and the path from question to lead.

The guide remembers what matters about a conversation on ``ChatSession.state``
— which service the visitor is interested in, where they are in the flow, and
the answers they have given — and uses it to ask **one** useful question at a
time, skip anything they have already told us, and stop asking once there is
enough to hand the conversation to the team.

Two hard rules, matching the business rules the chatbot must obey:

* Every summary bullet comes from something the visitor actually said or
  typed. Nothing is guessed, padded or paraphrased into a claim.
* Browser automation is a capability, never a sale: a need for it is
  clarified and carried into the automation service instead.
"""
import re

from .intents import (
    CAPABILITY_REPLY,
    INTENTS,
    READY_SUGGESTIONS,
    detect_intent,
    is_conversion,
    is_need,
    looks_like_question,
    mentions_selling_browser_automation,
)
from .page_context import _normalise_path, service_for_path

# Enough to qualify a real project without turning the chat into an intake
# form. Skipped questions (already answered, or slots volunteered early) do
# not count, so a visitor who gives everything up front is done immediately.
MAX_ANSWERS = 4
# How often an unanswered question may be re-offered after a detour, before
# the guide stops pushing it.
MAX_OFFERS = 3

SUMMARY_TITLE = "Here's what I understood"

# ── Slot extraction ───────────────────────────────────────────────────────────

_BUSINESS_TYPES = (
    ('manufacturing', ('manufacturing', 'manufacturer', 'factory', 'factories',
                       'production line')),
    ('retail', ('retail', 'boutique')),
    ('e-commerce', ('e-commerce business', 'ecommerce business',
                    'ecommerce store', 'e-commerce store', 'online shop',
                    'online retailer', 'webshop')),
    ('agency', ('agency', 'agencies', 'creative studio')),
    ('SaaS', ('saas', 'software company', 'b2b software')),
    ('healthcare', ('clinic', 'hospital', 'healthcare', 'medical practice',
                    'dental practice')),
    ('education', ('school', 'university', 'college', 'edtech',
                   'training company')),
    ('hospitality', ('restaurant', 'hotel', 'cafe', 'coffee shop', 'catering',
                     'hospitality')),
    ('finance', ('bank', 'insurance', 'accounting firm', 'financial services')),
    ('logistics', ('logistics', 'freight', 'courier', 'shipping company')),
    ('real estate', ('real estate', 'estate agent', 'property company')),
    ('construction', ('construction', 'contractor', 'building company')),
    ('non-profit', ('nonprofit', 'non-profit', 'charity')),
    ('media', ('media company', 'publisher', 'magazine')),
    ('automotive', ('automotive', 'car dealership', 'garage')),
    ('agriculture', ('farm', 'agriculture')),
    ('technology', ('tech company', 'it company', 'technology company')),
)

# Third-party tools the visitor may name as data sources or current systems.
# "Website" is deliberately absent: on a website project every answer would
# mention one, and it would end up as a phantom data source in summaries.
_SYSTEMS = (
    ('Salesforce', ('salesforce',)),
    ('HubSpot', ('hubspot',)),
    ('Zoho', ('zoho',)),
    ('Pipedrive', ('pipedrive',)),
    ('Shopify', ('shopify',)),
    ('WooCommerce', ('woocommerce',)),
    ('WordPress', ('wordpress',)),
    ('Wix', ('wix',)),
    ('Magento', ('magento',)),
    ('Odoo', ('odoo',)),
    ('SAP', ('sap',)),
    ('ERPNext', ('erpnext',)),
    ('QuickBooks', ('quickbooks',)),
    ('Xero', ('xero',)),
    ('Stripe', ('stripe',)),
    ('Airtable', ('airtable',)),
    ('Notion', ('notion',)),
    ('Excel', ('excel', 'google sheets', 'spreadsheets')),
    ('email', ('outlook', 'gmail', 'email system')),
    ('a CRM', ('crm',)),
    ('an ERP', ('erp',)),
)

# The vocabulary of things a project can cover. Answers are matched against
# it so a reply like "inventory and purchasing" becomes two requirement
# bullets — their words, not ours.
_REQUIREMENTS = (
    'sales', 'marketing', 'inventory', 'purchasing', 'procurement', 'orders',
    'accounting', 'invoicing', 'billing', 'payroll', 'recruitment', 'support',
    'shipping', 'logistics', 'production', 'scheduling', 'appointments',
    'bookings', 'reporting', 'analytics', 'payments', 'subscriptions',
    'returns', 'quality', 'maintenance', 'training', 'projects', 'timesheets',
    'expenses', 'budgets', 'customers', 'products', 'catalogue', 'catalog',
    'contracts', 'leads', 'tickets', 'hr',
)

_EMAIL_RE = re.compile(r'[\w.+-]+@[\w-]+\.[a-z]{2,}\b', re.I)
_PHONE_RE = re.compile(r'(?:\+?\d[\d\s().-]{7,}\d)')
_PHONE_CONTEXT_RE = re.compile(
    r'(?:phone|call|whatsapp|number|text|tel(?:ephone)?|reach me)'
    r'[\s:=]*((?:\+?\d[\d\s().-]{7,}\d))', re.I)
_DOMAIN_RE = re.compile(r'(?<![\w@.\-])(?:https?://)?(?:www\.)?'
                        r'([a-z0-9-]+(?:\.[a-z0-9-]+)+)(?![\w-])', re.I)
_DOMAIN_NOISE = {'js', 'py', 'php', 'md', 'html', 'css', 'pdf', 'png',
                 'jpg', 'jpeg', 'svg', 'zip', 'json', 'txt'}

_SIZE_RANGE_RE = re.compile(
    r'\b(\d{1,4})\s*(?:-|–|to|and)\s*(\d{1,4})\s*'
    r'(?:people|staff|employees|users|team members)\b', re.I)
_SIZE_SINGLE_RE = re.compile(
    r'\b(?:about|around|just|only|over|under|more than|less than|up to)?\s*'
    r'(\d{1,4})\s+(?:people|staff|employees|team members|users)\b', re.I)
_SIZE_WORD_RE = re.compile(
    r'\b(?:small|medium|mid-sized|mid sized|large|big)\s+'
    r'(?:business|company|team|startup|organisation|organization|operation)\b',
    re.I)

_TIMELINE_RE = re.compile(
    r'\b(within|in|under|less than|no more than|by)\s+(?:the\s+)?'
    r'(\d{1,3})\s*(day|week|month|quarter|year)s?\b', re.I)
_TIMELINE_SOON_RE = re.compile(
    r'\b(asap|as soon as possible|urgent|immediately|by the end of the '
    r'(?:month|year|quarter)|next month|this month|next quarter|next year)\b',
    re.I)

_BUDGET_RANGE_RE = re.compile(
    r'\$\s?(\d[\d,.]*)\s*([kKmM])?\s*(?:-|–|to)\s*\$\s?(\d[\d,.]*)\s*([kKmM])?')
_BUDGET_CONTEXT_RE = re.compile(
    r'\b(?:budget|price range|price|cost)\s*(?:of|is|around|about|between|:)?'
    r'\s*\$\s?(\d[\d,.]*)\s*([kKmM])?', re.I)

# Intents whose projects are built around data moving between systems, so a
# named tool is a real data source there.
_DATA_INTENTS = {'dashboard', 'erp', 'integration', 'automation', 'software',
                 'ecommerce'}


def _find_phrase(text, table):
    for label, phrases in table:
        for phrase in phrases:
            if re.search(r'\b' + re.escape(phrase) + r'\b', text, re.I):
                return label
    return None


def _find_all(text, table):
    found = []
    for label, phrases in table:
        for phrase in phrases:
            if re.search(r'\b' + re.escape(phrase) + r'\b', text, re.I):
                found.append(label)
                break
    return found


def _extract_requirements(text):
    found = []
    for word in _REQUIREMENTS:
        if re.search(r'\b' + word + r's?\b', text, re.I):
            found.append(word if word.upper() != 'HR' else 'HR')
    # "HR" and other case-sensitive labels keep the case they were written with.
    return [item if item != 'hr' else 'HR' for item in found]


def extract_slots(text, intent=None, include_systems=False):
    """Pull structured facts out of a message. Only what is really there."""
    text = text or ''
    lowered = text.lower()
    slots = {}

    business = _find_phrase(lowered, _BUSINESS_TYPES)
    if business:
        slots['business_type'] = business

    match = _SIZE_RANGE_RE.search(text)
    if match:
        slots['company_size'] = f'{match.group(1)}–{match.group(2)}'
        slots['users'] = slots['company_size']
    else:
        match = _SIZE_SINGLE_RE.search(text)
        if match:
            slots['company_size'] = match.group(1)
            slots['users'] = match.group(1)
        else:
            match = _SIZE_WORD_RE.search(text)
            if match:
                slots['company_size'] = match.group(1).lower()

    match = _TIMELINE_RE.search(text)
    if match:
        unit = match.group(3).lower()
        plural = unit if match.group(2) == '1' and unit.endswith('s') is False \
            else unit
        amount = int(match.group(2))
        plural = unit + ('s' if amount != 1 and not unit.endswith('s') else '')
        slots['timeline'] = f'{match.group(1).lower()} {amount} {plural}'
    else:
        match = _TIMELINE_SOON_RE.search(text)
        if match:
            phrase = match.group(1).lower()
            slots['timeline'] = 'ASAP' if phrase in (
                'asap', 'as soon as possible', 'urgent', 'immediately') \
                else phrase

    match = _BUDGET_RANGE_RE.search(text)
    if match:
        slots['budget'] = match.group(0).strip()
    else:
        match = _BUDGET_CONTEXT_RE.search(text)
        if match:
            suffix = 'k' if (match.group(2) or '').lower() == 'k' else ''
            slots['budget'] = f'${match.group(1)}{suffix}'

    requirements = _extract_requirements(lowered)
    if requirements:
        slots['requirements'] = requirements

    if include_systems:
        systems = _find_all(lowered, _SYSTEMS)
        if systems:
            slots['systems'] = systems

    email = _EMAIL_RE.search(text)
    if email:
        slots['contact'] = email.group(0)
    else:
        phone = _PHONE_CONTEXT_RE.search(text) or (
            {'group': lambda _i: None} if not text.strip().startswith('+')
            else None)
        if phone:
            value = phone.group(1) if hasattr(phone, 'group') else None
            if value:
                slots['contact'] = ' '.join(value.split())

    for match in _DOMAIN_RE.finditer(text):
        domain = match.group(1)
        tail = domain.rsplit('.', 1)[-1].lower()
        if len(tail) >= 2 and tail not in _DOMAIN_NOISE:
            slots['website'] = domain
            break

    return slots


# ── State ─────────────────────────────────────────────────────────────────────

def load_state(session):
    """The session's conversation state as a dict, whatever session is."""
    state = getattr(session, 'state', None)
    if not isinstance(state, dict):
        state = {}
    return state


def remember_page(session, page):
    """Record where the visitor is reading from, for page-aware turns."""
    if not page:
        return
    state = load_state(session)
    # Normalised the same way the registry normalises it, so a trailing slash
    # in the widget's URL never turns into a second, different page.
    path = _normalise_path(str(page.get('path') or ''))[:300]
    title = str(page.get('title') or '')[:200]
    if not path and not title:
        return
    state['page'] = {'path': path, 'title': title}
    session.state = state


def stage_of(session):
    return load_state(session).get('stage') or 'discovery'


# ── Qualification ─────────────────────────────────────────────────────────────

def _slot_filled(state, key):
    if key in state.get('answers', {}):
        return True
    if state.get('slots', {}).get(key):
        return True
    # Naming a system answers both "what does it pull from" and "what do you
    # use today" — one fact, no need to ask twice.
    if key in ('data_sources', 'current_systems') and state.get('slots', {}).get('systems'):
        return True
    return False


def next_question(state):
    """The question to ask now, or None when it is time to stop asking."""
    spec = INTENTS.get(state.get('intent') or '')
    if not spec:
        return None
    if len(state.get('answers', {})) >= MAX_ANSWERS:
        return None
    asked = state.get('asked') or []
    for key, text in spec['questions']:
        if key in asked:
            continue
        if _slot_filled(state, key):
            continue
        return {'key': key, 'text': text}
    return None


def _merge_slots(state, fresh):
    slots = state.setdefault('slots', {})
    for key, value in fresh.items():
        if isinstance(value, list):
            existing = slots.get(key) or []
            slots[key] = list(dict.fromkeys(existing + value))
        elif value:
            slots[key] = value


def _ack(state, fresh=None):
    """One short line that proves the answer landed, never a rubber stamp."""
    business = state.get('slots', {}).get('business_type')
    fresh_requirements = (fresh or {}).get('requirements')
    if business and fresh_requirements:
        return (f"Noted \u2014 for a {business} business, that means focusing "
                f"on {', '.join(fresh_requirements)}.")
    if business:
        return f"Noted \u2014 a {business} business."
    if state.get('intent') == 'automation' and (fresh or {}).get('process'):
        return 'Noted \u2014 that process is a good candidate.'
    return 'Thanks \u2014 that helps.'


def _chips(titles):
    return [{'title': title} for title in titles]


def _resolve_recommendations(spec, user):
    """Live, readable pages for this intent, as ``{title, url}`` objects."""
    from .corpus import access_for_url_name, user_can_read
    from django.urls import NoReverseMatch, reverse
    from .search import page_is_live

    links = []
    for url_name, label in spec.get('recommendations', ()):
        if not user_can_read(user, access_for_url_name(url_name)):
            continue
        try:
            path = reverse(url_name)
        except NoReverseMatch:
            continue
        if not page_is_live(path):
            continue
        links.append({'title': label, 'url': path})
    return links


def _structured(intent_key, state, user, confidence):
    """Everything the front end renders beyond the reply itself."""
    spec = INTENTS[intent_key]
    recommendations = _resolve_recommendations(spec, user)
    payload = {
        'intent': intent_key,
        'confidence': confidence,
        'stage': state.get('stage') or 'discovery',
        'recommendations': recommendations,
    }
    if state.get('stage') == 'ready':
        payload['cta'] = {'label': 'Request a Consultation', 'action': 'lead'}
        summary = lead_summary(state)
        if summary:
            payload['lead_summary'] = summary
    return payload


def _set_flags(flags, payload):
    if flags is None:
        return
    flags['structured'] = payload


# ── Visitor-facing summary ────────────────────────────────────────────────────

_SUMMARY_SOLUTION = {
    'website': 'A new website',
    'ecommerce': 'An online store',
    'mobile': 'A mobile app',
    'dashboard': 'A custom business dashboard',
    'erp': 'An ERP solution',
    'automation': 'Process automation',
    'integration': 'Connected systems',
    'branding': 'Brand identity work',
    'seo': 'SEO work',
    'software': 'Custom software',
}

_REQUIREMENT_VERB = {
    'dashboard': 'Tracking', 'erp': 'Covering', 'automation': 'Automating',
    'website': 'Features', 'integration': 'Syncing', 'branding': 'Needs',
    'seo': 'Focus', 'ecommerce': 'Store needs', 'mobile': 'App needs',
    'software': 'Needs',
}


def _one_line(text, limit=120):
    text = ' '.join(str(text).split())
    if len(text) > limit:
        text = text[:limit].rsplit(' ', 1)[0] + '\u2026'
    return text


def summary_bullets(state):
    """The visitor's own answers as a short bullet list. Never invented."""
    intent = state.get('intent') or ''
    slots = state.get('slots', {})
    answers = state.get('answers', {})
    bullets = []

    solution = _SUMMARY_SOLUTION.get(intent)
    if solution:
        bullets.append(solution)

    if slots.get('business_type'):
        bullets.append(f'For a {slots["business_type"]} business')

    size = slots.get('company_size')
    if size and size not in (slots.get('business_type'),):
        if re.match(r'^\d', size):
            bullets.append(f'Team of {size}')
        else:
            bullets.append(f'A {size} business')

    requirements = slots.get('requirements') or []
    if requirements:
        verb = _REQUIREMENT_VERB.get(intent, 'Focus')
        bullets.append(f'{verb} {", ".join(requirements[:6])}')
    elif answers.get('process'):
        bullets.append(f'Automating: {_one_line(answers["process"])}')

    systems = slots.get('systems') or []
    if systems:
        bullets.append(f'Connecting {", ".join(systems[:5])}')

    users = slots.get('users')
    if users:
        bullets.append(f'Access for {users} users' if re.match(r'^\d', str(users))
                       else f'Access for {users}')
    elif answers.get('users'):
        bullets.append(f'Users: {_one_line(answers["users"])}')

    timeline = slots.get('timeline')
    if timeline:
        bullets.append(timeline[0].upper() + timeline[1:])

    pain = answers.get('pain_points') or answers.get('problem')
    if pain and len(bullets) < 7:
        bullets.append(f'Main pain point: {_one_line(pain)}')
    elif answers.get('goal') and len(bullets) < 7:
        bullets.append(f'Goal: {_one_line(answers["goal"])}')

    return bullets[:7]


def lead_summary(state):
    """Visitor-facing summary block, or None when there is too little said."""
    bullets = summary_bullets(state)
    if len(bullets) < 2:
        return None
    return {'title': SUMMARY_TITLE, 'bullets': bullets}


# ── Team-facing summary (the lead the team reads) ────────────────────────────

def team_summary(state):
    """Structured handover text in the shape the team expects to read."""
    intent = state.get('intent') or ''
    spec = INTENTS.get(intent, {})
    slots = state.get('slots', {})
    answers = state.get('answers', {})

    lines = [f'Lead intent: {spec.get("label", intent)}']

    def add(heading, value):
        if value:
            lines.extend(['', f'{heading}:', _one_line(value, 400)])

    business = answers.get('business_type')
    if not business and slots.get('business_type'):
        business = f'{slots["business_type"]} business'
    add('Business', business)

    needs = ', '.join(slots.get('requirements') or [])
    if not needs:
        needs = answers.get('process') or answers.get('goal') or answers.get('problem')
    add('Needs', needs)

    add('Data sources', ', '.join(slots.get('systems') or []))
    add('Users', slots.get('users') or answers.get('users'))
    add('Main pain point', answers.get('pain_points') or answers.get('problem'))
    add('Timeline', slots.get('timeline'))
    add('Budget', slots.get('budget'))
    add('Website', slots.get('website'))
    add('Contact', slots.get('contact'))
    add('Recommended solution', spec.get('label'))

    return '\n'.join(lines)


def lead_fields(state):
    intent = state.get('intent') or ''
    spec = INTENTS.get(intent, {})
    slots = dict(state.get('slots') or {})
    return {
        'intent': intent,
        'solution': spec.get('label', ''),
        'contact': slots.get('contact', ''),
        'data': {'slots': slots, 'answers': dict(state.get('answers') or {})},
    }


# ── Turn handling ─────────────────────────────────────────────────────────────

def _ready_turn(state, user, confidence, flags):
    """Enough (or an explicit ask): show the summary, offer the next step."""
    state['stage'] = 'ready'
    spec = INTENTS[state['intent']]
    summary = lead_summary(state)
    if summary:
        reply = ("That's everything I need for now. Here's what I understood "
                 "from our chat \u2014 if it looks right, request a "
                 "consultation and I'll pass this summary to the team with "
                 "this conversation.")
    else:
        reply = (f"{spec['pitch']} Would you like to request a consultation?")
    payload = _structured(state['intent'], state, user, confidence)
    _set_flags(flags, payload)
    return reply, _chips(READY_SUGGESTIONS), payload['recommendations']


def _qualifying_turn(state, fresh, user, confidence, flags):
    """Acknowledge the answer, then ask exactly one more question."""
    question = next_question(state)
    if question is None:
        return _ready_turn(state, user, confidence, flags)

    state['offers'] = 0
    reply = f"{_ack(state, fresh)} {question['text']}"
    payload = _structured(state['intent'], state, user, confidence)
    _set_flags(flags, payload)
    chips = _chips(INTENTS[state['intent']]['follow_ups'])
    return reply, chips, payload['recommendations']


def _start_qualification(state, intent_key, text, user, confidence, flags):
    """First commercial turn: recommend the service, ask the first question."""
    if state.get('intent') != intent_key:
        # A new project: the business facts carry over, the answers to the
        # previous sequence do not.
        state['intent'] = intent_key
        state['answers'] = {}
        state['asked'] = []
        state['offers'] = 0
    state['stage'] = 'qualifying'

    fresh = extract_slots(text, intent_key,
                          include_systems=intent_key in _DATA_INTENTS)
    _merge_slots(state, fresh)

    spec = INTENTS[intent_key]
    question = next_question(state)
    reply = spec['pitch']
    if question:
        reply = f"{reply} {question['text']}"
    else:
        state['stage'] = 'ready'
        return _ready_turn(state, user, confidence, flags)

    payload = _structured(intent_key, state, user, confidence)
    _set_flags(flags, payload)
    return reply, _chips(spec['follow_ups']), payload['recommendations']


def _capability_turn(state, text, user, confidence, flags):
    """Browser automation: clarify it is a capability, then carry on."""
    state['intent'] = 'automation'
    state['answers'] = {}
    state['asked'] = []
    state['offers'] = 0
    state['stage'] = 'qualifying'

    fresh = extract_slots(text, 'automation', include_systems=True)
    _merge_slots(state, fresh)

    question = next_question(state)
    reply = CAPABILITY_REPLY
    if question:
        reply = f"{reply} {question['text']}"
    else:
        state['stage'] = 'ready'
        return _ready_turn(state, user, confidence, flags)

    payload = _structured('automation', state, user, confidence)
    _set_flags(flags, payload)
    return reply, _chips(INTENTS['automation']['follow_ups']), \
        payload['recommendations']


def _offer_pending(state, flags):
    """After a detour, re-surface the unanswered question — gently."""
    question = next_question(state)
    if not question:
        return
    if (state.get('offers') or 0) >= MAX_OFFERS:
        return
    state['offers'] = (state.get('offers') or 0) + 1
    if flags is not None:
        flags['pending_question'] = question['text']


def handle_turn(message, session, user=None, flags=None):
    """Run the conversation layer for one message.

    Returns the ``(reply, suggestions, links)`` triple when this message is
    part of a need/recommendation/qualification flow, or None to let the
    existing answer pipeline (greetings, curated answers, site index) handle
    it unchanged. Structured extras leave through ``flags``.
    """
    state = load_state(session)
    text = (message or '').strip()
    if not text:
        return None

    page_path = (state.get('page') or {}).get('path', '')
    page_service = service_for_path(page_path)

    intent_now, confidence = detect_intent(text, page_service)
    need = is_need(text)
    conversion = is_conversion(text)
    stage = state.get('stage') or 'discovery'
    state['turns'] = (state.get('turns') or 0) + 1
    # Confidence belongs to the project, not to the sentence. "Book a
    # consultation" names no service, but the project already identified is
    # still what the visitor is asking about, so the turn keeps its confidence.
    if confidence:
        state['confidence'] = confidence
    else:
        confidence = state.get('confidence') or confidence

    # ── Mid-flow: a plain answer to the pending question ──
    if stage == 'qualifying' and not need and not conversion:
        if looks_like_question(text):
            _offer_pending(state, flags)
            return None
        pending = next_question(state)
        if pending:
            state['answers'][pending['key']] = _one_line(text, 300)
            state.setdefault('asked', []).append(pending['key'])
        fresh = extract_slots(
            text, state.get('intent'),
            include_systems=state.get('intent') in _DATA_INTENTS)
        _merge_slots(state, fresh)
        return _qualifying_turn(state, fresh, user, confidence, flags)

    # ── Browser automation is a capability, not a product ──
    if intent_now == 'browser_automation':
        if need or conversion or mentions_selling_browser_automation(text):
            return _capability_turn(state, text, user, confidence, flags)
        return None

    # ── A stated requirement or an explicit ask ──
    if need or conversion:
        intent_key = intent_now
        if intent_key is None or INTENTS[intent_key]['qualifiable'] is False:
            intent_key = state.get('intent')
        if not intent_key or INTENTS[intent_key]['qualifiable'] is False:
            return None

        if conversion:
            # An explicit ask outranks the questionnaire: offer the handover
            # now, with whatever has been learned so far.
            state['intent'] = intent_key
            fresh = extract_slots(text, intent_key,
                                  include_systems=intent_key in _DATA_INTENTS)
            _merge_slots(state, fresh)
            return _ready_turn(state, user, confidence, flags)

        if state.get('intent') == intent_key and stage in ('qualifying', 'ready'):
            # Same project: fold any new facts in and keep the flow moving.
            fresh = extract_slots(text, intent_key,
                                  include_systems=intent_key in _DATA_INTENTS)
            _merge_slots(state, fresh)
            if stage == 'ready':
                return _ready_turn(state, user, confidence, flags)
            return _qualifying_turn(state, fresh, user, confidence, flags)

        return _start_qualification(state, intent_key, text, user,
                                    confidence, flags)

    return None
