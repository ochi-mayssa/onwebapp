from django.db import models
from django.conf import settings
from django.utils import timezone


class ChatSession(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)
    session_id = models.CharField(max_length=100, unique=True)
    # Everything the guide remembers about this conversation: detected intent,
    # qualification stage, page context and the slots filled in so far. Server
    # side only — nothing here is ever sent back to the visitor verbatim.
    state = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Session {self.session_id} - {self.user}"


class ChatMessage(models.Model):
    # AGENT is written by the call centre dashboard, not the bot, but it lives
    # in the same log: the visitor sees one continuous transcript.
    SENDER_USER = 'USER'
    SENDER_BOT = 'BOT'
    SENDER_AGENT = 'AGENT'

    SENDER_CHOICES = [
        (SENDER_USER, 'User'),
        (SENDER_BOT, 'Bot'),
        (SENDER_AGENT, 'Agent'),
    ]

    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name='messages')
    sender = models.CharField(max_length=10, choices=SENDER_CHOICES)
    # Only set for AGENT messages, so the visitor is told who picked them up.
    agent = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                              null=True, blank=True, related_name='chat_messages')
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f"{self.sender}: {self.content[:50]}"

    def agent_label(self):
        """Display name for an agent message, falling back to a generic label."""
        if self.agent_id and self.agent:
            return self.agent.get_full_name() or self.agent.get_username()
        return 'Support'


class CallRequestQuerySet(models.QuerySet):
    def open(self):
        return self.filter(status__in=[CallRequest.STATUS_NEW, CallRequest.STATUS_CLAIMED])


class CallRequest(models.Model):
    """One visitor who asked the bot for a person.

    Created only by an explicit request ("call me", the Call button), never by
    the bot's low-confidence fallback, so the queue reflects real demand instead
    of every question the bot could not answer.

    The transcript is not copied here: it stays on ChatSession.messages so an
    agent always reads the live conversation, including anything said after the
    handoff.
    """

    STATUS_NEW = 'NEW'
    STATUS_CLAIMED = 'CLAIMED'
    STATUS_RESOLVED = 'RESOLVED'
    STATUS_CHOICES = [
        (STATUS_NEW, 'New'),
        (STATUS_CLAIMED, 'Claimed'),
        (STATUS_RESOLVED, 'Resolved'),
    ]

    # Ordered by how long an agent has already been sitting on it.
    AGE_PRIORITY = [
        (0, 'Under 5 min'),
        (1, '5 to 15 min'),
        (2, 'Over 15 min'),
    ]
    PRIORITY_UNDER_5 = 0
    PRIORITY_5_TO_15 = 1
    PRIORITY_OVER_15 = 2

    session = models.OneToOneField(ChatSession, on_delete=models.CASCADE,
                                   related_name='call_request')
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                     null=True, blank=True,
                                     related_name='call_requests')
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                    null=True, blank=True,
                                    related_name='assigned_call_requests')

    reason = models.CharField(max_length=200, blank=True)
    channel = models.CharField(
        max_length=20, blank=True,
        help_text='How the visitor was offered to connect: call, chat or form.',
    )

    status = models.CharField(max_length=10, choices=STATUS_CHOICES,
                              default=STATUS_NEW, db_index=True)

    notes = models.TextField(blank=True)
    resolution = models.TextField(blank=True)

    escalated_at = models.DateTimeField(default=timezone.now)
    assigned_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CallRequestQuerySet.as_manager()

    class Meta:
        ordering = ['-escalated_at']
        indexes = [
            models.Index(fields=['status', '-escalated_at']),
        ]
        verbose_name_plural = 'call requests'

    def __str__(self):
        who = self.requested_by or self.session_id[:8]
        return f"{who} ({self.get_status_display()})"

    @property
    def is_open(self):
        return self.status in (self.STATUS_NEW, self.STATUS_CLAIMED)

    @property
    def waiting_seconds(self):
        end = self.resolved_at or timezone.now()
        return int((end - self.escalated_at).total_seconds())

    @property
    def waiting_label(self):
        seconds = self.waiting_seconds
        if seconds < 300:
            return 'Under 5 min'
        if seconds < 900:
            return '5 to 15 min'
        return 'Over 15 min'

    @property
    def priority(self):
        seconds = self.waiting_seconds
        if seconds < 300:
            return self.PRIORITY_UNDER_5
        if seconds < 900:
            return self.PRIORITY_5_TO_15
        return self.PRIORITY_OVER_15

    @property
    def priority_label(self):
        return dict(self.AGE_PRIORITY)[self.priority]

    @property
    def transcript(self):
        return self.session.messages.select_related('session')

    @property
    def message_count(self):
        return self.session.messages.count()

    @property
    def agent_reply_count(self):
        return self.session.messages.filter(sender=ChatMessage.SENDER_AGENT).count()

    def claim(self, agent):
        """Assign to an agent.

        Idempotent for the same agent, and a no-op once resolved or when another
        agent already owns the conversation, so a double click or a second staff
        member cannot hijack a live chat.
        """
        if self.status == self.STATUS_RESOLVED:
            return False
        if self.assigned_to_id and self.assigned_to_id != agent.pk:
            return False
        if self.assigned_to_id == agent.pk and self.status == self.STATUS_CLAIMED:
            return True
        self.assigned_to = agent
        self.assigned_at = timezone.now()
        self.status = self.STATUS_CLAIMED
        self.save(update_fields=['assigned_to', 'assigned_at', 'status', 'updated_at'])
        return True

    def release(self):
        self.assigned_to = None
        self.assigned_at = None
        if self.status == self.STATUS_CLAIMED:
            self.status = self.STATUS_NEW
        self.save(update_fields=['assigned_to', 'assigned_at', 'status', 'updated_at'])

    def resolve(self, resolution=''):
        self.status = self.STATUS_RESOLVED
        self.resolved_at = timezone.now()
        if resolution:
            self.resolution = resolution[:2000]
        self.save(update_fields=['status', 'resolved_at', 'resolution', 'updated_at'])


class ChatLead(models.Model):
    """A conversation the guide turned into a qualified request.

    Created only when the visitor confirms a consultation request, so the row
    always reflects something the visitor actually asked for. The summary text
    is written from the answers they gave during the chat — never guessed —
    and is what the team reads first in the admin and on the transcript page.

    One per session: confirming twice updates the existing lead rather than
    queuing duplicates.
    """

    STATUS_NEW = 'new'
    STATUS_CONTACTED = 'contacted'
    STATUS_CLOSED = 'closed'
    STATUS_CHOICES = [
        (STATUS_NEW, 'New'),
        (STATUS_CONTACTED, 'Contacted'),
        (STATUS_CLOSED, 'Closed'),
    ]

    session = models.OneToOneField(ChatSession, on_delete=models.CASCADE,
                                   related_name='lead')
    # Canonical intent key (dashboard, erp, website, ...) plus a human label
    # for list views where the key means nothing on its own.
    intent = models.CharField(max_length=40, blank=True)
    solution = models.CharField(max_length=120, blank=True)
    summary = models.TextField()
    # Raw qualification slots, so the team sees the answers behind the summary.
    data = models.JSONField(default=dict, blank=True)
    contact = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES,
                              default=STATUS_NEW, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.solution or self.intent or 'Lead'} ({self.get_status_display()})"

