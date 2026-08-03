from django.core.management.base import BaseCommand
from django.utils.text import slugify
from django.utils import timezone
from django.db import models
from django.contrib.auth import get_user_model
from forum.models import ForumCategory, ForumTag, ForumBadge, ForumPost


class Command(BaseCommand):
    help = 'Seed forum with default categories, tags, badges, and sample posts'

    def handle(self, *args, **options):
        self._create_categories()
        self._create_tags()
        self._create_badges()
        self._create_sample_posts()
        self.stdout.write(self.style.SUCCESS('Forum seeded successfully'))

    def _get_or_create_user(self, username, email=None, first_name='', last_name=''):
        User = get_user_model()
        user, created = User.objects.get_or_create(
            username=username,
            defaults=dict(
                email=email or f'{username}@example.com',
                first_name=first_name or username.capitalize(),
                last_name=last_name,
            ),
        )
        if created:
            user.set_password('password123')
            user.save()
        return user

    def _create_categories(self):
        categories = [
            ('General Discussion', 'General chat and announcements', 'fas fa-comments', '#6366f1', 0),
            ('Showcase', 'Share your projects and get feedback', 'fas fa-rocket', '#10b981', 1),
            ('Help & Support', 'Get help with your projects', 'fas fa-life-ring', '#f59e0b', 2),
            ('Tutorials & Guides', 'Share knowledge and tutorials', 'fas fa-book', '#3b82f6', 3),
            ('Jobs & Opportunities', 'Job postings, freelance, internships', 'fas fa-briefcase', '#8b5cf6', 4),
            ('Events', 'Hackathons, webinars, meetups, workshops', 'fas fa-calendar', '#ec4899', 5),
            ('Feedback & Suggestions', 'Share ideas to improve the platform', 'fas fa-lightbulb', '#14b8a6', 6),
        ]
        for name, desc, icon, color, order in categories:
            ForumCategory.objects.get_or_create(
                slug=slugify(name),
                defaults=dict(
                    name=name, description=desc, icon=icon,
                    color=color, order=order, is_active=True,
                ),
            )
        self.stdout.write(f'  Created {len(categories)} categories')

    def _create_tags(self):
        tags = [
            ('python', '#3776AB'), ('javascript', '#F7DF1E'), ('react', '#61DAFB'),
            ('django', '#092E20'), ('html', '#E34F26'), ('css', '#1572B6'),
            ('design', '#FF6B6B'), ('mobile', '#34C759'), ('api', '#6C5CE7'),
            ('database', '#336791'), ('devops', '#2396ED'), ('security', '#E74C3C'),
            ('ui-ux', '#A29BFE'), ('testing', '#55EFC4'), ('performance', '#FDCB6E'),
            ('beginner', '#00B894'), ('advanced', '#E17055'), ('tutorial', '#0984E3'),
            ('showcase', '#6C5CE7'), ('job', '#00CEC9'), ('event', '#FDA7DF'),
            ('question', '#F9CA24'), ('discussion', '#7F8C8D'),
        ]
        for name, color in tags:
            ForumTag.objects.get_or_create(
                slug=slugify(name),
                defaults=dict(name=name, color=color),
            )
        self.stdout.write(f'  Created {len(tags)} tags')

    def _create_badges(self):
        badges = [
            ('First Post', 'first_post', 'Published your first post', 'fas fa-pen-fancy', '#6366f1'),
            ('First Comment', 'first_comment', 'Left your first comment', 'fas fa-comment', '#10b981'),
            ('First Upvote', 'first_upvote', 'Received your first upvote', 'fas fa-thumbs-up', '#3b82f6'),
            ('Popular Post', 'popular_post', 'Post reached 10 upvotes', 'fas fa-fire', '#f59e0b'),
            ('Viral Post', 'viral_post', 'Post reached 50 upvotes', 'fas fa-bolt', '#ef4444'),
            ('Solution Provider', 'solution_provider', 'Had a comment marked as solution', 'fas fa-check-circle', '#8b5cf6'),
            ('Helping Hand', 'helping_hand', 'Left 10 comments', 'fas fa-hands-helping', '#14b8a6'),
            ('Conversation Starter', 'conversation_starter', 'Created 5 posts', 'fas fa-comments', '#ec4899'),
            ('Showcase Star', 'showcase_star', 'Featured in showcase', 'fas fa-star', '#f59e0b'),
            ('Veteran', 'veteran', 'Member for over a year', 'fas fa-crown', '#6366f1'),
        ]
        for name, slug_val, desc, icon, color in badges:
            ForumBadge.objects.get_or_create(
                slug=slug_val,
                defaults=dict(
                    name=name, description=desc, icon=icon, color=color,
                    criteria=desc,
                ),
            )
        self.stdout.write(f'  Created {len(badges)} badges')

    def _create_sample_posts(self):
        users = [
            self._get_or_create_user('alice', 'alice@example.com', 'Alice', 'Johnson'),
            self._get_or_create_user('bob', 'bob@example.com', 'Bob', 'Smith'),
            self._get_or_create_user('carol', 'carol@example.com', 'Carol', 'Davis'),
        ]
        gen_cat = ForumCategory.objects.get(slug='general-discussion')
        help_cat = ForumCategory.objects.get(slug='help-support')
        showcase_cat = ForumCategory.objects.get(slug='showcase')
        tutorial_cat = ForumCategory.objects.get(slug='tutorials-guides')
        feedback_cat = ForumCategory.objects.get(slug='feedback-suggestions')
        jobs_cat = ForumCategory.objects.get(slug='jobs-opportunities')

        python_tag = ForumTag.objects.get(slug='python')
        django_tag = ForumTag.objects.get(slug='django')
        react_tag = ForumTag.objects.get(slug='react')
        beginner_tag = ForumTag.objects.get(slug='beginner')
        question_tag = ForumTag.objects.get(slug='question')
        discussion_tag = ForumTag.objects.get(slug='discussion')
        showcase_tag = ForumTag.objects.get(slug='showcase')
        tutorial_tag = ForumTag.objects.get(slug='tutorial')
        design_tag = ForumTag.objects.get(slug='design')

        posts_data = [
            dict(
                author=users[0], category=gen_cat, title='Welcome to the Community Forum!',
                content='Hello everyone! We are excited to launch our new community forum. This is the place to discuss everything related to web development, share your projects, ask for help, and connect with fellow developers.\n\nFeel free to introduce yourself in the comments below! What kind of projects are you working on?',
                tags=[discussion_tag], status='published', is_pinned=True, views_count=42, score=15, upvotes=18, downvotes=3,
            ),
            dict(
                author=users[1], category=help_cat, title='How do I deploy a Django app to production?',
                content='I have built a Django application locally and it works great. Now I want to deploy it to production but I am not sure about the best approach.\n\nShould I use Docker? What about database migrations in production? Any recommendations for hosting providers that work well with Django?\n\nThanks in advance for your help!',
                tags=[python_tag, django_tag, question_tag], status='published', views_count=28, score=10, upvotes=12, downvotes=2,
            ),
            dict(
                author=users[2], category=showcase_cat, title='My Personal Portfolio Website - Built with React',
                content='I just finished building my personal portfolio website using React and Tailwind CSS. I wanted to share it with the community and get some feedback.\n\nKey features:\n- Responsive design\n- Dark/light mode toggle\n- Project showcase with filtering\n- Contact form with EmailJS integration\n\nCheck out the live demo and let me know what you think!',
                tags=[react_tag, design_tag, showcase_tag], status='published', is_showcase=True, project_name='Portfolio Website', tech_stack='React, Tailwind CSS, Vite', views_count=35, score=20, upvotes=22, downvotes=2,
                github_link='https://github.com/carol/portfolio', live_demo='https://carol.dev',
            ),
            dict(
                author=users[0], category=tutorial_cat, title='Getting Started with Django REST Framework',
                content='In this tutorial, I will walk you through building a simple REST API using Django REST Framework.\n\nWe will cover:\n1. Setting up DRF\n2. Creating serializers\n3. Building ViewSets\n4. Adding authentication\n5. Testing endpoints\n\nThis is aimed at beginners who already know basic Django.',
                tags=[python_tag, django_tag, tutorial_tag], status='published', views_count=56, score=25, upvotes=28, downvotes=3,
            ),
            dict(
                author=users[1], category=feedback_cat, title='Feature Request: Dark Mode for the Dashboard',
                content='I would love to see a dark mode option for the platform dashboard. I know the forum already supports dark mode through the theme toggle, but the dashboard pages could also benefit.\n\nWhat does everyone else think? Would you use dark mode on the dashboard?',
                tags=[discussion_tag, design_tag], status='published', views_count=19, score=8, upvotes=10, downvotes=2,
            ),
            dict(
                author=users[2], category=jobs_cat, title='Junior Django Developer Position Available',
                content='We are hiring a junior Django developer to join our team!\n\nRequirements:\n- Basic knowledge of Python and Django\n- Familiarity with HTML/CSS\n- Willingness to learn\n\nNice to have:\n- Experience with React or Vue\n- Understanding of REST APIs\n\nLocation: Remote\nSalary: Competitive',
                tags=[python_tag, django_tag],
                status='published', views_count=31, score=12, upvotes=14, downvotes=2,
            ),
        ]

        created = 0
        for data in posts_data:
            tags = data.pop('tags', [])
            title = data['title']
            post, was_created = ForumPost.objects.get_or_create(
                slug=slugify(title)[:350],
                defaults=dict(
                    excerpt=data['content'][:300],
                    **data,
                ),
            )
            if was_created:
                post.tags.add(*tags)
                created += 1
                ForumCategory.objects.filter(pk=post.category_id).update(
                    post_count=models.F('post_count') + 1
                )

        self.stdout.write(f'  Created {created} sample posts')
