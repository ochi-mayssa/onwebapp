"""Where the chatbot's searchable content comes from.

Two kinds of source:

* **Pages** – real rendered pages of this site, listed in ``PAGE_SOURCES``. Each
  carries an access level so the chatbot never quotes a page the current visitor
  is not allowed to see.
* **Records** – rows from the database (blog posts, forum posts, reviews) that
  are already public, harvested by the collectors at the end of this module.
"""
import logging

from django.urls import NoReverseMatch, reverse

from .text_utils import clean_plain_text

logger = logging.getLogger(__name__)

# ── Access levels ──────────────────────────────────────────────────────────────

PUBLIC = 'public'
AUTH = 'auth'
STAFF = 'staff'

_ACCESS_ORDER = {PUBLIC: 0, AUTH: 1, STAFF: 2}


def access_for_user(user):
    """Highest access level the given user is allowed to read."""
    if user is None or not getattr(user, 'is_authenticated', False):
        return PUBLIC
    if getattr(user, 'is_staff', False) or getattr(user, 'is_superuser', False):
        return STAFF
    return AUTH


def user_can_read(user, access):
    return _ACCESS_ORDER.get(access, 0) <= _ACCESS_ORDER[access_for_user(user)]

# ── Page registry ──────────────────────────────────────────────────────────────
# (url_name, display title, access)

PAGE_SOURCES = (
    # ── Public: core marketing ──
    ('home:home', 'Home', PUBLIC),
    ('home:about', 'About Us', PUBLIC),
    ('home:automation_home', 'Website Automation', PUBLIC),
    ('home:rpa_bpa', 'RPA & BPA', PUBLIC),
    ('home:ux_design', 'UX Design', PUBLIC),
    ('home:ui_design', 'UI Design', PUBLIC),
    ('home:software_home', 'Software Development', PUBLIC),
    ('home:web_development', 'Web Development', PUBLIC),
    ('home:mobile_development', 'Mobile Development', PUBLIC),
    ('home:ecommerce_development', 'eCommerce Development', PUBLIC),
    ('home:erp_service', 'ERP Service', PUBLIC),
    ('home:build_website', 'Request a Website', PUBLIC),
    ('home:video_explainer', 'Platform Overview', PUBLIC),
    ('home:privacy', 'Privacy Policy', PUBLIC),
    ('home:terms', 'Terms of Service', PUBLIC),

    # ── Public: services, integration, SEO ──
    ('services:index', 'Services', PUBLIC),
    ('services:smart_factory', 'Smart Factory', PUBLIC),
    ('services:iot_integration', 'IoT Integration', PUBLIC),
    ('services:predictive_maintenance', 'Predictive Maintenance', PUBLIC),
    ('services:social_intelligence', 'Social Intelligence', PUBLIC),
    ('services:keyword_checker', 'Keyword Checker', PUBLIC),
    ('services:engagement_analytics', 'Engagement Analytics', PUBLIC),
    ('integration:integration_homepage', 'Integration', PUBLIC),
    ('integration:data_integration', 'Data Integration', PUBLIC),
    ('integration:b2b_integration', 'B2B Integration', PUBLIC),
    ('integration:system_integration', 'System Integration', PUBLIC),
    ('integration:social_media_integration', 'Social Media Integration', PUBLIC),
    ('seo_analyzer:seo_home_marketing', 'SEO Services', PUBLIC),
    ('seo_analyzer:seo_keyword_marketing', 'SEO Keyword Research', PUBLIC),
    ('seo_analyzer:seo_content_marketing', 'SEO Content Optimisation', PUBLIC),
    ('seo_analyzer:seo_url_marketing', 'SEO URL Analysis', PUBLIC),
    ('seo_analyzer:seo_links_marketing', 'SEO Link Analysis', PUBLIC),
    ('seo_analyzer:free_pre_check', 'Free Website SEO Check', PUBLIC),
    ('seo_analyzer:sitemap', 'XML Sitemap Tool', PUBLIC),

    # ── Public: transactional, community, content ──
    ('contact:contact', 'Contact Us', PUBLIC),
    ('payments:plans', 'Pricing & Plans', PUBLIC),
    ('branding:landing', 'Branding', PUBLIC),
    ('blog:index', 'Blog', PUBLIC),
    ('blog:articles', 'Articles', PUBLIC),
    ('forum:home', 'Community Forum', PUBLIC),
    ('forum:events', 'Forum Events', PUBLIC),
    ('forum:jobs', 'Jobs Board', PUBLIC),
    ('forum:showcase', 'Community Showcase', PUBLIC),
    ('forum:leaderboard', 'Forum Leaderboard', PUBLIC),
    ('forum:search', 'Forum Search', PUBLIC),
    ('community:home', 'Community', PUBLIC),

    # ── Signed-in members ──
    ('platform_monitoring:hub', 'Platform Monitoring', AUTH),
    ('platform_monitoring:seo', 'Website Monitoring', AUTH),
    ('platform_monitoring:automation', 'Automation Hub', AUTH),
    ('platform_monitoring:task_scheduler', 'Task Scheduler', AUTH),
    ('platform_monitoring:execution_logs', 'Execution Logs', AUTH),
    ('platform_monitoring:automation_status', 'Automation Status', AUTH),
    ('platform_monitoring:integrations', 'Monitoring Integrations', AUTH),
    ('platform_monitoring:iot', 'IoT Monitoring', AUTH),
    ('platform_monitoring:security', 'Security Monitoring', AUTH),
    ('platform_monitoring:social', 'Social Monitoring', AUTH),
    ('platform_monitoring:competitor', 'Competitor Monitoring', AUTH),
    ('services:industrial_automation', 'Industrial Automation', AUTH),
    ('services:competitor_tracking', 'Competitor Tracking', AUTH),
    ('services:market_analysis_tools', 'Market Analysis Tools', AUTH),
    ('services:seo_analytics', 'SEO Analytics', AUTH),
    ('services:social_media_tracking', 'Social Media Tracking', AUTH),
    ('services:erp_integration', 'ERP Integration', AUTH),
    ('services:erpnext_dashboard', 'ERPNext Dashboard', AUTH),
    ('services:crm_integration', 'CRM Integration', AUTH),
    ('services:link_analyzer', 'Link Analyzer', AUTH),
    ('services:keyword_research', 'Keyword Research', AUTH),
    ('seo_analyzer:index', 'SEO Tools', AUTH),
    ('seo_analyzer:backlinks', 'Backlink Monitor', AUTH),
    ('seo_analyzer:checker', 'SEO Checker', AUTH),
    ('seo_analyzer:link_checker', 'Link Checker', AUTH),
    ('seo_analyzer:monitoring', 'SEO Monitoring', AUTH),
    ('seo_analyzer:url_intelligence', 'URL Intelligence', AUTH),

    # ── Staff only ──
    ('projects:dashboard', 'Projects', STAFF),
    ('projects:admin_dashboard', 'Project Dashboard', STAFF),
    ('projects:admin_kanban', 'Project Pipeline', STAFF),
    ('crm:customer_list', 'CRM Customers', STAFF),
    ('crm:dashboard', 'CRM Dashboard', STAFF),
    ('operations:ops_dashboard', 'Operations', STAFF),
    ('rpa_dashboard:rpa_dashboard', 'RPA Dashboard', STAFF),
    ('digital_presence:overview', 'Digital Presence', STAFF),
    ('digital_presence:social_media', 'Social Presence', STAFF),
    ('branding:dashboard', 'Branding Studio', STAFF),
    ('branding:analytics_overview', 'Branding Analytics', STAFF),
    ('branding:kanban', 'Branding Pipeline', STAFF),
    ('branding:unified_dashboard', 'Branding Overview', STAFF),
)


def iter_page_sources():
    """Yield ``(source_id, title, url, access)`` for every page that reverses."""
    for url_name, title, access in PAGE_SOURCES:
        try:
            path = reverse(url_name)
        except NoReverseMatch:
            logger.debug('chatbot index: cannot reverse %s', url_name)
            continue
        yield url_name, title, path, access


_ACCESS_BY_NAME = {name: access for name, _, access in PAGE_SOURCES}


def access_for_url_name(url_name):
    """Access level of a page, so hand-written answers respect it too.

    The curated knowledge base links pages by URL name and would otherwise offer
    a signed-in-only page to an anonymous visitor.
    """
    return _ACCESS_BY_NAME.get(url_name, PUBLIC)


# ── Database collectors ────────────────────────────────────────────────────────

_MAX_RECORDS = 60


def _collect_blog():
    from blog.models import Article, BlogPost

    out = []
    for model, url_name in ((Article, 'blog:article_detail'),
                             (BlogPost, 'blog:blog_detail')):
        try:
            rows = model.objects.filter(is_published=True).order_by('-created_at')[:_MAX_RECORDS]
        except Exception as exc:
            logger.debug('chatbot index: blog %s unavailable: %s', model.__name__, exc)
            continue
        for row in rows:
            try:
                path = reverse(url_name, args=[row.slug])
            except NoReverseMatch:
                continue
            body = ' '.join(filter(None, [clean_plain_text(row.description),
                                          clean_plain_text(row.content)]))
            out.append(('blog:%s:%s' % (model.__name__.lower(), row.pk),
                        row.title or 'Untitled', path, PUBLIC, row.title or '', body))
    return out


def _collect_forum():
    from forum.models import ForumCategory, ForumPost

    out = []
    try:
        categories = ForumCategory.objects.all()
    except Exception:
        categories = []
    for category in categories:
        body = clean_plain_text(getattr(category, 'description', ''))
        if body:
            try:
                path = reverse('forum:category', args=[category.slug])
            except NoReverseMatch:
                continue
            out.append(('forum:category:%s' % category.pk, category.name, path,
                        PUBLIC, category.name, body))

    try:
        posts = (ForumPost.objects
                 .filter(status='published', is_hidden=False)
                 .order_by('-created_at')[:_MAX_RECORDS])
    except Exception as exc:
        logger.debug('chatbot index: forum posts unavailable: %s', exc)
        return out

    for post in posts:
        try:
            path = reverse('forum:post_detail', args=[post.slug])
        except NoReverseMatch:
            continue
        parts = [clean_plain_text(post.excerpt), clean_plain_text(post.content)]
        if getattr(post, 'is_showcase', False):
            parts.append(clean_plain_text(getattr(post, 'tech_stack', '')))
        body = ' '.join(p for p in parts if p)
        if body:
            out.append(('forum:post:%s' % post.pk, post.title or 'Forum post',
                        path, PUBLIC, post.title or '', body))

        for comment in post.comments.filter(is_active=True).select_related('author')[:10]:
            text = clean_plain_text(comment.content)
            if not text:
                continue
            out.append(('forum:comment:%s' % comment.pk, 'Comment on: %s' % (post.title or ''),
                        path, PUBLIC, post.title or '', text))
    return out


def _collect_reviews():
    try:
        from social_proof.models import SocialEvent
    except Exception:
        return []
    try:
        rows = SocialEvent.objects.filter(is_approved=True).order_by('-occurred_at')[:_MAX_RECORDS]
    except Exception as exc:
        logger.debug('chatbot index: social proof unavailable: %s', exc)
        return []
    out = []
    for row in rows:
        text = clean_plain_text(row.text)
        if not text:
            continue
        url = row.url or reverse('community:home')
        out.append(('review:%s' % row.pk, 'Customer review by %s' % (row.author_name or 'a client'),
                    url, PUBLIC, row.author_name or '', text))
    return out


def collect_records():
    """All database-backed, already-public content."""
    records = []
    for collector in (_collect_blog, _collect_forum, _collect_reviews):
        try:
            records.extend(collector())
        except Exception as exc:
            logger.warning('chatbot index: collector %s failed: %s', collector.__name__, exc)
    return records
