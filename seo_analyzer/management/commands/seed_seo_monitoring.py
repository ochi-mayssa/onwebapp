import random
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from seo_analyzer.models import SEOMonitoringSnapshot


class Command(BaseCommand):
    help = 'Seed SEO monitoring snapshots with sample data'

    def handle(self, *args, **options):
        now = timezone.now()
        domains = ['onwebapp.com']
        types = ['website', 'internal', 'external', 'backlinks']
        count = 0

        for domain in domains:
            for analysis_type in types:
                for i in range(6):
                    SEOMonitoringSnapshot.objects.get_or_create(
                        source_identifier=f'seed-{domain}-{analysis_type}-{i}',
                        defaults={
                            'website': f'https://{domain}',
                            'domain': domain,
                            'analysis_type': analysis_type,
                            'health_score': random.randint(40, 95),
                            'visibility_score': random.randint(30, 90),
                            'technical_score': random.randint(50, 95),
                            'performance_score': random.randint(40, 90),
                            'content_score': random.randint(35, 85),
                            'security_score': random.randint(60, 99),
                            'broken_links': random.randint(0, 12),
                            'redirects': random.randint(0, 8),
                            'internal_links': random.randint(20, 200),
                            'external_links': random.randint(5, 80),
                            'indexed_pages': random.randint(10, 500),
                            'issues_count': random.randint(0, 15),
                            'working_links': random.randint(50, 300),
                            'errors_count': random.randint(0, 5),
                            'created_at': now - timedelta(days=30 - i),
                        },
                    )
                    count += 1

        self.stdout.write(self.style.SUCCESS(f'Created {count} monitoring snapshots'))
