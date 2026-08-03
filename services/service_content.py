
from django.utils.translation import gettext_lazy as _

SERVICE_CONTENT = {
    'project-management': {
        'title': _('Project Management'),
        'subtitle': _('Intelligent Workflows for Modern Teams'),
        'badge': 'WF-001',
        'icon': 'fas fa-tasks',
        'color': 'primary',
        'hero_bg': 'linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%)',
        'layout': 'standard',
        'description': _('Streamline your operations with our AI-enhanced project management suite. From automated task assignment to predictive timeline estimation, we help you deliver faster.'),
        'features': [
            {
                'title': _('Smart Automation'),
                'description': _('Automatically assign tasks and update statuses based on triggers.'),
                'icon': 'fas fa-robot'
            },
            {
                'title': _('Visual Planning'),
                'description': _('Switch between Kanban, Gantt, and List views instantly.'),
                'icon': 'fas fa-chart-gantt'
            },
            {
                'title': _('Resource Optimization'),
                'description': _('Balance workload across your team with real-time capacity insights.'),
                'icon': 'fas fa-users-cog'
            }
        ],
        'benefits': [
            _('Reduce project overhead by 30%'),
            _('Improve team collaboration and visibility'),
            _('Never miss a deadline with smart alerts')
        ],
        'onboarding': {
            'title': _('Get Started in Minutes'),
            'steps': [
                {'title': _('Import Data'), 'desc': _('Sync with Jira, Trello, or CSV.')},
                {'title': _('Invite Team'), 'desc': _('Set roles and permissions.')},
                {'title': _('Start Tracking'), 'desc': _('Launch your first sprint.')}
            ]
        },
        'cta': {
            'text': _('Start Free Trial'),
            'link': 'home:demo_request',
            'secondary_text': _('View Pricing'),
            'secondary_link': 'home:use_cases'
        },
        'seo': {
            'title': 'Project Management Software | OnWebApp',
            'description': 'Best-in-class project management tool with automation and AI features.'
        }
    },
    'payment-automation': {
        'title': _('Payment Automation'),
        'subtitle': _('Global Payments, Simplified'),
        'badge': 'WF-002',
        'icon': 'fas fa-credit-card',
        'color': 'success',
        'hero_bg': 'linear-gradient(135deg, #e0f7fa 0%, #80deea 100%)',
        'layout': 'standard',
        'description': _('Handle subscriptions, one-time payments, and complex billing cycles with ease. Secure, compliant, and integrated with major gateways.'),
        'features': [
            {
                'title': _('Recurring Billing'),
                'description': _('Automate subscription renewals and dunning management.'),
                'icon': 'fas fa-sync'
            },
            {
                'title': _('Global Currencies'),
                'description': _('Accept payments in 135+ currencies automatically.'),
                'icon': 'fas fa-globe'
            },
            {
                'title': _('Fraud Protection'),
                'description': _('AI-driven fraud detection to keep your revenue safe.'),
                'icon': 'fas fa-shield-alt'
            }
        ],
        'benefits': [
            _('Reduce failed payments by 25%'),
            _('Automate tax calculation and compliance'),
            _('Instant reconciliation with finance tools')
        ],
        'onboarding': {
            'title': _('Seamless Integration'),
            'steps': [
                {'title': _('Connect Gateway'), 'desc': _('Link Stripe or PayPal account.')},
                {'title': _('Define Plans'), 'desc': _('Set up pricing tiers.')},
                {'title': _('Go Live'), 'desc': _('Embed checkout on your site.')}
            ]
        },
        'cta': {
            'text': _('Automate Payments Now'),
            'link': 'home:demo_request',
            'secondary_text': _('Documentation'),
            'secondary_link': 'home:api_docs'
        },
        'seo': {
            'title': 'Payment Automation Platform | OnWebApp',
            'description': 'Automate your billing, subscriptions, and invoicing securely.'
        }
    },
    'dashboard-analytics': {
        'title': _('Analytics Hub'),
        'subtitle': _('Your Business at a Glance'),
        'badge': 'WF-003',
        'icon': 'fas fa-chart-line',
        'color': 'info',
        'hero_bg': 'linear-gradient(135deg, #e1f5fe 0%, #b3e5fc 100%)',
        'layout': 'standard',
        'description': _('Unify data from marketing, sales, and operations into a single source of truth. Real-time dashboards for data-driven leadership.'),
        'features': [
            {
                'title': _('Custom Dashboards'),
                'description': _('Drag-and-drop widgets to build your perfect view.'),
                'icon': 'fas fa-th-large'
            },
            {
                'title': _('Predictive Insights'),
                'description': _('AI forecasts revenue and user growth trends.'),
                'icon': 'fas fa-crystal-ball'
            },
            {
                'title': _('Data Export'),
                'description': _('Download reports in PDF, CSV, or Excel formats.'),
                'icon': 'fas fa-file-export'
            }
        ],
        'benefits': [
            _('Eliminate data silos'),
            _('Make faster, informed decisions'),
            _('Share insights with stakeholders instantly')
        ],
        'onboarding': {
            'title': _('Data in Minutes'),
            'steps': [
                {'title': _('Connect Sources'), 'desc': _('Link CRM, Ads, and DBs.')},
                {'title': _('Build Views'), 'desc': _('Select key metrics.')},
                {'title': _('Visualize'), 'desc': _('See your data come to life.')}
            ]
        },
        'cta': {
            'text': _('Try Analytics Hub'),
            'link': 'home:demo_request',
            'secondary_text': _('Live Demo'),
            'secondary_link': 'home:demo_request'
        },
        'seo': {
            'title': 'Business Analytics Dashboard | OnWebApp',
            'description': 'Centralized business intelligence and analytics reporting tools.'
        }
    },
    'social-intelligence': {
        'title': _('Social Intelligence'),
        'subtitle': _('Listen, Analyze, Engage'),
        'badge': 'WF-004',
        'icon': 'fas fa-share-alt',
        'color': 'warning',
        'hero_bg': 'linear-gradient(135deg, #fff3e0 0%, #ffe0b2 100%)',
        'layout': 'standard',
        'description': _('Monitor brand sentiment, track competitors, and discover trends across all major social platforms in real-time.'),
        'features': [
            {
                'title': _('Multi-Platform Crawling'),
                'description': _('Track Twitter, LinkedIn, Instagram, and more.'),
                'icon': 'fas fa-hashtag'
            },
            {
                'title': _('Sentiment Analysis'),
                'description': _('Understand how people feel about your brand.'),
                'icon': 'fas fa-smile'
            },
            {
                'title': _('Trend Spotting'),
                'description': _('Identify viral topics before they peak.'),
                'icon': 'fas fa-fire'
            }
        ],
        'benefits': [
            _('Protect your brand reputation'),
            _('Identify influencer opportunities'),
            _('Benchmark against competitors')
        ],
        'onboarding': {
            'title': _('Start Listening'),
            'steps': [
                {'title': _('Add Keywords'), 'desc': _('Brand name, products, hashtags.')},
                {'title': _('Set Alerts'), 'desc': _('Get notified on spikes.')},
                {'title': _('Analyze'), 'desc': _('View sentiment reports.')}
            ]
        },
        'cta': {
            'text': _('Start Monitoring'),
            'link': 'services:social_dashboard',
            'secondary_text': _('View Features'),
            'secondary_link': 'home:features'
        },
        'seo': {
            'title': 'Social Media Intelligence Tool | OnWebApp',
            'description': 'Advanced social listening and brand monitoring platform.'
        }
    },
    'hr-operations': {
        'title': _('HR Operations'),
        'subtitle': _('People First, Paperwork Last'),
        'badge': 'WF-005',
        'icon': 'fas fa-user-tie',
        'color': 'danger',
        'hero_bg': 'linear-gradient(135deg, #ffebee 0%, #ffcdd2 100%)',
        'layout': 'standard',
        'description': _('Modernize your HR stack. From seamless onboarding to automated payroll sync, give your employees the experience they deserve.'),
        'features': [
            {
                'title': _('Digital Onboarding'),
                'description': _('Paperless contract signing and document collection.'),
                'icon': 'fas fa-file-signature'
            },
            {
                'title': _('Leave Management'),
                'description': _('Self-service portal for time-off requests.'),
                'icon': 'fas fa-calendar-check'
            },
            {
                'title': _('Performance Reviews'),
                'description': _('Structured cycles for feedback and growth.'),
                'icon': 'fas fa-star'
            }
        ],
        'benefits': [
            _('Reduce admin time by 50%'),
            _('Improve employee satisfaction'),
            _('Ensure compliance automatically')
        ],
        'onboarding': {
            'title': _('Modernize HR'),
            'steps': [
                {'title': _('Import Staff'), 'desc': _('Bulk upload employee data.')},
                {'title': _('Configure Policies'), 'desc': _('Set leave and work rules.')},
                {'title': _('Invite Team'), 'desc': _('Launch self-service portal.')}
            ]
        },
        'cta': {
            'text': _('Upgrade HR Ops'),
            'link': 'home:demo_request',
            'secondary_text': _('Contact Sales'),
            'secondary_link': 'contact:contact'
        },
        'seo': {
            'title': 'HR Operations Software | OnWebApp',
            'description': 'HR management system for modern employee experiences.'
        }
    },
    'iot-integration': {
        'title': _('IoT Control'),
        'subtitle': _('The Industrial Internet of Things'),
        'badge': 'WF-006',
        'icon': 'fas fa-microchip',
        'color': 'secondary',
        'hero_bg': 'linear-gradient(135deg, #eceff1 0%, #cfd8dc 100%)',
        'layout': 'standard',
        'description': _('Connect, monitor, and control your industrial hardware. Real-time telemetry and remote command execution for smart factories.'),
        'features': [
            {
                'title': _('Device Management'),
                'description': _('Provision and update fleet devices over-the-air.'),
                'icon': 'fas fa-server'
            },
            {
                'title': _('Real-time Telemetry'),
                'description': _('Sub-second latency for sensor data streams.'),
                'icon': 'fas fa-wave-square'
            },
            {
                'title': _('Automated Alerts'),
                'description': _('Instant notifications for hardware anomalies.'),
                'icon': 'fas fa-bell'
            }
        ],
        'benefits': [
            _('Reduce downtime with predictive maintenance'),
            _('Centralize control of distributed assets'),
            _('Scale from 10 to 10k devices')
        ],
        'onboarding': {
            'title': _('Connect Devices'),
            'steps': [
                {'title': _('Install SDK'), 'desc': _('Python/C++ agents for hardware.')},
                {'title': _('Provision'), 'desc': _('Secure handshake with cloud.')},
                {'title': _('Monitor'), 'desc': _('See live data streams.')}
            ]
        },
        'cta': {
            'text': _('Explore IoT Suite'),
            'link': 'services:industrial_automation',
            'secondary_text': _('Read Case Study'),
            'secondary_link': 'home:use_cases'
        },
        'seo': {
            'title': 'Industrial IoT Platform | OnWebApp',
            'description': 'Secure IoT device management and control platform.'
        }
    },
    'finance-billing': {
        'title': _('Finance & Billing'),
        'subtitle': _('Financial Clarity for Enterprise'),
        'badge': 'WF-007',
        'icon': 'fas fa-file-invoice-dollar',
        'color': 'primary',
        'hero_bg': 'linear-gradient(135deg, #e8eaf6 0%, #c5cae9 100%)',
        'layout': 'standard',
        'description': _('Close your books faster. Comprehensive financial management handling invoicing, expenses, and ledger reconciliation.'),
        'features': [
            {
                'title': _('Smart Invoicing'),
                'description': _('Auto-generate invoices based on usage or milestones.'),
                'icon': 'fas fa-file-invoice'
            },
            {
                'title': _('Expense Tracking'),
                'description': _('Scan receipts and automate approvals.'),
                'icon': 'fas fa-receipt'
            },
            {
                'title': _('Financial Reconciliation'),
                'description': _('Sync with bank accounts and ledgers automatically.'),
                'icon': 'fas fa-balance-scale'
            }
        ],
        'benefits': [
            _('Reduce month-end closing time by 40%'),
            _('Improve cash flow visibility'),
            _('Eliminate manual data entry errors')
        ],
        'onboarding': {
            'title': _('Unified Finance'),
            'steps': [
                {'title': _('Import Ledger'), 'desc': _('Upload historical records.')},
                {'title': _('Connect Banks'), 'desc': _('Link corporate accounts.')},
                {'title': _('Set Workflows'), 'desc': _('Automate invoice approvals.')}
            ]
        },
        'cta': {
            'text': _('Start Finance Demo'),
            'link': 'home:demo_request',
            'secondary_text': _('Contact Finance Team'),
            'secondary_link': 'contact:contact'
        },
        'seo': {
            'title': 'Finance and Billing Software | OnWebApp',
            'description': 'Automated enterprise billing and finance solutions.'
        }
    },
    'erp-integration': {
        'title': _('ERP Integration'),
        'subtitle': _('Unified Enterprise Operations'),
        'badge': 'ERP-001',
        'icon': 'fas fa-industry',
        'color': 'info',
        'hero_bg': 'linear-gradient(135deg, #fdfbfb 0%, #ebedee 100%)',
        'layout': 'standard',
        'description': _('Connect your entire business. Our ERP integration suite bridges the gap between sales, inventory, finance, and human resources into a single source of truth.'),
        'features': [
            {
                'title': _('Real-time Inventory'),
                'description': _('Track stock levels across multiple warehouses instantly.'),
                'icon': 'fas fa-boxes'
            },
            {
                'title': _('Financial Reporting'),
                'description': _('Generate P&L statements and balance sheets automatically.'),
                'icon': 'fas fa-file-invoice-dollar'
            },
            {
                'title': _('Resource Planning'),
                'description': _('Optimize human and material resources with AI forecasting.'),
                'icon': 'fas fa-users-cog'
            }
        ],
        'benefits': [
            _('35% improvement in operational efficiency'),
            _('Real-time visibility across all departments'),
            _('Data-driven decision making with AI insights')
        ],
        'onboarding': {
            'title': _('Fast Implementation'),
            'steps': [
                {'title': _('Data Mapping'), 'desc': _('Connect existing ERP or legacy databases.')},
                {'title': _('Module Setup'), 'desc': _('Configure modules for your specific industry.')},
                {'title': _('Team Training'), 'desc': _('Roll out to your organization with ease.')}
            ]
        },
        'cta': {
            'text': _('Request ERP Demo'),
            'link': 'home:demo_request',
            'secondary_text': _('Explore Modules'),
            'secondary_link': 'services:index'
        },
        'seo': {
            'title': 'ERP Integration & Enterprise Software | OnWebApp',
            'description': 'Advanced ERP integration solutions for modern enterprises.'
        }
    },
    'crm-integration': {
        'title': _('CRM Integration'),
        'subtitle': _('Customer-Centric Automation'),
        'badge': 'CRM-001',
        'icon': 'fas fa-address-book',
        'color': 'primary',
        'hero_bg': 'linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%)',
        'layout': 'standard',
        'description': _('Master your customer relationships. Our CRM suite automates lead capture, tracks sales pipelines, and provides deep insights into customer behavior and sentiment.'),
        'features': [
            {
                'title': _('Lead Automation'),
                'description': _('Capture and score leads from any source automatically.'),
                'icon': 'fas fa-user-plus'
            },
            {
                'title': _('Pipeline Visualizer'),
                'description': _('Track your sales funnel in real-time with drag-and-drop ease.'),
                'icon': 'fas fa-funnel-dollar'
            },
            {
                'title': _('Customer Insights'),
                'description': _('Analyze customer sentiment and lifecycle value with AI.'),
                'icon': 'fas fa-brain'
            }
        ],
        'benefits': [
            _('Increase conversion rates by 25%'),
            _('Streamline sales team communication'),
            _('Personalize customer engagement at scale')
        ],
        'onboarding': {
            'title': _('Quick Setup'),
            'steps': [
                {'title': _('Connect Data'), 'desc': _('Sync with existing contact databases.')},
                {'title': _('Define Stages'), 'desc': _('Customize your sales pipeline stages.')},
                {'title': _('Automate'), 'desc': _('Set up automated follow-up sequences.')}
            ]
        },
        'cta': {
            'text': _('Get CRM Demo'),
            'link': 'home:demo_request',
            'secondary_text': _('View CRM Features'),
            'secondary_link': 'services:index'
        },
        'seo': {
            'title': 'CRM Integration & Sales Automation | OnWebApp',
            'description': 'Advanced CRM solutions for automated customer relationship management.'
        }
    },
    'tax-compliance': {
        'title': _('Tax Compliance'),
        'subtitle': _('Global Tax Intelligence'),
        'badge': 'WF-007-B',
        'icon': 'fas fa-calculator',
        'color': 'primary',
        'hero_bg': 'linear-gradient(135deg, #e8eaf6 0%, #c5cae9 100%)',
        'layout': 'standard',
        'description': _('Stay compliant effortlessly. Automated tax calculations and reporting for major global jurisdictions.'),
        'features': [
            {
                'title': _('Tax Compliance'),
                'description': _('Automated tax calculations for major jurisdictions.'),
                'icon': 'fas fa-calculator'
            }
        ],
        'benefits': [
            _('Shorten billing cycles'),
            _('Real-time cash flow visibility'),
            _('Audit-ready financial records')
        ],
        'onboarding': {
            'title': _('Setup Finance'),
            'steps': [
                {'title': _('Connect Bank'), 'desc': _('Secure read-only access.')},
                {'title': _('Import Ledger'), 'desc': _('Map chart of accounts.')},
                {'title': _('Automate'), 'desc': _('Set up recurring invoices.')}
            ]
        },
        'cta': {
            'text': _('Manage Finances'),
            'link': 'home:demo_request',
            'secondary_text': _('Pricing'),
            'secondary_link': 'home:use_cases'
        },
        'seo': {
            'title': 'Finance & Billing Software | OnWebApp',
            'description': 'Enterprise financial management and billing automation.'
        }
    },
    'platform-monitoring': {
        'title': _('Enterprise Platform Monitoring'),
        'subtitle': _('Real-time Visibility into Site Health, Performance, and Security'),
        'badge': 'PM-001',
        'icon': 'fas fa-desktop',
        'color': 'info',
        'hero_bg': 'linear-gradient(135deg, #e0f2f1 0%, #80cbc4 100%)',
        'layout': 'standard',
        'description': _('Empower your business with a comprehensive monitoring suite. From global uptime checks and multi-protocol monitoring to Core Web Vitals, SSL expiry alerts, and Real User Monitoring (RUM). Get deep insights into site health, performance, and security anomalies with one unified dashboard.'),
        'features': [
            {
                'title': _('Uptime & Availability'),
                'description': _('Global uptime checks, multi-protocol monitoring (HTTP/S, TCP, DNS), and maintenance windows.'),
                'icon': 'fas fa-check-circle'
            },
            {
                'title': _('Performance & Speed'),
                'description': _('Core Web Vitals tracking, waterfall analysis, and geo-latency insights for sub-second performance.'),
                'icon': 'fas fa-bolt'
            },
            {
                'title': _('Content Integrity'),
                'description': _('Keyword monitoring, broken link scans, and transaction integrity checks for critical journeys.'),
                'icon': 'fas fa-search'
            },
            {
                'title': _('Security & Certificates'),
                'description': _('SSL expiry alerts, security headers audit, and DNS/domain safeguard monitoring.'),
                'icon': 'fas fa-shield-alt'
            },
            {
                'title': _('Real User Experience (UX)'),
                'description': _('Real User Monitoring (RUM), session replays, and UX heuristics like rage clicks and long tasks.'),
                'icon': 'fas fa-users'
            },
            {
                'title': _('SEO & Analytics'),
                'description': _('On-page signals, technical SEO audits, and indexability tracking for maximum visibility.'),
                'icon': 'fas fa-chart-line'
            }
        ],
        'benefits': [
            _('Maximize website availability with global redundancy'),
            _('Detect and fix performance bottlenecks before users do'),
            _('Ensure optimal security posture and certificate validity'),
            _('Gain deep visibility into real user behavior and satisfaction')
        ],
        'onboarding': {
            'title': _('Launch Your Monitoring Hub'),
            'steps': [
                {'title': _('Add Platform'), 'desc': _('Enter your website URL and set up global probe nodes.')},
                {'title': _('Configure Alerts'), 'desc': _('Set thresholds for Slack, Email, and SMS notifications.')},
                {'title': _('Enable RBAC'), 'desc': _('Configure role-based access control and multi-account management.')}
            ]
        },
        'cta': {
            'text': _('Start Monitoring Now'),
            'link': 'services:platform_monitoring',
            'secondary_text': _('View Status Page'),
            'secondary_link': 'services:platform_monitoring'
        },
        'seo': {
            'title': 'SaaS Platform Monitoring | OnWebApp',
            'description': 'Real-time website health, performance, and security monitoring with RUM and global uptime checks.'
        }
    },
    'industrial-automation': {
        'title': _('Industrial Automation'),
        'subtitle': _('Optimize Your Production Line'),
        'badge': 'WF-008',
        'icon': 'fas fa-industry',
        'color': 'dark',
        'hero_bg': 'linear-gradient(135deg, #cfd8dc 0%, #90a4ae 100%)',
        'layout': 'tool',
        'description': _('Analyze and optimize your industrial processes with AI-driven insights. Upload your data and let our algorithms identify bottlenecks.'),
        'features': [
            {
                'title': _('Process Mining'),
                'description': _('Visualize workflows to find inefficiencies.'),
                'icon': 'fas fa-project-diagram'
            },
            {
                'title': _('Throughput Analysis'),
                'description': _('Maximize output with data-backed adjustments.'),
                'icon': 'fas fa-tachometer-alt'
            },
            {
                'title': _('Quality Control'),
                'description': _('Detect defects earlier in the production line.'),
                'icon': 'fas fa-search-plus'
            }
        ],
        'benefits': [
            _('Increase production efficiency by 20%'),
            _('Reduce waste and operational costs'),
            _('Extend equipment lifespan')
        ],
        'onboarding': {
            'title': _('Start Optimizing'),
            'steps': [
                {'title': _('Connect Data'), 'desc': _('Upload logs or connect SCADA.')},
                {'title': _('Analyze'), 'desc': _('Run our automation models.')},
                {'title': _('Implement'), 'desc': _('Apply recommended changes.')}
            ]
        },
        'cta': {
            'text': _('Run Automation Tool'),
            'link': '#tool-integration',
            'secondary_text': _('Documentation'),
            'secondary_link': 'home:api_docs'
        },
        'seo': {
            'title': 'Industrial Automation Tools | OnWebApp',
            'description': 'AI-powered industrial automation and process optimization.'
        }
    },
    'predictive-maintenance': {
        'title': _('Predictive Maintenance'),
        'subtitle': _('Zero Unplanned Downtime'),
        'badge': 'WF-009',
        'icon': 'fas fa-tools',
        'color': 'warning',
        'hero_bg': 'linear-gradient(135deg, #fff8e1 0%, #ffecb3 100%)',
        'layout': 'tool',
        'description': _('Use machine learning to predict equipment failures before they happen. Schedule maintenance only when needed.'),
        'features': [
            {
                'title': _('Vibration Analysis'),
                'description': _('Detect anomalies in rotating machinery.'),
                'icon': 'fas fa-wave-square'
            },
            {
                'title': _('Thermal Monitoring'),
                'description': _('Identify overheating components instantly.'),
                'icon': 'fas fa-thermometer-half'
            },
            {
                'title': _('Lifecycle Prediction'),
                'description': _('Estimate remaining useful life (RUL).'),
                'icon': 'fas fa-hourglass-half'
            }
        ],
        'benefits': [
            _('Eliminate catastrophic failures'),
            _('Reduce maintenance costs by 40%'),
            _('Optimize spare parts inventory')
        ],
        'onboarding': {
            'title': _('Implement Prediction'),
            'steps': [
                {'title': _('Install Sensors'), 'desc': _('Deploy IoT vibration sensors.')},
                {'title': _('Train Model'), 'desc': _('Feed historical failure data.')},
                {'title': _('Predict'), 'desc': _('Get alerts on potential failures.')}
            ]
        },
        'cta': {
            'text': _('Check Machine Status'),
            'link': '#tool-integration',
            'secondary_text': _('Learn More'),
            'secondary_link': 'home:use_cases'
        },
        'seo': {
            'title': 'Predictive Maintenance System | OnWebApp',
            'description': 'Predictive maintenance software using AI and IoT sensors.'
        }
    },
    'competitor-tracking': {
        'title': _('Competitor Tracking'),
        'subtitle': _('Stay Ahead of the Market'),
        'badge': 'WF-010',
        'icon': 'fas fa-chess',
        'color': 'danger',
        'hero_bg': 'linear-gradient(135deg, #ffcdd2 0%, #e57373 100%)',
        'layout': 'tool',
        'description': _('Gain strategic advantage by monitoring your competitors’ moves. Track their pricing, marketing, and product updates.'),
        'features': [
            {
                'title': _('Price Monitoring'),
                'description': _('Real-time alerts on competitor price changes.'),
                'icon': 'fas fa-tags'
            },
            {
                'title': _('Ad Intelligence'),
                'description': _('See where competitors are running ads.'),
                'icon': 'fas fa-ad'
            },
            {
                'title': _('Content Strategy'),
                'description': _('Analyze their top-performing content.'),
                'icon': 'fas fa-pen-fancy'
            }
        ],
        'benefits': [
            _('React faster to market changes'),
            _('Identify gaps in competitor offerings'),
            _('Win more deals with better intel')
        ],
        'onboarding': {
            'title': _('Start Tracking'),
            'steps': [
                {'title': _('Identify Rivals'), 'desc': _('Enter competitor domains.')},
                {'title': _('Select Metrics'), 'desc': _('Choose what to track.')},
                {'title': _('Get Reports'), 'desc': _('Weekly intelligence briefings.')}
            ]
        },
        'cta': {
            'text': _('Analyze Competitor'),
            'link': '#tool-integration',
            'secondary_text': _('View Sample Report'),
            'secondary_link': 'home:use_cases'
        },
        'seo': {
            'title': 'Competitor Analysis Tool | OnWebApp',
            'description': 'Track competitors and market trends with precision.'
        }
    },
    'social-media-tracking': {
        'title': _('Social Media Tracking'),
        'subtitle': _('Master Your Social Reach'),
        'badge': 'WF-011',
        'icon': 'fas fa-share-alt-square',
        'color': 'info',
        'hero_bg': 'linear-gradient(135deg, #b3e5fc 0%, #4fc3f7 100%)',
        'layout': 'tool',
        'description': _('Deep dive into your social media performance. Track growth, engagement, and audience demographics across platforms.'),
        'features': [
            {
                'title': _('Growth Tracking'),
                'description': _('Monitor follower count over time.'),
                'icon': 'fas fa-chart-line'
            },
            {
                'title': _('Engagement Metrics'),
                'description': _('Likes, shares, and comments analysis.'),
                'icon': 'fas fa-heart'
            },
            {
                'title': _('Best Time to Post'),
                'description': _('AI suggests optimal posting schedules.'),
                'icon': 'fas fa-clock'
            }
        ],
        'benefits': [
            _('Grow your audience faster'),
            _('Increase engagement rates'),
            _('Prove ROI to stakeholders')
        ],
        'onboarding': {
            'title': _('Connect Socials'),
            'steps': [
                {'title': _('Link Accounts'), 'desc': _('Connect FB, Twitter, LinkedIn.')},
                {'title': _('Set Goals'), 'desc': _('Define growth targets.')},
                {'title': _('Track'), 'desc': _('Watch your dashboard update.')}
            ]
        },
        'cta': {
            'text': _('Track Social Stats'),
            'link': '#tool-integration',
            'secondary_text': _('Compare Platforms'),
            'secondary_link': 'home:use_cases'
        },
        'seo': {
            'title': 'Social Media Tracker | OnWebApp',
            'description': 'Comprehensive social media analytics and tracking tool.'
        }
    },
    'keyword-research': {
        'title': _('Keyword Research'),
        'subtitle': _('Unlock Search Traffic'),
        'badge': 'WF-012',
        'icon': 'fas fa-key',
        'color': 'primary',
        'hero_bg': 'linear-gradient(135deg, #e1f5fe 0%, #81d4fa 100%)',
        'layout': 'tool',
        'description': _('Discover high-value keywords that your customers are searching for. Plan your content strategy with data-backed insights.'),
        'features': [
            {
                'title': _('Volume Data'),
                'description': _('Accurate monthly search volumes.'),
                'icon': 'fas fa-search'
            },
            {
                'title': _('Difficulty Score'),
                'description': _('Assess ranking potential instantly.'),
                'icon': 'fas fa-tachometer-alt'
            },
            {
                'title': _('Related Terms'),
                'description': _('Find long-tail keyword opportunities.'),
                'icon': 'fas fa-project-diagram'
            }
        ],
        'benefits': [
            _('Increase organic traffic'),
            _('Target the right audience'),
            _('Optimize ad spend efficiency')
        ],
        'onboarding': {
            'title': _('Find Keywords'),
            'steps': [
                {'title': _('Enter Topic'), 'desc': _('Start with a seed keyword.')},
                {'title': _('Filter'), 'desc': _('Select volume and difficulty.')},
                {'title': _('Export'), 'desc': _('Download your list.')}
            ]
        },
        'cta': {
            'text': _('Research Keywords'),
            'link': '#tool-integration',
            'secondary_text': _('SEO Guide'),
            'secondary_link': 'home:api_docs'
        },
        'seo': {
            'title': 'Keyword Research Tool | OnWebApp',
            'description': 'Free keyword research tool for SEO and content marketing.'
        }
    },
    'engagement-analytics': {
        'title': _('Engagement Analytics'),
        'subtitle': _('Deep User Insights'),
        'badge': 'WF-013',
        'icon': 'fas fa-users',
        'color': 'success',
        'hero_bg': 'linear-gradient(135deg, #c8e6c9 0%, #81c784 100%)',
        'layout': 'tool',
        'description': _('Understand how users interact with your content. Measure retention, click-through rates, and session depth.'),
        'features': [
            {
                'title': _('Heatmaps'),
                'description': _('Visual representation of user clicks.'),
                'icon': 'fas fa-fire-alt'
            },
            {
                'title': _('Session Recording'),
                'description': _('Replay user sessions to find friction.'),
                'icon': 'fas fa-video'
            },
            {
                'title': _('Funnel Analysis'),
                'description': _('See where users drop off.'),
                'icon': 'fas fa-filter'
            }
        ],
        'benefits': [
            _('Improve UX design'),
            _('Boost conversion rates'),
            _('Reduce bounce rates')
        ],
        'onboarding': {
            'title': _('Track Engagement'),
            'steps': [
                {'title': _('Install Pixel'), 'desc': _('Add snippet to your site.')},
                {'title': _('Define Events'), 'desc': _('Tag key actions.')},
                {'title': _('Monitor'), 'desc': _('Watch real-time behavior.')}
            ]
        },
        'cta': {
            'text': _('Analyze Engagement'),
            'link': '#tool-integration',
            'secondary_text': _('Live Demo'),
            'secondary_link': 'home:demo_request'
        },
        'seo': {
            'title': 'User Engagement Analytics | OnWebApp',
            'description': 'Track and improve user engagement on your website.'
        }
    },
    'seo-performance-dashboard': {
        'title': _('SEO Dashboard'),
        'subtitle': _('Search Performance at a Glance'),
        'badge': 'WF-014',
        'icon': 'fas fa-chart-area',
        'color': 'primary',
        'hero_bg': 'linear-gradient(135deg, #bbdefb 0%, #64b5f6 100%)',
        'layout': 'tool',
        'description': _('Comprehensive SEO reporting. Track rankings, backlinks, and technical health in one place.'),
        'features': [
            {
                'title': _('Rank Tracking'),
                'description': _('Monitor keyword positions daily.'),
                'icon': 'fas fa-list-ol'
            },
            {
                'title': _('Backlink Monitor'),
                'description': _('Track new and lost backlinks.'),
                'icon': 'fas fa-link'
            },
            {
                'title': _('Site Audit'),
                'description': _('Find technical SEO issues.'),
                'icon': 'fas fa-stethoscope'
            }
        ],
        'benefits': [
            _('Maintain high search rankings'),
            _('Recover from traffic drops'),
            _('Report value to clients')
        ],
        'onboarding': {
            'title': _('Setup Dashboard'),
            'steps': [
                {'title': _('Connect GSC'), 'desc': _('Link Google Search Console.')},
                {'title': _('Add Domain'), 'desc': _('Enter your website URL.')},
                {'title': _('Audit'), 'desc': _('Run initial health check.')}
            ]
        },
        'cta': {
            'text': _('Check SEO Performance'),
            'link': '#tool-integration',
            'secondary_text': _('Features'),
            'secondary_link': 'home:features'
        },
        'seo': {
            'title': 'SEO Performance Dashboard | OnWebApp',
            'description': 'All-in-one SEO dashboard for performance tracking.'
        }
    },
    'link-analyzer': {
        'title': _('Link Analyzer'),
        'subtitle': _('Healthy Links, Healthy Site'),
        'badge': 'WF-015',
        'icon': 'fas fa-link',
        'color': 'secondary',
        'hero_bg': 'linear-gradient(135deg, #cfd8dc 0%, #b0bec5 100%)',
        'layout': 'tool',
        'description': _('Scan your website for broken links, redirect chains, and malicious external links. Keep your link profile clean.'),
        'features': [
            {
                'title': _('Broken Link Checker'),
                'description': _('Find 404s instantly.'),
                'icon': 'fas fa-unlink'
            },
            {
                'title': _('Redirect Mapper'),
                'description': _('Visualize redirect paths.'),
                'icon': 'fas fa-random'
            },
            {
                'title': _('External Link Audit'),
                'description': _('Vet sites you link to.'),
                'icon': 'fas fa-external-link-alt'
            }
        ],
        'benefits': [
            _('Improve user experience'),
            _('Boost SEO authority'),
            _('Avoid search penalties')
        ],
        'onboarding': {
            'title': _('Scan Links'),
            'steps': [
                {'title': _('Enter URL'), 'desc': _('Home page or specific page.')},
                {'title': _('Scan'), 'desc': _('Crawler checks all links.')},
                {'title': _('Fix'), 'desc': _('Export list of errors.')}
            ]
        },
        'cta': {
            'text': _('Analyze Links'),
            'link': '#tool-integration',
            'secondary_text': _('Why it matters'),
            'secondary_link': 'home:help_center'
        },
        'seo': {
            'title': 'Broken Link Analyzer | OnWebApp',
            'description': 'Free tool to check for broken links and redirects.'
        }
    },
    'keyword-checker': {
        'title': _('Keyword Feasibility Checker'),
        'subtitle': _('Can You Rank for This?'),
        'badge': 'WF-016',
        'icon': 'fas fa-check-double',
        'color': 'primary',
        'hero_bg': 'linear-gradient(135deg, #e8eaf6 0%, #c5cae9 100%)',
        'layout': 'tool',
        'description': _('Validate if your site can realistically rank for specific keywords. Analyze competition, domain authority, and page quality.'),
        'features': [
            {
                'title': _('Feasibility Score'),
                'description': _('Instant yes/no on ranking potential.'),
                'icon': 'fas fa-traffic-light'
            },
            {
                'title': _('Gap Analysis'),
                'description': _('See what competitors have that you don\'t.'),
                'icon': 'fas fa-arrows-alt-h'
            },
            {
                'title': _('SERP Analysis'),
                'description': _('Deep dive into the top 10 results.'),
                'icon': 'fas fa-list-ol'
            }
        ],
        'benefits': [
            _('Stop wasting time on impossible keywords'),
            _('Focus resources on low-hanging fruit'),
            _('Build a realistic content roadmap')
        ],
        'onboarding': {
            'title': _('Check Feasibility'),
            'steps': [
                {'title': _('Enter Keyword'), 'desc': _('Target search term.')},
                {'title': _('Enter URL'), 'desc': _('Your landing page.')},
                {'title': _('Analyze'), 'desc': _('Get feasibility report.')}
            ]
        },
        'cta': {
            'text': _('Check Keyword'),
            'link': '#tool-integration',
            'secondary_text': _('Research Tool'),
            'secondary_link': 'services:keyword_research'
        },
        'seo': {
            'title': 'Keyword Feasibility Checker | OnWebApp',
            'description': 'Check if you can rank for specific keywords with our SEO feasibility tool.'
        }
    },
    'social-brand-tracking': {
        'title': _('Brand Tracking'),
        'subtitle': _('Monitor Your Brand Across Platforms'),
        'badge': 'WF-017',
        'icon': 'fas fa-copyright',
        'color': 'warning',
        'hero_bg': 'linear-gradient(135deg, #fff3e0 0%, #ffe0b2 100%)',
        'layout': 'tool',
        'description': _('Track specific handles and brand mentions across multiple social platforms. Analyze sentiment and referral traffic.'),
        'features': [
            {
                'title': _('Multi-Platform'),
                'description': _('Track Facebook, Twitter, Instagram, and more.'),
                'icon': 'fas fa-share-alt'
            },
            {
                'title': _('Sentiment Analysis'),
                'description': _('Visual breakdown of positive/negative mentions.'),
                'icon': 'fas fa-smile-beam'
            },
            {
                'title': _('Referral Traffic'),
                'description': _('See which platforms drive the most traffic.'),
                'icon': 'fas fa-exchange-alt'
            }
        ],
        'benefits': [
            _('Protect your brand reputation'),
            _('Measure campaign effectiveness'),
            _('Understand audience sentiment')
        ],
        'onboarding': {
            'title': _('Start Tracking'),
            'steps': [
                {'title': _('Enter Handle'), 'desc': _('Your brand username.')},
                {'title': _('Select Platforms'), 'desc': _('Choose networks to scan.')},
                {'title': _('Analyze'), 'desc': _('Get comprehensive report.')}
            ]
        },
        'cta': {
            'text': _('Track Brand'),
            'link': '#tool-integration',
            'secondary_text': _('Social Intelligence'),
            'secondary_link': 'services:social_intelligence'
        },
        'seo': {
            'title': 'Brand Tracking Tool | OnWebApp',
            'description': 'Monitor brand mentions and sentiment across social media.'
        }
    },
    'smart-factory-systems': {
        'title': _('Smart Factory'),
        'subtitle': _('Intelligent Manufacturing Ecosystem'),
        'badge': 'WF-018',
        'icon': 'fas fa-cogs',
        'color': 'dark',
        'hero_bg': 'linear-gradient(135deg, #cfd8dc 0%, #607d8b 100%)',
        'layout': 'standard',
        'description': _('Connect your entire production line to a central nervous system. Real-time data, automated decisions, and seamless integration.'),
        'features': [
            {
                'title': _('Centralized Control'),
                'description': _('Manage all machines from one dashboard.'),
                'icon': 'fas fa-desktop'
            },
            {
                'title': _('Automated Decisions'),
                'description': _('AI adjusts parameters in real-time.'),
                'icon': 'fas fa-brain'
            },
            {
                'title': _('Energy Optimization'),
                'description': _('Reduce power consumption automatically.'),
                'icon': 'fas fa-bolt'
            }
        ],
        'benefits': [
            _('Increase overall equipment effectiveness (OEE)'),
            _('Reduce energy costs by 15%'),
            _('Streamline production scheduling')
        ],
        'onboarding': {
            'title': _('Go Smart'),
            'steps': [
                {'title': _('Map Factory'), 'desc': _('Create digital twin.')},
                {'title': _('Connect Nodes'), 'desc': _('Link machines to network.')},
                {'title': _('Automate'), 'desc': _('Set rules and triggers.')}
            ]
        },
        'cta': {
            'text': _('Optimize Production'),
            'link': 'services:industrial_automation',
            'secondary_text': _('Case Studies'),
            'secondary_link': 'home:use_cases'
        },
        'seo': {
            'title': 'Smart Factory Systems | OnWebApp',
            'description': 'Integrated smart factory solutions for modern manufacturing.'
        }
    },
    'market-analysis-tools': {
        'title': _('Market Analysis'),
        'subtitle': _('Data-Driven Market Intelligence'),
        'badge': 'WF-019',
        'icon': 'fas fa-chart-pie',
        'color': 'info',
        'hero_bg': 'linear-gradient(135deg, #e0f7fa 0%, #26c6da 100%)',
        'layout': 'tool',
        'description': _('Analyze market trends, customer demographics, and industry shifts. Make strategic decisions with confidence.'),
        'features': [
            {
                'title': _('Trend Analysis'),
                'description': _('Spot emerging market trends early.'),
                'icon': 'fas fa-arrow-trend-up'
            },
            {
                'title': _('Demographic Insights'),
                'description': _('Know your audience inside out.'),
                'icon': 'fas fa-users'
            },
            {
                'title': _('Competitor Benchmarking'),
                'description': _('Compare performance against industry leaders.'),
                'icon': 'fas fa-balance-scale'
            }
        ],
        'benefits': [
            _('Identify new market opportunities'),
            _('Optimize product positioning'),
            _('Reduce risk in new ventures')
        ],
        'onboarding': {
            'title': _('Start Analyzing'),
            'steps': [
                {'title': _('Select Sector'), 'desc': _('Choose your industry.')},
                {'title': _('Define Scope'), 'desc': _('Regional or global analysis.')},
                {'title': _('Get Report'), 'desc': _('Comprehensive market breakdown.')}
            ]
        },
        'cta': {
            'text': _('Analyze Market'),
            'link': '#tool-integration',
            'secondary_text': _('Pricing'),
            'secondary_link': 'home:use_cases'
        },
        'seo': {
            'title': 'Market Analysis Tools | OnWebApp',
            'description': 'Professional market analysis and intelligence tools.'
        }
    },
    'content-creation': {
        'title': _('Content Creation'),
        'subtitle': _('Scale Your Content Production'),
        'badge': 'WF-020',
        'icon': 'fas fa-pen-nib',
        'color': 'primary',
        'hero_bg': 'linear-gradient(135deg, #f3e5f5 0%, #ce93d8 100%)',
        'layout': 'standard',
        'description': _('Generate high-quality content at scale. From blog posts to social media captions, our tools help you tell your story.'),
        'features': [
            {
                'title': _('AI Writing Assistant'),
                'description': _('Draft articles in minutes.'),
                'icon': 'fas fa-magic'
            },
            {
                'title': _('SEO Optimization'),
                'description': _('Ensure your content ranks well.'),
                'icon': 'fas fa-search'
            },
            {
                'title': _('Multi-Format'),
                'description': _('Text, images, and video scripts.'),
                'icon': 'fas fa-photo-video'
            }
        ],
        'benefits': [
            _('Triple your content output'),
            _('Maintain consistent brand voice'),
            _('Engage audiences across channels')
        ],
        'onboarding': {
            'title': _('Create Content'),
            'steps': [
                {'title': _('Choose Type'), 'desc': _('Blog, Social, Email.')},
                {'title': _('Input Brief'), 'desc': _('Topic and tone settings.')},
                {'title': _('Generate'), 'desc': _('Receive drafts instantly.')}
            ]
        },
        'cta': {
            'text': _('Start Creating'),
            'link': 'home:demo_request',
            'secondary_text': _('Examples'),
            'secondary_link': 'home:use_cases'
        },
        'seo': {
            'title': 'Content Creation Platform | OnWebApp',
            'description': 'AI-powered content creation tools for marketing teams.'
        }
    },
    'email-marketing': {
        'title': _('Email Marketing'),
        'subtitle': _('Reach Your Audience Directly'),
        'badge': 'WF-021',
        'icon': 'fas fa-envelope-open-text',
        'color': 'success',
        'hero_bg': 'linear-gradient(135deg, #e8f5e9 0%, #a5d6a7 100%)',
        'layout': 'standard',
        'description': _('Design, send, and track email campaigns that convert. Automated workflows to nurture leads into customers.'),
        'features': [
            {
                'title': _('Drag-and-Drop Editor'),
                'description': _('Beautiful emails without coding.'),
                'icon': 'fas fa-paint-brush'
            },
            {
                'title': _('Automation Flows'),
                'description': _('Welcome series, cart abandonment, etc.'),
                'icon': 'fas fa-route'
            },
            {
                'title': _('A/B Testing'),
                'description': _('Optimize subject lines and content.'),
                'icon': 'fas fa-vials'
            }
        ],
        'benefits': [
            _('Increase open rates by 20%'),
            _('Drive more revenue per subscriber'),
            _('Save time with automation')
        ],
        'onboarding': {
            'title': _('Launch Campaign'),
            'steps': [
                {'title': _('Import List'), 'desc': _('Upload contacts.')},
                {'title': _('Design'), 'desc': _('Choose template and customize.')},
                {'title': _('Send'), 'desc': _('Schedule or send immediately.')}
            ]
        },
        'cta': {
            'text': _('Start Emailing'),
            'link': 'home:demo_request',
            'secondary_text': _('Pricing'),
            'secondary_link': 'home:use_cases'
        },
        'seo': {
            'title': 'Email Marketing Software | OnWebApp',
            'description': 'Email marketing platform with automation and analytics.'
        }
    }
}
