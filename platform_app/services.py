from .models import Link, IoTDevice, SocialAccount, SecurityAudit

class PlatformService:
    """
    Service layer to handle data retrieval for the platform dashboard.
    This acts as an abstraction over direct database access or external API calls.
    """

    @staticmethod
    def get_dashboard_stats():
        """
        Retrieves statistics for the dashboard from the database.
        """
        # Count links (as a proxy for website tools usage or just total links)
        # For "tools available", we might still want to list the hardcoded tools,
        # but maybe we count how many are "active" or configured.
        # For now, let's keep "website_tools_count" as the number of available tools (static 4)
        # OR count the number of Link objects? The dashboard says "Tools available".
        # Let's keep it static 4 for "Tools available" as they are features.
        
        # Real counts:
        iot_count = IoTDevice.objects.filter(status='active').count()
        social_count = SocialAccount.objects.filter(is_active=True).count()
        
        security_audit = SecurityAudit.objects.last()
        security_score = security_audit.score if security_audit else 0

        return {
            'website_tools_count': 4, # Static feature count
            'iot_devices_count': iot_count,
            'social_accounts_count': social_count,
            'security_score': security_score
        }

    @staticmethod
    def get_website_tools():
        """
        Retrieves the list of available website analysis tools.
        """
        # These are features, so they are static for now unless we store features in DB
        return [
            {
                'name': 'Internal Link Analysis',
                'icon': 'fas fa-link',
                'url': '#' # Could link to actual views
            },
            {
                'name': 'External Link Monitor',
                'icon': 'fas fa-external-link-alt',
                'url': '#'
            },
            {
                'name': 'Backlink Checker',
                'icon': 'fas fa-retweet',
                'url': '#'
            },
            {
                'name': 'XML Sitemap Generator',
                'icon': 'fas fa-sitemap',
                'url': '#'
            }
        ]

    @staticmethod
    def get_automation_tools():
        """
        Retrieves the list of industrial automation tools/features.
        """
        return [
            {
                'name': 'IoT Device Dashboard',
                'icon': 'fas fa-microchip',
                'url': '#'
            },
            {
                'name': 'Real-time Analytics',
                'icon': 'fas fa-chart-line',
                'url': '#'
            },
            {
                'name': 'Automation Rules',
                'icon': 'fas fa-cogs',
                'url': '#'
            },
            {
                'name': 'Alerts & Notifications',
                'icon': 'fas fa-bell',
                'url': '#'
            }
        ]
