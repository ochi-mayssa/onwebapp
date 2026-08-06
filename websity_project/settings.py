"""
Django settings for websity_project project.
"""

import os
import sys
import traceback
from pathlib import Path
from datetime import timedelta

# ============================================================================
# DEBUGGING - Added to catch errors
# ============================================================================
print("=" * 80)
print("🚀 LOADING DJANGO SETTINGS...")
print(f"Python version: {sys.version}")
print(f"Current directory: {os.getcwd()}")
print("=" * 80)

try:
    # Build paths inside the project like this: BASE_DIR / 'subdir'
    BASE_DIR = Path(__file__).resolve().parent.parent

    # WeasyPrint / GTK+ path setup for Windows
    GTK_PATH = r'C:\Program Files\GTK3-Runtime Win64\bin'
    if os.path.exists(GTK_PATH):
        os.environ['PATH'] = GTK_PATH + os.pathsep + os.environ.get('PATH', '')

    # ============================================================================
    # SECURITY WARNING: keep the secret key used in production secret!
    # ============================================================================
    SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-bhg@b&btr99*q&4cs+2lb2*0@4)jf35(z_2q-b36ah1i-!gchb')

    # ============================================================================
    # SECURITY WARNING: don't run with debug turned on in production!
    # ============================================================================
    DEBUG = os.environ.get('DEBUG', 'True').lower() in ('1', 'true', 'yes', 'on')
    print(f"DEBUG mode: {DEBUG}")

    # ============================================================================
    # ALLOWED_HOSTS
    # ============================================================================
    ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1,onwebapp.onrender.com,.onrender.com').split(',')
    ALLOWED_HOSTS = [h.strip() for h in ALLOWED_HOSTS if h.strip()]
    
    # Auto-add Render domain if running on Render
    if os.environ.get('RENDER'):
        render_hostname = os.environ.get('RENDER_EXTERNAL_HOSTNAME', 'onwebapp.onrender.com')
        if render_hostname not in ALLOWED_HOSTS:
            ALLOWED_HOSTS.append(render_hostname)
        if '.onrender.com' not in ALLOWED_HOSTS:
            ALLOWED_HOSTS.append('.onrender.com')
    
    print(f"ALLOWED_HOSTS: {ALLOWED_HOSTS}")

    # ============================================================================
    # CSRF TRUSTED ORIGINS
    # ============================================================================
    CSRF_TRUSTED_ORIGINS = os.environ.get('CSRF_TRUSTED_ORIGINS', '').split(',')
    CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in CSRF_TRUSTED_ORIGINS if origin.strip()]
    
    # Auto-add Render domain
    if os.environ.get('RENDER'):
        render_hostname = os.environ.get('RENDER_EXTERNAL_HOSTNAME', 'onwebapp.onrender.com')
        https_origin = f'https://{render_hostname}'
        if https_origin not in CSRF_TRUSTED_ORIGINS:
            CSRF_TRUSTED_ORIGINS.append(https_origin)
    
    if not CSRF_TRUSTED_ORIGINS and DEBUG:
        CSRF_TRUSTED_ORIGINS = ['http://localhost:8000', 'http://127.0.0.1:8000']
    
    print(f"CSRF_TRUSTED_ORIGINS: {CSRF_TRUSTED_ORIGINS}")

    # ============================================================================
    # APPLICATION DEFINITION - Only include apps that exist
    # ============================================================================
    INSTALLED_APPS = [
        # Django built-in
        'django.contrib.admin',
        'django.contrib.auth',
        'django.contrib.contenttypes',
        'django.contrib.sessions',
        'django.contrib.messages',
        'django.contrib.staticfiles',
        'django.contrib.sitemaps',
        'django.contrib.humanize',
        
        # Third-party apps
        'rest_framework',
        'rest_framework_simplejwt',
        'django_filters',
        'drf_spectacular',
        'channels',
        'whitenoise',
        
        # Your project apps - only uncomment those that exist
        'home',
        'users',
        'services',
        'blog',
        'contact',
        # 'chatbot',  # Comment out if missing
        'payments',
        # 'seo_analyzer',  # Comment out if missing
        'projects',
        # 'platform_app',  # Comment out if missing
        # 'platform_monitoring',  # Comment out if missing
        # 'operations',  # Comment out if missing
        # 'rpa_dashboard',  # Comment out if missing
        # 'crm',  # Comment out if missing
        # 'community',  # Comment out if missing
        # 'social_proof',  # Comment out if missing
        # 'forum',  # Comment out if missing
        # 'branding',  # Comment out if missing
    ]

    print(f"INSTALLED_APPS: {[app for app in INSTALLED_APPS if not app.startswith('django.')]}")

    # ============================================================================
    # MIDDLEWARE
    # ============================================================================
    MIDDLEWARE = [
        'django.middleware.cache.UpdateCacheMiddleware',
        'django.middleware.security.SecurityMiddleware',
        'whitenoise.middleware.WhiteNoiseMiddleware',
        'django.contrib.sessions.middleware.SessionMiddleware',
        'django.middleware.locale.LocaleMiddleware',
        'django.middleware.common.CommonMiddleware',
        'django.middleware.csrf.CsrfViewMiddleware',
        'django.contrib.auth.middleware.AuthenticationMiddleware',
        'django.contrib.messages.middleware.MessageMiddleware',
        'django.middleware.clickjacking.XFrameOptionsMiddleware',
        'django.middleware.cache.FetchFromCacheMiddleware',
    ]

    # Only add custom middleware if debug is on and modules exist
    if DEBUG:
        try:
            import branding.middleware
            MIDDLEWARE.insert(0, 'branding.middleware.QueryCountMiddleware')
            print("✅ Added QueryCountMiddleware")
        except ImportError:
            print("⚠️ branding.middleware.QueryCountMiddleware not available, skipping")

        try:
            import branding.middleware
            MIDDLEWARE.append('branding.middleware.RateLimitMiddleware')
            print("✅ Added RateLimitMiddleware")
        except ImportError:
            print("⚠️ branding.middleware.RateLimitMiddleware not available, skipping")

    # ============================================================================
    # URLS
    # ============================================================================
    ROOT_URLCONF = 'websity_project.urls'

    # ============================================================================
    # TEMPLATES
    # ============================================================================
    TEMPLATES = [
        {
            'BACKEND': 'django.template.backends.django.DjangoTemplates',
            'DIRS': [BASE_DIR / 'templates'] if (BASE_DIR / 'templates').exists() else [],
            'APP_DIRS': True,
            'OPTIONS': {
                'context_processors': [
                    'django.template.context_processors.request',
                    'django.contrib.auth.context_processors.auth',
                    'django.contrib.messages.context_processors.messages',
                ],
            },
        },
    ]

    # ============================================================================
    # WSGI / ASGI
    # ============================================================================
    WSGI_APPLICATION = 'websity_project.wsgi.application'
    ASGI_APPLICATION = 'websity_project.asgi.application'

    # ============================================================================
    # CHANNELS
    # ============================================================================
    REDIS_URL = os.environ.get('REDIS_URL') or os.environ.get('CELERY_BROKER_URL')
    
    if REDIS_URL:
        CHANNEL_LAYERS = {
            "default": {
                "BACKEND": "channels_redis.core.RedisChannelLayer",
                "CONFIG": {
                    "hosts": [REDIS_URL],
                },
            },
        }
        print("✅ Using Redis channel layer")
    else:
        CHANNEL_LAYERS = {
            "default": {
                "BACKEND": "channels.layers.InMemoryChannelLayer"
            }
        }
        print("⚠️ Using in-memory channel layer (Redis not configured)")

    # ============================================================================
    # DATABASE
    # ============================================================================
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

    # Use PostgreSQL if DATABASE_URL is set
    if os.environ.get('DATABASE_URL'):
        import dj_database_url
        DATABASES['default'] = dj_database_url.config(
            default=os.environ.get('DATABASE_URL'),
            conn_max_age=600,
            conn_health_checks=True,
        )
        print("✅ Using PostgreSQL database")
    else:
        print("⚠️ Using SQLite database (not recommended for production)")

    # ============================================================================
    # PASSWORD VALIDATION
    # ============================================================================
    AUTH_PASSWORD_VALIDATORS = [
        {
            'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
        },
        {
            'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        },
        {
            'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
        },
        {
            'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
        },
    ]

    # ============================================================================
    # INTERNATIONALIZATION
    # ============================================================================
    LANGUAGE_CODE = 'en'
    LANGUAGES = [
        ('en', 'English'),
        ('fr', 'Français'),
        ('ar', 'Arabic'),
    ]
    LOCALE_PATHS = [BASE_DIR / 'locale'] if (BASE_DIR / 'locale').exists() else []
    TIME_ZONE = 'UTC'
    USE_I18N = True
    USE_TZ = True

    # ============================================================================
    # STATIC FILES
    # ============================================================================
    STATIC_URL = '/static/'
    STATIC_ROOT = BASE_DIR / 'staticfiles'
    STATICFILES_DIRS = [BASE_DIR / 'static'] if (BASE_DIR / 'static').exists() else []

    # Create staticfiles directory if it doesn't exist
    if not STATIC_ROOT.exists():
        STATIC_ROOT.mkdir(parents=True, exist_ok=True)
        print(f"✅ Created STATIC_ROOT: {STATIC_ROOT}")
    else:
        print(f"✅ STATIC_ROOT exists: {STATIC_ROOT}")

    STORAGES = {
        'staticfiles': {
            'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
        },
    }

    # ============================================================================
    # MEDIA FILES
    # ============================================================================
    MEDIA_URL = '/media/'
    MEDIA_ROOT = BASE_DIR / 'media'
    if not MEDIA_ROOT.exists():
        MEDIA_ROOT.mkdir(parents=True, exist_ok=True)

    # ============================================================================
    # AUTHENTICATION
    # ============================================================================
    LOGIN_REDIRECT_URL = 'users:onboarding' if 'users' in INSTALLED_APPS else '/admin/'
    LOGOUT_REDIRECT_URL = '/'

    # ============================================================================
    # DEFAULT PRIMARY KEY
    # ============================================================================
    DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

    # ============================================================================
    # REST FRAMEWORK
    # ============================================================================
    REST_FRAMEWORK = {
        'DEFAULT_AUTHENTICATION_CLASSES': (
            'rest_framework_simplejwt.authentication.JWTAuthentication',
            'rest_framework.authentication.SessionAuthentication',
        ),
        'DEFAULT_PERMISSION_CLASSES': (
            'rest_framework.permissions.IsAuthenticated',
        ),
        # Commented out because branding might not exist
        # 'DEFAULT_PAGINATION_CLASS': 'branding.api.pagination.BrandPagination',
        'PAGE_SIZE': 20,
        'DEFAULT_FILTER_BACKENDS': (
            'django_filters.rest_framework.DjangoFilterBackend',
            'rest_framework.filters.SearchFilter',
            'rest_framework.filters.OrderingFilter',
        ),
        'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
        'DEFAULT_THROTTLE_CLASSES': (
            'rest_framework.throttling.AnonRateThrottle',
            'rest_framework.throttling.UserRateThrottle',
        ),
        'DEFAULT_THROTTLE_RATES': {
            'anon': '100/hour',
            'user': '1000/hour',
        },
        # Commented out because branding might not exist
        # 'EXCEPTION_HANDLER': 'branding.api.exceptions.custom_exception_handler',
    }

    # ============================================================================
    # SIMPLE JWT
    # ============================================================================
    SIMPLE_JWT = {
        'ACCESS_TOKEN_LIFETIME': timedelta(minutes=30),
        'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
        'ROTATE_REFRESH_TOKENS': True,
        'BLACKLIST_AFTER_ROTATION': False,
        'AUTH_HEADER_TYPES': ('Bearer',),
        'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
    }

    # ============================================================================
    # DRF SPECTACULAR
    # ============================================================================
    SPECTACULAR_SETTINGS = {
        'TITLE': 'Websity Branding API',
        'DESCRIPTION': 'REST API for the Websity Branding Service',
        'VERSION': '1.0.0',
        'SERVE_INCLUDE_SCHEMA': False,
        'COMPONENT_SPLIT_REQUEST': True,
    }

    # ============================================================================
    # EMAIL
    # ============================================================================
    EMAIL_HOST = os.environ.get('EMAIL_HOST', '')
    EMAIL_PORT = int(os.environ.get('EMAIL_PORT', 587))
    EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
    EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
    EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'True').lower() in ('1', 'true', 'yes')
    DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'noreply@example.com')

    if EMAIL_HOST_USER and EMAIL_HOST_PASSWORD and EMAIL_HOST:
        EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
        print("✅ Using SMTP email backend")
    else:
        EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
        print("⚠️ Using console email backend (not configured for SMTP)")

    # ============================================================================
    # STRIPE
    # ============================================================================
    STRIPE_PUBLISHABLE_KEY = os.environ.get('STRIPE_PUBLISHABLE_KEY', '')
    STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY', '')
    STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET', '')

    # ============================================================================
    # CELERY
    # ============================================================================
    USE_CELERY = os.environ.get('USE_CELERY', 'False').lower() in ('1', 'true', 'yes')
    CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
    CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', CELERY_BROKER_URL)
    
    # Only include tasks if the apps exist
    CELERY_BEAT_SCHEDULE = {}
    
    if 'social_proof' in INSTALLED_APPS:
        CELERY_BEAT_SCHEDULE['collect-social-events-every-minute'] = {
            'task': 'social_proof.tasks.collect_social_events',
            'schedule': 60.0,
        }
    
    if 'crm' in INSTALLED_APPS:
        CELERY_BEAT_SCHEDULE['update-crm-health-scores-every-hour'] = {
            'task': 'crm.tasks.update_all_customer_health_scores',
            'schedule': 3600.0,
        }
    
    if 'branding' in INSTALLED_APPS:
        CELERY_BEAT_SCHEDULE.update({
            'calculate-template-metrics-daily': {
                'task': 'branding.tasks.calculate_template_metrics',
                'schedule': 86400.0,
            },
            'scan-pending-assets-every-10-minutes': {
                'task': 'branding.tasks.scan_pending_assets',
                'schedule': 600.0,
            },
            'anonymize-expired-requests-daily': {
                'task': 'branding.tasks.anonymize_expired_requests',
                'schedule': 86400.0,
            },
            'cleanup-expired-exports-daily': {
                'task': 'branding.tasks.cleanup_expired_exports',
                'schedule': 86400.0,
            },
        })

    # ============================================================================
    # CLAMAV
    # ============================================================================
    CLAMAV_ENABLED = os.environ.get('CLAMAV_ENABLED', 'False').lower() in ('1', 'true', 'yes')
    CLAMAV_HOST = os.environ.get('CLAMAV_HOST', '127.0.0.1')
    CLAMAV_PORT = int(os.environ.get('CLAMAV_PORT', '3310'))
    CLAMAV_TIMEOUT = int(os.environ.get('CLAMAV_TIMEOUT', '10'))

    # ============================================================================
    # CACHE
    # ============================================================================
    if REDIS_URL:
        CACHES = {
            'default': {
                'BACKEND': 'django.core.cache.backends.redis.RedisCache',
                'LOCATION': REDIS_URL,
                'TIMEOUT': 300,
                'OPTIONS': {
                    'MAX_ENTRIES': 1000,
                }
            }
        }
        print("✅ Using Redis cache")
    else:
        CACHES = {
            'default': {
                'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
                'LOCATION': 'unique-snowflake',
                'TIMEOUT': 300,
                'OPTIONS': {
                    'MAX_ENTRIES': 1000,
                }
            }
        }
        print("⚠️ Using in-memory cache (Redis not configured)")

    CACHE_MIDDLEWARE_ALIAS = 'default'
    CACHE_MIDDLEWARE_SECONDS = 300
    CACHE_MIDDLEWARE_KEY_PREFIX = 'branding_site'

    # ============================================================================
    # SITE URL
    # ============================================================================
    SITE_URL = os.environ.get('SITE_URL', 'http://127.0.0.1:8000')

    # ============================================================================
    # LOGGING
    # ============================================================================
    LOGGING = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'verbose': {
                'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
                'style': '{',
            },
            'simple': {
                'format': '{levelname} {message}',
                'style': '{',
            },
        },
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'formatter': 'verbose',
            },
            'file': {
                'class': 'logging.FileHandler',
                'filename': '/tmp/django.log',
                'formatter': 'verbose',
            } if os.path.exists('/tmp') else None,
        },
        'root': {
            'handlers': ['console'],
            'level': 'DEBUG' if DEBUG else 'INFO',
        },
        'loggers': {
            'django': {
                'handlers': ['console'],
                'level': 'DEBUG' if DEBUG else 'INFO',
                'propagate': False,
            },
            'django.request': {
                'handlers': ['console'],
                'level': 'DEBUG' if DEBUG else 'ERROR',
                'propagate': False,
            },
            'django.db.backends': {
                'handlers': ['console'],
                'level': 'DEBUG' if DEBUG else 'ERROR',
                'propagate': False,
            },
        },
    }

    # Add file handler if available
    if LOGGING['handlers']['file']:
        LOGGING['root']['handlers'].append('file')

    if DEBUG:
        LOGGING['loggers'].update({
            'branding.queries': {
                'handlers': ['console'],
                'level': 'DEBUG',
                'propagate': False,
            },
            'branding.security': {
                'handlers': ['console'],
                'level': 'WARNING',
                'propagate': False,
            },
        })

    # ============================================================================
    # PRODUCTION HARDENING SETTINGS
    # ============================================================================
    # CSRF Settings
    CSRF_COOKIE_SECURE = not DEBUG
    CSRF_COOKIE_HTTPONLY = True
    CSRF_COOKIE_SAMESITE = 'Lax'

    # Session Settings
    SESSION_COOKIE_SECURE = not DEBUG
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

    # Security Headers
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_SECURITY_POLICY = {
        'default-src': ("'self'",),
        'script-src': ("'self'", 'cdn.jsdelivr.net'),
        'style-src': ("'self'", 'cdn.jsdelivr.net'),
        'img-src': ("'self'", 'data:'),
        'font-src': ("'self'", 'cdn.jsdelivr.net'),
    }

    # Force HTTPS in production
    if not DEBUG and os.environ.get('RENDER'):
        SECURE_SSL_REDIRECT = True
        SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
        SECURE_HSTS_SECONDS = 31536000
        SECURE_HSTS_INCLUDE_SUBDOMAINS = True
        SECURE_HSTS_PRELOAD = True
        print("✅ HTTPS security settings enabled")
    else:
        SECURE_SSL_REDIRECT = False
        SECURE_HSTS_SECONDS = 0
        SECURE_HSTS_INCLUDE_SUBDOMAINS = False
        SECURE_HSTS_PRELOAD = False
        print("⚠️ HTTPS security settings disabled (development mode)")

    # ============================================================================
    # SENTRY
    # ============================================================================
    SENTRY_DSN = os.environ.get('SENTRY_DSN', '')
    if SENTRY_DSN:
        try:
            import sentry_sdk
            from sentry_sdk.integrations.django import DjangoIntegration
            sentry_sdk.init(
                dsn=SENTRY_DSN,
                integrations=[DjangoIntegration()],
                traces_sample_rate=0.1,
                send_default_pii=False,
                environment=os.environ.get('ENVIRONMENT', 'production'),
            )
            print("✅ Sentry initialized")
        except ImportError:
            print("⚠️ Sentry SDK not installed, skipping")

    # ============================================================================
    # ERP Integration
    # ============================================================================
    ERP_GATEWAY_URL = os.environ.get('ERP_GATEWAY_URL', 'http://localhost:3000')
    ERP_DOMAIN = os.environ.get('ERP_DOMAIN', 'onwebapp.com')

    # ============================================================================
    # SUCCESS MESSAGE
    # ============================================================================
    print("=" * 80)
    print("✅ Django settings loaded successfully!")
    print(f"DEBUG: {DEBUG}")
    print(f"ALLOWED_HOSTS: {ALLOWED_HOSTS}")
    print(f"STATIC_ROOT: {STATIC_ROOT}")
    print(f"STATICFILES_DIRS: {STATICFILES_DIRS}")
    print(f"INSTALLED_APPS count: {len(INSTALLED_APPS)}")
    print("=" * 80)

except Exception as e:
    print("=" * 80)
    print("❌ CRITICAL ERROR IN SETTINGS:")
    print(f"Error type: {type(e).__name__}")
    print(f"Error message: {str(e)}")
    print("\nFull traceback:")
    traceback.print_exc()
    print("=" * 80)
    
    # Write to file for debugging
    try:
        with open('/tmp/settings_error.log', 'w') as f:
            f.write(f"Error: {e}\n")
            f.write(traceback.format_exc())
        print("✅ Error written to /tmp/settings_error.log")
    except:
        pass
    
    # Re-raise to stop deployment
    raise
