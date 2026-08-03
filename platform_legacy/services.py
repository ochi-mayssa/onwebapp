class PlatformService:
    """
    Service layer to handle data retrieval for the platform dashboard.
    This acts as an abstraction over direct database access or external API calls.
    """

    @staticmethod
    def get_dashboard_stats():
        """
        Retrieves statistics for the dashboard.
        Currently returns mock data, but designed to be replaced with real DB queries or API calls.
        """
        # TODO: Replace with real queries to Analytics/IoT/Social services
        return {
            'website_tools_count': 4,
            'iot_devices_count': 12,
            'social_accounts_count': 8,
            'security_score': 94
        }

    @staticmethod
    def get_website_tools():
        """
        Retrieves the list of available website analysis tools.
        """
        return [
            {
                'name': 'Internal Link Analysis',
                'icon': 'fas fa-link',
                'url': '#'
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
