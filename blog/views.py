from django.shortcuts import render, get_object_or_404, redirect
from django.http import Http404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.core.paginator import Paginator

from .models import Article, BlogPost

try:
    from branding.roles import designer_required
except ImportError:
    from django.contrib.auth.decorators import login_required as designer_required


# 
# PUBLIC VIEWS
# 

def index(request):
    """Blog landing page"""
    posts = BlogPost.objects.filter(is_published=True)
    return render(request, 'blog/index.html', {'posts': posts})


def articles(request):
    """Long-form articles listing"""
    article_list = Article.objects.filter(is_published=True)
    return render(request, 'blog/articles.html', {'articles': article_list})


def article_detail(request, slug):
    """Individual article detail page"""
    article = get_object_or_404(Article, slug=slug, is_published=True)

    # Find prev/next articles
    all_articles = list(Article.objects.filter(is_published=True).values_list('slug', flat=True))
    try:
        current_index = all_articles.index(slug)
    except ValueError:
        current_index = -1

    prev_slug = all_articles[current_index - 1] if current_index > 0 else None
    next_slug = all_articles[current_index + 1] if current_index < len(all_articles) - 1 else None

    prev_article = Article.objects.filter(slug=prev_slug).first() if prev_slug else None
    next_article = Article.objects.filter(slug=next_slug).first() if next_slug else None

    return render(request, 'blog/article_detail.html', {
        'article': article,
        'prev_article': prev_article,
        'next_article': next_article,
    })


def blog_detail(request, slug):
    """Individual blog post detail page"""
    post = get_object_or_404(BlogPost, slug=slug, is_published=True)

    all_posts = list(BlogPost.objects.filter(is_published=True).values_list('slug', flat=True))
    try:
        current_index = all_posts.index(slug)
    except ValueError:
        current_index = -1

    prev_slug = all_posts[current_index - 1] if current_index > 0 else None
    next_slug = all_posts[current_index + 1] if current_index < len(all_posts) - 1 else None

    prev_post = BlogPost.objects.filter(slug=prev_slug).first() if prev_slug else None
    next_post = BlogPost.objects.filter(slug=next_slug).first() if next_slug else None

    return render(request, 'blog/blog_detail.html', {
        'post': post,
        'prev_post': prev_post,
        'next_post': next_post,
    })


# 
# MANAGEMENT VIEWS (Designer Dashboard)
# 

@designer_required
def manage_articles(request):
    """List all articles for management"""
    query = request.GET.get('q', '')
    tag_filter = request.GET.get('tag', '')
    status_filter = request.GET.get('status', '')

    articles_qs = Article.objects.all()

    if query:
        articles_qs = articles_qs.filter(
            Q(title__icontains=query) | Q(description__icontains=query)
        )
    if tag_filter:
        articles_qs = articles_qs.filter(tag=tag_filter)
    if status_filter == 'published':
        articles_qs = articles_qs.filter(is_published=True)
    elif status_filter == 'draft':
        articles_qs = articles_qs.filter(is_published=False)

    paginator = Paginator(articles_qs, 12)
    page = request.GET.get('page', 1)
    articles_page = paginator.get_page(page)

    return render(request, 'blog/manage_articles.html', {
        'articles': articles_page,
        'query': query,
        'tag_filter': tag_filter,
        'status_filter': status_filter,
        'tag_choices': Article.TAG_CHOICES,
        'total_count': Article.objects.count(),
        'published_count': Article.objects.filter(is_published=True).count(),
        'draft_count': Article.objects.filter(is_published=False).count(),
    })


@designer_required
def add_article(request):
    """Add a new article"""
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        tag = request.POST.get('tag', 'Integration')
        image = request.FILES.get('image')
        service_url = request.POST.get('service_url', '').strip()
        description = request.POST.get('description', '').strip()
        content = request.POST.get('content', '').strip()
        read_time = request.POST.get('read_time', '5 min read').strip()
        is_published = request.POST.get('is_published') == 'on'

        if not title or not description or not content:
            messages.error(request, 'Title, description, and content are required.')
            return render(request, 'blog/article_form.html', {
                'article': None,
                'tag_choices': Article.TAG_CHOICES,
                'action': 'add',
            })

        article = Article(
            title=title,
            tag=tag,
            image=image,
            service_url=service_url,
            description=description,
            content=content,
            read_time=read_time,
            is_published=is_published,
            author=request.user,
        )
        article.save()
        messages.success(request, f'Article "{article.title}" created successfully.')
        return redirect('blog:manage_articles')

    return render(request, 'blog/article_form.html', {
        'article': None,
        'tag_choices': Article.TAG_CHOICES,
        'action': 'add',
    })


@designer_required
def edit_article(request, pk):
    """Edit an existing article"""
    article = get_object_or_404(Article, pk=pk)

    if request.method == 'POST':
        article.title = request.POST.get('title', '').strip()
        article.tag = request.POST.get('tag', 'Integration')
        if request.FILES.get('image'):
            article.image = request.FILES.get('image')
        article.service_url = request.POST.get('service_url', '').strip()
        article.description = request.POST.get('description', '').strip()
        article.content = request.POST.get('content', '').strip()
        article.read_time = request.POST.get('read_time', '5 min read').strip()
        article.is_published = request.POST.get('is_published') == 'on'

        if not article.title or not article.description or not article.content:
            messages.error(request, 'Title, description, and content are required.')
            return render(request, 'blog/article_form.html', {
                'article': article,
                'tag_choices': Article.TAG_CHOICES,
                'action': 'edit',
            })

        article.save()
        messages.success(request, f'Article "{article.title}" updated successfully.')
        return redirect('blog:manage_articles')

    return render(request, 'blog/article_form.html', {
        'article': article,
        'tag_choices': Article.TAG_CHOICES,
        'action': 'edit',
    })


@designer_required
def delete_article(request, pk):
    """Delete an article"""
    article = get_object_or_404(Article, pk=pk)

    if request.method == 'POST':
        title = article.title
        article.delete()
        messages.success(request, f'Article "{title}" deleted successfully.')
        return redirect('blog:manage_articles')

    return render(request, 'blog/delete_confirm.html', {
        'item': article,
        'item_type': 'article',
        'cancel_url': 'blog:manage_articles',
    })


@designer_required
def manage_blog_posts(request):
    """List all blog posts for management"""
    query = request.GET.get('q', '')
    tag_filter = request.GET.get('tag', '')
    status_filter = request.GET.get('status', '')

    posts_qs = BlogPost.objects.all()

    if query:
        posts_qs = posts_qs.filter(
            Q(title__icontains=query) | Q(description__icontains=query)
        )
    if tag_filter:
        posts_qs = posts_qs.filter(tag=tag_filter)
    if status_filter == 'published':
        posts_qs = posts_qs.filter(is_published=True)
    elif status_filter == 'draft':
        posts_qs = posts_qs.filter(is_published=False)

    paginator = Paginator(posts_qs, 12)
    page = request.GET.get('page', 1)
    posts_page = paginator.get_page(page)

    return render(request, 'blog/manage_posts.html', {
        'posts': posts_page,
        'query': query,
        'tag_filter': tag_filter,
        'status_filter': status_filter,
        'tag_choices': BlogPost.TAG_CHOICES,
        'total_count': BlogPost.objects.count(),
        'published_count': BlogPost.objects.filter(is_published=True).count(),
        'draft_count': BlogPost.objects.filter(is_published=False).count(),
    })


@designer_required
def add_blog_post(request):
    """Add a new blog post"""
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        tag = request.POST.get('tag', 'Tips')
        image = request.FILES.get('image')
        description = request.POST.get('description', '').strip()
        content = request.POST.get('content', '').strip()
        read_time = request.POST.get('read_time', '3 min').strip()
        is_published = request.POST.get('is_published') == 'on'

        if not title or not description or not content:
            messages.error(request, 'Title, description, and content are required.')
            return render(request, 'blog/post_form.html', {
                'post': None,
                'tag_choices': BlogPost.TAG_CHOICES,
                'action': 'add',
            })

        post = BlogPost(
            title=title,
            tag=tag,
            image=image,
            description=description,
            content=content,
            read_time=read_time,
            is_published=is_published,
            author=request.user,
        )
        post.save()
        messages.success(request, f'Blog post "{post.title}" created successfully.')
        return redirect('blog:manage_blog_posts')

    return render(request, 'blog/post_form.html', {
        'post': None,
        'tag_choices': BlogPost.TAG_CHOICES,
        'action': 'add',
    })


@designer_required
def edit_blog_post(request, pk):
    """Edit an existing blog post"""
    post = get_object_or_404(BlogPost, pk=pk)

    if request.method == 'POST':
        post.title = request.POST.get('title', '').strip()
        post.tag = request.POST.get('tag', 'Tips')
        if request.FILES.get('image'):
            post.image = request.FILES.get('image')
        post.description = request.POST.get('description', '').strip()
        post.content = request.POST.get('content', '').strip()
        post.read_time = request.POST.get('read_time', '3 min').strip()
        post.is_published = request.POST.get('is_published') == 'on'

        if not post.title or not post.description or not post.content:
            messages.error(request, 'Title, description, and content are required.')
            return render(request, 'blog/post_form.html', {
                'post': post,
                'tag_choices': BlogPost.TAG_CHOICES,
                'action': 'edit',
            })

        post.save()
        messages.success(request, f'Blog post "{post.title}" updated successfully.')
        return redirect('blog:manage_blog_posts')

    return render(request, 'blog/post_form.html', {
        'post': post,
        'tag_choices': BlogPost.TAG_CHOICES,
        'action': 'edit',
    })


@designer_required
def delete_blog_post(request, pk):
    """Delete a blog post"""
    post = get_object_or_404(BlogPost, pk=pk)

    if request.method == 'POST':
        title = post.title
        post.delete()
        messages.success(request, f'Blog post "{title}" deleted successfully.')
        return redirect('blog:manage_blog_posts')

    return render(request, 'blog/delete_confirm.html', {
        'item': post,
        'item_type': 'blog post',
        'cancel_url': 'blog:manage_blog_posts',
    })
