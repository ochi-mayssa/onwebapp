from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from .models import (
    ForumCategory, ForumTag, ForumPost, ForumComment, ForumReaction,
    Bookmark, ForumBadge, UserBadge, FollowUser, FollowCategory,
)

User = get_user_model()


class ForumModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass123')
        self.category = ForumCategory.objects.create(
            name='Development', slug='development', description='Dev discussions'
        )
        self.tag = ForumTag.objects.create(name='Django', slug='django')
        self.post = ForumPost.objects.create(
            author=self.user, category=self.category,
            title='Test Post Title', slug='test-post-title',
            content='This is a test post content for the forum.',
            status='published',
        )
        self.post.tags.add(self.tag)

    def test_category_creation(self):
        self.assertEqual(str(self.category), 'Development')
        self.assertEqual(self.category.post_count, 0)

    def test_tag_creation(self):
        self.assertEqual(str(self.tag), 'Django')

    def test_post_creation(self):
        self.assertEqual(str(self.post), 'Test Post Title')
        self.assertEqual(self.post.status, 'published')
        self.assertEqual(self.post.author, self.user)
        self.assertIn(self.tag, self.post.tags.all())
        self.assertGreaterEqual(self.post.reading_time, 1)

    def test_post_auto_excerpt(self):
        self.assertIn('test post content', self.post.excerpt)

    def test_post_update_vote_counts(self):
        ForumReaction.objects.create(user=self.user, post=self.post, reaction_type='upvote')
        self.post.update_vote_counts()
        self.assertEqual(self.post.upvotes, 1)
        self.assertEqual(self.post.score, 1)

    def test_comment_creation(self):
        comment = ForumComment.objects.create(
            post=self.post, author=self.user, content='Great post!'
        )
        self.assertEqual(str(comment), f'Comment by {self.user.username} on {self.post.title[:50]}')
        self.assertEqual(comment.get_depth, 0)

    def test_nested_comment_depth(self):
        parent = ForumComment.objects.create(
            post=self.post, author=self.user, content='Parent'
        )
        child = ForumComment.objects.create(
            post=self.post, author=self.user, parent=parent, content='Child'
        )
        grandchild = ForumComment.objects.create(
            post=self.post, author=self.user, parent=child, content='Grandchild'
        )
        self.assertEqual(parent.get_depth, 0)
        self.assertEqual(child.get_depth, 1)
        self.assertEqual(grandchild.get_depth, 2)

    def test_bookmark(self):
        bookmark = Bookmark.objects.create(user=self.user, post=self.post)
        self.assertEqual(str(bookmark), f'{self.user.username} bookmarked {self.post.title[:50]}')

    def test_badge_creation(self):
        badge = ForumBadge.objects.create(
            name='First Post', slug='first-post',
            description='First post badge', icon='fas fa-star',
        )
        self.assertEqual(str(badge), 'First Post')

    def test_user_badge(self):
        badge = ForumBadge.objects.create(name='Test Badge', slug='test-badge')
        ub = UserBadge.objects.create(user=self.user, badge=badge)
        self.assertEqual(str(ub), f'{self.user.username} - Test Badge')

    def test_follow_user(self):
        user2 = User.objects.create_user(username='user2', password='testpass123')
        follow = FollowUser.objects.create(follower=self.user, following=user2)
        self.assertEqual(str(follow), f'{self.user.username} follows {user2.username}')

    def test_follow_category(self):
        follow = FollowCategory.objects.create(user=self.user, category=self.category)
        self.assertEqual(str(follow), f'{self.user.username} follows {self.category.name}')

    def test_reaction_post_unique_together(self):
        ForumReaction.objects.create(user=self.user, post=self.post, reaction_type='upvote')
        with self.assertRaises(Exception):
            ForumReaction.objects.create(user=self.user, post=self.post, reaction_type='upvote')

    def test_comment_reaction_unique_together(self):
        comment = ForumComment.objects.create(post=self.post, author=self.user, content='test')
        ForumReaction.objects.create(user=self.user, comment=comment, reaction_type='like')
        with self.assertRaises(Exception):
            ForumReaction.objects.create(user=self.user, comment=comment, reaction_type='like')


class ForumViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='testuser', password='testpass123')
        self.category = ForumCategory.objects.create(
            name='Development', slug='development', is_active=True
        )
        self.tag = ForumTag.objects.create(name='Python', slug='python')
        self.post = ForumPost.objects.create(
            author=self.user, category=self.category,
            title='Test Post', slug='test-post',
            content='This is a test post with enough content to be valid.',
            status='published',
        )
        self.post.tags.add(self.tag)

    def test_forum_home_status(self):
        resp = self.client.get(reverse('forum:home'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Trending')
        self.assertContains(resp, 'Latest Discussions')

    def test_category_detail(self):
        resp = self.client.get(reverse('forum:category', args=['development']))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Development')

    def test_tag_detail(self):
        resp = self.client.get(reverse('forum:tag', args=['python']))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Python')

    def test_post_detail(self):
        resp = self.client.get(reverse('forum:post_detail', args=['test-post']))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Test Post')
        self.assertContains(resp, 'Comments')

    def test_post_detail_increments_views(self):
        old_views = self.post.views_count
        self.client.get(reverse('forum:post_detail', args=['test-post']))
        self.post.refresh_from_db()
        self.assertEqual(self.post.views_count, old_views + 1)

    def test_search_view(self):
        resp = self.client.get(reverse('forum:search'), {'q': 'Test'})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Test Post')

    def test_search_no_results(self):
        resp = self.client.get(reverse('forum:search'), {'q': 'xyznonexistent'})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'No posts found')

    def test_create_post_requires_login(self):
        resp = self.client.get(reverse('forum:post_create'))
        self.assertEqual(resp.status_code, 302)

    def test_create_post_logged_in(self):
        self.client.login(username='testuser', password='testpass123')
        resp = self.client.get(reverse('forum:post_create'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Create a Post')

    def test_create_post_submit(self):
        self.client.login(username='testuser', password='testpass123')
        resp = self.client.post(reverse('forum:post_create'), {
            'title': 'My New Forum Post Title',
            'category': self.category.pk,
            'content': 'This is a detailed post content with enough characters to pass validation and be published.',
            'status': 'published',
            'tags_input': 'django, react',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(ForumPost.objects.filter(title='My New Forum Post Title').exists())

    def test_comment_requires_login(self):
        resp = self.client.post(reverse('forum:comment_create', args=['test-post']), {'content': 'Nice!'})
        self.assertEqual(resp.status_code, 302)

    def test_comment_logged_in(self):
        self.client.login(username='testuser', password='testpass123')
        resp = self.client.post(reverse('forum:comment_create', args=['test-post']), {'content': 'Great post!'})
        self.assertIn(resp.status_code, [200, 302])

    def test_vote_upvote(self):
        self.client.login(username='testuser', password='testpass123')
        from django.http import JsonResponse
        resp = self.client.post(
            reverse('forum:post_vote', args=['test-post']),
            {'reaction': 'upvote'},
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('score', data)

    def test_bookmark_toggle(self):
        self.client.login(username='testuser', password='testpass123')
        resp = self.client.post(
            reverse('forum:post_bookmark', args=['test-post']),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['bookmarked'])
        resp2 = self.client.post(
            reverse('forum:post_bookmark', args=['test-post']),
            content_type='application/json',
        )
        self.assertFalse(resp2.json()['bookmarked'])

    def test_leaderboard_page(self):
        resp = self.client.get(reverse('forum:leaderboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Top Contributors')

    def test_showcase_page(self):
        resp = self.client.get(reverse('forum:showcase'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Project Showcase')

    def test_jobs_page(self):
        resp = self.client.get(reverse('forum:jobs'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Jobs & Opportunities')

    def test_user_profile(self):
        resp = self.client.get(reverse('forum:user_profile', args=['testuser']))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'testuser')

    def test_events_page(self):
        resp = self.client.get(reverse('forum:events'))
        self.assertEqual(resp.status_code, 200)

    def test_api_posts_json(self):
        resp = self.client.get(reverse('forum:api_posts_json'))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('posts', data)
        self.assertGreaterEqual(len(data['posts']), 1)

    def test_post_edit_own(self):
        self.client.login(username='testuser', password='testpass123')
        resp = self.client.get(reverse('forum:post_edit', args=['test-post']))
        self.assertEqual(resp.status_code, 200)
        resp = self.client.post(reverse('forum:post_edit', args=['test-post']), {
            'title': 'Updated Post Title Here',
            'category': self.category.pk,
            'content': 'This updated post content has enough characters to pass validation and be saved.',
            'status': 'published',
        })
        self.assertEqual(resp.status_code, 302)
        self.post.refresh_from_db()
        self.assertEqual(self.post.title, 'Updated Post Title Here')

    def test_post_archive(self):
        self.client.login(username='testuser', password='testpass123')
        resp = self.client.post(reverse('forum:post_delete', args=['test-post']))
        self.assertIn(resp.status_code, [200, 302])
        self.post.refresh_from_db()
        self.assertEqual(self.post.status, 'archived')

    def test_form_validation_title_too_short(self):
        self.client.login(username='testuser', password='testpass123')
        resp = self.client.post(reverse('forum:post_create'), {
            'title': 'Short',
            'content': 'This is a detailed post content with enough characters to pass validation.',
        })
        self.assertEqual(resp.status_code, 200)

    def test_follow_user_view(self):
        user2 = User.objects.create_user(username='user2', password='testpass123')
        self.client.login(username='testuser', password='testpass123')
        resp = self.client.post(
            reverse('forum:follow_user', args=['user2']),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['following'])

    def test_solution_marking(self):
        self.client.login(username='testuser', password='testpass123')
        comment = ForumComment.objects.create(
            post=self.post, author=self.user, content='Solution comment'
        )
        resp = self.client.post(
            reverse('forum:comment_solution', args=[comment.pk]),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        comment.refresh_from_db()
        self.assertTrue(comment.is_solution)