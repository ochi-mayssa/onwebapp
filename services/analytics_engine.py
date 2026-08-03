from django.db.models import Sum, Avg, Count
from django.utils import timezone
from .models import SocialPost, SocialUser, Hashtag, PlatformMetrics
from .crawlers.instagram_crawler import InstagramCrawler
from .crawlers.tiktok_crawler import TikTokCrawler
from .crawlers.youtube_crawler import YouTubeCrawler
from .crawlers.twitter_crawler import TwitterCrawler
from .crawlers.facebook_crawler import FacebookCrawler
from .crawlers.linkedin_crawler import LinkedInCrawler
from projects.models import WorkflowNotification
from django.contrib.auth import get_user_model
import re
import logging

User = get_user_model()
logger = logging.getLogger(__name__)

class AnalyticsEngine:
    def __init__(self):
        self.crawlers = {
            'instagram': InstagramCrawler(),
            'tiktok': TikTokCrawler(),
            'youtube': YouTubeCrawler(),
            'twitter': TwitterCrawler(),
            'facebook': FacebookCrawler(),
            'linkedin': LinkedInCrawler()
        }

    def run_analysis(self, platform, target):
        """
        Main entry point: Crawl -> Process -> Analyze
        """
        try:
            crawler = self.crawlers.get(platform)
            if not crawler:
                raise ValueError(f"No crawler for {platform}")

            # 1. Crawl
            try:
                raw_posts = crawler.crawl(target)
            except Exception as e:
                self._notify_admin(f"Crawler failed for {platform}: {str(e)}", severity='HIGH')
                logger.error(f"Crawler failed for {platform}: {e}")
                return {'status': 'error', 'message': f'Crawler failed: {str(e)}'}

            if not raw_posts:
                self._notify_admin(f"No data returned for {platform} target {target}", severity='MEDIUM')
                return {'status': 'no_data', 'message': f'No posts found for {target}'}

            # 2. Process & Save
            processed_count = 0
            new_posts = 0
            
            for post_data in raw_posts:
                try:
                    # Save User
                    user_info = post_data.pop('user_data')
                    user, created = SocialUser.objects.update_or_create(
                        platform_id=str(user_info['id']),
                        defaults={
                            'username': user_info['username'],
                            'platform': platform,
                            'followers_count': user_info.get('followers', 0)
                        }
                    )

                    # Extract Hashtags
                    caption = post_data.get('caption', '')
                    tags = re.findall(r"#(\w+)", caption)
                    
                    # Save Post
                    post, p_created = SocialPost.objects.update_or_create(
                        post_id=str(post_data['post_id']),
                        defaults={
                            'user': user,
                            'platform': platform,
                            'post_url': post_data['post_url'],
                            'caption': caption,
                            'posted_at': post_data['posted_at'], # Ensure crawler returns ISO or datetime
                            'likes': post_data.get('likes', 0),
                            'comments': post_data.get('comments', 0),
                            'shares': post_data.get('shares', 0),
                            'views': post_data.get('views', 0)
                        }
                    )

                    if p_created:
                        new_posts += 1

                    # Associate Hashtags
                    for tag_name in tags:
                        tag, _ = Hashtag.objects.get_or_create(name=tag_name.lower())
                        post.hashtags.add(tag)
                        # Update basic hashtag stats
                        tag.total_posts = tag.posts.count()
                        tag.avg_engagement = tag.posts.aggregate(avg=Avg('engagement_score'))['avg'] or 0
                        tag.save()

                    # Classify
                    self._classify_post(post)
                    processed_count += 1

                except Exception as e:
                    logger.error(f"Error processing post {post_data.get('post_id', 'unknown')}: {e}")
                    # Continue processing other posts even if one fails
                    continue

            # 3. Update Platform Metrics
            self._update_platform_metrics(platform)

            return {
                'status': 'success',
                'posts_processed': processed_count,
                'new_posts': new_posts,
                'user': user.username
            }

        except Exception as e:
            logger.critical(f"Critical failure in run_analysis: {e}")
            self._notify_admin(f"Critical Analytics Failure: {str(e)}", severity='HIGH')
            return {'status': 'error', 'message': str(e)}

    def _classify_post(self, post):
        """
        Classifies post as Viral, Normal, or Low based on relative performance.
        """
        try:
            # Get average engagement for this user
            avg_eng = SocialPost.objects.filter(user=post.user).aggregate(avg=Avg('engagement_score'))['avg'] or 0
            
            if avg_eng == 0:
                post.classification = 'normal'
            elif post.engagement_score > avg_eng * 2:
                post.classification = 'viral'
            elif post.engagement_score < avg_eng * 0.5:
                post.classification = 'low'
            else:
                post.classification = 'normal'
            post.save()
        except Exception as e:
            logger.error(f"Error classifying post {post.id}: {e}")

    def _update_platform_metrics(self, platform):
        try:
            posts = SocialPost.objects.filter(platform=platform)
            total = posts.count()
            if total > 0:
                avg_rate = posts.aggregate(avg=Avg('engagement_score'))['avg']
                PlatformMetrics.objects.update_or_create(
                    platform=platform,
                    defaults={
                        'total_posts_tracked': total,
                        'avg_engagement_rate': avg_rate
                    }
                )
        except Exception as e:
            logger.error(f"Error updating platform metrics for {platform}: {e}")

    def get_dashboard_stats(self):
        """
        Aggregates data for the dashboard.
        """
        try:
            stats = {
                'total_posts': SocialPost.objects.count(),
                'total_users': SocialUser.objects.count(),
                'viral_posts': SocialPost.objects.filter(classification='viral').count(),
                'platforms': list(PlatformMetrics.objects.values()),
                'top_hashtags': list(Hashtag.objects.order_by('-avg_engagement')[:5].values('name', 'avg_engagement', 'total_posts'))
            }
            return stats
        except Exception as e:
            logger.error(f"Error fetching dashboard stats: {e}")
            return {}

    def _notify_admin(self, message, severity='MEDIUM'):
        """
        Helper to notify admins of system issues.
        """
        try:
            admins = User.objects.filter(is_superuser=True)
            for admin in admins:
                WorkflowNotification.objects.create(
                    recipient=admin,
                    notification_type='SYSTEM',
                    message=message,
                    severity=severity
                )
        except Exception as e:
            logger.error(f"Failed to send admin notification: {e}")
