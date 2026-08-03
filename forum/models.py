import uuid
from django.db import models
from django.conf import settings
from django.utils.text import slugify
from django.utils import timezone
from django.db.models import F, Q


User = settings.AUTH_USER_MODEL


class ForumCategory(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True, max_length=120)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, blank=True, help_text='Font Awesome icon class')
    color = models.CharField(max_length=20, blank=True, help_text='Hex or named color')
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    post_count = models.PositiveIntegerField(default=0, editable=False)

    class Meta:
        ordering = ['order', 'name']
        verbose_name_plural = 'Forum categories'

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class ForumTag(models.Model):
    name = models.CharField(max_length=50)
    slug = models.SlugField(unique=True, max_length=60)
    color = models.CharField(max_length=20, blank=True, default='#6366f1')

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class ForumPostManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().select_related('author', 'category').prefetch_related('tags')

    def published(self):
        return self.get_queryset().filter(status='published', is_hidden=False)

    def trending(self):
        return self.published().order_by('-score', '-views_count')

    def latest(self):
        return self.published().order_by('-created_at')

    def most_votes(self):
        return self.published().order_by('-upvotes')

    def most_comments(self):
        from django.db.models import Count
        return self.published().annotate(
            comment_count=Count('comments')
        ).order_by('-comment_count')

    def pinned(self):
        return self.published().filter(is_pinned=True)

    def with_counts(self):
        return self.published()


class ForumPost(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('archived', 'Archived'),
    ]
    MODERATION_CHOICES = [
        ('approved', 'Approved'),
        ('pending', 'Pending'),
        ('reported', 'Reported'),
    ]

    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='forum_posts')
    category = models.ForeignKey(ForumCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name='posts')
    title = models.CharField(max_length=300)
    slug = models.SlugField(unique=True, max_length=350)
    content = models.TextField()
    excerpt = models.TextField(blank=True, max_length=500)
    featured_image = models.URLField(blank=True)
    tags = models.ManyToManyField(ForumTag, blank=True, related_name='posts')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    moderation_status = models.CharField(max_length=20, choices=MODERATION_CHOICES, default='approved')
    is_pinned = models.BooleanField(default=False)
    is_locked = models.BooleanField(default=False)
    is_hidden = models.BooleanField(default=False, help_text='Author can hide post from public listing')
    views_count = models.PositiveIntegerField(default=0)
    upvotes = models.PositiveIntegerField(default=0)
    downvotes = models.PositiveIntegerField(default=0)
    score = models.IntegerField(default=0)
    bookmarks_count = models.PositiveIntegerField(default=0, editable=False)
    is_showcase = models.BooleanField(default=False)
    project_name = models.CharField(max_length=200, blank=True)
    tech_stack = models.CharField(max_length=500, blank=True)
    github_link = models.URLField(blank=True)
    live_demo = models.URLField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ForumPostManager()

    class Meta:
        ordering = ['-is_pinned', '-created_at']
        indexes = [
            models.Index(fields=['-score', '-created_at']),
            models.Index(fields=['status', 'moderation_status', '-created_at']),
            models.Index(fields=['author', 'status', '-created_at']),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title)
            slug = base
            counter = 1
            while ForumPost.objects.filter(slug=slug).exists():
                slug = f"{base}-{counter}"
                counter += 1
            self.slug = slug
        if not self.excerpt and self.content:
            self.excerpt = self.content[:300]
        super().save(*args, **kwargs)

    def update_vote_counts(self):
        from django.db.models import Count, Q
        agg = self.reactions.aggregate(
            up=Count('pk', filter=Q(reaction_type='upvote')),
            down=Count('pk', filter=Q(reaction_type='downvote')),
        )
        self.upvotes = agg['up']
        self.downvotes = agg['down']
        self.score = self.upvotes - self.downvotes
        self.save(update_fields=['upvotes', 'downvotes', 'score', 'updated_at'])

    @property
    def comment_count(self):
        return self.comments.filter(is_active=True).count()

    @property
    def reading_time(self):
        wpm = 200
        words = len(self.content.split())
        minutes = max(1, round(words / wpm))
        return minutes


class ForumComment(models.Model):
    post = models.ForeignKey(ForumPost, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='forum_comments')
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='replies')
    content = models.TextField()
    upvotes = models.PositiveIntegerField(default=0)
    downvotes = models.PositiveIntegerField(default=0)
    is_solution = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_solution', 'created_at']
        indexes = [
            models.Index(fields=['post', 'created_at']),
            models.Index(fields=['author', '-created_at']),
        ]

    def __str__(self):
        return f"Comment by {self.author.username} on {self.post.title[:50]}"

    def update_vote_counts(self):
        agg = self.reactions.aggregate(
            up=models.Count('pk', filter=models.Q(reaction_type='upvote')),
            down=models.Count('pk', filter=models.Q(reaction_type='downvote')),
        )
        self.upvotes = agg['up']
        self.downvotes = agg['down']
        self.save(update_fields=['upvotes', 'downvotes', 'updated_at'])

    @property
    def get_depth(self):
        depth = 0
        parent = self.parent
        while parent:
            depth += 1
            if depth > 10:
                break
            parent = parent.parent
        return depth


class ForumReaction(models.Model):
    REACTION_TYPES = [
        ('upvote', 'Upvote'),
        ('downvote', 'Downvote'),
        ('like', 'Like'),
        ('love', 'Love'),
        ('insightful', 'Insightful'),
        ('funny', 'Funny'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='forum_reactions')
    post = models.ForeignKey(ForumPost, on_delete=models.CASCADE, null=True, blank=True, related_name='reactions')
    comment = models.ForeignKey(ForumComment, on_delete=models.CASCADE, null=True, blank=True, related_name='reactions')
    reaction_type = models.CharField(max_length=20, choices=REACTION_TYPES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [
            ('user', 'post', 'reaction_type'),
            ('user', 'comment', 'reaction_type'),
        ]
        indexes = [
            models.Index(fields=['user', 'post']),
            models.Index(fields=['user', 'comment']),
        ]

    def __str__(self):
        target = self.post or self.comment
        return f"{self.user.username} {self.reaction_type} {target}"


class Bookmark(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='forum_bookmarks')
    post = models.ForeignKey(ForumPost, on_delete=models.CASCADE, related_name='bookmarks')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['user', 'post']
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} bookmarked {self.post.title[:50]}"


class FollowCategory(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='followed_categories')
    category = models.ForeignKey(ForumCategory, on_delete=models.CASCADE, related_name='followers')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['user', 'category']
        verbose_name_plural = 'Follow categories'

    def __str__(self):
        return f"{self.user.username} follows {self.category.name}"


class FollowUser(models.Model):
    follower = models.ForeignKey(User, on_delete=models.CASCADE, related_name='following')
    following = models.ForeignKey(User, on_delete=models.CASCADE, related_name='followers')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['follower', 'following']

    def __str__(self):
        return f"{self.follower.username} follows {self.following.username}"


class ForumReport(models.Model):
    REASON_CHOICES = [
        ('spam', 'Spam'),
        ('harassment', 'Harassment'),
        ('off_topic', 'Off-topic'),
        ('copyright', 'Copyright violation'),
        ('other', 'Other'),
    ]
    reporter = models.ForeignKey(User, on_delete=models.CASCADE, related_name='forum_reports')
    post = models.ForeignKey(ForumPost, on_delete=models.CASCADE, null=True, blank=True, related_name='reports')
    comment = models.ForeignKey(ForumComment, on_delete=models.CASCADE, null=True, blank=True, related_name='reports')
    reason = models.CharField(max_length=20, choices=REASON_CHOICES)
    description = models.TextField(blank=True)
    is_resolved = models.BooleanField(default=False)
    resolved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='resolved_reports')
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        target = self.post or self.comment
        return f"Report: {self.reason} on {target}"


class ForumBadge(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, blank=True)
    color = models.CharField(max_length=20, blank=True, default='#6366f1')
    criteria = models.CharField(max_length=200, blank=True, help_text='How to earn this badge')

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class UserBadge(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='forum_badges')
    badge = models.ForeignKey(ForumBadge, on_delete=models.CASCADE, related_name='awards')
    awarded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['user', 'badge']
        ordering = ['-awarded_at']

    def __str__(self):
        return f"{self.user.username} - {self.badge.name}"


class ForumEvent(models.Model):
    EVENT_TYPES = [
        ('hackathon', 'Hackathon'),
        ('webinar', 'Webinar'),
        ('meetup', 'Meetup'),
        ('workshop', 'Workshop'),
    ]
    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    event_type = models.CharField(max_length=20, choices=EVENT_TYPES)
    description = models.TextField()
    location = models.CharField(max_length=200, blank=True)
    is_online = models.BooleanField(default=True)
    meeting_link = models.URLField(blank=True)
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    registration_link = models.URLField(blank=True)
    is_published = models.BooleanField(default=False)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='forum_events')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-start_date']

    def __str__(self):
        return self.title


class ForumJob(models.Model):
    JOB_TYPES = [
        ('internship', 'Internship'),
        ('freelance', 'Freelance'),
        ('full_time', 'Full-Time'),
        ('website_request', 'Website Request'),
        ('brand_design', 'Brand Design Project'),
    ]
    company = models.CharField(max_length=200)
    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    job_type = models.CharField(max_length=20, choices=JOB_TYPES)
    description = models.TextField()
    requirements = models.TextField(blank=True)
    location = models.CharField(max_length=200, blank=True)
    is_remote = models.BooleanField(default=False)
    salary_range = models.CharField(max_length=100, blank=True)
    application_link = models.URLField(blank=True)
    contact_email = models.EmailField(blank=True)
    is_active = models.BooleanField(default=True)
    posted_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='forum_jobs')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} at {self.company}"