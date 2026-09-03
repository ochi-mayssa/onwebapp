from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('platform_monitoring', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='GA4Property',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('property_id', models.CharField(max_length=50, verbose_name='GA4 Property ID')),
                ('display_name', models.CharField(max_length=255, verbose_name='Display Name')),
                ('account_name', models.CharField(blank=True, max_length=255, verbose_name='Account Name')),
                ('access_token', models.TextField(verbose_name='Access Token')),
                ('refresh_token', models.TextField(verbose_name='Refresh Token')),
                ('token_expires_at', models.DateTimeField(verbose_name='Token Expires At')),
                ('is_active', models.BooleanField(default=True, verbose_name='Active')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created At')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated At')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ga4_properties', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'GA4 Property',
                'verbose_name_plural': 'GA4 Properties',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='GA4Report',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date_range', models.CharField(choices=[('7d', 'Last 7 Days'), ('30d', 'Last 30 Days'), ('90d', 'Last 90 Days')], default='30d', max_length=10, verbose_name='Date Range')),
                ('total_users', models.BigIntegerField(default=0, verbose_name='Total Users')),
                ('sessions', models.BigIntegerField(default=0, verbose_name='Sessions')),
                ('screen_page_views', models.BigIntegerField(default=0, verbose_name='Screen Page Views')),
                ('avg_session_duration', models.FloatField(default=0, verbose_name='Avg Session Duration (s)')),
                ('engagement_rate', models.FloatField(default=0, verbose_name='Engagement Rate (%)')),
                ('bounce_rate', models.FloatField(default=0, verbose_name='Bounce Rate (%)')),
                ('sessions_per_user', models.FloatField(default=0, verbose_name='Sessions Per User')),
                ('trends', models.JSONField(blank=True, default=list, verbose_name='Period Comparison Trends')),
                ('traffic_sources', models.JSONField(blank=True, default=list, verbose_name='Traffic Sources')),
                ('raw_data', models.JSONField(blank=True, default=dict, verbose_name='Raw API Data')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created At')),
                ('property', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reports', to='platform_monitoring.ga4property')),
            ],
            options={
                'verbose_name': 'GA4 Report',
                'verbose_name_plural': 'GA4 Reports',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='ga4property',
            index=models.Index(fields=['user', 'is_active'], name='ga4prop_user_active_idx'),
        ),
        migrations.AddIndex(
            model_name='ga4property',
            index=models.Index(fields=['property_id'], name='ga4prop_propid_idx'),
        ),
        migrations.AddIndex(
            model_name='ga4report',
            index=models.Index(fields=['property', '-created_at'], name='ga4report_prop_created_idx'),
        ),
        migrations.AddIndex(
            model_name='ga4report',
            index=models.Index(fields=['date_range'], name='ga4report_daterange_idx'),
        ),
    ]
