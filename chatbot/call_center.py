"""Staff-side call centre.

Where an escalated chat lands: a queue of visitors who asked the bot for a
person, each with the full transcript attached. An agent claims a ticket, types
replies that appear in the visitor's chat, and resolves it.

Beside the queue sits the full chat log. The queue only holds conversations that
became a ticket, so it cannot answer "what did that visitor actually ask?", and
most of the answers that would make a good impression were never escalated. The
log is therefore read-only: an agent can read any conversation, and turning one
into work is an explicit escalate.

Access is login + is_staff. The transcripts are customer conversations, so this
is deliberately the narrowest gate that still lets support staff in.
"""
from django.contrib import messages as flash
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from .models import CallRequest, ChatMessage, ChatSession

PAGE_SIZE = 25

# Lazy querysets, one per queue tab. They are never evaluated here, only
# filtered further per request, so a single definition can be reused safely.
STATUS_FILTERS = {
    'open': CallRequest.objects.open(),
    'new': CallRequest.objects.filter(status=CallRequest.STATUS_NEW),
    'mine': None,  # filled in per-request, needs the agent
    'resolved': CallRequest.objects.filter(status=CallRequest.STATUS_RESOLVED),
    'all': CallRequest.objects.all(),
}

# The same three ways of looking at the log, without the queue's status tabs.
CHAT_FILTERS = ('all', 'escalated', 'plain')


def _visible(queryset, request):
    """Trim the queue to what this agent is allowed to see.

    Staff see everything. A non-staff authenticated user only ever sees their own
    requests, which keeps the route from being a way to read other people's chats
    if it is ever opened to regular accounts.
    """
    if request.user.is_staff:
        return queryset
    return queryset.filter(requested_by=request.user)


def _can_act_as_agent(request, ticket):
    """Whether this user may work the ticket, not just read their own copy.

    Reading your own conversation is harmless; posting as OnWebApp staff into it
    is not, so only staff and the assigned agent may answer.
    """
    return request.user.is_staff or ticket.assigned_to_id == request.user.id


def _visible_sessions(queryset, request):
    """The same visibility rule as the queue, applied to raw chat sessions.

    A session with no ticket still has to obey the gate: it is a customer
    conversation, and this is the only thing standing between the log and any
    logged-in visitor.
    """
    if request.user.is_staff:
        return queryset
    return queryset.filter(user=request.user)


def _refuse_agent_action(request, ticket):
    flash.error(request, 'You are not assigned to this request.')
    return redirect('chatbot:call_center_detail', pk=ticket.pk)


def _filter_kwargs(request):
    selected = request.GET.get('filter') or 'open'
    if selected not in STATUS_FILTERS:
        selected = 'open'

    if selected == 'mine':
        base = _visible(CallRequest.objects.filter(
            status=CallRequest.STATUS_CLAIMED, assigned_to=request.user), request)
    else:
        base = _visible(STATUS_FILTERS[selected], request)

    query = (request.GET.get('q') or '').strip()
    if query:
        base = base.filter(
            Q(reason__icontains=query)
            | Q(requested_by__username__icontains=query)
            | Q(requested_by__email__icontains=query)
            | Q(session__session_id__icontains=query)
            | Q(assigned_to__username__icontains=query)
        )

    return base, selected, query


@login_required
def dashboard(request):
    queryset, selected, query = _filter_kwargs(request)

    # Annotated rather than a property per row: one query for the page instead
    # of a message count per ticket.
    queryset = queryset.annotate(
        message_total=Count('session__messages', distinct=True),
        agent_total=Count('session__messages',
                          filter=Q(session__messages__sender=ChatMessage.SENDER_AGENT),
                          distinct=True),
    )

    open_total = _visible(CallRequest.objects.open(), request).count()
    mine_total = _visible(
        CallRequest.objects.filter(status=CallRequest.STATUS_CLAIMED,
                                   assigned_to=request.user), request).count()

    paginator = Paginator(queryset.order_by('-escalated_at'), PAGE_SIZE)
    page = paginator.get_page(request.GET.get('page'))

    querystring = request.GET.copy()
    querystring.pop('page', None)

    filter_labels = {
        'open': _('Open'),
        'new': _('Unclaimed'),
        'mine': _('Assigned to me'),
        'resolved': _('Resolved'),
        'all': _('All'),
    }

    return render(request, 'chatbot/call_center.html', {
        'page_obj': page,
        'paginator': paginator,
        'selected_filter': selected,
        'query': query,
        'querystring': querystring.urlencode(),
        'open_total': open_total,
        'mine_total': mine_total,
        'tickets': page.object_list,
        'filter_labels': filter_labels,
        'status_new': CallRequest.STATUS_NEW,
        'status_claimed': CallRequest.STATUS_CLAIMED,
        'status_resolved': CallRequest.STATUS_RESOLVED,
    })


@login_required
def detail(request, pk):
    ticket = get_object_or_404(
        _visible(CallRequest.objects.select_related(
            'session', 'requested_by', 'assigned_to'), request), pk=pk)

    can_manage = request.user.is_staff or ticket.assigned_to_id == request.user.id

    if request.method == 'POST':
        return _handle_post(request, ticket, can_manage)

    transcript = list(ticket.session.messages.select_related('agent'))

    return render(request, 'chatbot/call_center_detail.html', {
        'ticket': ticket,
        'transcript': transcript,
        'can_manage': can_manage,
        'status_new': CallRequest.STATUS_NEW,
        'status_claimed': CallRequest.STATUS_CLAIMED,
        'status_resolved': CallRequest.STATUS_RESOLVED,
    })


@require_POST
@login_required
def claim(request, pk):
    ticket = get_object_or_404(
        _visible(CallRequest.objects.select_related('assigned_to'), request), pk=pk)

    if not request.user.is_staff:
        return _refuse_agent_action(request, ticket)

    if ticket.status == CallRequest.STATUS_RESOLVED:
        flash.error(request, 'That request was already resolved.')
        return redirect('chatbot:call_center_detail', pk=ticket.pk)

    # Someone else already has this conversation open. Taking it silently would
    # let two agents write into the same visitor's chat.
    if ticket.assigned_to_id and ticket.assigned_to_id != request.user.id:
        flash.info(request, f'{ticket.assigned_to} is already answering this visitor.')
        return redirect('chatbot:call_center_detail', pk=ticket.pk)

    ticket.claim(request.user)
    flash.success(request, 'You are now answering this visitor.')
    return redirect('chatbot:call_center_detail', pk=ticket.pk)


@require_POST
@login_required
def release(request, pk):
    ticket = get_object_or_404(
        _visible(CallRequest.objects.select_related('assigned_to'), request), pk=pk)

    if not _can_act_as_agent(request, ticket):
        return _refuse_agent_action(request, ticket)

    ticket.release()
    flash.info(request, 'Released back to the queue.')
    return redirect('chatbot:call_center_detail', pk=ticket.pk)


@require_POST
@login_required
def reply(request, pk):
    """Post into the conversation. The visitor sees it in their chat panel."""
    ticket = get_object_or_404(
        _visible(CallRequest.objects.select_related('session'), request), pk=pk)

    if not _can_act_as_agent(request, ticket):
        return _refuse_agent_action(request, ticket)

    text = (request.POST.get('message') or '').strip()
    if not text:
        flash.error(request, 'Write something before sending.')
        return redirect('chatbot:call_center_detail', pk=ticket.pk)

    text = text[:2000]

    # Answering an unclaimed ticket is the same as claiming it first.
    if not ticket.assigned_to_id:
        ticket.claim(request.user)

    ChatMessage.objects.create(
        session=ticket.session,
        sender=ChatMessage.SENDER_AGENT,
        agent=request.user,
        content=text,
    )

    if request.POST.get('resolve'):
        ticket.resolve(text)

    return redirect('chatbot:call_center_detail', pk=ticket.pk)


def _handle_post(request, ticket, can_manage):
    """Handle the inline notes / resolve form on the detail page."""
    if not can_manage:
        flash.error(request, 'You are not assigned to this request.')
        return redirect('chatbot:call_center_detail', pk=ticket.pk)

    if 'resolve' in request.POST:
        ticket.resolve((request.POST.get('resolution') or '').strip())
        flash.success(request, 'Request resolved.')
    else:
        ticket.notes = (request.POST.get('notes') or '').strip()[:4000]
        ticket.save(update_fields=['notes', 'updated_at'])
        flash.success(request, 'Notes saved.')

    return redirect('chatbot:call_center_detail', pk=ticket.pk)


@login_required
def chats(request):
    """Every conversation, escalated or not.

    Read-only. The queue answers "who is waiting?", this answers "what is this
    person actually trying to do?", and the two lists are deliberately separate:
    a queue that held every greeting would stop meaning anything.
    """
    queryset = _visible_sessions(ChatSession.objects.select_related('user'), request)

    selected = request.GET.get('filter') or 'all'
    if selected not in CHAT_FILTERS:
        selected = 'all'
    if selected == 'escalated':
        queryset = queryset.filter(call_request__isnull=False)
    elif selected == 'plain':
        queryset = queryset.filter(call_request__isnull=True)

    query = (request.GET.get('q') or '').strip()
    if query:
        # Searching the words people actually typed, not just the metadata.
        queryset = queryset.filter(
            Q(session_id__icontains=query)
            | Q(user__username__icontains=query)
            | Q(user__email__icontains=query)
            | Q(messages__content__icontains=query)
        ).distinct()

    queryset = queryset.annotate(
        message_total=Count('messages', distinct=True),
        user_total=Count(
            'messages', filter=Q(messages__sender=ChatMessage.SENDER_USER),
            distinct=True),
        # Whether a session became a ticket, counted rather than followed: a
        # reverse one-to-one that does not exist cannot be select_related, and
        # reading it per row would be a query for every line on the page.
        ticket_total=Count('call_request', distinct=True),
    ).order_by('-updated_at')

    paginator = Paginator(queryset, PAGE_SIZE)
    page = paginator.get_page(request.GET.get('page'))

    # One extra query for the newest line of every row on this page, rather than
    # a last() per session.
    sessions = list(page.object_list)
    newest = {}
    for message in ChatMessage.objects.filter(
            session__in=sessions).order_by('session_id', '-timestamp'):
        newest.setdefault(message.session_id, message)
    for session in sessions:
        session.preview = newest.get(session.pk)
        session.has_ticket = session.ticket_total > 0

    querystring = request.GET.copy()
    querystring.pop('page', None)

    filter_labels = {
        'all': _('All chats'),
        'escalated': _('Escalated'),
        'plain': _('Never escalated'),
    }

    return render(request, 'chatbot/call_center_chats.html', {
        'page_obj': page,
        'paginator': paginator,
        'selected_filter': selected,
        'query': query,
        'querystring': querystring.urlencode(),
        'chats': sessions,
        'filter_labels': filter_labels,
        'total_chats': _visible_sessions(ChatSession.objects.all(), request).count(),
        'escalated_total': _visible_sessions(
            ChatSession.objects.filter(call_request__isnull=False), request).count(),
    })


@login_required
def chat_detail(request, session_id):
    """Read one conversation. No reply box: see :func:`escalate`."""
    session = get_object_or_404(
        _visible_sessions(ChatSession.objects.select_related('user'), request),
        session_id=session_id,
    )

    # OneToOne raises rather than returning None, and getattr swallows that.
    ticket = getattr(session, 'call_request', None)

    return render(request, 'chatbot/call_center_chat.html', {
        'chat': session,
        'transcript': list(session.messages.select_related('agent')),
        'ticket': ticket,
        'status_new': CallRequest.STATUS_NEW,
        'status_claimed': CallRequest.STATUS_CLAIMED,
        'status_resolved': CallRequest.STATUS_RESOLVED,
    })


@require_POST
@login_required
def escalate(request, session_id):
    """Turn a logged conversation into a ticket, then hand over to the queue.

    This is the only way to answer someone who never asked for a human, and it is
    a separate, deliberate click rather than a reply box on the transcript.
    """
    session = get_object_or_404(
        _visible_sessions(ChatSession.objects.select_related('user'), request),
        session_id=session_id,
    )

    if not request.user.is_staff:
        flash.error(request, 'You are not assigned to this request.')
        return redirect('chatbot:call_center_chat', session_id=session.session_id)

    existing = getattr(session, 'call_request', None)
    if existing:
        flash.info(request, 'This conversation is already in the queue.')
        return redirect('chatbot:call_center_detail', pk=existing.pk)

    # The visitor's own words are the most useful reason on the ticket.
    last_user_message = session.messages.filter(
        sender=ChatMessage.SENDER_USER).order_by('-timestamp').first()
    reason = ' '.join((last_user_message.content if last_user_message else '').split())
    if not reason:
        reason = 'Escalated by staff from the chat log'

    ticket = CallRequest.objects.create(
        session=session,
        requested_by=session.user,
        reason=reason[:200],
        # 'staff' rather than a channel the visitor picked: nobody clicked
        # anything, so claiming they did would be a lie in the audit trail.
        channel='staff',
        escalated_at=timezone.now(),
    )

    flash.success(request, 'Added to the queue. You can reply from the ticket page.')
    return redirect('chatbot:call_center_detail', pk=ticket.pk)


@login_required
def queue_api(request):
    """Small JSON poll so the queue badge count can update without a reload."""
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    scope = request.GET.get('scope') or 'open'
    if scope == 'mine':
        queryset = _visible(CallRequest.objects.filter(
            status=CallRequest.STATUS_CLAIMED, assigned_to=request.user), request)
    elif scope == 'resolved':
        queryset = _visible(CallRequest.objects.filter(
            status=CallRequest.STATUS_RESOLVED), request)
    else:
        queryset = _visible(CallRequest.objects.open(), request)

    counts = {
        'open': _visible(CallRequest.objects.open(), request).count(),
        'new': _visible(CallRequest.objects.filter(
            status=CallRequest.STATUS_NEW), request).count(),
        'mine': _visible(CallRequest.objects.filter(
            status=CallRequest.STATUS_CLAIMED, assigned_to=request.user), request).count(),
        'resolved': _visible(CallRequest.objects.filter(
            status=CallRequest.STATUS_RESOLVED), request).count(),
    }

    oldest = queryset.order_by('escalated_at').first()

    return JsonResponse({
        'count': queryset.count(),
        'counts': counts,
        'oldest_waiting': oldest.waiting_label if oldest else None,
        'oldest_age': oldest.waiting_seconds if oldest else None,
        'generated_at': timezone.now().isoformat(),
    })
