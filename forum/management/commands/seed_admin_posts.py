from django.core.management.base import BaseCommand
from django.utils.text import slugify
from django.utils import timezone
from django.db import models
from django.contrib.auth import get_user_model
from forum.models import ForumCategory, ForumTag, ForumPost, ForumComment


class Command(BaseCommand):
    help = 'Create admin accounts and seed forum posts from OnWebApp admin team'

    def handle(self, *args, **options):
        admins = self._create_admin_accounts()
        self._create_admin_posts(admins)
        self.stdout.write(self.style.SUCCESS('Admin accounts and posts seeded successfully'))

    def _create_admin_accounts(self):
        User = get_user_model()
        admin_data = [
            {
                'username': 'onwebapp_admin',
                'email': 'admin@onwebapp.com',
                'first_name': 'OnWebApp',
                'last_name': 'Admin',
                'is_staff': True,
                'is_superuser': True,
            },
            {
                'username': 'onwebapp_team',
                'email': 'team@onwebapp.com',
                'first_name': 'OnWebApp',
                'last_name': 'Team',
                'is_staff': True,
                'is_superuser': False,
            },
            {
                'username': 'onwebapp_support',
                'email': 'support@onwebapp.com',
                'first_name': 'Support',
                'last_name': 'Team',
                'is_staff': True,
                'is_superuser': False,
            },
        ]
        admins = {}
        for data in admin_data:
            user, created = User.objects.get_or_create(
                username=data['username'],
                defaults=data,
            )
            if created:
                user.set_password('OnWebApp2026!')
                user.save()
                self.stdout.write(f'  Created admin: {user.username}')
            admins[user.username] = user
        return admins

    def _create_admin_posts(self, admins):
        admin_user = admins['onwebapp_admin']
        team_user = admins['onwebapp_team']
        support_user = admins['onwebapp_support']

        gen_cat = ForumCategory.objects.get(slug='general-discussion')
        help_cat = ForumCategory.objects.get(slug='help-support')
        tutorial_cat = ForumCategory.objects.get(slug='tutorials-guides')
        feedback_cat = ForumCategory.objects.get(slug='feedback-suggestions')

        discussion_tag = ForumTag.objects.get(slug='discussion')
        announcement_tag, _ = ForumTag.objects.get_or_create(
            slug='announcement', defaults={'name': 'Announcement', 'color': '#ef4444'}
        )
        tutorial_tag = ForumTag.objects.get(slug='tutorial')
        question_tag = ForumTag.objects.get(slug='question')
        python_tag = ForumTag.objects.get(slug='python')
        django_tag = ForumTag.objects.get(slug='django')
        beginner_tag = ForumTag.objects.get(slug='beginner')
        design_tag = ForumTag.objects.get(slug='design')
        mobile_tag = ForumTag.objects.get(slug='mobile')
        security_tag = ForumTag.objects.get(slug='security')

        posts_data = [
            {
                'author': admin_user,
                'category': gen_cat,
                'title': 'Welcome to the OnWebApp Community Forum!',
                'content': (
                    'Welcome to our community forum! This is your space to connect with fellow creators, '
                    'share your projects, ask questions, and learn from each other.\n\n'
                    'Here is what you can do:\n'
                    '- Start a discussion in General Discussion\n'
                    '- Showcase your project in the Showcase category\n'
                    '- Ask for help in Help & Support\n'
                    '- Share tutorials in Tutorials & Guides\n\n'
                    'Our team is here to help you succeed. Do not hesitate to ask questions -- '
                    'no question is too small.\n\n'
                    'Introduce yourself in the comments and tell us what you are working on!'
                ),
                'tags': [announcement_tag, discussion_tag],
                'status': 'published',
                'is_pinned': True,
                'views_count': 156,
                'score': 42,
                'upvotes': 45,
                'downvotes': 3,
            },
            {
                'author': team_user,
                'category': gen_cat,
                'title': 'Platform Update: New Features This Month',
                'content': (
                    'We have been busy shipping improvements to make your experience better. '
                    'Here is what is new:\n\n'
                    '1. **Brand Assist** -- Get a complete brand identity (logo, colors, typography) '
                    'generated for your community project in minutes.\n\n'
                    '2. **Website Builder** -- Our onboarding wizard now walks you through '
                    'every step of creating your website, from domain to launch.\n\n'
                    '3. **Forum Improvements** -- Better search, smoother navigation, and '
                    'new badges to recognize your contributions.\n\n'
                    'Try them out and let us know what you think!'
                ),
                'tags': [announcement_tag],
                'status': 'published',
                'views_count': 89,
                'score': 28,
                'upvotes': 30,
                'downvotes': 2,
            },
            {
                'author': admin_user,
                'category': tutorial_cat,
                'title': 'How to Launch Your Community Website in Under 14 Days',
                'content': (
                    'Getting a website live does not have to take months. Here is our proven '
                    'process for launching a professional community website in under two weeks:\n\n'
                    '**Day 1-2: Planning**\n'
                    'Define your audience, gather content (text, images, logos), and choose your '
                    'platform features.\n\n'
                    '**Day 3-5: Design**\n'
                    'Use our Brand Assist tool to create your visual identity, or bring your own. '
                    'Select a template that fits your mission.\n\n'
                    '**Day 6-10: Build**\n'
                    'Our team builds your site while you review progress at each milestone. '
                    'No surprises.\n\n'
                    '**Day 11-13: Test & Refine**\n'
                    'We run performance tests, check mobile responsiveness, and fine-tune '
                    'every detail.\n\n'
                    '**Day 14: Launch**\n'
                    'Go live with confidence. We handle hosting, SSL, and backups.\n\n'
                    'Ready to start? Use the project wizard to begin your brief today.'
                ),
                'tags': [tutorial_tag, beginner_tag],
                'status': 'published',
                'views_count': 203,
                'score': 55,
                'upvotes': 58,
                'downvotes': 3,
            },
            {
                'author': support_user,
                'category': help_cat,
                'title': 'Getting Started Guide: Your First Steps on OnWebApp',
                'content': (
                    'New here? This guide will help you get set up and running quickly.\n\n'
                    '**Step 1: Create Your Account**\n'
                    'Sign up with your email and complete your profile.\n\n'
                    '**Step 2: Start a Project**\n'
                    'Go to the Dashboard and click "New Project" to launch the onboarding wizard. '
                    'It will guide you through selecting services and describing your needs.\n\n'
                    '**Step 3: Explore Brand Assist**\n'
                    'Need a logo or brand identity? Brand Assist generates a complete brand kit '
                    'tailored to your community project.\n\n'
                    '**Step 4: Join the Forum**\n'
                    'You are already here! Introduce yourself, ask questions, and connect with '
                    'other community builders.\n\n'
                    'Need help at any point? Our support team responds within a few hours.'
                ),
                'tags': [beginner_tag, tutorial_tag],
                'status': 'published',
                'views_count': 134,
                'score': 35,
                'upvotes': 38,
                'downvotes': 3,
            },
            {
                'author': admin_user,
                'category': feedback_cat,
                'title': 'What Features Would You Like to See Next?',
                'content': (
                    'We are always looking for ways to improve OnWebApp. Your feedback '
                    'directly shapes our roadmap.\n\n'
                    'Some ideas we are considering:\n'
                    '- E-commerce integration for selling merchandise\n'
                    '- Email newsletter builder\n'
                    '- Event management and ticketing\n'
                    '- Multi-language support\n'
                    '- Advanced analytics dashboard\n\n'
                    'Which of these would be most valuable to you? Or do you have other ideas? '
                    'Drop your thoughts in the comments below.'
                ),
                'tags': [discussion_tag],
                'status': 'published',
                'views_count': 67,
                'score': 22,
                'upvotes': 24,
                'downvotes': 2,
            },
            {
                'author': team_user,
                'category': tutorial_cat,
                'title': '5 Tips for Making Your Community Website Stand Out',
                'content': (
                    'Your community project deserves a website that makes an impact. '
                    'Here are five tips from our design team:\n\n'
                    '1. **Tell Your Story** -- People connect with stories, not features. '
                    'Put your mission front and center.\n\n'
                    '2. **Use High-Quality Images** -- Invest in good photography or use '
                    'our recommended free image resources.\n\n'
                    '3. **Keep It Simple** -- A clean, focused website converts better '
                    'than a cluttered one. Less is more.\n\n'
                    '4. **Mobile First** -- Over 60% of visitors will view your site on '
                    'a phone. Design for mobile first.\n\n'
                    '5. **Clear Call to Action** -- Tell visitors exactly what to do next: '
                    'join, donate, volunteer, or share.\n\n'
                    'Need help implementing these? Our Website Building service handles '
                    'all of this for you.'
                ),
                'tags': [tutorial_tag, design_tag],
                'status': 'published',
                'views_count': 112,
                'score': 31,
                'upvotes': 34,
                'downvotes': 3,
            },
            {
                'author': support_user,
                'category': help_cat,
                'title': 'Common Questions About Hosting and Domains',
                'content': (
                    'Here are answers to the most common questions we receive about hosting '
                    'and domain setup:\n\n'
                    '**Do I need to buy my own domain?**\n'
                    'You can use a free subdomain (yourproject.onwebapp.com) or connect '
                    'your own custom domain.\n\n'
                    '**Is SSL included?**\n'
                    'Yes. Every site gets a free SSL certificate for secure HTTPS connections.\n\n'
                    '**What about backups?**\n'
                    'We run automatic daily backups. You can restore any backup from your dashboard.\n\n'
                    '**Can I migrate away later?**\n'
                    'Absolutely. You own your content and can export it at any time. '
                    'No lock-in.\n\n'
                    'Have more questions? Ask in the comments or contact our support team.'
                ),
                'tags': [beginner_tag, question_tag],
                'status': 'published',
                'views_count': 78,
                'score': 18,
                'upvotes': 20,
                'downvotes': 2,
            },
            {
                'author': admin_user,
                'category': gen_cat,
                'title': 'Community Spotlight: How Local Organizations Are Using OnWebApp',
                'content': (
                    'We are inspired by the incredible work our community members are doing. '
                    'Here are a few highlights:\n\n'
                    '**Community Garden Collective** -- Launched a website to coordinate '
                    'volunteer schedules and share gardening tips with 200+ members.\n\n'
                    '**Youth Coding Academy** -- Built an online learning hub where students '
                    'can access tutorials, submit projects, and track progress.\n\n'
                    '**Neighborhood Watch Network** -- Created a secure platform for residents '
                    'to share updates, report issues, and stay connected.\n\n'
                    '**Faith Community Alliance** -- Designed a vibrant website with event '
                    'calendars, donation integration, and member directories.\n\n'
                    'Want to be featured? Share your project in the Showcase category!'
                ),
                'tags': [discussion_tag, mobile_tag],
                'status': 'published',
                'views_count': 94,
                'score': 27,
                'upvotes': 29,
                'downvotes': 2,
            },
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

        self.stdout.write(f'  Created {created} admin posts')
