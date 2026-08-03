import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseForbidden
from django.db import models
from django.db.models import Count, Q
from django.utils import timezone
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.contrib import messages
from django.views.decorators.http import require_POST

from .models import (
    ForumCategory, ForumTag, ForumPost, ForumComment, ForumReaction,
    Bookmark, FollowUser, FollowCategory, ForumBadge, UserBadge,
    ForumEvent, ForumJob, ForumReport,
)
from .forms import (
    ForumPostForm, ForumCommentForm, ForumReportForm,
    ForumJobForm, ForumEventForm, ForumSearchForm,
)
from .permissions import (
    can_create_post, can_edit_post, can_delete_post, can_moderate,
    can_pin_post, can_lock_post, can_comment, can_vote, can_report,
    get_user_reputation, ForumPermissions,
)
from .services import (
    get_trending_posts, get_latest_discussions, get_top_contributors,
    get_community_stats, check_and_award_badges, get_duplicate_posts,
    contains_profanity, toggle_bookmark, toggle_follow_user,
    toggle_follow_category, create_notification,
)


def forum_home(request):
    pinned = ForumPost.objects.pinned()[:5]
    trending = get_trending_posts(10)
    latest = get_latest_discussions(15)

    sort = request.GET.get('sort', 'latest')
    if sort == 'trending':
        all_posts = ForumPost.objects.trending()
    elif sort == 'votes':
        all_posts = ForumPost.objects.most_votes()
    else:
        all_posts = ForumPost.objects.latest()

    paginator = Paginator(all_posts, 20)
    page = request.GET.get('page', 1)
    try:
        all_posts_page = paginator.page(page)
    except (PageNotAnInteger, EmptyPage):
        all_posts_page = paginator.page(1)

    categories = ForumCategory.objects.filter(is_active=True).annotate(
        total_posts=Count('posts', filter=Q(posts__status='published'))
    )
    top_tags = ForumTag.objects.annotate(
        total_posts=Count('posts', filter=Q(posts__status='published'))
    ).order_by('-total_posts')[:15]
    top_users = get_top_contributors('all', 10)
    stats = get_community_stats()
    perm = ForumPermissions(request.user) if request.user.is_authenticated else None

    return render(request, 'forum/home.html', {
        'pinned': pinned,
        'trending': trending,
        'latest': latest,
        'all_posts': all_posts_page,
        'sort': sort,
        'categories': categories,
        'top_tags': top_tags,
        'top_users': top_users,
        'stats': stats,
        'perm': perm,
    })


def category_detail(request, slug):
    category = get_object_or_404(ForumCategory, slug=slug, is_active=True)
    posts = ForumPost.objects.with_counts().filter(
        category=category, status='published'
    )
    sort = request.GET.get('sort', 'newest')
    if sort == 'trending':
        posts = posts.order_by('-score', '-views_count')
    elif sort == 'votes':
        posts = posts.order_by('-upvotes')
    elif sort == 'comments':
        posts = posts.order_by('-comment_count')
    else:
        posts = posts.order_by('-created_at')

    paginator = Paginator(posts, 20)
    page = request.GET.get('page', 1)
    try:
        posts_page = paginator.page(page)
    except (PageNotAnInteger, EmptyPage):
        posts_page = paginator.page(1)

    return render(request, 'forum/category.html', {
        'category': category,
        'posts': posts_page,
        'sort': sort,
        'is_following': (
            FollowCategory.objects.filter(
                user=request.user, category=category
            ).exists() if request.user.is_authenticated else False
        ),
    })


def tag_detail(request, slug):
    tag = get_object_or_404(ForumTag, slug=slug)
    posts = ForumPost.objects.with_counts().filter(
        tags=tag, status='published'
    ).order_by('-created_at')
    paginator = Paginator(posts, 20)
    page = request.GET.get('page', 1)
    try:
        posts_page = paginator.page(page)
    except (PageNotAnInteger, EmptyPage):
        posts_page = paginator.page(1)

    return render(request, 'forum/tag.html', {
        'tag': tag,
        'posts': posts_page,
    })


@login_required
def post_create(request):
    if not can_create_post(request.user):
        messages.error(request, 'You do not have permission to create posts.')
        return redirect('forum:home')

    if request.method == 'POST':
        form = ForumPostForm(request.POST)
        if form.is_valid():
            post = form.save(commit=False)
            post.author = request.user
            if contains_profanity(post.content) or contains_profanity(post.title):
                messages.error(request, 'Your post contains prohibited content.')
                return render(request, 'forum/post_form.html', {'form': form, 'edit': False})

            duplicate = get_duplicate_posts(post.content, request.user)
            if duplicate:
                messages.warning(
                    request,
                    f'This looks very similar to your post "{duplicate.title}". '
                    f'Please check before posting again.'
                )

            if post.status == 'published' and not post.excerpt:
                post.excerpt = post.content[:300]
            post.save()
            form._save_tags(post, form.cleaned_data.get('tags_input', ''))
            if post.status == 'published':
                check_and_award_badges(request.user)
            messages.success(request, 'Your post has been created!')
            return redirect('forum:post_detail', slug=post.slug)
    else:
        form = ForumPostForm(initial={'status': 'published'})

    return render(request, 'forum/post_form.html', {
        'form': form,
        'edit': False,
    })


def post_detail(request, slug):
    post = get_object_or_404(
        ForumPost.objects.select_related('author', 'author__profile', 'category'),
        slug=slug,
    )
    ForumPost.objects.filter(pk=post.pk).update(views_count=post.views_count + 1)

    is_owner = request.user.is_authenticated and request.user == post.author

    comments = post.comments.filter(parent=None, is_active=True).select_related(
        'author', 'author__profile'
    ).prefetch_related('replies__author__profile')

    related = ForumPost.objects.with_counts().filter(
        category=post.category
    ).exclude(pk=post.pk)[:5]

    is_bookmarked = False
    user_vote = None
    perm = None
    analytics = None
    open_reports = None

    if request.user.is_authenticated:
        is_bookmarked = Bookmark.objects.filter(user=request.user, post=post).exists()
        user_reaction = ForumReaction.objects.filter(
            user=request.user, post=post
        ).first()
        if user_reaction:
            user_vote = user_reaction.reaction_type
        perm = ForumPermissions(request.user)

        if is_owner:
            reaction_breakdown = ForumReaction.objects.filter(post=post).values(
                'reaction_type'
            ).annotate(count=models.Count('id')).order_by('-count')
            bookmark_count = Bookmark.objects.filter(post=post).count()
            share_estimates = {
                'twitter': 0,
                'linkedin': 0,
                'facebook': 0,
            }
            open_reports = ForumReport.objects.filter(post=post, is_resolved=False).count()

            analytics = {
                'views': post.views_count,
                'upvotes': post.upvotes,
                'downvotes': post.downvotes,
                'score': post.score,
                'comments': post.comment_count,
                'bookmarks': bookmark_count,
                'reactions': list(reaction_breakdown),
                'shares': share_estimates,
            }

    return render(request, 'forum/post_detail.html', {
        'post': post,
        'comments': comments,
        'related': related,
        'is_bookmarked': is_bookmarked,
        'user_vote': user_vote,
        'perm': perm,
        'is_owner': is_owner,
        'can_edit_post': can_edit_post(request.user, post) if request.user.is_authenticated else False,
        'analytics': analytics,
        'open_reports': open_reports,
    })


@login_required
def post_edit(request, slug):
    post = get_object_or_404(ForumPost, slug=slug)
    if not can_edit_post(request.user, post):
        return HttpResponseForbidden()

    if request.method == 'POST':
        form = ForumPostForm(request.POST, instance=post)
        if form.is_valid():
            form.save()
            messages.success(request, 'Your post has been updated.')
            return redirect('forum:post_detail', slug=post.slug)
    else:
        form = ForumPostForm(instance=post)

    return render(request, 'forum/post_form.html', {
        'form': form,
        'edit': True,
        'post': post,
    })


@login_required
@require_POST
def post_delete(request, slug):
    post = get_object_or_404(ForumPost, slug=slug)
    if not can_delete_post(request.user, post):
        return HttpResponseForbidden()
    post.status = 'archived'
    post.save()
    messages.success(request, 'Post has been archived.')
    return redirect('forum:home')


@login_required
@require_POST
def post_vote(request, slug):
    if not can_vote(request.user):
        return JsonResponse({'error': 'Login required'}, status=403)

    post = get_object_or_404(ForumPost, slug=slug)
    data = json.loads(request.body)
    reaction_type = data.get('reaction', 'upvote')

    existing = ForumReaction.objects.filter(
        user=request.user, post=post
    ).first()

    if existing:
        if existing.reaction_type == reaction_type:
            existing.delete()
            post.update_vote_counts()
            return JsonResponse({
                'action': 'removed',
                'score': post.score,
                'upvotes': post.upvotes,
                'downvotes': post.downvotes,
            })
        else:
            existing.reaction_type = reaction_type
            existing.save()
    else:
        ForumReaction.objects.create(
            user=request.user, post=post, reaction_type=reaction_type
        )

    post.update_vote_counts()
    if post.author != request.user and reaction_type in ('upvote', 'downvote', 'like', 'love'):
        create_notification(
            post.author,
            f'{reaction_type}_post',
            {'post_id': post.pk, 'post_slug': post.slug, 'post_title': post.title,
             'username': request.user.username},
        )
    return JsonResponse({
        'action': 'voted',
        'score': post.score,
        'upvotes': post.upvotes,
        'downvotes': post.downvotes,
    })


@login_required
@require_POST
def post_bookmark(request, slug):
    post = get_object_or_404(ForumPost, slug=slug)
    result = toggle_bookmark(request.user, post)
    return JsonResponse({'bookmarked': result})


@login_required
@require_POST
def post_pin(request, slug):
    if not can_pin_post(request.user):
        return HttpResponseForbidden()
    post = get_object_or_404(ForumPost, slug=slug)
    post.is_pinned = not post.is_pinned
    post.save(update_fields=['is_pinned'])
    return JsonResponse({'pinned': post.is_pinned})


@login_required
@require_POST
def post_lock(request, slug):
    if not can_lock_post(request.user):
        return HttpResponseForbidden()
    post = get_object_or_404(ForumPost, slug=slug)
    post.is_locked = not post.is_locked
    post.save(update_fields=['is_locked'])
    return JsonResponse({'locked': post.is_locked})


@login_required
def my_posts(request):
    published = ForumPost.objects.filter(author=request.user, status='published').order_by('-created_at')
    drafts = ForumPost.objects.filter(author=request.user, status='draft').order_by('-created_at')
    archived = ForumPost.objects.filter(author=request.user, status='archived').order_by('-created_at')

    from users.models import ActivityLog
    notifications = ActivityLog.objects.filter(
        user=request.user, action__startswith='new_'
    ).order_by('-timestamp')[:50]

    published_paginator = Paginator(published, 10)
    drafts_paginator = Paginator(drafts, 10)
    archived_paginator = Paginator(archived, 10)

    pub_page = request.GET.get('pub_page', 1)
    draft_page = request.GET.get('draft_page', 1)
    arch_page = request.GET.get('arch_page', 1)

    tab = request.GET.get('tab', 'published')

    try:
        published_page = published_paginator.page(pub_page)
    except (PageNotAnInteger, EmptyPage):
        published_page = published_paginator.page(1)
    try:
        drafts_page = drafts_paginator.page(draft_page)
    except (PageNotAnInteger, EmptyPage):
        drafts_page = drafts_paginator.page(1)
    try:
        archived_page = archived_paginator.page(arch_page)
    except (PageNotAnInteger, EmptyPage):
        archived_page = archived_paginator.page(1)

    return render(request, 'forum/my_posts.html', {
        'published': published_page,
        'drafts': drafts_page,
        'archived': archived_page,
        'notifications': notifications,
        'active_tab': tab,
    })


@login_required
@require_POST
def post_hide(request, slug):
    post = get_object_or_404(ForumPost, slug=slug)
    if request.user != post.author:
        return HttpResponseForbidden()
    post.is_hidden = not post.is_hidden
    post.save(update_fields=['is_hidden'])
    return JsonResponse({'hidden': post.is_hidden})


@login_required
def comment_create(request, slug):
    post = get_object_or_404(ForumPost, slug=slug)
    if not can_comment(request.user, post):
        messages.error(request, 'This post is locked.')
        return redirect('forum:post_detail', slug=slug)

    parent_id = request.POST.get('parent_id')
    parent = None
    if parent_id:
        parent = get_object_or_404(ForumComment, pk=parent_id, post=post)

    if request.method == 'POST':
        form = ForumCommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.author = request.user
            comment.post = post
            comment.parent = parent

            if contains_profanity(comment.content):
                messages.error(request, 'Your comment contains prohibited content.')
                return redirect('forum:post_detail', slug=slug)

            comment.save()
            check_and_award_badges(request.user)
            if post.author != request.user:
                create_notification(
                    post.author,
                    'new_comment',
                    {'post_id': post.pk, 'post_slug': post.slug, 'post_title': post.title,
                     'username': request.user.username, 'comment_id': comment.pk},
                )
            if parent and parent.author != request.user:
                create_notification(
                    parent.author,
                    'reply_comment',
                    {'post_id': post.pk, 'post_slug': post.slug, 'post_title': post.title,
                     'username': request.user.username, 'comment_id': comment.pk},
                )
            messages.success(request, 'Comment added!')
        else:
            messages.error(request, 'Invalid comment.')
    return redirect('forum:post_detail', slug=slug)


@login_required
@require_POST
def comment_vote(request, comment_id):
    if not can_vote(request.user):
        return JsonResponse({'error': 'Login required'}, status=403)
    comment = get_object_or_404(ForumComment, pk=comment_id)
    data = json.loads(request.body)
    reaction_type = data.get('reaction', 'upvote')

    existing = ForumReaction.objects.filter(
        user=request.user, comment=comment
    ).first()
    if existing:
        if existing.reaction_type == reaction_type:
            existing.delete()
            action = 'removed'
        else:
            existing.reaction_type = reaction_type
            existing.save()
            action = 'changed'
    else:
        ForumReaction.objects.create(
            user=request.user, comment=comment, reaction_type=reaction_type
        )
        action = 'voted'

    comment.update_vote_counts()
    return JsonResponse({
        'action': action,
        'upvotes': comment.upvotes,
        'downvotes': comment.downvotes,
    })


@login_required
@require_POST
def comment_solution(request, comment_id):
    comment = get_object_or_404(ForumComment, pk=comment_id)
    if request.user != comment.post.author and not can_moderate(request.user):
        return HttpResponseForbidden()
    comment.is_solution = not comment.is_solution
    comment.save(update_fields=['is_solution'])
    if comment.is_solution:
        check_and_award_badges(comment.author)
    return JsonResponse({'is_solution': comment.is_solution})


@login_required
@require_POST
def comment_delete(request, comment_id):
    comment = get_object_or_404(ForumComment, pk=comment_id)
    if request.user != comment.author and not can_moderate(request.user):
        return HttpResponseForbidden()
    comment.is_active = False
    comment.save(update_fields=['is_active'])
    return JsonResponse({'deleted': True})


def search(request):
    form = ForumSearchForm(request.GET)
    posts = ForumPost.objects.with_counts().filter(status='published')
    query = request.GET.get('q', '').strip()
    sort = request.GET.get('sort', 'newest')
    category_slug = request.GET.get('category', '')
    tags_input = request.GET.get('tags', '').strip()

    if query:
        posts = posts.filter(
            Q(title__icontains=query) |
            Q(content__icontains=query) |
            Q(author__username__icontains=query)
        )
    if category_slug:
        posts = posts.filter(category__slug=category_slug)
    if tags_input:
        tag_slugs = [t.strip() for t in tags_input.split(',') if t.strip()]
        posts = posts.filter(tags__slug__in=tag_slugs).distinct()

    if sort == 'trending':
        posts = posts.order_by('-score', '-views_count')
    elif sort == 'votes':
        posts = posts.order_by('-upvotes')
    elif sort == 'comments':
        posts = posts.order_by('-comment_count')
    else:
        posts = posts.order_by('-created_at')

    paginator = Paginator(posts, 20)
    page = request.GET.get('page', 1)
    try:
        posts_page = paginator.page(page)
    except (PageNotAnInteger, EmptyPage):
        posts_page = paginator.page(1)

    return render(request, 'forum/search.html', {
        'form': form,
        'posts': posts_page,
        'query': query,
    })


def user_profile(request, username):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    profile_user = get_object_or_404(User, username=username)
    profile = getattr(profile_user, 'profile', None)

    is_owner = request.user.is_authenticated and request.user == profile_user

    posts = ForumPost.objects.filter(author=profile_user, status='published')
    if not is_owner:
        posts = posts.filter(is_hidden=False)
    posts = posts.order_by('-created_at')
    comments = ForumComment.objects.filter(author=profile_user, is_active=True).order_by('-created_at')
    badges = UserBadge.objects.filter(user=profile_user).select_related('badge')
    reputation = get_user_reputation(profile_user)
    followers_count = FollowUser.objects.filter(following=profile_user).count()
    following_count = FollowUser.objects.filter(follower=profile_user).count()
    total_comments = ForumComment.objects.filter(author=profile_user, is_active=True).count()

    is_following = False
    if request.user.is_authenticated and request.user != profile_user:
        is_following = FollowUser.objects.filter(
            follower=request.user, following=profile_user
        ).exists()

    owner_data = {}
    if is_owner:
        drafts = ForumPost.objects.filter(author=profile_user, status='draft').order_by('-created_at')
        saved_posts = ForumPost.objects.filter(bookmarks__user=profile_user).order_by('-bookmarks__created_at')
        hidden_posts = ForumPost.objects.filter(author=profile_user, is_hidden=True).order_by('-created_at')

        draft_page = request.GET.get('draft_page', 1)
        saved_page = request.GET.get('saved_page', 1)
        hidden_page = request.GET.get('hidden_page', 1)

        draft_paginator = Paginator(drafts, 10)
        saved_paginator = Paginator(saved_posts, 10)
        hidden_paginator = Paginator(hidden_posts, 10)

        try:
            drafts_page = draft_paginator.page(draft_page)
        except (PageNotAnInteger, EmptyPage):
            drafts_page = draft_paginator.page(1)
        try:
            saved_page_obj = saved_paginator.page(saved_page)
        except (PageNotAnInteger, EmptyPage):
            saved_page_obj = saved_paginator.page(1)
        try:
            hidden_page_obj = hidden_paginator.page(hidden_page)
        except (PageNotAnInteger, EmptyPage):
            hidden_page_obj = hidden_paginator.page(1)

        owner_data = {
            'drafts': drafts_page,
            'saved_posts': saved_page_obj,
            'hidden_posts': hidden_page_obj,
            'total_bookmarks': Bookmark.objects.filter(user=profile_user).count(),
            'unread_notifications': 0,
            'moderation_history': ForumReport.objects.filter(post__author=profile_user).count(),
        }

    post_paginator = Paginator(posts, 10)
    comment_paginator = Paginator(comments, 10)
    post_page = request.GET.get('post_page', 1)
    comment_page = request.GET.get('comment_page', 1)

    try:
        posts_page = post_paginator.page(post_page)
    except (PageNotAnInteger, EmptyPage):
        posts_page = post_paginator.page(1)
    try:
        comments_page = comment_paginator.page(comment_page)
    except (PageNotAnInteger, EmptyPage):
        comments_page = comment_paginator.page(1)

    tab = request.GET.get('tab', 'posts')

    return render(request, 'forum/user_profile.html', {
        'profile_user': profile_user,
        'profile': profile,
        'posts': posts_page,
        'comments': comments_page,
        'badges': badges,
        'reputation': reputation,
        'followers_count': followers_count,
        'following_count': following_count,
        'total_comments': total_comments,
        'is_following': is_following,
        'is_owner': is_owner,
        'owner_data': owner_data,
        'active_tab': tab,
    })


@login_required
@require_POST
def follow_user(request, username):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    target = get_object_or_404(User, username=username)
    result = toggle_follow_user(request.user, target)
    return JsonResponse({'following': result})


@login_required
@require_POST
def follow_category(request, slug):
    category = get_object_or_404(ForumCategory, slug=slug)
    result = toggle_follow_category(request.user, category)
    return JsonResponse({'following': result})


def leaderboard(request):
    period = request.GET.get('period', 'week')
    users = get_top_contributors(period, 50)

    return render(request, 'forum/leaderboard.html', {
        'top_users': users,
        'period': period,
    })


def events(request):
    events_list = ForumEvent.objects.filter(is_published=True).order_by('start_date')
    upcoming = events_list.filter(start_date__gte=timezone.now())
    past = events_list.filter(start_date__lt=timezone.now())

    return render(request, 'forum/events.html', {
        'upcoming': upcoming,
        'past': past,
    })


def jobs(request):
    jobs_list = ForumJob.objects.filter(is_active=True).order_by('-created_at')
    job_type = request.GET.get('type', '')
    if job_type:
        jobs_list = jobs_list.filter(job_type=job_type)

    return render(request, 'forum/jobs.html', {
        'jobs': jobs_list,
        'current_type': job_type,
    })


@login_required
def job_create(request):
    if request.method == 'POST':
        form = ForumJobForm(request.POST)
        if form.is_valid():
            job = form.save(commit=False)
            job.posted_by = request.user
            job.save()
            messages.success(request, 'Job posted successfully!')
            return redirect('forum:jobs')
    else:
        form = ForumJobForm()

    return render(request, 'forum/job_form.html', {'form': form})


@login_required
def report_create(request, slug):
    post = get_object_or_404(ForumPost, slug=slug)
    if not can_report(request.user):
        return HttpResponseForbidden()

    if request.method == 'POST':
        form = ForumReportForm(request.POST)
        if form.is_valid():
            report = form.save(commit=False)
            report.reporter = request.user
            report.post = post
            report.save()
            messages.success(request, 'Report submitted. We will review it shortly.')
            return redirect('forum:post_detail', slug=slug)
    else:
        form = ForumReportForm()

    return render(request, 'forum/report_form.html', {
        'form': form,
        'post': post,
    })


def moderation(request):
    if not can_moderate(request.user):
        return HttpResponseForbidden()

    reports = ForumReport.objects.filter(is_resolved=False).select_related(
        'reporter', 'post', 'comment'
    ).order_by('-created_at')
    reported_posts = ForumPost.objects.filter(
        reports__is_resolved=False
    ).distinct().order_by('-created_at')

    return render(request, 'forum/moderation.html', {
        'reports': reports,
        'reported_posts': reported_posts,
    })


@login_required
@require_POST
def resolve_report(request, report_id):
    if not can_moderate(request.user):
        return HttpResponseForbidden()
    report = get_object_or_404(ForumReport, pk=report_id)
    report.is_resolved = True
    report.resolved_by = request.user
    report.resolved_at = timezone.now()
    report.save()
    return JsonResponse({'resolved': True})


def showcase(request):
    posts = ForumPost.objects.with_counts().filter(
        is_showcase=True, status='published'
    ).order_by('-created_at')
    paginator = Paginator(posts, 20)
    page = request.GET.get('page', 1)
    try:
        posts_page = paginator.page(page)
    except (PageNotAnInteger, EmptyPage):
        posts_page = paginator.page(1)

    return render(request, 'forum/showcase.html', {'posts': posts_page})


def api_posts_json(request):
    sort = request.GET.get('sort', 'latest')
    if sort == 'trending':
        posts = ForumPost.objects.trending()
    else:
        posts = ForumPost.objects.latest()
    data = []
    for p in posts[:10]:
        data.append({
            'id': p.id,
            'title': p.title,
            'slug': p.slug,
            'author': p.author.username,
            'score': p.score,
            'upvotes': p.upvotes,
            'comment_count': p.comment_count,
            'created_at': p.created_at.isoformat(),
        })
    return JsonResponse({'posts': data})