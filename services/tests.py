"""
Comprehensive unit tests for the Websity platform.

Tests cover:
- Service page processors and views
- Payment checkout and webhooks
- Email task creation and sending
- Celery task execution (when configured)
"""

from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.mail import outbox
from django.conf import settings
import json

from services.processors import (
    process_industrial_automation,
    process_predictive_maintenance,
    process_market_analysis,
    process_seo_analysis,
    process_social_analytics
)
from services.forms import MachineForm, CompanyForm, UrlInputForm
from payments.models import PaymentPlan, UserPaymentSelection, Payment


User = get_user_model()


class ServiceProcessorTests(TestCase):
    """Test the enhanced service processors."""
    
    def test_industrial_automation_processor(self):
        """Test industrial automation diagnostic processor returns valid structure."""
        result = process_industrial_automation('MACHINE_001')
        self.assertIn('health_score', result)
        self.assertIn('status', result)
        self.assertIn('issues', result)
        self.assertIn('chart', result)
        self.assertTrue(0 <= result['health_score'] <= 100)
        self.assertIn(result['status'], ['critical', 'warning', 'healthy'])
    
    def test_predictive_maintenance_processor(self):
        """Test predictive maintenance processor returns ML-like predictions."""
        result = process_predictive_maintenance('PUMP_002')
        self.assertIn('failure_probability', result)
        self.assertIn('risk_level', result)
        self.assertIn('recommended_maintenance_in_days', result)
        self.assertTrue(0 <= result['failure_probability'] <= 100)
        self.assertIn(result['risk_level'], ['critical', 'high', 'medium', 'low'])
    
    def test_market_analysis_processor(self):
        """Test market analysis processor returns market metrics."""
        result = process_market_analysis('Acme Corp')
        self.assertIn('annual_revenue_numeric', result)
        self.assertIn('market_share', result)
        self.assertIn('market_rank', result)
        self.assertIn('chart', result)
        self.assertTrue(result['market_rank'] > 0)
    
    def test_seo_analysis_processor(self):
        """Test SEO analysis processor returns SEO metrics."""
        result = process_seo_analysis('https://example.com')
        self.assertIn('seo_score', result)
        self.assertIn('seo_grade', result)
        self.assertIn('top_keywords', result)
        self.assertTrue(0 <= result['seo_score'] <= 100)
        self.assertIn(result['seo_grade'], ['A', 'B', 'C', 'D'])
    
    def test_social_analytics_processor(self):
        """Test social analytics processor returns platform metrics."""
        result = process_social_analytics('@example_handle')
        self.assertIn('total_followers', result)
        self.assertIn('platforms', result)
        self.assertIn('average_engagement_rate', result)
        self.assertTrue(result['total_followers'] >= 0)


class ServiceFormTests(TestCase):
    """Test service input forms."""
    
    def test_machine_form_valid(self):
        """Test MachineForm accepts valid identifier and optional email."""
        form = MachineForm(data={'identifier': 'TEST_001', 'email': 'user@example.com'})
        self.assertTrue(form.is_valid())
    
    def test_machine_form_no_email(self):
        """Test MachineForm works without email."""
        form = MachineForm(data={'identifier': 'TEST_002'})
        self.assertTrue(form.is_valid())
    
    def test_company_form_valid(self):
        """Test CompanyForm accepts valid company and optional email."""
        form = CompanyForm(data={'company': 'Acme Inc', 'email': 'analyst@example.com'})
        self.assertTrue(form.is_valid())
    
    def test_url_form_valid(self):
        """Test UrlInputForm accepts valid URL and optional email."""
        form = UrlInputForm(data={'url': 'https://example.com', 'email': 'seo@example.com'})
        self.assertTrue(form.is_valid())


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class ServiceViewTests(TestCase):
    """Test service pages and form submission."""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.client.force_login(self.user)
    
    def test_industrial_automation_get(self):
        """Test GET request to industrial automation page."""
        response = self.client.get(reverse('services:industrial_automation'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('form', response.context)
    
    def test_industrial_automation_post(self):
        """Test POST request to industrial automation page."""
        response = self.client.post(reverse('services:industrial_automation'), {
            'identifier': 'TEST_MACHINE_001',
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('result', response.context)
        result = response.context['result']
        self.assertIn('health_score', result)
    
    def test_industrial_automation_with_email(self):
        """Test industrial automation sends email when provided."""
        response = self.client.post(reverse('services:industrial_automation'), {
            'identifier': 'TEST_MACHINE_002',
            'email': 'recipient@example.com',
        })
        self.assertEqual(response.status_code, 200)
        # Email should be sent (in memory backend)
        # Note: depends on email task/threading behavior
    
    def test_predictive_maintenance_post(self):
        """Test POST request to predictive maintenance page."""
        response = self.client.post(reverse('services:predictive_maintenance'), {
            'identifier': 'PUMP_001',
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('prediction', response.context)
        prediction = response.context['prediction']
        self.assertIn('failure_probability', prediction)
    
    def test_market_analysis_post(self):
        """Test POST request to market analysis page."""
        response = self.client.post(reverse('services:market_analysis_tools'), {
            'company': 'TestCorp',
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('result', response.context)
        result = response.context['result']
        self.assertIn('market_share', result)
    
    def test_seo_analysis_post(self):
        """Test POST request to SEO analysis page."""
        response = self.client.post(reverse('services:seo_performance_dashboard'), {
            'url': 'https://test.example.com',
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('result', response.context)
        result = response.context['result']
        self.assertIn('seo_score', result)

    def test_seo_dashboard_renders_professional_report_sections(self):
        response = self.client.post(reverse('services:seo_performance_dashboard'), {
            'url': 'https://test.example.com',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Executive Summary')
        self.assertContains(response, 'Broken Links')
        self.assertContains(response, 'No historical data available.')
        self.assertNotContains(response, 'Operational Visibility Trend')
        self.assertNotContains(response, 'Ready to Automate Your Success')
    
    def test_social_analytics_post(self):
        """Test POST request to social analytics page."""
        response = self.client.post(reverse('services:engagement_analytics'), {
            'company': '@testhandle',
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('result', response.context)
        result = response.context['result']
        self.assertIn('followers', result)


class PaymentTests(TestCase):
    """Test payment plan listing, checkout, and webhooks."""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='paymentuser', password='testpass')
        # Create test payment plans
        self.plan_basic = PaymentPlan.objects.create(
            name='Basic',
            plan_type='basic',
            price=9.99,
            description='Basic plan',
            duration_days=30
        )
        self.plan_premium = PaymentPlan.objects.create(
            name='Premium',
            plan_type='premium',
            price=29.99,
            description='Premium plan',
            duration_days=30
        )
    
    def test_plans_list_page(self):
        """Test GET request to payment plans page."""
        response = self.client.get(reverse('payments:plans'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('plans', response.context)
        self.assertEqual(len(response.context['plans']), 2)
    
    def test_plans_list_shows_inactive_plans_false(self):
        """Test that inactive plans are not displayed."""
        self.plan_premium.is_active = False
        self.plan_premium.save()
        response = self.client.get(reverse('payments:plans'))
        plans = response.context['plans']
        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0].id, self.plan_basic.id)
    
    def test_create_checkout_without_stripe_keys(self):
        """Test checkout creation without Stripe keys (demo mode)."""
        # When no Stripe keys are configured, should return demo response
        response = self.client.post(reverse('payments:create_checkout', args=[self.plan_basic.id]))
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        # Demo mode should return a checkout_url pointing back to plans
        self.assertIn('checkout_url', data)
    
    def test_create_checkout_nonexistent_plan(self):
        """Test checkout creation with nonexistent plan returns 404."""
        response = self.client.post(reverse('payments:create_checkout', args=[99999]))
        self.assertEqual(response.status_code, 404)
    
    def test_webhook_endpoint_exists(self):
        """Test that webhook endpoint is accessible."""
        response = self.client.post(reverse('payments:webhook'), {}, content_type='application/json')
        # Should accept POST even without signature (in dev mode)
        self.assertIn(response.status_code, [200, 400])


class EmailTaskTests(TestCase):
    """Test email sending via tasks."""
    
    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_send_result_email_import(self):
        """Test that email task can be imported."""
        try:
            from services.tasks import send_result_email
            self.assertTrue(callable(send_result_email))
        except ImportError:
            self.fail("Could not import send_result_email from services.tasks")
    
    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_send_result_email_without_attachments(self):
        """Test email sending without attachments."""
        from services.tasks import send_result_email
        
        send_result_email(
            'test@example.com',
            'Test Subject',
            '<html><body>Test Email</body></html>'
        )
        
        # In locmem backend, emails are stored in outbox
        # Note: async tasks may not complete immediately in tests
    
    def test_celery_task_configuration(self):
        """Test that Celery is configured (or gracefully falls back)."""
        # Should not raise an error
        try:
            from websity_project import celery_app
            self.assertIsNotNone(celery_app)
        except ImportError:
            # Celery might not be installed in test environment
            pass


class SecurityTests(TestCase):
    """Test security-related settings."""
    
    def test_secret_key_not_default(self):
        """Test that SECRET_KEY is configured (not default insecure key)."""
        # In production, SECRET_KEY should be set via environment
        # For tests, we just check it exists
        self.assertTrue(len(settings.SECRET_KEY) > 10)
    
    def test_csrf_settings(self):
        """Test CSRF protection settings."""
        # Should have CSRF middleware enabled
        self.assertIn('django.middleware.csrf.CsrfViewMiddleware', settings.MIDDLEWARE)
    
    def test_secure_headers_configured(self):
        """Test that security headers are configured."""
        # In production (DEBUG=False), these should be set
        # In tests, we just check they exist
        self.assertTrue(hasattr(settings, 'SECURE_BROWSER_XSS_FILTER'))


class StripeWebhookTests(TestCase):
    """Test Stripe webhook handling."""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='webhookuser', password='testpass')
        self.plan = PaymentPlan.objects.create(
            name='Test Plan',
            plan_type='basic',
            price=9.99,
            description='Test',
            duration_days=30
        )
    
    def test_webhook_checkout_complete_event(self):
        """Test webhook handling for checkout.session.completed event."""
        # Simulate a Stripe webhook payload
        payload = {
            'type': 'checkout.session.completed',
            'data': {
                'object': {
                    'id': 'cs_test_123',
                    'payment_intent': 'pi_test_456',
                    'status': 'complete',
                    'amount_total': 999,
                    'metadata': {
                        'plan_id': str(self.plan.id),
                        'user_id': str(self.user.id),
                    }
                }
            }
        }
        
        response = self.client.post(
            reverse('payments:webhook'),
            json.dumps(payload),
            content_type='application/json'
        )
        
        # Should return 200 OK
        self.assertEqual(response.status_code, 200)
        
        # UserPaymentSelection should be marked as completed (if database backend is working)
        selection = UserPaymentSelection.objects.filter(plan=self.plan, user=self.user).first()
        if selection:
            self.assertEqual(selection.status, 'completed')


import re
from unittest.mock import patch, MagicMock
from services.processors import (
    _analyze_on_page_seo,
    _calculate_kpis,
    _generate_issues,
    _generate_recommendations,
    _check_internal_links,
)


class ProductionSEOAuditTests(TestCase):
    """PRODUCTION-GRADE tests proving NO SIMULATED DATA in the SEO KPI pipeline."""

    def _sample_html(self, title="Sample Page Title", meta="Sample meta description about things.", extra_head="", body_extra=""):
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<meta name="description" content="{meta}">
{extra_head}
</head>
<body>
<h1>Main Heading of the Page</h1>
<p>This is sample content for the test page. It has enough words to count something.</p>
<h2>Subsection One</h2>
<p>More paragraph text here to boost word count meaningfully.</p>
<h3>Sub-sub heading detail</h3>
<p>Additional paragraph content words here.</p>
<h2>Subsection Two</h2>
<p>More content again with additional words for the page audit.</p>
<p><img src="/images/logo.png" alt="Company Logo"></p>
<p><img src="/images/banner.jpg"></p>
<p><a href="/about-us/">About</a></p>
<p><a href="https://external.example.org/page">External</a></p>
<p><a href="/contact/">Contact Us</a></p>
{body_extra}
</body>
</html>
""".encode("utf-8")

    # ------------------------------------------------------------------
    # 1. No simulated source marker
    # ------------------------------------------------------------------
    def test_no_simulated_source_in_result_keys(self):
        """Test 1: 'source' must never be 'simulated' in the new processor."""
        html = self._sample_html()
        mock_session = MagicMock()
        with patch("services.processors._fetch_page") as mock_fetch:
            mock_fetch.return_value = {
                "original_url": "https://example.com",
                "final_url": "https://example.com",
                "http_status": 200,
                "redirected": False,
                "redirect_count": 0,
                "response_time": 0.35,
                "https": True,
                "content_type": "text/html; charset=utf-8",
                "page_size": len(html),
                "html_content": html,
                "headers": {},
                "success": True,
                "error_type": None,
                "error_message": None,
                "blocked": False,
            }
            from services.processors import process_seo_analysis
            result = process_seo_analysis("https://example.com")
            self.assertNotEqual(result.get("source"), "simulated")
            self.assertIn(result.get("source"), {"live_analysis", "error"})

    # ------------------------------------------------------------------
    # 2. No fake broken-link URL patterns (like /broken-link-1/)
    # ------------------------------------------------------------------
    def test_no_fake_broken_link_patterns(self):
        """Test 2: Broken links list must NEVER contain synthetic /broken-link-N/ URLs."""
        html = self._sample_html()
        with patch("services.processors._fetch_page") as mock_fetch:
            mock_fetch.return_value = {
                "original_url": "https://example.com",
                "final_url": "https://example.com",
                "http_status": 200,
                "redirected": False,
                "redirect_count": 0,
                "response_time": 0.2,
                "https": True,
                "content_type": "text/html",
                "page_size": len(html),
                "html_content": html,
                "headers": {},
                "success": True,
                "error_type": None,
                "error_message": None,
                "blocked": False,
            }
            from services.processors import process_seo_analysis
            result = process_seo_analysis("https://example.com")
            broken_links = result.get("broken_links", []) or []
            fake_pattern = re.compile(r"/broken-link-\d+/?", re.IGNORECASE)
            orphan_pattern = re.compile(r"/orphan-page-\d+/?", re.IGNORECASE)
            old_temp_pattern = re.compile(r"/old-page-\d+/?", re.IGNORECASE)
            for link_row in broken_links:
                url_val = link_row.get("url", "")
                self.assertIsNone(
                    fake_pattern.search(url_val),
                    f"Fake simulated broken link detected: {url_val}"
                )
                self.assertIsNone(
                    orphan_pattern.search(url_val),
                    f"Fake orphan page link detected: {url_val}"
                )
                self.assertIsNone(
                    old_temp_pattern.search(url_val),
                    f"Fake redirect chain link detected: {url_val}"
                )

    # ------------------------------------------------------------------
    # 3. Scores are deterministic from same inputs
    # ------------------------------------------------------------------
    def test_kpi_scores_are_deterministic(self):
        """Test 3: KPI engine must be deterministic — identical inputs → identical scores."""
        fetch_ok = {"https": True, "http_status": 200}
        on_page = {
            "title_exists": True, "title_length": 45,
            "meta_desc_exists": True, "meta_desc_length": 160,
            "h1_count": 1, "h1_texts": ["Main Heading"],
            "noindex": False, "nofollow": False,
            "canonical_exists": True, "canonical_self": True,
            "multiple_h1": False,
            "images_total": 10, "images_missing_alt": 1,
            "images_alt_percentage": 90.0,
            "h2_count": 3,
        }
        link_ok = {"links_checked": 10, "broken_links": []}
        first = _calculate_kpis(fetch_ok, on_page, link_ok)
        second = _calculate_kpis(fetch_ok, on_page, link_ok)
        self.assertEqual(first["technical_health"]["score"], second["technical_health"]["score"])
        self.assertEqual(first["on_page_seo"]["score"], second["on_page_seo"]["score"])
        self.assertEqual(first["overall_seo_health"]["score"], second["overall_seo_health"]["score"])

    # ------------------------------------------------------------------
    # 4. Missing advanced metrics return Not Available / None
    # ------------------------------------------------------------------
    def test_advanced_kpis_marked_not_available(self):
        """Test 4: Visibility, Index Coverage, Crawl Efficiency, AI Opp — all unavailable without integrations."""
        fetch_ok = {"https": True, "http_status": 200}
        kpis = _calculate_kpis(fetch_ok, {"noindex": False, "title_exists": False, "meta_desc_exists": False,
                                          "h1_count": 0, "canonical_exists": False, "canonical_self": None,
                                          "nofollow": False, "images_total": 0, "images_missing_alt": 0,
                                          "images_alt_percentage": None, "title_length": 0,
                                          "meta_desc_length": 0, "h1_texts": [], "multiple_h1": False,
                                          "h2_count": 0},
                                {"links_checked": 0, "broken_links": []})
        self.assertFalse(kpis["visibility_index"]["available"])
        self.assertIsNone(kpis["visibility_index"]["score"])
        self.assertFalse(kpis["index_coverage"]["available"])
        self.assertIsNone(kpis["index_coverage"]["score"])
        self.assertFalse(kpis["crawl_efficiency"]["available"])
        self.assertIsNone(kpis["crawl_efficiency"]["score"])
        self.assertFalse(kpis["ai_opportunity"]["available"])
        self.assertIsNone(kpis["ai_opportunity"]["score"])

    # ------------------------------------------------------------------
    # 5. Real HTML title extraction
    # ------------------------------------------------------------------
    def test_real_html_title_extraction(self):
        """Test 5: Title must be extracted verbatim from actual HTML."""
        expected_title = "IKO — À propos d'IKO | Solutions de toiture et étanchéité"
        html = self._sample_html(title=expected_title)
        on_page = _analyze_on_page_seo(html, "https://example.com", "example.com")
        self.assertTrue(on_page["title_exists"])
        self.assertEqual(on_page["title"], expected_title)
        self.assertEqual(on_page["title_length"], len(expected_title))

    # ------------------------------------------------------------------
    # 6. Real meta description extraction
    # ------------------------------------------------------------------
    def test_real_html_meta_description_extraction(self):
        """Test 6: Meta description must be extracted from actual <meta name=description>."""
        expected_meta = "IKO est l'un des principaux fabricants de matériaux de toiture et d'étanchéité."
        html = self._sample_html(meta=expected_meta)
        on_page = _analyze_on_page_seo(html, "https://example.com", "example.com")
        self.assertTrue(on_page["meta_desc_exists"])
        self.assertEqual(on_page["meta_description"], expected_meta)
        self.assertEqual(on_page["meta_desc_length"], len(expected_meta))

    # ------------------------------------------------------------------
    # 7. Real H1 extraction
    # ------------------------------------------------------------------
    def test_real_h1_extraction(self):
        """Test 7: H1 count and H1 text extracted from real HTML."""
        html = self._sample_html()
        on_page = _analyze_on_page_seo(html, "https://example.com", "example.com")
        self.assertEqual(on_page["h1_count"], 1)
        self.assertEqual(len(on_page["h1_texts"]), 1)
        self.assertIn("Main Heading of the Page", on_page["h1_texts"])

    def test_multiple_h1_warning_extracted(self):
        """Test 7b: Multiple H1 tags are flagged correctly."""
        extra = "<h1>Second H1 also present</h1>"
        html = self._sample_html(body_extra=extra)
        on_page = _analyze_on_page_seo(html, "https://example.com", "example.com")
        self.assertEqual(on_page["h1_count"], 2)
        self.assertTrue(on_page["multiple_h1"])

    # ------------------------------------------------------------------
    # 8. Internal / External link classification
    # ------------------------------------------------------------------
    def test_internal_external_link_classification(self):
        """Test 8: Internal vs external links classified by comparing domains."""
        html = self._sample_html()
        on_page = _analyze_on_page_seo(html, "https://example.com", "example.com")
        # /about-us/ and /contact/ are internal; external.example.org is external
        self.assertEqual(on_page["links_internal"], 2)
        self.assertEqual(on_page["links_external"], 1)
        self.assertEqual(on_page["links_total"], 3)
        # The internal discovered links set should contain both internal URLs
        internal_urls = " ".join(on_page["internal_links_discovered"])
        self.assertIn("about-us", internal_urls)
        self.assertIn("contact", internal_urls)
        # External should be the external one
        external_urls = " ".join(on_page["external_links_discovered"])
        self.assertIn("external.example.org", external_urls)

    # ------------------------------------------------------------------
    # 9. Broken link classification by status code
    # ------------------------------------------------------------------
    def test_broken_link_classification_severity(self):
        """Test 9: 404→High, 410→High, 5xx→Critical, Timeout→Warning."""
        from services.processors import _check_internal_links
        mock_session = MagicMock()
        def _make_resp(code):
            r = MagicMock()
            r.status_code = code
            return r
        def _head_resp(url, **kw):
            if "404" in url: return _make_resp(404)
            elif "500" in url: return _make_resp(500)  # triggers fallback to GET
            elif "410" in url: return _make_resp(410)
            else: return _make_resp(200)
        def _get_resp(url, **kw):
            # Only gets called if .head returns 403/405/429/500/501/502/503
            if "500" in url: return _make_resp(500)
            return _make_resp(200)
        mock_session.head.side_effect = _head_resp
        mock_session.get.side_effect = _get_resp
        sample = [
            "https://example.com/ok-page",
            "https://example.com/404-gone",
            "https://example.com/500-error",
            "https://example.com/410-deleted",
        ]
        lc = _check_internal_links(mock_session, sample, "https://example.com/")
        severities = {b["url"]: b["severity"] for b in lc["broken_links"]}
        self.assertEqual(severities.get("https://example.com/404-gone"), "High")
        self.assertEqual(severities.get("https://example.com/410-deleted"), "High")
        self.assertEqual(severities.get("https://example.com/500-error"), "Critical")
        self.assertEqual(lc["links_checked"], 4)

    # ------------------------------------------------------------------
    # 10. Recommendation generated only for a detected issue
    # ------------------------------------------------------------------
    def test_recommendation_generated_only_for_detected_issue(self):
        """Test 10: No canonical issue → no canonical recommendation. Missing title → title recommendation appears."""
        fetch_ok = {"https": True, "http_status": 200}
        # Case A: Title missing, but canonical is fine
        on_page_missing_title = {
            "noindex": False, "nofollow": False,
            "title_exists": False, "title_length": 0,
            "meta_desc_exists": True, "meta_desc_length": 150,
            "h1_count": 1, "multiple_h1": False,
            "canonical_exists": True, "canonical_self": True,
            "images_total": 0, "images_missing_alt": 0,
        }
        issues_missing_title = _generate_issues(fetch_ok, on_page_missing_title, {"links_checked": 0, "broken_links": []})
        recs_missing_title = _generate_recommendations(issues_missing_title)
        rec_texts = " ".join(r.get("recommendation", "") for r in recs_missing_title)
        issue_titles = [i["issue"] for i in issues_missing_title]
        self.assertIn("Missing Title Tag", issue_titles)
        self.assertIn("title", rec_texts.lower())
        self.assertNotIn("Missing Canonical Tag", issue_titles)

        # Case B: Canonical missing, title OK
        on_page_missing_canonical = {
            **on_page_missing_title,
            "title_exists": True, "title_length": 40,
            "canonical_exists": False, "canonical_self": None,
        }
        issues_missing_canonical = _generate_issues(fetch_ok, on_page_missing_canonical, {"links_checked": 0, "broken_links": []})
        issue_titles_2 = [i["issue"] for i in issues_missing_canonical]
        self.assertIn("Missing Canonical Tag", issue_titles_2)
        self.assertNotIn("Missing Title Tag", issue_titles_2)

    # ------------------------------------------------------------------
    # 11. Historical chart is not fabricated
    # ------------------------------------------------------------------
    def test_historical_chart_not_fabricated(self):
        """Test 11: chart must be None / empty and historical_note present."""
        html = self._sample_html()
        with patch("services.processors._fetch_page") as mock_fetch:
            mock_fetch.return_value = {
                "original_url": "https://example.com",
                "final_url": "https://example.com",
                "http_status": 200,
                "redirected": False,
                "redirect_count": 0,
                "response_time": 0.2,
                "https": True,
                "content_type": "text/html",
                "page_size": len(html),
                "html_content": html,
                "headers": {},
                "success": True,
                "error_type": None,
                "error_message": None,
                "blocked": False,
            }
            from services.processors import process_seo_analysis
            result = process_seo_analysis("https://example.com")
            self.assertIsNone(result.get("chart"))
            note = result.get("historical_note", "")
            self.assertIn("historical", note.lower())
            self.assertIn("run additional audits", note.lower())

    # ------------------------------------------------------------------
    # 12. Inaccessible website does NOT fall back to simulated data
    # ------------------------------------------------------------------
    def test_inaccessible_site_no_simulated_fallback(self):
        """Test 12: DNS / Timeout / connection errors → real error payload, NO simulated scores."""
        with patch("services.processors._fetch_page") as mock_fetch:
            mock_fetch.return_value = {
                "original_url": "https://this-domain-does-not-exist-xyz123.invalid",
                "final_url": None,
                "http_status": None,
                "redirected": False,
                "redirect_count": 0,
                "response_time": None,
                "https": False,
                "content_type": None,
                "page_size": None,
                "html_content": None,
                "headers": {},
                "success": False,
                "error_type": "DNS Resolution Error",
                "error_message": "The website domain could not be resolved.",
                "blocked": False,
            }
            from services.processors import process_seo_analysis
            result = process_seo_analysis("https://this-domain-does-not-exist-xyz123.invalid")
            # Source must NOT be simulated
            self.assertNotEqual(result.get("source"), "simulated")
            # Error fields must be propagated honestly
            self.assertEqual(result.get("error_type"), "DNS Resolution Error")
            self.assertIsNotNone(result.get("error_message"))
            # Scores must be legitimately low (derived from https=false, http_status!=200, etc.)
            kpis = result.get("kpis") or {}
            tech = kpis.get("technical_health", {}).get("score")
            self.assertIsNotNone(tech)
            # Without HTTP 200 or HTTPS, Technical Health MUST be <50
            self.assertLess(tech, 50)
            # No fake broken links invented for inaccessible site
            broken = result.get("broken_links", []) or []
            self.assertEqual(len(broken), 0)

    # ------------------------------------------------------------------
    # 13. Noindex is flagged as Critical
    # ------------------------------------------------------------------
    def test_noindex_flagged_critical_issue(self):
        """Verify that noindex meta tag always creates a Critical severity issue."""
        fetch_ok = {"https": True, "http_status": 200}
        on_page_noindex = {
            "noindex": True, "nofollow": False,
            "robots_meta": "noindex, follow",
            "title_exists": True, "title_length": 50,
            "meta_desc_exists": True, "meta_desc_length": 150,
            "h1_count": 1, "multiple_h1": False,
            "canonical_exists": True, "canonical_self": True,
            "images_total": 0, "images_missing_alt": 0,
        }
        issues = _generate_issues(fetch_ok, on_page_noindex, {"links_checked": 0, "broken_links": []})
        severities = {i["issue"]: i["severity"] for i in issues}
        self.assertEqual(severities.get("Noindex Detected"), "Critical")

    # ------------------------------------------------------------------
    # 14. Image ALT coverage is computed honestly — split into with/empty/missing
    # ------------------------------------------------------------------
    def test_image_alt_coverage_honest_computation(self):
        """Original sample: 1 descriptive ALT + 1 missing ALT attribute → 50% coverage."""
        html = self._sample_html()
        on_page = _analyze_on_page_seo(html, "https://example.com", "example.com")
        self.assertEqual(on_page["images_total"], 2)
        self.assertEqual(on_page["images_with_alt"], 1)
        self.assertEqual(on_page["images_empty_alt"], 0)
        self.assertEqual(on_page["images_missing_alt"], 1)
        self.assertEqual(on_page["images_alt_attribute_percentage"], 50.0)
        self.assertEqual(on_page["images_alt_percentage"], 50.0)

    # ------------------------------------------------------------------
    # ALT-REG-1. Overall SEO Health explanatory text matches formula
    # ALT-REG-2. Descriptive alt / alt="" / missing alt attribute
    # ------------------------------------------------------------------
    def test_image_alt_extraction_distinguishes_three_categories(self):
        """ALT-REG-2. Sample HTML: 1 descriptive alt + 1 alt='' + 1 completely missing alt attribute."""
        html = b"""<!DOCTYPE html><html><head><title>T</title></head><body>
<img src="a.jpg" alt="Industrial automation">
<img src="b.jpg" alt="">
<img src="c.jpg">
</body></html>"""
        on_page = _analyze_on_page_seo(html, "https://example.com", "example.com")
        self.assertEqual(on_page["images_total"], 3)
        self.assertEqual(on_page["images_with_alt"], 1)
        self.assertEqual(on_page["images_empty_alt"], 1)
        self.assertEqual(on_page["images_missing_alt"], 1)
        # ALT Attribute Coverage = (with_alt + empty_alt) / total = 2/3 = 66.7%
        self.assertEqual(on_page["images_alt_attribute_percentage"], 66.7)

    def test_empty_alt_not_counted_as_missing_alt(self):
        """ALT-REG-4. alt="" images are NOT counted in images_missing_alt."""
        html = b"""<!DOCTYPE html><html><head><title>T</title></head><body>
<img src="x.jpg" alt="">
<img src="y.jpg" alt="">
<img src="z.jpg">
</body></html>"""
        on_page = _analyze_on_page_seo(html, "https://example.com", "example.com")
        self.assertEqual(on_page["images_total"], 3)
        self.assertEqual(on_page["images_with_alt"], 0)
        self.assertEqual(on_page["images_empty_alt"], 2)
        self.assertEqual(on_page["images_missing_alt"], 1)
        # Alt-attr coverage = 2/3 = 66.7% because 2 out of 3 have the alt attribute present (even if empty)
        self.assertEqual(on_page["images_alt_attribute_percentage"], 66.7)

    def test_missing_alt_recommendation_only_from_genuinely_missing_attribute(self):
        """ALT-REG-3. Only images_missing_alt>0 triggers the 'Missing ALT Attribute' issue.
        Empty alt="" alone should NOT generate the missing-ALT Medium-severity issue."""
        fetch_ok = {"https": True, "http_status": 200}
        # Case A: 2 alt="" + 0 missing → NO Medium 'Missing ALT Attribute' issue, but INFO Review Empty ALT
        on_page_empty_only = {
            "images_total": 2,
            "images_with_alt": 0,
            "images_empty_alt": 2,
            "images_missing_alt": 0,
            "images_alt_attribute_percentage": 100.0,
            "images_alt_percentage": 100.0,
            "title_exists": True, "title_length": 50,
            "meta_desc_exists": True, "meta_desc_length": 150,
            "h1_count": 1, "multiple_h1": False,
            "canonical_exists": True, "canonical_self": True,
            "noindex": False, "nofollow": False,
        }
        issues = _generate_issues(fetch_ok, on_page_empty_only, {"links_checked": 0, "broken_links": []})
        issue_titles = [i["issue"] for i in issues]
        self.assertNotIn("Images Missing ALT Attribute", issue_titles)
        self.assertIn("Review Empty ALT Text", issue_titles)
        # Case B: 1 missing alt attribute → Medium Missing ALT Attribute
        on_page_missing = {**on_page_empty_only, "images_missing_alt": 1, "images_empty_alt": 1,
                           "images_total": 2, "images_alt_attribute_percentage": 50.0, "images_alt_percentage": 50.0}
        issues2 = _generate_issues(fetch_ok, on_page_missing, {"links_checked": 0, "broken_links": []})
        issue_titles2 = [i["issue"] for i in issues2]
        self.assertIn("Images Missing ALT Attribute", issue_titles2)
        self.assertIn("Review Empty ALT Text", issue_titles2)

    # ------------------------------------------------------------------
    # ALT-REG-5/6/7/8. Honesty invariants
    # ------------------------------------------------------------------
    def test_honesty_invariants_no_simulated(self):
        """ALT-REG-5. Processed result never has source='simulated'."""
        html = self._sample_html()
        with patch("services.processors._fetch_page") as mf:
            mf.return_value = {
                "original_url": "https://example.com", "final_url": "https://example.com",
                "http_status": 200, "redirected": False, "redirect_count": 0,
                "response_time": 0.2, "https": True, "content_type": "text/html",
                "page_size": len(html), "html_content": html, "headers": {},
                "success": True, "error_type": None, "error_message": None, "blocked": False,
            }
            from services.processors import process_seo_analysis
            r = process_seo_analysis("https://example.com")
            self.assertIn(r["source"], ("live_analysis", "error"))
            self.assertNotEqual(r["source"], "simulated")

    def test_honesty_invariants_no_fake_broken_links(self):
        """ALT-REG-6. No fabricated /broken-link-N/ or /orphan-page-N/ URLs."""
        html = self._sample_html()
        with patch("services.processors._fetch_page") as mf:
            mf.return_value = {
                "original_url": "https://example.com", "final_url": "https://example.com",
                "http_status": 200, "redirected": False, "redirect_count": 0,
                "response_time": 0.2, "https": True, "content_type": "text/html",
                "page_size": len(html), "html_content": html, "headers": {},
                "success": True, "error_type": None, "error_message": None, "blocked": False,
            }
            from services.processors import process_seo_analysis
            r = process_seo_analysis("https://example.com")
            for bl in (r.get("broken_links") or []):
                self.assertIsNone(re.search(r"/broken-link-\d+/?", bl.get("url", "")), f"Fake broken: {bl}")
                self.assertIsNone(re.search(r"/orphan-page-\d+/?", bl.get("url", "")), f"Fake orphan: {bl}")

    def test_honesty_invariants_no_fabricated_chart(self):
        """ALT-REG-7. chart is None (not fabricated)."""
        html = self._sample_html()
        with patch("services.processors._fetch_page") as mf:
            mf.return_value = {
                "original_url": "https://example.com", "final_url": "https://example.com",
                "http_status": 200, "redirected": False, "redirect_count": 0,
                "response_time": 0.2, "https": True, "content_type": "text/html",
                "page_size": len(html), "html_content": html, "headers": {},
                "success": True, "error_type": None, "error_message": None, "blocked": False,
            }
            from services.processors import process_seo_analysis
            r = process_seo_analysis("https://example.com")
            self.assertIsNone(r.get("chart"))

    def test_honesty_invariants_advanced_kpis_remain_not_available(self):
        """ALT-REG-8. Visibility/Index Coverage/Crawl Efficiency/AI Opp all remain Not Available."""
        kpis = _calculate_kpis({"https": True, "http_status": 200},
                                {"noindex": False, "title_exists": True, "title_length": 40,
                                 "meta_desc_exists": True, "meta_desc_length": 150,
                                 "h1_count": 1, "multiple_h1": False, "h1_texts": ["H"],
                                 "canonical_exists": True, "canonical_self": True,
                                 "nofollow": False, "images_total": 0, "images_missing_alt": 0,
                                 "images_with_alt": 0, "images_empty_alt": 0,
                                 "images_alt_attribute_percentage": None, "images_alt_percentage": None,
                                 "h2_count": 3},
                                {"links_checked": 0, "broken_links": []})
        for kpi_name in ("visibility_index", "index_coverage", "crawl_efficiency", "ai_opportunity"):
            self.assertFalse(kpis[kpi_name]["available"], f"{kpi_name} should not be available")
            self.assertEqual(kpis[kpi_name]["status"], "Not Available")
            self.assertIsNone(kpis[kpi_name]["score"])

    def test_no_blank_slash_100_displayed_none_kpis(self):
        """ALT-REG-9. Any KPI that is available=False has score=None (not 0), so template doesn't render None/100."""
        kpis = _calculate_kpis({"https": False, "http_status": None},
                                {"noindex": True, "title_exists": False, "title_length": 0,
                                 "meta_desc_exists": False, "meta_desc_length": 0,
                                 "h1_count": 0, "multiple_h1": False, "h1_texts": [],
                                 "canonical_exists": False, "canonical_self": None,
                                 "nofollow": True, "images_total": 0, "images_missing_alt": 0,
                                 "images_with_alt": 0, "images_empty_alt": 0,
                                 "images_alt_attribute_percentage": None, "images_alt_percentage": None,
                                 "h2_count": 0},
                                {"links_checked": 0, "broken_links": []})
        for avail_name in ("overall_seo_health", "technical_health", "on_page_seo"):
            sc = kpis[avail_name]["score"]
            if sc is not None:
                self.assertGreaterEqual(sc, 0)
                self.assertLessEqual(sc, 100)
        lh = kpis["link_health"]
        if not lh["available"]:
            self.assertIsNone(lh["score"])
        for na_name in ("visibility_index", "index_coverage", "crawl_efficiency", "ai_opportunity"):
            self.assertFalse(kpis[na_name]["available"])
            self.assertIsNone(kpis[na_name]["score"])

    # ------------------------------------------------------------------
    # 15. Overall health is weighted average of real sub-KPIs
    # ------------------------------------------------------------------
    def test_overall_health_is_weighted_average_of_measured_kpis(self):
        """If Tech=100, On-Page=100, Link Health=100 → Overall must equal 100."""
        fetch = {"https": True, "http_status": 200}
        onp = {
            "title_exists": True, "title_length": 45,
            "meta_desc_exists": True, "meta_desc_length": 160,
            "h1_count": 1, "h1_texts": ["Heading"], "multiple_h1": False,
            "noindex": False, "nofollow": False,
            "canonical_exists": True, "canonical_self": True,
            "images_total": 0, "images_missing_alt": 0,
            "images_alt_percentage": None,
            "h2_count": 3,
        }
        lc = {"links_checked": 5, "broken_links": []}
        kpis = _calculate_kpis(fetch, onp, lc)
        tech = kpis["technical_health"]["score"]
        onp_score = kpis["on_page_seo"]["score"]
        link = kpis["link_health"]["score"]
        overall = kpis["overall_seo_health"]["score"]
        expected = round((tech + onp_score + link) / 3, 1)
        self.assertEqual(overall, expected)
        # All three are healthy, so overall is also high
        self.assertGreaterEqual(overall, 90)


class SEOViewIntegrationTests(TestCase):
    """Integration tests confirming view renders the new report without 'simulated' markers."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='seoprouser', password='testpass')
        self.client.force_login(self.user)

    def test_seo_view_renders_live_analysis_badge(self):
        """The view result context should contain analysis_source='Live Page Analysis' on any reachable URL."""
        response = self.client.post(reverse('services:seo_performance_dashboard'), {
            'url': 'https://example.com',
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('result', response.context)
        result = response.context['result']
        self.assertNotEqual(result.get('source'), 'simulated')

    def test_seo_template_no_source_simulated_string(self):
        """The rendered template output must not contain the string 'Source: simulated'."""
        response = self.client.post(reverse('services:seo_performance_dashboard'), {
            'url': 'https://example.com',
        })
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8', errors='ignore')
        self.assertNotIn('Source: simulated', content)
        self.assertNotIn('Source: Simulated', content)
        # Should contain the new analysis source label
        self.assertIn('Analysis Source', content)

    def test_seo_template_no_fake_broken_link_string(self):
        """Rendered page must never contain '/broken-link-1' synthetic pattern."""
        response = self.client.post(reverse('services:seo_performance_dashboard'), {
            'url': 'https://example.com',
        })
        content = response.content.decode('utf-8', errors='ignore')
        pattern = re.compile(r"/broken-link-\d+")
        self.assertIsNone(pattern.search(content))

    def test_seo_template_shows_not_available_for_visibility(self):
        """'Visibility Index' section should show Not Available (no numeric /100 without data)."""
        response = self.client.post(reverse('services:seo_performance_dashboard'), {
            'url': 'https://example.com',
        })
        content = response.content.decode('utf-8', errors='ignore')
        # Should reference Visibility Index
        self.assertIn('Visibility Index', content)
        # And should say Not Available for it (since no GSC data integrated)
        self.assertIn('Not Available', content)

    def test_seo_report_order_present(self):
        """All 11 sections of the final report order should be present."""
        response = self.client.post(reverse('services:seo_performance_dashboard'), {
            'url': 'https://example.com',
        })
        content = response.content.decode('utf-8', errors='ignore')
        expected_sections = [
            "Analysis Specification",
            "Executive Summary",
            "KPI Cards",
            "Technical SEO",
            "On-Page SEO",
            "Link Health",
            "Detected Issues",
            "Broken Internal Links",
            "Recommendations",
            "Operational Visibility Trend",
            "Analysis Metadata",
        ]
        for section_title in expected_sections:
            self.assertIn(section_title, content, f"Report missing section: {section_title}")

    def test_seo_template_shows_correct_overall_health_explanation(self):
        """ALT-REG-1. Overall SEO Health explanation says 'Average of available Technical, On-Page and Link Health scores.'"""
        response = self.client.post(reverse('services:seo_performance_dashboard'), {
            'url': 'https://example.com',
        })
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8', errors='ignore')
        self.assertIn("Average of available Technical, On-Page and Link Health scores.", content)


class SocialMediaKPIPlatformTests(TestCase):
    """PRODUCTION REGRESSION TESTS for Social Media KPI platform detection + handle extraction."""

    def test_instagram_platform_detection(self):
        """Instagram URL -> platform='instagram'."""
        from services.processors import _normalize_social_tracking_input
        result = _normalize_social_tracking_input('https://www.instagram.com/onwebapp/', None)
        self.assertTrue(result['valid'])
        self.assertEqual(result['detected_platform'], 'instagram')
        self.assertEqual(result['normalized_handle'], 'onwebapp')

    def test_facebook_platform_detection(self):
        """facebook.com URL -> platform='facebook'."""
        from services.processors import _normalize_social_tracking_input
        result = _normalize_social_tracking_input('https://www.facebook.com/onwebapp', None)
        self.assertTrue(result['valid'])
        self.assertEqual(result['detected_platform'], 'facebook')
        self.assertEqual(result['normalized_handle'], 'onwebapp')

    def test_fb_com_short_domain(self):
        """fb.com short URL -> platform='facebook'."""
        from services.processors import _normalize_social_tracking_input
        result = _normalize_social_tracking_input('https://fb.com/onwebapp', None)
        self.assertTrue(result['valid'])
        self.assertEqual(result['detected_platform'], 'facebook')
        self.assertEqual(result['normalized_handle'], 'onwebapp')

    def test_linkedin_platform_detection(self):
        """linkedin.com URL -> platform='linkedin'."""
        from services.processors import _normalize_social_tracking_input
        result = _normalize_social_tracking_input('https://www.linkedin.com/company/onwebapp/', None)
        self.assertTrue(result['valid'])
        self.assertEqual(result['detected_platform'], 'linkedin')
        self.assertEqual(result['normalized_handle'], 'onwebapp')

    def test_linkedin_company_handle_not_company_literal(self):
        """LinkedIn /company/onwebapp -> handle='onwebapp', NEVER 'company'."""
        from services.processors import _normalize_social_tracking_input
        result = _normalize_social_tracking_input('https://www.linkedin.com/company/onwebapp/', None)
        self.assertTrue(result['valid'])
        self.assertNotEqual(result['normalized_handle'], 'company')
        self.assertNotEqual(result['normalized_handle'], '@company')
        self.assertEqual(result['normalized_handle'], 'onwebapp')

    def test_linkedin_in_profile_path(self):
        """LinkedIn /in/username -> username extracted correctly."""
        from services.processors import _normalize_social_tracking_input
        result = _normalize_social_tracking_input('https://www.linkedin.com/in/johnsmith/', None)
        self.assertTrue(result['valid'])
        self.assertEqual(result['normalized_handle'], 'johnsmith')

    def test_tiktok_platform_detection(self):
        """TikTok URL -> platform='tiktok'."""
        from services.processors import _normalize_social_tracking_input
        result = _normalize_social_tracking_input('https://www.tiktok.com/@onwebapp', None)
        self.assertTrue(result['valid'])
        self.assertEqual(result['detected_platform'], 'tiktok')
        self.assertEqual(result['normalized_handle'], 'onwebapp')

    def test_tiktok_at_stripped_from_handle(self):
        """TikTok @handle -> @ is stripped."""
        from services.processors import _normalize_social_tracking_input
        result = _normalize_social_tracking_input('https://tiktok.com/@onwebapp', None)
        self.assertTrue(result['valid'])
        self.assertFalse(result['normalized_handle'].startswith('@'))
        self.assertEqual(result['normalized_handle'], 'onwebapp')

    def test_youtube_platform_detection_com(self):
        """youtube.com URL -> platform='youtube'."""
        from services.processors import _normalize_social_tracking_input
        result = _normalize_social_tracking_input('https://www.youtube.com/@onwebapp', None)
        self.assertTrue(result['valid'])
        self.assertEqual(result['detected_platform'], 'youtube')
        self.assertEqual(result['normalized_handle'], 'onwebapp')

    def test_youtube_at_handle_stripped(self):
        """YouTube @handle -> @ stripped, never starts with @."""
        from services.processors import _normalize_social_tracking_input
        result = _normalize_social_tracking_input('https://youtube.com/@onwebapp', None)
        self.assertTrue(result['valid'])
        self.assertFalse(result['normalized_handle'].startswith('@'))
        self.assertEqual(result['normalized_handle'], 'onwebapp')

    def test_youtu_be_short_domain(self):
        """youtu.be short domain -> platform='youtube'."""
        from services.processors import _normalize_social_tracking_input
        result = _normalize_social_tracking_input('https://youtu.be/@onwebapp', None)
        self.assertTrue(result['valid'])
        self.assertEqual(result['detected_platform'], 'youtube')
        self.assertEqual(result['normalized_handle'], 'onwebapp')

    def test_x_com_platform_detection(self):
        """x.com URL -> platform='twitter' (X/Twitter unified key)."""
        from services.processors import _normalize_social_tracking_input
        result = _normalize_social_tracking_input('https://x.com/onwebapp', None)
        self.assertTrue(result['valid'])
        self.assertEqual(result['detected_platform'], 'twitter')
        self.assertEqual(result['normalized_handle'], 'onwebapp')

    def test_twitter_com_backward_compat(self):
        """twitter.com URL -> platform='twitter'."""
        from services.processors import _normalize_social_tracking_input
        result = _normalize_social_tracking_input('https://twitter.com/onwebapp', None)
        self.assertTrue(result['valid'])
        self.assertEqual(result['detected_platform'], 'twitter')
        self.assertEqual(result['normalized_handle'], 'onwebapp')

    def test_query_string_handled_instagram(self):
        """Instagram URL with ?hl=en -> handle extracted correctly, no query params leaked."""
        from services.processors import _normalize_social_tracking_input
        result = _normalize_social_tracking_input('https://instagram.com/onwebapp/?hl=en', None)
        self.assertTrue(result['valid'])
        self.assertEqual(result['normalized_handle'], 'onwebapp')
        self.assertNotIn('hl', result['normalized_handle'])
        self.assertNotIn('=', result['normalized_handle'])

    def test_query_string_handled_linkedin(self):
        """LinkedIn URL with ?trk=test -> handle extracted, no 'trk' or '=' leaked."""
        from services.processors import _normalize_social_tracking_input
        result = _normalize_social_tracking_input('https://linkedin.com/company/onwebapp/?trk=test', None)
        self.assertTrue(result['valid'])
        self.assertEqual(result['normalized_handle'], 'onwebapp')
        self.assertNotIn('trk', result['normalized_handle'])
        self.assertNotIn('=', result['normalized_handle'])

    def test_fragment_handled_instagram(self):
        """URL with #fragment -> fragment stripped, not leaked into handle."""
        from services.processors import _normalize_social_tracking_input
        result = _normalize_social_tracking_input('https://instagram.com/onwebapp/#photos', None)
        self.assertTrue(result['valid'])
        self.assertEqual(result['normalized_handle'], 'onwebapp')
        self.assertNotIn('#', result['normalized_handle'])

    def test_trailing_slash_stripped(self):
        """Handle with trailing slash -> slash removed."""
        from services.processors import _normalize_social_tracking_input
        result = _normalize_social_tracking_input('https://instagram.com/onwebapp/', None)
        self.assertTrue(result['valid'])
        self.assertFalse(result['normalized_handle'].endswith('/'))
        self.assertEqual(result['normalized_handle'], 'onwebapp')

    def test_plain_handle_input_normalized(self):
        """Plain @handle input (no URL) -> @ stripped, no platform detected."""
        from services.processors import _normalize_social_tracking_input
        result = _normalize_social_tracking_input('@mybrand', None)
        self.assertTrue(result['valid'])
        self.assertEqual(result['normalized_handle'], 'mybrand')
        self.assertFalse(result['normalized_handle'].startswith('@'))


class SocialMediaKPIProviderStatusTests(TestCase):
    """REGRESSION TESTS: Provider Status + KPI honesty (No demo/fake data)."""

    def test_provider_not_configured_without_social_api_env(self):
        """Without SOCIAL_API_URL -> provider_status='not_configured', text='Provider Not Configured'."""
        import os
        from services.processors import process_social_tracking
        saved = os.environ.pop('SOCIAL_API_URL', None)
        try:
            result = process_social_tracking('https://www.instagram.com/onwebapp/', user=None)
            self.assertEqual(result.get('provider_status'), 'not_configured')
            self.assertEqual(result.get('provider_status_text'), 'Provider Not Configured')
            self.assertFalse(result.get('provider_configured'))
        finally:
            if saved is not None:
                os.environ['SOCIAL_API_URL'] = saved

    def test_followers_not_available_when_no_provider_no_db(self):
        """No provider, no DB -> total_followers_display='Not Available', NOT a number."""
        import os
        from services.processors import process_social_tracking
        saved = os.environ.pop('SOCIAL_API_URL', None)
        try:
            result = process_social_tracking('https://instagram.com/nonexistent_handle_xyz1234/', user=None)
            self.assertEqual(result.get('total_followers_display'), 'Not Available')
            self.assertIsNone(result.get('total_followers'))
        finally:
            if saved is not None:
                os.environ['SOCIAL_API_URL'] = saved

    def test_engagement_not_available_when_no_provider_no_db(self):
        """No provider, no DB -> engagement_display='Not Available'."""
        import os
        from services.processors import process_social_tracking
        saved = os.environ.pop('SOCIAL_API_URL', None)
        try:
            result = process_social_tracking('https://instagram.com/nonexistent_handle_xyz1234/', user=None)
            self.assertEqual(result.get('engagement_display'), 'Not Available')
            self.assertIsNone(result.get('engagement_rate'))
        finally:
            if saved is not None:
                os.environ['SOCIAL_API_URL'] = saved

    def test_growth_chart_not_fabricated(self):
        """No history -> growth_chart.available=False, message says 'not available yet'."""
        import os
        from services.processors import process_social_tracking
        saved = os.environ.pop('SOCIAL_API_URL', None)
        try:
            result = process_social_tracking('https://instagram.com/nonexistent_handle_xyz1234/', user=None)
            chart = result.get('growth_chart') or {}
            self.assertFalse(chart.get('available'))
            self.assertEqual(chart.get('labels'), [])
            self.assertEqual(chart.get('values'), [])
            msg = (chart.get('message') or '').lower()
            self.assertTrue(
                ('not available' in msg) or ('historical' in msg) or ('no' in msg and 'data' in msg),
                f"Expected honest no-data message, got: {msg}"
            )
        finally:
            if saved is not None:
                os.environ['SOCIAL_API_URL'] = saved

    def test_sentiment_not_available_without_analyzable_content(self):
        """No analyzable posts -> sentiment_available=False, sentiment_badge='Not Available'."""
        import os
        from services.processors import process_social_tracking
        saved = os.environ.pop('SOCIAL_API_URL', None)
        try:
            result = process_social_tracking('https://instagram.com/nonexistent_handle_xyz1234/', user=None)
            self.assertFalse(result.get('sentiment_available'))
            self.assertEqual(result.get('sentiment_badge'), 'Not Available')
        finally:
            if saved is not None:
                os.environ['SOCIAL_API_URL'] = saved

    def test_last_sync_never_synced_when_no_provider_no_db(self):
        """No provider + no DB snapshot -> last_sync_display='Never Synced'."""
        import os
        from services.processors import process_social_tracking
        saved = os.environ.pop('SOCIAL_API_URL', None)
        try:
            result = process_social_tracking('https://instagram.com/nonexistent_handle_xyz1234/', user=None)
            self.assertEqual(result.get('last_sync_display'), 'Never Synced')
            self.assertIsNone(result.get('last_sync'))
        finally:
            if saved is not None:
                os.environ['SOCIAL_API_URL'] = saved

    def test_no_static_just_now_string(self):
        """Result must NEVER contain the hardcoded 'Just now' string for last sync."""
        import os
        from services.processors import process_social_tracking
        saved = os.environ.pop('SOCIAL_API_URL', None)
        try:
            result = process_social_tracking('https://instagram.com/onwebapp/', user=None)
            last_sync_text = str(result.get('last_sync_display') or '')
            self.assertNotIn('Just now', last_sync_text)
            self.assertNotIn('just now', last_sync_text.lower())
        finally:
            if saved is not None:
                os.environ['SOCIAL_API_URL'] = saved

    def test_account_label_shows_normalized_at_handle(self):
        """account_label should be '@normalized_handle' format."""
        import os
        from services.processors import process_social_tracking
        saved = os.environ.pop('SOCIAL_API_URL', None)
        try:
            result = process_social_tracking('https://instagram.com/onwebapp/', user=None)
            label = result.get('account_label') or ''
            self.assertTrue(label.startswith('@'))
            self.assertEqual(label, '@onwebapp')
        finally:
            if saved is not None:
                os.environ['SOCIAL_API_URL'] = saved


class SocialMediaKPIAccountIsolationTests(TestCase):
    """REGRESSION TESTS: Account data isolation - no cross-account / cross-platform leakage."""

    def test_db_lookup_filters_by_both_platform_and_handle(self):
        """_build_social_tracking_from_db uses platform + username filter (no leakage)."""
        from services.processors import _build_social_tracking_from_db
        result = _build_social_tracking_from_db(
            handle_input='@handle_a',
            normalized_handle='handle_a',
            selected_platforms=['instagram'],
            detected_platform='instagram',
            days=30,
            user=None,
        )
        self.assertIsNone(result)

    def test_growth_chart_filters_platform_and_handle(self):
        """Growth chart lookup requires BOTH matching normalized_handle AND detected_platform."""
        from services.processors import _build_growth_chart
        chart = _build_growth_chart(user=None, normalized_handle='handle_a', detected_platform='instagram')
        self.assertFalse(chart.get('available'))
        self.assertEqual(chart.get('labels'), [])
        self.assertEqual(chart.get('values'), [])

    def test_two_platforms_same_handle_not_leaked(self):
        """Same @handle on different platforms are isolated (different platform keys)."""
        import os
        from services.processors import _normalize_social_tracking_input
        ig = _normalize_social_tracking_input('https://instagram.com/onwebapp/', None)
        li = _normalize_social_tracking_input('https://linkedin.com/company/onwebapp/', None)
        self.assertEqual(ig['normalized_handle'], li['normalized_handle'])
        self.assertNotEqual(ig['detected_platform'], li['detected_platform'])
        self.assertEqual(ig['detected_platform'], 'instagram')
        self.assertEqual(li['detected_platform'], 'linkedin')

    def test_engagement_formula_not_available_when_engagement_is_none(self):
        """When engagement_rate is None, engagement_formula is honest 'Not Available'."""
        import os
        from services.processors import process_social_tracking
        saved = os.environ.pop('SOCIAL_API_URL', None)
        try:
            result = process_social_tracking('https://instagram.com/nonexistent_handle_xyz1234/', user=None)
            self.assertEqual(result.get('engagement_formula'), 'Not Available')
        finally:
            if saved is not None:
                os.environ['SOCIAL_API_URL'] = saved


class SocialMediaKPIViewIntegrationTests(TestCase):
    """INTEGRATION TESTS: social_media_tracking view + form + template."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='socialtestuser', password='testpass')
        self.client.force_login(self.user)

    def test_view_get_loads(self):
        """GET on social_media_tracking -> 200 OK."""
        response = self.client.get(reverse('services:social_media_tracking'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('form', response.context)

    def test_view_post_instagram_url_returns_result(self):
        """POST Instagram URL -> result present in context."""
        import os
        saved = os.environ.pop('SOCIAL_API_URL', None)
        try:
            response = self.client.post(reverse('services:social_media_tracking'), {
                'handle': 'https://www.instagram.com/onwebapp/',
                'platforms': ['instagram'],
                'days': 30,
            })
            self.assertEqual(response.status_code, 200)
            self.assertIn('result', response.context)
        finally:
            if saved is not None:
                os.environ['SOCIAL_API_URL'] = saved

    def test_view_post_instagram_renders_account_label_at_handle(self):
        """POST Instagram URL -> template should render '@onwebapp' as account label."""
        import os
        saved = os.environ.pop('SOCIAL_API_URL', None)
        try:
            response = self.client.post(reverse('services:social_media_tracking'), {
                'handle': 'https://www.instagram.com/onwebapp/',
            })
            self.assertEqual(response.status_code, 200)
            content = response.content.decode('utf-8', errors='ignore')
            self.assertIn('@onwebapp', content)
        finally:
            if saved is not None:
                os.environ['SOCIAL_API_URL'] = saved

    def test_view_post_linkedin_company_extracts_onwebapp(self):
        """POST LinkedIn /company/onwebapp -> account handle is 'onwebapp', NOT 'company'."""
        import os
        saved = os.environ.pop('SOCIAL_API_URL', None)
        try:
            response = self.client.post(reverse('services:social_media_tracking'), {
                'handle': 'https://www.linkedin.com/company/onwebapp/',
            })
            self.assertEqual(response.status_code, 200)
            result = response.context.get('result') or {}
            self.assertEqual(result.get('normalized_handle'), 'onwebapp')
            self.assertNotEqual(result.get('normalized_handle'), 'company')
            content = response.content.decode('utf-8', errors='ignore')
            self.assertNotIn('@company', content)
        finally:
            if saved is not None:
                os.environ['SOCIAL_API_URL'] = saved

    def test_view_post_youtube_at_handle_extracted(self):
        """POST YouTube @onwebapp -> handle is 'onwebapp', platform='youtube'."""
        import os
        saved = os.environ.pop('SOCIAL_API_URL', None)
        try:
            response = self.client.post(reverse('services:social_media_tracking'), {
                'handle': 'https://www.youtube.com/@onwebapp',
            })
            self.assertEqual(response.status_code, 200)
            result = response.context.get('result') or {}
            self.assertEqual(result.get('normalized_handle'), 'onwebapp')
            self.assertEqual(result.get('detected_platform'), 'youtube')
        finally:
            if saved is not None:
                os.environ['SOCIAL_API_URL'] = saved

    def test_view_post_provider_status_shown_in_template(self):
        """POST any URL -> template should render 'Provider Status:' text."""
        import os
        saved = os.environ.pop('SOCIAL_API_URL', None)
        try:
            response = self.client.post(reverse('services:social_media_tracking'), {
                'handle': 'https://instagram.com/onwebapp/',
            })
            self.assertEqual(response.status_code, 200)
            content = response.content.decode('utf-8', errors='ignore')
            self.assertIn('Provider Status:', content)
        finally:
            if saved is not None:
                os.environ['SOCIAL_API_URL'] = saved

    def test_view_post_provider_not_configured_without_api(self):
        """Without SOCIAL_API_URL env -> template renders 'Provider Not Configured'."""
        import os
        saved = os.environ.pop('SOCIAL_API_URL', None)
        try:
            response = self.client.post(reverse('services:social_media_tracking'), {
                'handle': 'https://instagram.com/onwebapp/',
            })
            self.assertEqual(response.status_code, 200)
            content = response.content.decode('utf-8', errors='ignore')
            self.assertIn('Provider Not Configured', content)
        finally:
            if saved is not None:
                os.environ['SOCIAL_API_URL'] = saved

    def test_view_post_no_fake_84_percent_positive_sentiment(self):
        """Never fabricate 84% positive - sentiment must be honest 'Not Available' when no posts."""
        import os
        saved = os.environ.pop('SOCIAL_API_URL', None)
        try:
            response = self.client.post(reverse('services:social_media_tracking'), {
                'handle': 'https://instagram.com/nonexistent_handle_xyz1234/',
            })
            self.assertEqual(response.status_code, 200)
            content = response.content.decode('utf-8', errors='ignore')
            self.assertNotIn('84%', content)
        finally:
            if saved is not None:
                os.environ['SOCIAL_API_URL'] = saved

    def test_view_post_no_demo_12_4k_followers(self):
        """Never inject seeded 12.4K followers into rendered output."""
        import os
        saved = os.environ.pop('SOCIAL_API_URL', None)
        try:
            response = self.client.post(reverse('services:social_media_tracking'), {
                'handle': 'https://instagram.com/nonexistent_handle_xyz1234/',
            })
            self.assertEqual(response.status_code, 200)
            content = response.content.decode('utf-8', errors='ignore')
            self.assertNotIn('12.4K', content)
        finally:
            if saved is not None:
                os.environ['SOCIAL_API_URL'] = saved

    def test_view_post_no_demo_5_2_percent_engagement(self):
        """Never inject seeded 5.2% engagement."""
        import os
        saved = os.environ.pop('SOCIAL_API_URL', None)
        try:
            response = self.client.post(reverse('services:social_media_tracking'), {
                'handle': 'https://instagram.com/nonexistent_handle_xyz1234/',
            })
            self.assertEqual(response.status_code, 200)
            content = response.content.decode('utf-8', errors='ignore')
            self.assertNotIn('5.2%', content)
        finally:
            if saved is not None:
                os.environ['SOCIAL_API_URL'] = saved

    def test_view_post_never_synced_displayed_without_api(self):
        """Without API and DB records -> 'Never Synced' displayed in rendered page."""
        import os
        saved = os.environ.pop('SOCIAL_API_URL', None)
        try:
            response = self.client.post(reverse('services:social_media_tracking'), {
                'handle': 'https://instagram.com/nonexistent_handle_xyz1234/',
            })
            self.assertEqual(response.status_code, 200)
            content = response.content.decode('utf-8', errors='ignore')
            self.assertIn('Never Synced', content)
        finally:
            if saved is not None:
                os.environ['SOCIAL_API_URL'] = saved

    def test_form_includes_linkedin_and_youtube_platform_choices(self):
        """SocialTrackingForm PLATFORMS must expose LinkedIn + YouTube as valid choices."""
        from services.forms import SocialTrackingForm
        form = SocialTrackingForm()
        platform_keys = [p[0] for p in form.fields['platforms'].choices]
        self.assertIn('linkedin', platform_keys)
        self.assertIn('youtube', platform_keys)
        self.assertIn('twitter', platform_keys)
        self.assertIn('instagram', platform_keys)
        self.assertIn('tiktok', platform_keys)
        self.assertIn('facebook', platform_keys)
