"""What the visitor is asking for, before any answer is written.

Detection is deliberately conservative and runs on two axes:

* **Need** — a first-person requirement ("I need a dashboard", "can you build
  a CRM for us?"). Only then does the conversation engine move from answering
  to recommending and qualifying. Informational questions keep going through
  the curated answers and the site index exactly as before.
* **Intent** — which OnWebApp service the need or question is about, scored by
  how specifically the message matches each service's vocabulary. Ties go to
  the most specific service, so "a dashboard for my website" is a dashboard.

Two rules encoded here rather than scattered:

* Browser automation is a **capability**, never a service. It gets a
  clarification branch, not a sales pitch or a quote CTA.
* The chatbot must not invent services: every intent maps to pages that
  actually exist in the URL table, resolved elsewhere with access checks.
"""
import re

_WORD = r'[a-z0-9][a-z0-9\'-]*'


def _compile(*phrases):
    """One word-bounded alternation per phrase list."""
    parts = []
    for phrase in phrases:
        escaped = r'\s+'.join(re.escape(word) for word in phrase.split())
        parts.append(escaped)
    return re.compile(r'\b(?:' + '|'.join(parts) + r')\b', re.I)


def _question(*phrases):
    return _compile(*phrases)


# ── Need and conversion signals ───────────────────────────────────────────────

# A first-person requirement. "Do you build websites?" is not one: the
# suggested questions on every service page are phrased that way, and they
# should get a good answer first, not a qualification interrogation.
NEED_RE = re.compile(
    r"\b(?:i|we)(?:'re|'s|'d| am| m| are)?\s+"
    r"(?:also\s+|really\s+|still\s+|just\s+|currently\s+)?"
    r"(?:need|needs|require|want|wants|am\s+looking\s+for|are\s+looking\s+for|"
    r"looking\s+for|would\s+like)\b"
    r'|\b(?:my|our)\s+(?:company|business|team|startup|organisation|organization)'
    r'\s+(?:needs?|wants?|requires?)\b'
    r'|\b(?:can|could|would)\s+you\s+'
    r'(?:build|make|create|develop|design|set\s+up|setup|handle|automate|deliver)\b'
    r'[^.?!]*\bfor\s+(?:me|us|my|our)\b'
    r"|\bi\s+(?:'m|am)\s+in\s+the\s+market\s+for\b",
    re.I,
)

# Questions that contain "I want to know" but are research, not a requirement.
NOT_NEED_RE = re.compile(
    r"\b(?:i|we)(?:'d| would| am| m| are)?\s+(?:just\s+)?"
    r'(?:want|need|would\s+like|like)\s+to\s+'
    r'(?:know|understand|learn|see|read|ask|find\s+out|check|compare|get)\b'
    r'|\b(?:i|we)\s+(?:was|were)\s+(?:just\s+)?(?:wondering|curious)\b'
    r'|\b(?:curious|just\s+wondering)\b',
    re.I,
)

# Explicit "I am ready to act". Only ever honoured when an intent is already
# known, so a bare "how much does it cost?" still goes to the pricing answer.
CONVERSION_RE = re.compile(
    r'\b(?:how\s+much|what\s+(?:does|will|would)\s+it\s+cost|pricing|prices?|costs?)\b'
    r'|\b(?:quotes?|quotations?|estimates?|proposals?)\b'
    r'|\b(?:demos?|demonstrations?|free\s+trials?|trials?)\b'
    r'|\bget\s+(?:started|going)\b'
    r'|\b(?:book|schedule|arrange)\s+(?:a|an|the)?\s*'
    r'(?:call|consultation|meeting|demo|appointment|appointment)s?\b'
    r'|\brequest\s+(?:a|an|the)?\s*'
    r'(?:quote|consultation|call|callback|estimate|proposal)s?\b'
    r'|\b(?:start|begin)\s+(?:a\s+)?project\b'
    r'|\bwork\s+with\s+(?:you|us)\b'
    r'|\bsign\s*up\b|\bsignup\b'
    r"|\bi\s+(?:need|want)\s+(?:a\s+)?quote\b",
    re.I,
)

# Anything shaped like a research question. Used mid-qualification to tell a
# detour ("tell me more about dashboards") from an answer ("sales and marketing").
DETOUR_RE = re.compile(
    r'\?\s*$'
    r'|^\s*(?:what|how|why|when|where|which|who|whose|tell\s+me|show\s+me|explain|'
    r'do\s+you|does|do|is|are|can|could|would|should|will|have|has|any|are\s+there|'
    r'is\s+there)\b',
    re.I,
)

# "Is browser automation something you sell?" — the question this capability
# must never answer with a price tag.
SELL_RE = re.compile(
    r'\b(?:sell|sells|selling|sold|buy|purchase|pricing|price|cost|package|'
    r'standalone|stand-alone|separately|as\s+a\s+service|its\s+own\s+service)\b',
    re.I,
)


def is_need(text):
    lowered = text or ''
    if NOT_NEED_RE.search(lowered):
        return False
    return bool(NEED_RE.search(lowered))


def is_conversion(text):
    return bool(CONVERSION_RE.search(text or ''))


def looks_like_question(text):
    return bool(DETOUR_RE.search((text or '').strip()))


def mentions_selling_browser_automation(text):
    return bool(SELL_RE.search(text or ''))


# ── Service intents ───────────────────────────────────────────────────────────
# Ordered most specific first: on a tie the first entry wins, so a message
# about "an online store on my website" resolves to ecommerce, not website.

INTENTS = {
    'ecommerce': {
        'label': 'eCommerce Development',
        'solution': 'online store',
        'qualifiable': True,
        'phrases': _question(
            'e-commerce', 'ecommerce', 'online store', 'webshop', 'web shop',
            'storefront', 'shopping cart', 'checkout', 'sell online',
            'product catalogue', 'product catalog', 'marketplace',
        ),
        'pitch': 'We build online stores and custom eCommerce experiences, '
                 'from the storefront to the checkout.',
        'recommendations': [('home:ecommerce_development', 'eCommerce Development')],
        'questions': [
            ('business_type', 'What do you sell, and to whom?'),
            ('requirements', 'What must the store handle — payments, shipping, '
                             'stock, or all of it?'),
            ('existing_website', 'Do you already have a store or website?'),
            ('integrations', 'Any systems it should connect to — inventory, '
                             'CRM, or marketplaces?'),
        ],
        'follow_ups': [
            'What platforms do you build on?',
            'Can you connect a store to my website?',
            'How long does an online store take?',
        ],
    },
    'mobile': {
        'label': 'Mobile Development',
        'solution': 'mobile app',
        'qualifiable': True,
        'phrases': _question(
            'mobile app', 'mobile application', 'app development',
            'ios', 'android', 'smartphone app', 'phone app', 'tablet app',
            'react native', 'flutter',
        ),
        'pitch': 'We develop mobile apps alongside web platforms, sharing the '
                 'backend where that makes sense.',
        'recommendations': [('home:mobile_development', 'Mobile Development')],
        'questions': [
            ('business_type', 'What type of business is the app for?'),
            ('goal', 'What should the app let people do?'),
            ('requirements', 'Do you need it for iOS, Android, or both?'),
            ('existing_website', 'Do you already have a website or backend '
                                 'to connect it to?'),
        ],
        'follow_ups': [
            'Which platforms do you build for?',
            'Can you build an app that connects to our website?',
            'How long does an app project take?',
        ],
    },
    'dashboard': {
        'label': 'Custom Business Dashboard',
        'solution': 'custom business dashboard',
        'qualifiable': True,
        'phrases': _question(
            'dashboard', 'kpi', 'kpis', 'key performance indicators',
            'business intelligence', 'data visualization', 'data visualisation',
            'reporting', 'track sales', 'tracking sales', 'sales data',
            'metrics', 'single view', 'one view', 'track our', 'track my',
            'monitor our performance', 'real time view', 'realtime view',
        ),
        'pitch': 'A custom business dashboard could be a good fit — we can '
                 'centralise sales, marketing, website and other business data '
                 'into one view.',
        'recommendations': [('home:dashboard_development',
                             'Custom Business Dashboards')],
        'questions': [
            ('business_type', 'What type of business do you run?'),
            ('requirements', 'What do you want to track — sales, marketing, '
                             'operations, or all of it?'),
            ('data_sources', 'Which systems should it pull data from — your '
                             'website, CRM, spreadsheets?'),
            ('users', 'Who will use the dashboard — just you, or a wider team?'),
            ('timeline', 'Do you have a deadline in mind?'),
        ],
        'follow_ups': [
            'What data can you connect?',
            'Can you connect my CRM?',
            'What should a sales dashboard show?',
        ],
    },
    'erp': {
        'label': 'ERP & Business Systems',
        'solution': 'ERP solution',
        'qualifiable': True,
        'phrases': _question(
            'erp', 'erpnext', 'enterprise resource planning', 'sap', 'odoo',
            'business system', 'business systems', 'crm system', 'inventory system',
            'accounting system', 'warehouse management', 'mrp',
        ),
        'pitch': 'Absolutely — we build and integrate ERP and business systems, '
                 'including ERPNext, SAP and Odoo.',
        'recommendations': [('home:erp_service', 'ERP Service')],
        'questions': [
            ('business_type', 'What type of business do you run?'),
            ('requirements', 'Which operations should it cover — inventory, '
                             'purchasing, sales, accounting, manufacturing, or HR?'),
            ('current_systems', 'What do you use today — spreadsheets, existing '
                                'software, or another ERP?'),
            ('users', 'How many people would use it?'),
            ('integrations', 'Any systems it must connect to?'),
        ],
        'follow_ups': [
            'Which ERP do you integrate with?',
            'Can you build a custom ERP?',
            'What processes can be automated?',
        ],
    },
    'automation': {
        'label': 'Business Automation',
        'solution': 'automation project',
        'qualifiable': True,
        'phrases': _question(
            'automation', 'automate', 'automated', 'rpa', 'bpa',
            'robotic process', 'workflow', 'workflows', 'back office',
            'back-office', 'repetitive', 'manual process', 'manual task',
            'manual work', 'scheduled task', 'process automation',
            'eliminate manual', 'human error',
        ),
        'pitch': 'We automate business processes end to end — workflows, '
                 'scheduled operations and RPA.',
        'recommendations': [
            ('home:rpa_bpa', 'RPA & BPA'),
            ('home:automation_home', 'Website Automation'),
        ],
        'questions': [
            ('process', 'Which process would you like to automate?'),
            ('current_systems', 'Which systems are involved — email, '
                                'spreadsheets, your website, an ERP?'),
            ('pain_points', 'What are the most repetitive steps today?'),
            ('goal', 'What would a good outcome look like — fewer manual steps, '
                     'faster turnaround, or fewer errors?'),
        ],
        'follow_ups': [
            'How does workflow automation work?',
            'What processes can be automated?',
            'Can you automate tasks across different systems?',
        ],
    },
    'integration': {
        'label': 'Systems Integration',
        'solution': 'integration project',
        'qualifiable': True,
        'phrases': _question(
            'integration', 'integrations', 'integrate', 'integrating',
            'connect', 'connecting', 'connector', 'connectors', 'sync',
            'synchronise', 'synchronize', 'api', 'webhook',
            'talk to each other', 'share data', 'import export',
            'third party', 'third-party', 'crm', 'salesforce', 'hubspot',
        ),
        'pitch': 'We connect websites, CRMs, ERPs and other tools so data '
                 'flows between them.',
        'recommendations': [('integration:integration_homepage', 'Integration')],
        'questions': [
            ('business_type', 'What type of business do you run?'),
            ('data_sources', 'Which systems need to connect — website, CRM, '
                             'ERP, spreadsheets?'),
            ('requirements', 'What data should move between them — contacts, '
                             'orders, reports?'),
            ('goal', 'What should happen once they are connected?'),
        ],
        'follow_ups': [
            'Which systems can you connect?',
            'Can you connect my website and CRM?',
            'How does data integration work?',
        ],
    },
    'branding': {
        'label': 'Brand & Design',
        'solution': 'design project',
        'qualifiable': True,
        'phrases': _question(
            'branding', 'brand identity', 'logo', 'visual identity',
            'brand guidelines', 'rebrand', 'ui design', 'ux design',
            'user interface design', 'redesign', 'design system',
        ),
        'pitch': 'We handle brand identity work, from a logo to a full set of '
                 'guidelines, and product design alongside it.',
        'recommendations': [
            ('branding:landing', 'Branding'),
            ('home:ui_design', 'UI Design'),
        ],
        'questions': [
            ('business_type', 'What type of business is the brand for?'),
            ('requirements', 'Do you need a new logo, a full identity, or a '
                             'redesign of what you have?'),
            ('existing_website', 'Do you already have brand guidelines or a '
                                 'website we should work from?'),
        ],
        'follow_ups': [
            'What does a branding project include?',
            'Do you redesign existing brands?',
            'What does your design process look like?',
        ],
    },
    'seo': {
        'label': 'SEO',
        'solution': 'SEO work',
        'qualifiable': True,
        'phrases': _question(
            'seo', 'search engine optimisation', 'search engine optimization',
            'search ranking', 'search rankings', 'google ranking', 'google rankings',
            'organic traffic', 'keyword research', 'backlinks', 'on page seo',
            'technical seo', 'serp',
        ),
        'pitch': 'We work on SEO across the technical, content and structure '
                 'sides of a site.',
        'recommendations': [('seo_analyzer:seo_home_marketing', 'SEO Services')],
        'questions': [
            ('website', 'What is your website address?'),
            ('goal', 'Are you after more organic traffic, technical fixes, '
                     'or content?'),
            ('current_systems', 'Do you already do any SEO work?'),
        ],
        'follow_ups': [
            'How do you improve SEO for a website?',
            'Can you audit my website SEO?',
            'What SEO tools do you offer?',
        ],
    },
    'website': {
        'label': 'Web Development',
        'solution': 'website project',
        'qualifiable': True,
        'phrases': _question(
            'website', 'web site', 'web page', 'webpage', 'web development',
            'web app', 'web application', 'landing page', 'online presence',
            'corporate site', 'business site', 'site for', 'web design',
        ),
        'pitch': 'Yes — we build custom websites and web applications, from a '
                 'business site to a full platform.',
        'recommendations': [
            ('home:web_development', 'Web Development'),
            ('home:build_website', 'Request a Website'),
        ],
        'questions': [
            ('business_type', 'What type of business is the website for?'),
            ('goal', 'What should the website do for you — sell, take bookings, '
                     'generate leads, or present the business?'),
            ('requirements', 'Any must-have features — online payments, forms, '
                             'a blog, multiple languages?'),
            ('existing_website', 'Do you already have a website or a domain?'),
            ('timeline', 'Do you have a timeline in mind?'),
        ],
        'follow_ups': [
            'What type of websites do you build?',
            'How long does a website project take?',
            'Do you redesign existing websites?',
        ],
    },
    'software': {
        'label': 'Custom Software',
        'solution': 'custom software project',
        'qualifiable': True,
        'phrases': _question(
            'custom software', 'software development', 'internal tool',
            'business platform', 'portal', 'saas', 'mvp', 'bespoke',
            'custom system', 'client portal', 'customer portal',
            'booking system', 'management system',
        ),
        'pitch': 'We build custom software and web applications around your '
                 'business logic, from an MVP to an internal tool.',
        'recommendations': [('home:software_home', 'Software Development')],
        'questions': [
            ('business_type', 'What type of business is it for?'),
            ('problem', 'What problem should the software solve?'),
            ('users', 'Who would use it, and what should they be able to do?'),
            ('current_systems', 'What do you use today for this?'),
        ],
        'follow_ups': [
            'What technologies do you build with?',
            'Can you build an internal tool for my team?',
            'How do you price a custom build?',
        ],
    },
    # ── Capability, not a service ──
    'browser_automation': {
        'label': 'Browser Automation',
        'solution': 'automation project',
        'qualifiable': False,
        'capability_for': 'automation',
        'phrases': _question(
            'browser automation', 'web automation', 'automate the browser',
            'automate our browser', 'scraping', 'scrape', 'web scraper',
            'selenium', 'headless browser', 'browser robot',
        ),
    },
    # ── Platform feature, informational only ──
    'monitoring': {
        'label': 'Platform Monitoring',
        'solution': 'monitoring',
        'qualifiable': False,
        'phrases': _question(
            'monitoring', 'uptime', 'downtime', 'response time',
            'availability', 'status page', 'alerts', 'alerting',
        ),
    },
}

# How a capability question is answered when the visitor is asking whether it
# can be bought: clear the distinction, then carry the conversation into the
# service that actually covers the work.
CAPABILITY_REPLY = (
    'Browser automation is a capability we use inside our automation and web '
    'projects rather than a product sold on its own. If there is a browser-based '
    'process you would like automated, that normally belongs in an automation '
    'project.'
)

# Chips offered once the guide has enough to hand the conversation over.
READY_SUGGESTIONS = [
    'Request a consultation',
    'Get a quote',
    'Tell me more about implementation',
]


def detect_intent(text, page_service=''):
    """Best-matching intent for ``text``: ``(key, confidence)`` or ``(None, 0)``.

    ``page_service`` — the service the visitor is currently reading about —
    breaks ties in the page's favour and stands in when the message is vague
    ("I need something like this" on the dashboards page).
    """
    text = text or ''
    best_key = None
    best_score = 0
    for key, spec in INTENTS.items():
        score = sum(1 for match in spec['phrases'].finditer(text) if match)
        if score > best_score:
            best_key, best_score = key, score

    if page_service and page_service in INTENTS:
        if best_key is None:
            best_key, best_score = page_service, 1
        elif best_key == page_service:
            best_score += 1

    if best_key is None:
        return None, 0.0
    confidence = min(0.99, 0.55 + 0.15 * (best_score - 1))
    return best_key, round(confidence, 2)
