"""Page-aware defaults rendered with the page itself.

The guide's opening line and its first few suggested questions belong to the
page the visitor is on, and they must be there the moment the panel opens —
not one round trip later, and not at all if the network is down. So the same
registry the live endpoint serves from is also rendered into the page, and the
widget treats it as the floor: it shows this until (and unless) the endpoint
answers with the access-filtered, index-checked version.
"""
from .page_context import DEFAULT_CONTEXT, static_context

# What the guide falls back to if even the registry cannot be read: the same
# opening line the endpoint would give any page.
_BROKEN = {
    'title': DEFAULT_CONTEXT['title'],
    'category': DEFAULT_CONTEXT['category'],
    'service': DEFAULT_CONTEXT['service'],
    'welcome': DEFAULT_CONTEXT['welcome'],
    'suggestions': [{'title': title} for title in DEFAULT_CONTEXT['suggestions']],
    'path': '',
    'url_name': '',
}


def chat_defaults(request):
    """Welcome copy and suggested questions for the page being rendered.

    Deliberately cheap — the registry and the URL table only, no database and
    no crawl index — because every template on the site runs it. Anything that
    needs a permission or a liveness check comes from the endpoint instead.
    """
    try:
        return {'chat_defaults': static_context(getattr(request, 'path', '') or '')}
    except Exception:
        # A broken page must not fail to render because the chatbot could not
        # work out where it is.
        return {'chat_defaults': dict(_BROKEN)}
