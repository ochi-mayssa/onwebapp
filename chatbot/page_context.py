"""Which page the visitor is looking at, and what that page implies.

The guide is not a generic assistant: on the Web Development page it should
know the visitor is probably interested in a website, and its suggested
questions should be about websites. This module keeps that knowledge in one
place — page title, section, the service the page belongs to and the
questions worth suggesting there — and resolves a request's path against the
real URL table, so no link can ever be invented.

Nothing here is rendered verbatim without the caller filtering it through
``user_can_read`` and ``page_is_live``; both are applied here too, so a
gated or broken page never leaks into suggestions or calls to action.
"""
import logging

from django.urls import NoReverseMatch, reverse

from .corpus import PAGE_SOURCES, access_for_url_name, user_can_read
from .search import page_is_live

logger = logging.getLogger(__name__)

# The service a page belongs to. These keys are shared with the intent layer:
# 'website', 'dashboard', 'erp' and friends are what the conversation engine
# qualifies. Entries that are capabilities rather than services carry
# ``service: 'browser_automation'``, which is never sold on its own.
GENERIC = ''

# The guide's opening line, the same wherever the visitor lands: one sentence
# the visitor can answer. The page introduces itself in its own second line
# (``page_intro`` in the entries below), and the questions offered underneath
# are that page's — so the first message is always the same and the second
# always belongs to the page being read.
WELCOME = 'Hello, how can I help you today?'

PAGE_CONTEXTS = {
    'home:home': {
        'title': 'Home',
        'category': 'Home',
        'service': GENERIC,
        'page_intro': "Ask about OnWebApp, our solutions, or tell us what you're trying to build.",
        'suggestions': [
            'What can OnWebApp build?',
            'I need a website',
            'I need a custom dashboard',
            'I need an ERP for my company',
        ],
    },
    'home:about': {
        'title': 'About OnWebApp',
        'category': 'Company',
        'service': GENERIC,
        'page_intro': 'This page is about OnWebApp itself — how we work and what we build.',
        'suggestions': [
            'What does OnWebApp do?',
            'What is your project process?',
            'What services do you offer?',
            'I would like to talk to someone',
        ],
    },
    'services:index': {
        'title': 'Services',
        'category': 'Services',
        'service': GENERIC,
        'page_intro': 'Every service we offer is listed here — ask about any of them, or tell us what you need.',
        'suggestions': [
            'What services do you offer?',
            'Can you build a custom business platform?',
            'How does business automation work?',
            'How much does it cost?',
        ],
    },
    'home:web_development': {
        'title': 'Web Development',
        'category': 'Services',
        'service': 'website',
        'page_intro': "You're viewing Web Development — ask what we build, how long projects take, or tell us about your project.",
        'suggestions': [
            'What type of websites do you build?',
            'Can you build a custom business platform?',
            'How long does a website project take?',
            'I need a website for my business.',
        ],
        'ctas': [{'label': 'Request a Website', 'url_name': 'home:build_website'}],
    },
    'home:build_website': {
        'title': 'Request a Website',
        'category': 'Services',
        'service': 'website',
        'page_intro': 'This page starts a website project — I can also answer questions about scope, features and timeline here.',
        'suggestions': [
            'What do you need from me to start?',
            'What features can a website include?',
            'I need a website for my business.',
            'How long does a website project take?',
        ],
    },
    'home:mobile_development': {
        'title': 'Mobile Development',
        'category': 'Services',
        'service': 'mobile',
        'page_intro': 'This page covers mobile app development.',
        'suggestions': [
            'Do you build mobile apps?',
            'Which platforms do you build for?',
            'I need a mobile app for my business.',
            'Can you build an app that connects to our website?',
        ],
    },
    'home:ecommerce_development': {
        'title': 'eCommerce Development',
        'category': 'Services',
        'service': 'ecommerce',
        'page_intro': 'This page covers online store development.',
        'suggestions': [
            'What eCommerce platforms do you build on?',
            'Can you connect a store to my existing website?',
            'I need an online store.',
            'Can you build a custom checkout?',
        ],
    },
    'home:dashboard_development': {
        'title': 'Custom Business Dashboards',
        'category': 'Services',
        'service': 'dashboard',
        'page_intro': 'This page covers custom dashboards — ask what we can build, how they get their data, and what they cost.',
        'suggestions': [
            'Can you build a dashboard for my business?',
            'What data sources can you connect?',
            'Can my existing website be connected to the dashboard?',
            'I need a sales dashboard.',
        ],
    },
    'home:erp_service': {
        'title': 'ERP & Business Systems',
        'category': 'Services',
        'service': 'erp',
        'page_intro': 'This page covers ERP and business systems — ask about modules, integrations and rollout.',
        'suggestions': [
            'I need an ERP for my company.',
            'Can you integrate ERPNext?',
            'What business processes can you automate?',
            'Can you build a custom ERP?',
        ],
    },
    'home:automation_home': {
        'title': 'Website Automation',
        'category': 'Automation',
        'service': 'automation',
        'page_intro': 'This page covers automation — workflows, scheduled tasks and the systems they connect.',
        'suggestions': [
            'How does workflow automation work?',
            'What processes can be automated?',
            'Can you automate tasks across different systems?',
            'I need to automate a repetitive process.',
        ],
    },
    'home:rpa_bpa': {
        'title': 'RPA & BPA',
        'category': 'Automation',
        'service': 'automation',
        'page_intro': 'This page covers Robotic and Business Process Automation.',
        'suggestions': [
            'What processes can be automated?',
            'Can you automate repetitive back-office tasks?',
            'How does workflow automation work?',
            'I need to automate a repetitive process.',
        ],
    },
    'home:rpa_solutions': {
        'title': 'RPA Solutions',
        'category': 'Automation',
        'service': 'automation',
        'page_intro': 'This page covers Robotic Process Automation solutions for repetitive business processes, including use cases, engagement options, and the consultation request form.',
        'suggestions': [
            'What processes can be automated?',
            'What does an RPA engagement cost?',
            'Should we use RPA or an API integration?',
            'I need to automate a repetitive process.',
        ],
    },
    'home:browser_web_automation': {
        # A capability used inside automation and web projects, not a service
        # the visitor can buy on its own — the questions reflect that.        'title': 'Browser & Web Automation',
        'category': 'Automation',
        'service': 'browser_automation',
        'page_intro': 'This page explains browser and web automation — a capability we apply inside projects rather than sell alone.',
        'suggestions': [
            'Is browser automation a service you sell?',
            'What processes can be automated?',
            'How does workflow automation work?',
            'Can you automate tasks across different systems?',
        ],
    },
    'home:software_home': {
        'title': 'Software Development',
        'category': 'Services',
        'service': 'software',
        'page_intro': 'This page covers custom software and web applications.',
        'suggestions': [
            'Can you build a custom business platform?',
            'What technologies do you build with?',
            'I need custom software for my business.',
            'Can you build an internal tool for my team?',
        ],
    },
    'home:ux_design': {
        'title': 'UX Design',
        'category': 'Design',
        'service': 'branding',
        'page_intro': 'This page covers UX design — research, flows and testing before any pixels.',
        'suggestions': [
            'Do you design user interfaces too?',
            'Can you redesign an existing product?',
            'I need UX design for my product.',
            'What does your design process look like?',
        ],
    },
    'home:ui_design': {
        'title': 'UI Design',
        'category': 'Design',
        'service': 'branding',
        'page_intro': 'This page covers UI design and interfaces.',
        'suggestions': [
            'Do you design user interfaces too?',
            'Can you redesign an existing product?',
            'I need UI design for my product.',
            'What does your design process look like?',
        ],
    },
    'branding:landing': {
        'title': 'Branding',
        'category': 'Design',
        'service': 'branding',
        'page_intro': 'This page covers brand identity — logos, systems and the guidelines that keep them consistent.',
        'suggestions': [
            'What does a branding project include?',
            'Do you redesign existing brands?',
            'I need a brand identity for my company.',
            'Can you design a logo and guidelines?',
        ],
    },
    'integration:integration_homepage': {
        'title': 'Integrations',
        'category': 'Integration',
        'service': 'integration',
        'page_intro': 'This page covers connecting systems, data and APIs.',
        'suggestions': [
            'Which systems can you connect?',
            'Can you connect my CRM to my website?',
            'I need my systems to talk to each other.',
            'Can you integrate data from different tools?',
        ],
    },
    'seo_analyzer:seo_home_marketing': {
        'title': 'SEO Services',
        'category': 'SEO',
        'service': 'seo',
        'page_intro': 'This page covers SEO services and tools.',
        'suggestions': [
            'How do you improve SEO for a website?',
            'Can you audit my website SEO?',
            'I need help with search rankings.',
            'What SEO tools do you offer?',
        ],
    },
    'payments:plans': {
        'title': 'Pricing & Plans',
        'category': 'Pricing',
        'service': GENERIC,
        'page_intro': 'This page lists our plans — ask for a price specific to your project.',
        'suggestions': [
            'What plans do you offer?',
            'How much does a custom project cost?',
            'I need a custom quote.',
            'What is included in each plan?',
        ],
    },
    'contact:contact': {
        'title': 'Contact',
        'category': 'Company',
        'service': GENERIC,
        'page_intro': 'You can reach the team here — or tell me what you need and I will pass it on.',
        'suggestions': [
            'I would like to talk to someone.',
            'I need a quote.',
            'I want to book a consultation.',
            'What can OnWebApp build?',
        ],
    },
    'blog:index': {
        'title': 'Blog',
        'category': 'Resources',
        'service': GENERIC,
        'page_intro': 'Articles and updates from OnWebApp.',
        'suggestions': [
            'What do you write about?',
            'What services do you offer?',
            'What can OnWebApp build?',
        ],
    },
    'forum:home': {
        'title': 'Community Forum',
        'category': 'Community',
        'service': GENERIC,
        'page_intro': 'The OnWebApp community forum.',
        'suggestions': [
            'How do I join the community?',
            'What services do you offer?',
            'What can OnWebApp build?',
        ],
    },
    'community:home': {
        'title': 'Community',
        'category': 'Community',
        'service': GENERIC,
        'page_intro': 'The OnWebApp community.',
        'suggestions': [
            'What is the community?',
            'What services do you offer?',
            'What can OnWebApp build?',
        ],
    },
    'platform_monitoring:hub': {
        'title': 'Platform Monitoring',
        'category': 'Platform',
        'service': GENERIC,
        'page_intro': 'This page covers platform monitoring — uptime, performance and alerts.',
        'suggestions': [
            'What does platform monitoring track?',
            'How do alerts work?',
            'What services do you offer?',
        ],
    },
}

DEFAULT_CONTEXT = {
    'title': 'OnWebApp',
    'category': '',
    'service': GENERIC,
    'welcome': WELCOME,
    'suggestions': [
        'What can OnWebApp build?',
        'I need a website',
        'I need a custom dashboard',
        'How much does it cost?',
    ],
    'ctas': [],
}

# A page the registry does not describe still gets a useful context, derived
# from the first section of its path: /services/smart-factory/ is a service
# page even though nobody wrote an entry for it.
_SECTION_FALLBACKS = (
    ('services', {'category': 'Services', 'title': 'Services'}),
    ('software', {'category': 'Services', 'service': 'website'}),
    ('design', {'category': 'Design', 'service': 'branding'}),
    ('automation', {'category': 'Automation', 'service': 'automation'}),
    ('integration', {'category': 'Integration', 'service': 'integration'}),
    ('seo', {'category': 'SEO', 'service': 'seo'}),
)

_path_lookup = None


def _normalise_path(path):
    path = (path or '').strip()[:300]
    if not path:
        return ''
    # Only a path is ever needed: a query string or fragment carries no page
    # identity and could carry anything.
    path = path.split('#', 1)[0].split('?', 1)[0]
    if not path.startswith('/'):
        path = '/' + path
    if len(path) > 1:
        path = path.rstrip('/')
    return path


def _build_path_lookup():
    """Map every registry path (plus every indexed page) to its URL name."""
    lookup = {}
    names = list(PAGE_CONTEXTS) + [name for name, _, _ in PAGE_SOURCES]
    for name in names:
        try:
            path = reverse(name)
        except NoReverseMatch:
            continue
        lookup.setdefault(_normalise_path(path), name)
    return lookup


def _lookup():
    global _path_lookup
    if _path_lookup is None:
        _path_lookup = _build_path_lookup()
    return _path_lookup


def match_page(path):
    """The registry entry for ``path``: exact first, then nearest section."""
    path = _normalise_path(path)
    if not path:
        return None, ''

    lookup = _lookup()
    url_name = lookup.get(path)
    if url_name:
        return PAGE_CONTEXTS.get(url_name), url_name

    # Longest prefix wins, so /software/web-development/ finds /software/
    # only when it has no entry of its own.
    best_prefix = best_name = None
    for known_path, name in lookup.items():
        if known_path == '/':
            continue
        if path == known_path or path.startswith(known_path + '/'):
            if best_prefix is None or len(known_path) > len(best_prefix):
                best_prefix, best_name = known_path, name
    if best_name:
        return PAGE_CONTEXTS.get(best_name), best_name
    return None, ''


def _service_from_section(path):
    """Fallback service/category for a page nobody wrote an entry for."""
    segments = [segment for segment in path.split('/') if segment]
    for section, extra in _SECTION_FALLBACKS:
        if section in segments:
            return extra
    return {}


def static_context(path):
    """Welcome copy, the page's own second line and questions for ``path``,
    with nothing to look up.

    No permissions, no crawl index: only the registry and the URL table. That
    makes it safe to run on every request (it backs the context processor the
    page renders with) and safe to fall back to when the live endpoint cannot
    be reached. Calls to action are left out on purpose — those have to be
    checked against the index before they are worth showing.
    """
    entry, url_name = match_page(path)
    fallback = _service_from_section(_normalise_path(path))

    context = dict(DEFAULT_CONTEXT)
    context.pop('ctas', None)
    context.update(fallback)
    if entry:
        context.update({key: value for key, value in entry.items()
                        if key != 'ctas'})
    elif url_name:
        context['title'] = url_name.split(':')[-1].replace('_', ' ').title()

    context['path'] = _normalise_path(path)
    context['url_name'] = url_name or ''
    context['service'] = context.get('service') or GENERIC
    context['suggestions'] = [
        {'title': title} for title in (entry or DEFAULT_CONTEXT)['suggestions']
    ]
    return context


def resolve_context(path, user=None):
    """Build the full page context for the visitor's current path.

    Returned dict is JSON-ready: welcome copy, suggested questions and calls
    to action, with every URL resolved against the real URL table and filtered
    for the visitor's access level and the index's live-page list.
    """
    context = static_context(path)
    entry, _ = match_page(path)
    url_names = [c['url_name'] for c in (entry or {}).get('ctas', ())]

    ctas = []
    for cta_url_name in url_names:
        if not user_can_read(user, access_for_url_name(cta_url_name)):
            continue
        try:
            cta_path = reverse(cta_url_name)
        except NoReverseMatch:
            continue
        if not page_is_live(cta_path):
            continue
        label = next((c['label'] for c in entry.get('ctas', [])
                      if c['url_name'] == cta_url_name), 'Learn more')
        ctas.append({'label': label, 'url': cta_path})
    context['ctas'] = ctas
    return context


def service_for_path(path):
    """The service key a page belongs to ('dashboard', 'erp', ...), or ''."""
    entry, _ = match_page(path)
    if entry:
        return entry.get('service') or GENERIC
    return (_service_from_section(_normalise_path(path)).get('service')
            or GENERIC)
