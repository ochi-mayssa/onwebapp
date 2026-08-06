import os
import time
from types import MappingProxyType, SimpleNamespace
from unittest.mock import MagicMock, patch
from urllib.parse import urlparse

import requests
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from seo_analyzer.models import (
    SEOIssue,
    SEOMonitoringSnapshot,
    SEOPageAudit,
    SEOResult,
    SEOTask,
    URLIntelligenceIssue,
    URLIntelligenceResult,
    URLIntelligenceTask,
)
from seo_analyzer.services.analyzer import analyze
from seo_analyzer.services.crawler import crawl
from seo_analyzer.services.link_checker import (
    BACKLINK_FALLBACK_MESSAGE,
    _get_session_pool,
    analyze_links,
    build_internal_link_findings,
    build_internal_link_health,
)
from seo_analyzer.services.url_intelligence import analyze_url
from seo_analyzer.services.url_intelligence_recommender import build_ai_recommendations
from seo_analyzer.services.url_intelligence_scoring import score_to_label
from seo_analyzer.services.url_intelligence_utils import build_optimized_url
from seo_analyzer.services.link_progress import (
    get_completed_link_report,
    reset_progress_store,
    start_link_analysis,
)
from seo_analyzer.views import get_canonical_status_label
from seo_analyzer.services.modular_sitemap_intelligence import (
    DigitalMarketingModule,
    GoogleDiscoveryModule,
    PageIntelligencePipeline,
    build_modular_sitemap_intelligence_report,
)
from seo_analyzer.services.monitoring import (
    build_change_detection,
    build_monitoring_dashboard,
    record_link_snapshot,
)
from seo_analyzer.services.pdf_report import (
    KeepTogether,
    _build_link_pdf_styles,
    _build_url_pdf_resolution_story,
    _prepare_link_pdf_payload,
    _prepare_url_intelligence_pdf_payload,
    _register_link_pdf_fonts,
    build_link_checker_pdf,
    build_url_intelligence_pdf,
)
from seo_analyzer.services.topic_intelligence import (
    build_topic_intelligence,
    build_topic_intelligence_from_html,
)


class FakeResponse:
    def __init__(
        self,
        url,
        status_code=200,
        headers=None,
        content=b"",
        text=None,
        history=None,
    ):
        self.url = url
        self.status_code = status_code
        self.headers = headers or {}
        self.content = content
        self.text = text if text is not None else content.decode("utf-8", errors="ignore")
        self.history = history or []
        self._content = content

    def iter_content(self, chunk_size=65536):
        for i in range(0, len(self.content), chunk_size):
            yield self.content[i : i + chunk_size]

    def close(self):
        pass


class FakeSession:
    def __init__(self):
        html = (
            b"<html><body>"
            b'<a href="/about">About</a>'
            b'<a href="https://external.example/page">External Resource</a>'
            b"</body></html>"
        )
        self.page_response = FakeResponse(
            "https://example.com",
            status_code=200,
            headers={"Content-Type": "text/html; charset=utf-8"},
            content=html,
        )

    def get(self, url, timeout=0, allow_redirects=True, stream=False, headers=None):
        if url == "https://example.com":
            return self.page_response
        if url == "https://external.example/page":
            history = [FakeResponse("https://external.example/page", status_code=301, headers={})]
            return FakeResponse(
                "https://external.example/final",
                status_code=200,
                headers={},
                history=history,
            )
        if url == "https://example.com/about":
            return FakeResponse(url, status_code=200, headers={})
        return FakeResponse(url, status_code=404, headers={})

    def head(self, url, timeout=0, allow_redirects=False, headers=None):
        if url == "https://example.com/about":
            return FakeResponse(url, status_code=200, headers={})
        if url == "https://external.example/page":
            return FakeResponse(
                url,
                status_code=301,
                headers={"Location": "https://external.example/final"},
            )
        return FakeResponse(url, status_code=404, headers={})


class EmptyLinkSession:
    def get(self, url, timeout=0, allow_redirects=True, stream=False, headers=None):
        html = b"<html><body><p>No links here.</p></body></html>"
        return FakeResponse(
            "https://example.com",
            status_code=200,
            headers={"Content-Type": "text/html; charset=utf-8"},
            content=html,
        )

    def head(self, url, timeout=0, allow_redirects=True, headers=None):
        return FakeResponse(url, status_code=200, headers={})


class TimeoutSession:
    def get(self, url, timeout=0, allow_redirects=True, stream=False, headers=None):
        raise requests.exceptions.ConnectTimeout("timeout")

    def head(self, url, timeout=0, allow_redirects=True, headers=None):
        raise requests.exceptions.ConnectTimeout("timeout")


class URLIntelligenceSession:
    def __init__(self, responses=None, errors=None):
        self.responses = responses or {}
        self.errors = errors or {}

    def get(self, url, timeout=0, allow_redirects=True, stream=False):
        request_url = urlparse(url)._replace(fragment="").geturl()
        if url in self.errors:
            raise self.errors[url]
        if request_url in self.errors:
            raise self.errors[request_url]
        response = self.responses.get(url) or self.responses.get(request_url)
        if response is None:
            for stored_url, stored_response in self.responses.items():
                if urlparse(stored_url)._replace(fragment="").geturl() == request_url:
                    response = stored_response
                    break
        if response is None:
            raise requests.exceptions.ConnectionError(f"No fake response registered for {url}")
        return response


class TrackingSession:
    def __init__(self, html: bytes, tracker: dict[str, dict[str, int]], responses=None):
        self.html = html
        self.tracker = tracker
        self.responses = responses or {}

    def get(self, url, timeout=0, allow_redirects=True, stream=False, headers=None):
        if url == "https://example.com":
            return FakeResponse(
                "https://example.com",
                status_code=200,
                headers={"Content-Type": "text/html; charset=utf-8"},
                content=self.html,
            )
        self._count(url, "get")
        response = self.responses.get(url)
        if isinstance(response, Exception):
            raise response
        if response is not None:
            return response
        return FakeResponse(url, status_code=404, headers={})

    def head(self, url, timeout=0, allow_redirects=True, headers=None):
        self._count(url, "head")
        response = self.responses.get(url)
        if isinstance(response, Exception):
            raise response
        if response is not None:
            return response
        return FakeResponse(url, status_code=404, headers={})

    def _count(self, url: str, method: str) -> None:
        bucket = self.tracker.setdefault(url, {"head": 0, "get": 0})
        bucket[method] += 1


class TopicContextFlowTests(TestCase):
    def setUp(self):
        self.topic_intelligence = {
            "primary_keyword": "SEO",
            "detected_topic": "SEO",
            "secondary_keywords": ["Search Engine Optimization", "Organic Search"],
            "semantic_keywords": ["Search Visibility", "SERP", "Content Strategy"],
            "long_tail_keywords": ["What is SEO", "SEO for beginners"],
            "search_intent": "Commercial",
            "content_category": "Guide / Article",
            "topic_cluster": "SEO & Search Visibility",
            "target_audience": "Digital marketing teams",
            "page_title": "What is SEO? Yoast Guide",
            "meta_description": "Learn how SEO supports digital marketing growth.",
            "primary_h1": "What is SEO?",
            "primary_h2": "SEO basics | SEO and digital marketing | SEO opportunities",
            "keyword_coverage_pct": 100,
            "semantic_relevance_pct": 88,
            "has_missing_h1": False,
        }

    @patch("seo_analyzer.services.modular_sitemap_intelligence.build_topic_intelligence_from_url")
    def test_page_context_uses_topic_intelligence_fields_for_web_pages(self, mock_topic_intelligence):
        mock_topic_intelligence.return_value = self.topic_intelligence

        context = PageIntelligencePipeline.build_page_context(
            "https://example.com/seo",
            "https://example.com/seo",
            "digital marketing",
        )

        self.assertEqual(context["detected_topic"], "SEO")
        self.assertEqual(context["primary_keyword"], "SEO")
        self.assertEqual(context["target_keyword"], "digital marketing")
        self.assertEqual(context["search_intent"], "Commercial")
        self.assertEqual(context["content_category"], "Guide / Article")
        self.assertEqual(context["topic_cluster"], "SEO & Search Visibility")
        self.assertEqual(context["target_audience"], "Digital marketing teams")
        self.assertIsInstance(context["analysis_context"], MappingProxyType)
        self.assertEqual(context["analysis_context"]["detected_topic"], "SEO")
        self.assertEqual(
            context["h2_headings"],
            ["SEO basics", "SEO and digital marketing", "SEO opportunities"],
        )
        self.assertGreaterEqual(context["topic_match_score"], 60)
        self.assertLessEqual(context["topic_match_score"], 90)
        self.assertIn(context["marketing_relevance"], ["Medium", "High"])

    def test_digital_marketing_module_consumes_page_context_without_title_word_fallback(self):
        analysis_context = MappingProxyType(
            {
                "target_keyword": "digital marketing",
                "detected_topic": "SEO",
                "primary_keyword": "SEO",
                "industry": "Marketing",
                "audience": "Digital marketing teams",
                "intent": "Commercial",
                "semantic_keywords": ("Search Visibility", "Digital Strategy"),
                "topic_cluster": "SEO & Search Visibility",
                "content_category": "Guide / Article",
            }
        )
        page_context = {
            "page_title": "What is SEO? Yoast Guide",
            "meta_description": "Learn how SEO supports digital marketing growth.",
            "analysis_context": analysis_context,
            "secondary_keywords": ["Search Engine Optimization", "Organic Search"],
        }

        analysis = DigitalMarketingModule.analyze(
            "https://example.com/seo",
            {
                "analysis_context": analysis_context,
                "page_context": page_context,
            },
        )

        self.assertEqual(analysis["primary_marketing_keyword"], "SEO")
        self.assertEqual(analysis["detected_topic"], "SEO")
        self.assertEqual(analysis["target_keyword"], "digital marketing")
        self.assertGreaterEqual(analysis["topic_match_score"], 60)
        self.assertLessEqual(analysis["topic_match_score"], 90)
        self.assertGreaterEqual(analysis["marketing_alignment_score"], 60)
        self.assertEqual(DigitalMarketingModule.score(analysis), analysis["marketing_alignment_score"])
        self.assertTrue(
            any("digital marketing" in item.lower() and "seo" in item.lower() for item in analysis["content_opportunities"])
        )

    @patch("seo_analyzer.services.modular_sitemap_intelligence.GoogleDiscoveryModule.discover", return_value=False)
    @patch("seo_analyzer.services.modular_sitemap_intelligence.VideoSitemapModule.discover", return_value=False)
    @patch("seo_analyzer.services.modular_sitemap_intelligence.ImageSitemapModule.discover", return_value=False)
    @patch("seo_analyzer.services.modular_sitemap_intelligence.XMLSitemapModule.discover", return_value=False)
    @patch("seo_analyzer.services.modular_sitemap_intelligence.resolve_final_url", return_value=("https://example.com/seo", "https://example.com/seo"))
    @patch("seo_analyzer.services.modular_sitemap_intelligence.build_topic_intelligence_from_url")
    def test_modular_report_uses_page_context_for_exec_summary_and_alignment(
        self,
        mock_topic_intelligence,
        _mock_resolve_final_url,
        _mock_xml_discover,
        _mock_image_discover,
        _mock_video_discover,
        _mock_google_discover,
    ):
        mock_topic_intelligence.return_value = self.topic_intelligence

        report = build_modular_sitemap_intelligence_report(
            "https://example.com/seo",
            target_keyword="digital marketing",
        )

        self.assertEqual(report["executive_summary"]["target_keyword"], "digital marketing")
        self.assertEqual(report["executive_summary"]["detected_topic"], "SEO")
        self.assertIsInstance(report["analysis_context"], MappingProxyType)
        self.assertEqual(report["analysis_context"]["primary_keyword"], "SEO")
        self.assertGreaterEqual(report["executive_summary"]["overall_marketing_readiness"], 60)
        self.assertEqual(report["module_results"]["digital_marketing"]["analysis"]["primary_marketing_keyword"], "SEO")
        self.assertEqual(report["content_alignment"]["detected_topic"], "SEO")
        self.assertEqual(
            report["content_alignment"]["semantic_keywords"],
            ["Search Visibility", "SERP", "Content Strategy"],
        )
        self.assertEqual(report["content_alignment"]["analysis_context"]["target_keyword"], "digital marketing")

    @patch("seo_analyzer.services.modular_sitemap_intelligence.build_topic_intelligence_from_url")
    def test_exact_topic_match_returns_100(self, mock_topic_intelligence):
        exact_match_topic = {**self.topic_intelligence, "primary_keyword": "Digital Marketing", "detected_topic": "Digital Marketing"}
        mock_topic_intelligence.return_value = exact_match_topic

        context = PageIntelligencePipeline.build_page_context(
            "https://example.com/marketing",
            "https://example.com/marketing",
            "digital marketing",
        )

        self.assertEqual(context["topic_match_score"], 100)
        self.assertEqual(context["semantic_match_score"], 100)

    def test_google_discovery_skips_videoobject_stage_when_no_videos_exist(self):
        class DiscoverySession:
            def __init__(self):
                self.headers = {}

            def get(self, url, timeout=0, allow_redirects=True):
                html = (
                    b"<html><head>"
                    b"<meta name='viewport' content='width=device-width, initial-scale=1'>"
                    b"<meta property='og:title' content='SEO guide'>"
                    b"<meta property='og:description' content='SEO guide description'>"
                    b"<meta property='og:image' content='https://example.com/image.jpg'>"
                    b"<script type='application/ld+json'>{\"@type\":\"Article\"}</script>"
                    b"</head><body><h1>SEO Guide</h1></body></html>"
                )
                return FakeResponse(url, status_code=200, headers={}, content=html)

        with patch("seo_analyzer.services.modular_sitemap_intelligence.requests.Session", return_value=DiscoverySession()):
            analysis = GoogleDiscoveryModule.analyze(
                "https://example.com/seo",
                {
                    "classification": {"analysis_mode": ["video", "google_discovery"]},
                    "video_results": {"videos_found": 0, "video_schema": False},
                },
            )

        stage_names = [stage["name"] for stage in analysis["stages"]]
        self.assertNotIn("VideoObject Schema", stage_names)

    @patch("seo_analyzer.services.modular_sitemap_intelligence.GoogleDiscoveryModule.discover", return_value=False)
    @patch("seo_analyzer.services.modular_sitemap_intelligence.VideoSitemapModule.analyze", return_value={"videos_found": 0})
    @patch("seo_analyzer.services.modular_sitemap_intelligence.VideoSitemapModule.discover", return_value=True)
    @patch("seo_analyzer.services.modular_sitemap_intelligence.ImageSitemapModule.discover", return_value=False)
    @patch("seo_analyzer.services.modular_sitemap_intelligence.XMLSitemapModule.discover", return_value=False)
    @patch("seo_analyzer.services.modular_sitemap_intelligence.resolve_final_url", return_value=("https://example.com/seo", "https://example.com/seo"))
    @patch("seo_analyzer.services.modular_sitemap_intelligence.build_topic_intelligence_from_url")
    def test_report_disables_video_module_when_no_videos_exist(
        self,
        mock_topic_intelligence,
        _mock_resolve_final_url,
        _mock_xml_discover,
        _mock_image_discover,
        _mock_video_discover,
        _mock_video_analyze,
        _mock_google_discover,
    ):
        mock_topic_intelligence.return_value = self.topic_intelligence

        report = build_modular_sitemap_intelligence_report(
            "https://example.com/seo",
            target_keyword="digital marketing",
        )

        self.assertNotIn("video", report["module_results"])


class SEOAnalyzerRouteTests(TestCase):
    def test_required_pages_return_200(self):
        responses = {
            "/services/": self.client.get(reverse("services:index")),
            "/seo/": self.client.get(reverse("seo_analyzer:index")),
            "/seo/checker/": self.client.get(reverse("seo_analyzer:checker")),
            "/seo/url-intelligence/": self.client.get(reverse("seo_analyzer:url_intelligence")),
            "/seo/link/": self.client.get(reverse("seo_analyzer:link_checker")),
            "/seo/backlinks/": self.client.get(reverse("seo_analyzer:backlinks")),
            "/seo/sitemap/": self.client.get(reverse("seo_analyzer:sitemap")),
            "/seo/monitoring/": self.client.get(reverse("seo_analyzer:monitoring")),
        }

        for response in responses.values():
            self.assertEqual(response.status_code, 200)

    def test_seo_home_page_exposes_all_active_tools(self):
        response = self.client.get(reverse("seo_analyzer:index"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "SEO Tools Navigation")
        self.assertContains(response, "Website Checker")
        self.assertContains(response, "URL Intelligence")
        self.assertContains(response, "Link Checker")
        self.assertContains(response, "Sitemap Intelligence")
        self.assertContains(response, "Backlink Analyzer")
        self.assertContains(response, "SEO Monitoring")
        self.assertContains(response, reverse("seo_analyzer:checker"))
        self.assertContains(response, reverse("seo_analyzer:url_intelligence"))
        self.assertContains(response, reverse("seo_analyzer:link_checker"))
        self.assertContains(response, reverse("seo_analyzer:sitemap"))
        self.assertContains(response, reverse("seo_analyzer:backlinks"))
        self.assertContains(response, reverse("seo_analyzer:monitoring"))

    def test_services_page_exposes_active_seo_tools(self):
        response = self.client.get(reverse("services:index"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Website Checker")
        self.assertContains(response, "URL Intelligence")
        self.assertContains(response, "Link Checker")
        self.assertContains(response, "Sitemap Intelligence")
        self.assertContains(response, "Backlink Analyzer")
        self.assertContains(response, reverse("seo_analyzer:checker"))
        self.assertContains(response, reverse("seo_analyzer:url_intelligence"))
        self.assertContains(response, reverse("seo_analyzer:link_checker"))
        self.assertContains(response, reverse("seo_analyzer:sitemap"))
        self.assertContains(response, reverse("seo_analyzer:backlinks"))

    def test_backlinks_route_renders_active_form_page(self):
        response = self.client.get(reverse("seo_analyzer:backlinks"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Backlink Analyzer")
        self.assertContains(response, 'value="backlinks"', html=False)


class TopicIntelligenceServiceTests(TestCase):
    def test_topic_intelligence_detects_transactional_page_and_missing_h1(self):
        topic = build_topic_intelligence(
            url="https://example.com/buy-menstrual-cup",
            page_title="Buy Menstrual Cup Online",
            meta_title="Buy Menstrual Cup Online",
            meta_description="Buy a reusable menstrual cup with fast delivery and safe period care.",
            content_text=(
                "Buy menstrual cup online for reusable period care. "
                "This product page helps shoppers compare menstrual cup sizes and pricing."
            ),
            word_count=420,
        )

        self.assertEqual(topic["primary_h1"], "H1 Missing")
        self.assertTrue(topic["has_missing_h1"])
        self.assertEqual(topic["search_intent"], "Transactional")
        self.assertEqual(topic["content_category"], "Product / Transaction Page")
        self.assertIn("Menstrual Cup", topic["primary_keyword"])
        self.assertLess(topic["ai_visibility_potential"], 90)
        self.assertIn("topic cluster", topic["ai_insight"])
        self.assertGreaterEqual(topic["search_intent_confidence_pct"], 60)
        self.assertIn("buyers", topic["target_audience"].lower())
        self.assertIn("keyword_intelligence", topic)
        self.assertIn("content_quality", topic)
        self.assertIn("technical_seo_intelligence", topic)
        self.assertIn("action_priority", topic)
        self.assertIn("competitor_mode", topic)
        self.assertTrue(topic["executive_summary"]["top_ai_recommendations"])

    def test_topic_intelligence_from_html_prioritizes_auth_content_over_footer_cta(self):
        html = b"""
        <html>
            <head>
                <title>Sign In | OnWebApp</title>
                <meta name="description" content="Login to access your OnWebApp dashboard securely.">
            </head>
            <body>
                <header>
                    <nav>Home Services Pricing Newsletter</nav>
                </header>
                <main>
                    <h1>Sign In</h1>
                    <p>Access your account dashboard and authenticate securely.</p>
                </main>
                <footer>
                    <div class="global-cta">Ready to Automate Your Success</div>
                    <div class="newsletter-signup">Subscribe to our newsletter</div>
                </footer>
            </body>
        </html>
        """

        topic = build_topic_intelligence_from_html("https://example.com/users/login/", html)

        self.assertIn(topic["detected_topic"], {"Sign In", "Login", "Authentication"})
        self.assertIn(topic["primary_keyword"], {"Sign In", "Login", "Authentication"})
        self.assertNotIn("Ready To Automate Your Success", topic["detected_topic"])
        self.assertNotIn("Ready To Automate Your Success", topic["primary_keyword"])


class MonitoringServiceTests(TestCase):
    def test_change_detection_and_dashboard_comparison_use_snapshot_history(self):
        older = SEOMonitoringSnapshot.objects.create(
            source_identifier="website:older",
            website="https://example.com",
            domain="example.com",
            analysis_type="website",
            health_score="71.00",
            visibility_score="66.00",
            ai_opportunity_score="62.00",
            technical_score="70.00",
            performance_score="61.00",
            content_score="64.00",
            security_score="100.00",
            broken_links=8,
            redirects=5,
            internal_links=40,
            indexed_pages=22,
            issues_count=15,
            tracked_items={
                "broken_links": ["https://example.com/old-broken", "https://example.com/legacy"],
                "redirect_links": ["https://example.com/old-redirect"],
                "internal_links": ["https://example.com/page-a"],
                "external_links": [],
            },
            metadata={"word_count_total": 900},
        )
        latest = SEOMonitoringSnapshot.objects.create(
            source_identifier="website:latest",
            website="https://example.com",
            domain="example.com",
            analysis_type="website",
            health_score="82.00",
            visibility_score="74.00",
            ai_opportunity_score="71.00",
            technical_score="79.00",
            performance_score="68.00",
            content_score="77.00",
            security_score="100.00",
            broken_links=3,
            redirects=2,
            internal_links=59,
            indexed_pages=28,
            issues_count=8,
            tracked_items={
                "broken_links": ["https://example.com/new-broken"],
                "redirect_links": [],
                "internal_links": [
                    "https://example.com/page-a",
                    "https://example.com/page-b",
                ],
                "external_links": ["https://external.example/resource"],
            },
            metadata={"word_count_total": 1200},
        )

        changes = build_change_detection(latest, older)
        dashboard = build_monitoring_dashboard(SEOMonitoringSnapshot.objects.filter(domain="example.com"))

        self.assertTrue(any(change["status"] == "NEW" and change["label"] == "Broken Links" for change in changes))
        self.assertTrue(any(change["status"] == "FIXED" and change["label"] == "Broken Links" for change in changes))
        self.assertTrue(any(row["label"] == "Health Score" and row["delta"].startswith("+11.00") for row in dashboard["current_vs_previous"]))
        self.assertEqual(dashboard["summary_cards"]["ai_trend"], "Improving")
        self.assertIn("Health Score improved by 11", dashboard["weekly_summary"])


class LinkCheckerServiceTests(TestCase):
    def test_build_session_does_not_force_a_user_agent_header(self):
        mock_session = MagicMock()
        mock_session.headers = {}

        with patch("seo_analyzer.services.link_checker.requests.Session", return_value=mock_session):
            session = _get_session_pool()

        self.assertIs(session, mock_session)
        self.assertEqual(session.headers, {})

    @patch("seo_analyzer.services.link_checker._get_session_pool", return_value=FakeSession())
    def test_internal_link_checker_extracts_same_domain_links(self, _mock_session):
        report = analyze_links("https://example.com", "internal")

        self.assertEqual(report["status"], "success")
        self.assertEqual(report["analysis_type"], "internal")
        self.assertEqual(report["summary"]["total_links"], 1)
        self.assertEqual(report["summary"]["working_links_count"], 1)
        self.assertEqual(report["links"][0]["link_url"], "https://example.com/about")
        self.assertEqual(report["status_badge"]["label"], "Excellent")
        self.assertEqual(report["recommendations"][0]["text"], "Internal linking structure is healthy.")
        self.assertEqual(report["recommendations"][1]["text"], "No broken internal links detected.")
        self.assertIn("topic_intelligence", report)
        self.assertIn("ai_visibility_potential", report["topic_intelligence"])
        self.assertIn("search_intent", report["topic_intelligence"])

    @patch("seo_analyzer.services.link_checker._get_session_pool", return_value=FakeSession())
    def test_external_link_checker_extracts_off_domain_links(self, _mock_session):
        report = analyze_links("https://example.com", "external")

        self.assertEqual(report["status"], "success")
        self.assertEqual(report["analysis_type"], "external")
        self.assertEqual(report["summary"]["total_links"], 1)
        self.assertEqual(report["summary"]["redirect_links_count"], 1)
        self.assertEqual(report["links"][0]["external_domain"], "external.example")
        self.assertEqual(
            report["external_insights"]["overview_metrics"]["total_external_links"], 1
        )
        self.assertEqual(
            report["external_insights"]["overview_metrics"]["unique_external_domains"], 1
        )
        self.assertEqual(
            report["external_insights"]["security_analysis"]["https_external_links"], 1
        )
        self.assertIn("topic_intelligence", report)
        self.assertIn("primary_keyword", report["topic_intelligence"])

    def test_backlink_checker_returns_fallback_without_provider_credentials(self):
        env_updates = {
            key: value
            for key, value in os.environ.items()
            if key not in {"MOZ_ACCESS_ID", "MOZ_SECRET_KEY"}
        }
        with patch.dict(os.environ, env_updates, clear=True):
            report = analyze_links("https://example.com", "backlinks")

        self.assertEqual(report["analysis_type"], "backlinks")
        self.assertEqual(report["status"], "error")
        self.assertEqual(report["fallback_message"], BACKLINK_FALLBACK_MESSAGE)
        self.assertTrue(report["provider_required"])
        self.assertFalse(report["metrics_available"])
        self.assertEqual(report["status_badge"]["label"], "Provider Required")
        self.assertIsNone(report["summary"]["total_links"])
        self.assertIn("topic_intelligence", report)
        self.assertEqual(report["topic_intelligence"]["primary_h1"], "Backlink Intelligence")

    @patch("seo_analyzer.services.link_checker._get_session_pool", return_value=TimeoutSession())
    def test_link_checker_returns_structured_error_payload(self, _mock_session):
        report = analyze_links("https://example.com", "internal")

        self.assertEqual(report["status"], "error")
        self.assertEqual(report["error_type"], "Connection Timeout")
        self.assertEqual(
            report["message"],
            "The website did not respond within the allowed timeout period.",
        )
        self.assertEqual(report["summary"]["total_issues"], 1)

    @patch("seo_analyzer.services.link_checker._get_session_pool", return_value=EmptyLinkSession())
    def test_link_checker_reports_no_links_found_state(self, _mock_session):
        report = analyze_links("https://example.com", "internal")

        self.assertEqual(report["status"], "success")
        self.assertEqual(report["summary"]["total_links"], 0)
        self.assertEqual(report["message"], "No Links Found")
        self.assertEqual(report["status_badge"]["label"], "Critical")

    def test_internal_duplicate_urls_are_checked_once(self):
        tracker: dict[str, dict[str, int]] = {}
        html = b"<html><body>" + (b'<a href="/about">About</a>' * 20) + b"</body></html>"

        with patch(
            "seo_analyzer.services.link_checker._get_session_pool",
            side_effect=lambda: TrackingSession(
                html,
                tracker,
                responses={
                    "https://example.com/about": FakeResponse(
                        "https://example.com/about",
                        status_code=200,
                        headers={},
                    )
                },
            ),
        ):
            report = analyze_links("https://example.com", "internal")

        self.assertEqual(report["summary"]["total_links"], 1)
        self.assertEqual(report["summary"]["working_links_count"], 1)
        self.assertEqual(report["performance_log"]["total_links_found"], 20)
        self.assertEqual(report["performance_log"]["unique_urls_checked"], 1)
        self.assertEqual(report["performance_log"]["duplicate_urls_skipped"], 19)
        self.assertEqual(tracker["https://example.com/about"]["head"], 1)
        self.assertEqual(tracker["https://example.com/about"]["get"], 0)

    def test_external_duplicate_urls_are_checked_once(self):
        tracker: dict[str, dict[str, int]] = {}
        html = (
            b"<html><body>"
            + (b'<a href="https://external.example/page">External Resource</a>' * 20)
            + b"</body></html>"
        )

        with patch(
            "seo_analyzer.services.link_checker._get_session_pool",
            side_effect=lambda: TrackingSession(
                html,
                tracker,
                responses={
                    "https://external.example/page": FakeResponse(
                        "https://external.example/page",
                        status_code=301,
                        headers={"Location": "https://external.example/final"},
                    )
                },
            ),
        ):
            report = analyze_links("https://example.com", "external")

        self.assertEqual(report["summary"]["total_links"], 1)
        self.assertEqual(report["summary"]["redirect_links_count"], 1)
        self.assertEqual(
            report["external_insights"]["overview_metrics"]["total_external_links"],
            1,
        )
        self.assertEqual(report["performance_log"]["total_links_found"], 20)
        self.assertEqual(report["performance_log"]["unique_urls_checked"], 1)
        self.assertEqual(report["performance_log"]["duplicate_urls_skipped"], 19)
        self.assertEqual(tracker["https://external.example/page"]["head"], 1)
        self.assertEqual(tracker["https://external.example/page"]["get"], 0)

    @patch("seo_analyzer.services.link_checker._get_session_pool", return_value=FakeSession())
    def test_internal_report_structure_remains_internal_specific(self, _mock_session):
        report = analyze_links("https://example.com", "internal")

        self.assertEqual(report["analysis_type"], "internal")
        self.assertEqual(report["external_insights"], {})
        self.assertEqual(report["recommendations"][0]["text"], "Internal linking structure is healthy.")
        self.assertIn("performance_log", report)

    @patch("seo_analyzer.services.link_checker._get_session_pool", return_value=FakeSession())
    def test_external_report_structure_remains_external_specific(self, _mock_session):
        report = analyze_links("https://example.com", "external")

        self.assertEqual(report["analysis_type"], "external")
        self.assertIn("overview_metrics", report["external_insights"])
        self.assertIn("domain_distribution", report["external_insights"])
        self.assertIn("security_analysis", report["external_insights"])
        self.assertIn("quality_section", report["external_insights"])
        self.assertIn("performance_log", report)

    def test_broken_links_are_still_classified_correctly(self):
        tracker: dict[str, dict[str, int]] = {}
        html = b'<html><body><a href="/missing">Missing</a></body></html>'

        with patch(
            "seo_analyzer.services.link_checker._get_session_pool",
            side_effect=lambda: TrackingSession(
                html,
                tracker,
                responses={
                    "https://example.com/missing": FakeResponse(
                        "https://example.com/missing",
                        status_code=404,
                        headers={},
                    )
                },
            ),
        ):
            report = analyze_links("https://example.com", "internal")

        self.assertEqual(report["status"], "success")
        self.assertEqual(report["summary"]["broken_links_count"], 1)
        self.assertEqual(report["links"][0]["status"], "broken")
        self.assertEqual(report["error_links"][0]["status"], "broken")

    def test_internal_link_classification_findings_and_recommendations_are_backend_driven(self):
        tracker: dict[str, dict[str, int]] = {}
        html = (
            b"<html><body>"
            b'<a href="/ok">OK</a>'
            b'<a href="/redirect">Redirect</a>'
            b'<a href="/missing">Missing</a>'
            b'<a href="/server-error">Server</a>'
            b'<a href="/slow">Slow</a>'
            b'<a href="/empty-anchor"></a>'
            b"</body></html>"
        )
        timeout_error = requests.exceptions.ConnectTimeout("timeout")

        with patch(
            "seo_analyzer.services.link_checker._get_session_pool",
            side_effect=lambda: TrackingSession(
                html,
                tracker,
                responses={
                    "https://example.com/ok": FakeResponse(
                        "https://example.com/ok",
                        status_code=200,
                        headers={},
                    ),
                    "https://example.com/redirect": FakeResponse(
                        "https://example.com/redirect",
                        status_code=301,
                        headers={"Location": "https://example.com/final"},
                    ),
                    "https://example.com/missing": FakeResponse(
                        "https://example.com/missing",
                        status_code=404,
                        headers={},
                    ),
                    "https://example.com/server-error": FakeResponse(
                        "https://example.com/server-error",
                        status_code=500,
                        headers={},
                    ),
                    "https://example.com/slow": timeout_error,
                    "https://example.com/empty-anchor": FakeResponse(
                        "https://example.com/empty-anchor",
                        status_code=200,
                        headers={},
                    ),
                },
            ),
        ):
            report = analyze_links("https://example.com", "internal")

        statuses = {row["link_url"]: row["status"] for row in report["links"]}
        self.assertEqual(statuses["https://example.com/ok"], "working")
        self.assertEqual(statuses["https://example.com/redirect"], "redirect")
        self.assertEqual(statuses["https://example.com/missing"], "broken")
        self.assertEqual(statuses["https://example.com/server-error"], "broken")
        self.assertEqual(statuses["https://example.com/slow"], "error")
        self.assertEqual(report["summary"]["broken_links_count"], 2)
        self.assertEqual(report["summary"]["redirect_links_count"], 1)
        self.assertEqual(report["summary"]["error_links_count"], 1)
        self.assertEqual(report["health"]["score"], 77)
        self.assertEqual(report["health"]["label"], "Good")
        finding_issues = {finding["issue"] for finding in report["findings"]}
        self.assertIn("Broken Internal Links", finding_issues)
        self.assertIn("Timeout / Error Links", finding_issues)
        self.assertIn("Redirected Internal Links", finding_issues)
        self.assertIn("Empty Anchor Text", finding_issues)
        self.assertIsInstance(report["recommendations"][0], dict)
        self.assertIn("priority", report["recommendations"][0])
        self.assertIn("estimated_gain", report["recommendations"][0])

    def test_internal_error_links_exclude_redirects_and_auth_redirects_are_labeled(self):
        tracker: dict[str, dict[str, int]] = {}
        html = (
            b"<html><body>"
            b'<a href="/services/industrial-automation">Industrial Automation</a>'
            b'<a href="/missing">Missing</a>'
            b"</body></html>"
        )

        with patch(
            "seo_analyzer.services.link_checker._get_session_pool",
            side_effect=lambda: TrackingSession(
                html,
                tracker,
                responses={
                    "https://example.com/services/industrial-automation": FakeResponse(
                        "https://example.com/services/industrial-automation",
                        status_code=302,
                        headers={"Location": "https://example.com/accounts/login/"},
                    ),
                    "https://example.com/missing": FakeResponse(
                        "https://example.com/missing",
                        status_code=404,
                        headers={},
                    ),
                },
            ),
        ):
            report = analyze_links("https://example.com", "internal")

        auth_row = next(
            row
            for row in report["links"]
            if row["link_url"] == "https://example.com/services/industrial-automation"
        )
        self.assertEqual(auth_row["status"], "redirect")
        self.assertIn("Authentication Required", auth_row["status_detail"])
        self.assertEqual([row["status"] for row in report["error_links"]], ["broken"])

    def test_timeout_links_become_errors_without_crashing(self):
        tracker: dict[str, dict[str, int]] = {}
        html = b'<html><body><a href="/slow">Slow</a></body></html>'
        timeout_error = requests.exceptions.ConnectTimeout("timeout")

        with patch(
            "seo_analyzer.services.link_checker._get_session_pool",
            side_effect=lambda: TrackingSession(
                html,
                tracker,
                responses={"https://example.com/slow": timeout_error},
            ),
        ):
            report = analyze_links("https://example.com", "internal")

        self.assertEqual(report["status"], "success")
        self.assertEqual(report["summary"]["error_links_count"], 1)
        self.assertEqual(report["links"][0]["status"], "error")
        self.assertIn("Connection Timeout", report["links"][0]["status_detail"])

    @patch("seo_analyzer.services.link_checker._get_session_pool", return_value=FakeSession())
    def test_internal_health_is_reused_by_pdf_payload_and_monitoring(self, _mock_session):
        report = analyze_links("https://example.com", "internal")

        payload = _prepare_link_pdf_payload(report)
        snapshot = record_link_snapshot(report)

        self.assertEqual(report["health"]["score"], payload["health"]["score"])
        self.assertEqual(report["health"]["label"], payload["health"]["label"])
        self.assertEqual(int(snapshot.health_score), report["health"]["score"])


class LinkCheckerPdfReportTests(TestCase):
    def test_link_checker_pdf_includes_professional_sections_for_external_links(self):
        pdf_bytes = build_link_checker_pdf(
            {
                "url": "https://example.com",
                "final_url": "https://example.com",
                "analysis_type": "external",
                "analysis_type_label": "External Links",
                "analyzed_at": "2026-06-24T18:30:00+00:00",
                "status_badge": {"label": "Good"},
                "metrics_available": True,
                "provider_required": False,
                "summary": {
                    "total_links": 8,
                    "working_links_count": 6,
                    "broken_links_count": 1,
                    "redirect_links_count": 1,
                    "error_links_count": 0,
                },
                "error_links": [
                    {
                        "link_url": "https://external.example/old",
                        "status_label": "Redirect",
                        "status_detail": "Redirected 1 time(s) to https://external.example/new",
                    }
                ],
                "recommendations": [
                    "Replace redirecting URLs with their final destination to improve crawl efficiency and page speed.",
                    "Diversify outbound references across more external domains to reduce reliance on a narrow source set.",
                ],
                "external_insights": {
                    "overview_metrics": {
                        "unique_external_domains": 4,
                    },
                    "security_analysis": {
                        "https_external_links": 7,
                        "http_external_links": 1,
                    },
                    "domain_distribution": [
                        {"domain": "external.example", "link_count": 3, "status": "Healthy"}
                    ],
                    "quality_section": {
                        "authority_available": "Not Available",
                        "domain_diversity": "Moderate",
                        "link_distribution": "Balanced",
                    },
                },
                "topic_intelligence": build_topic_intelligence(
                    url="https://example.com/seo/link-audit",
                    page_title="Best SEO Link Audit",
                    meta_title="Best SEO Link Audit",
                    meta_description="Compare and audit external links for SEO performance.",
                    h1="Best SEO Link Audit",
                    content_text="Best SEO link audit platform to compare external link quality and trust.",
                    word_count=520,
                ),
            }
        )

        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        self.assertIn(b"Link Checker Report", pdf_bytes)
        self.assertIn(b"Primary SEO Topic Intelligence", pdf_bytes)
        self.assertIn(b"AI Visibility Potential", pdf_bytes)
        self.assertIn(b"Executive Summary", pdf_bytes)
        self.assertIn(b"External Links Report", pdf_bytes)
        self.assertIn(b"Domain Distribution", pdf_bytes)
        self.assertIn(b"Recommendations", pdf_bytes)
        self.assertIn(b"Generated by OnWebApp SEO Intelligence Platform", pdf_bytes)

    def test_link_checker_pdf_uses_provider_required_instead_of_zero_metrics(self):
        pdf_bytes = build_link_checker_pdf(
            {
                "url": "https://example.com",
                "final_url": "https://example.com",
                "analysis_type": "backlinks",
                "analysis_type_label": "Backlink Intelligence",
                "analyzed_at": "2026-06-24T18:30:00+00:00",
                "status_badge": {"label": "Provider Required"},
                "metrics_available": False,
                "provider_required": True,
                "error_type": "Provider Required",
                "summary": {
                    "total_links": None,
                    "working_links_count": None,
                    "broken_links_count": None,
                    "redirect_links_count": None,
                    "error_links_count": None,
                },
                "error_links": [],
                "unavailable_details": [
                    "No supported backlink provider is currently connected."
                ],
                "recommendations": [
                    "Backlink analysis requires external authority data that cannot be discovered through website crawling alone."
                ],
                "topic_intelligence": build_topic_intelligence(
                    url="https://example.com/backlinks",
                    page_title="Backlink Intelligence",
                    meta_title="Backlink Intelligence",
                    meta_description="Backlink visibility and authority intelligence for the analyzed domain.",
                    h1="Backlink Intelligence",
                    content_text="Backlink intelligence helps assess authority, visibility, and referring domains.",
                    word_count=310,
                ),
            }
        )

        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        self.assertIn(b"Primary SEO Topic Intelligence", pdf_bytes)
        self.assertIn(b"Provider Required", pdf_bytes)
        self.assertIn(b"external authority data", pdf_bytes)
        self.assertNotIn(b"(0) Tj", pdf_bytes)


class SEONetworkRegressionTests(TestCase):
    @patch("seo_analyzer.services.analyzer.check_https_validity", return_value=False)
    def test_successful_root_response_overrides_https_helper_failure(
        self, _mock_https_helper
    ):
        task = SEOTask.objects.create(
            url="https://example.com",
            domain="example.com",
            status="running",
        )
        page = SEOPageAudit.objects.create(
            task=task,
            url="https://example.com",
            final_url="https://example.com",
            status_code=200,
            response_time=0.2,
            page_size=1024,
            h1_count=1,
            h2_count=0,
            word_count=350,
            internal_links_count=1,
        )

        result = analyze(
            task,
            {
                "root_page": page,
                "crawl_succeeded": True,
                "sitemap_entries": set(),
                "has_robots": False,
                "has_sitemap": False,
            },
        )

        self.assertIsNotNone(result)
        self.assertTrue(result.https_status)
        self.assertFalse(task.issues.filter(name="Missing HTTPS Certificate").exists())

    @patch("seo_analyzer.services.crawler.requests.Session.get")
    @patch("seo_analyzer.services.crawler.requests.get")
    def test_crawl_marks_failed_only_when_root_request_itself_fails(
        self, mock_requests_get, mock_session_get
    ):
        mock_requests_get.side_effect = requests.exceptions.ConnectionError(
            "[Errno -2] Name or service not known"
        )
        mock_session_get.side_effect = requests.exceptions.ConnectionError(
            "[Errno -2] Name or service not known"
        )

        task = SEOTask.objects.create(
            url="https://invalid.example.test",
            domain="invalid.example.test",
        )
        crawl_data = crawl(task)
        task.refresh_from_db()

        self.assertFalse(crawl_data["crawl_succeeded"])
        self.assertEqual(crawl_data["error_type"], "DNS Resolution Error")
        self.assertEqual(task.status, "failed")
        self.assertFalse(SEOResult.objects.filter(task=task).exists())


class SEOAnalyzerViewTests(TestCase):
    def tearDown(self):
        reset_progress_store()
        super().tearDown()

    def _build_link_report(self, analysis_type):
        labels = {
            "internal": "Internal Links",
            "external": "External Links",
            "backlinks": "Backlink Intelligence",
        }
        report = {
            "url": "https://example.com",
            "domain": "example.com",
            "final_url": "https://example.com",
            "analysis_type": analysis_type,
            "analysis_type_label": labels[analysis_type],
            "analyzed_at": "2026-06-24T18:30:00+00:00",
            "status": "success",
            "error_type": "",
            "message": "",
            "summary": {
                "total_links": 2,
                "working_links_count": 1,
                "broken_links_count": 0,
                "redirect_links_count": 1,
                "error_links_count": 0,
                "total_issues": 1,
            },
            "links": [
                {
                    "link_url": "https://example.com/about",
                    "anchor_text": "About",
                    "source_page": "https://example.com",
                    "http_status_code": 200,
                    "status": "working",
                    "status_label": "Working",
                    "status_detail": "OK",
                    "redirect_count": 0,
                },
                {
                    "link_url": "https://external.example/page",
                    "anchor_text": "External Resource",
                    "source_page": "https://example.com",
                    "http_status_code": 301,
                    "status": "redirect",
                    "status_label": "Redirect",
                    "status_detail": "Redirect (301)",
                    "external_domain": "external.example",
                    "redirect_count": 1,
                },
            ],
            "error_links": [
                {
                    "link_url": "https://external.example/page",
                    "anchor_text": "External Resource",
                    "source_page": "https://example.com",
                    "http_status_code": 301,
                    "status": "redirect",
                    "status_label": "Redirect",
                    "status_detail": "Redirect (301)",
                    "external_domain": "external.example",
                    "redirect_count": 1,
                }
            ],
            "unavailable_details": [],
            "fallback_message": "",
            "recommendations": ["Replace redirecting URLs with their final destination."],
            "status_badge": {
                "label": "Good",
                "class": "bg-primary-subtle text-primary border border-primary-subtle",
            },
            "metrics_available": True,
            "provider_required": False,
            "supported_providers": [],
            "external_insights": {},
            "topic_intelligence": build_topic_intelligence(
                url="https://example.com/seo/link-audit",
                page_title=f"{labels[analysis_type]} SEO Intelligence",
                meta_title=f"{labels[analysis_type]} SEO Intelligence",
                meta_description="Audit link quality, crawlability, and SEO trust signals.",
                h1=f"{labels[analysis_type]} SEO Intelligence",
                content_text=(
                    "Audit link quality, crawlability, and SEO trust signals with strategic search intent analysis."
                ),
                word_count=480,
            ),
        }
        if analysis_type == "internal":
            report["health"] = build_internal_link_health(report["summary"])
            report["findings"] = build_internal_link_findings(report["summary"], report["links"])
            report["recommendations"] = [
                {
                    "text": "Replace redirecting URLs with their final destination.",
                    "priority": "Medium",
                    "difficulty": "Easy",
                    "estimated_gain": "+10 SEO Score",
                    "business_impact": "Direct routing improves analyzed page crawl efficiency and user navigation.",
                    "estimated_time": "15 minutes",
                    "confidence": "High",
                }
            ]
            report["status_badge"] = {
                "label": report["health"]["label"],
                "class": "bg-success-subtle text-success border border-success-subtle",
            }
        return report

    def _fake_analyze(self, task, _crawl_data):
        SEOResult.objects.create(
            task=task,
            final_url=task.url,
            https_status=True,
            main_status_code=200,
            main_response_time=0.25,
            health_score="82.00",
            technical_score="79.00",
            on_page_score="77.00",
            performance_score="68.00",
            discovery_score="74.00",
            ai_opportunity_score="71.00",
            total_issues=0,
            pages_crawled=1,
            internal_links_count=5,
            broken_internal_links_count=0,
            redirect_count=1,
        )

    @patch("seo_analyzer.views.crawl", return_value={"crawl_succeeded": True, "pages_crawled": 1})
    @patch("seo_analyzer.views.analyze")
    def test_website_checker_still_works_and_pdf_downloads(
        self, mock_analyze, _mock_crawl
    ):
        mock_analyze.side_effect = self._fake_analyze

        response = self.client.post(
            reverse("seo_analyzer:checker"),
            {"url": "https://example.com", "max_pages": 5},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "SEO Audit Report")

        task = SEOTask.objects.latest("created_at")
        self.assertTrue(SEOResult.objects.filter(task=task).exists())
        self.assertTrue(
            SEOMonitoringSnapshot.objects.filter(
                source_identifier=f"website:{task.id}",
                analysis_type="website",
            ).exists()
        )

        pdf_response = self.client.get(
            reverse("seo_analyzer:download_report", args=["website", task.id])
        )
        self.assertEqual(pdf_response.status_code, 200)
        self.assertEqual(pdf_response["Content-Type"], "application/pdf")
        self.assertTrue(pdf_response.content.startswith(b"%PDF"))
        self.assertIn(b"Primary SEO Topic Intelligence", pdf_response.content)
        self.assertIn(b"AI Visibility Potential", pdf_response.content)

    def test_checker_page_shows_seo_tools_nav_and_recent_audit_actions(self):
        task = SEOTask.objects.create(
            url="https://example.com",
            domain="example.com",
            status="completed",
        )
        SEOResult.objects.create(
            task=task,
            final_url=task.url,
            https_status=True,
            main_status_code=200,
            main_response_time=0.25,
            health_score="82.00",
            technical_score="79.00",
            on_page_score="77.00",
            performance_score="68.00",
            discovery_score="74.00",
            ai_opportunity_score="71.00",
            total_issues=0,
            pages_crawled=1,
            internal_links_count=5,
            broken_internal_links_count=0,
            redirect_count=1,
        )

        response = self.client.get(reverse("seo_analyzer:checker"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "SEO Tools")
        self.assertContains(response, "Website Checker")
        self.assertContains(response, "Link Checker")
        self.assertContains(response, "Sitemap Intelligence")
        self.assertContains(response, "Backlink Analyzer")
        self.assertContains(response, "View Results")
        self.assertContains(response, "Download PDF Report")

    def test_dashboard_shows_download_button_and_open_action(self):
        User = get_user_model()
        user = User.objects.create_superuser(username="seo-dashboard", email="seo-dashboard@example.com", password="secret123")
        self.client.force_login(user)

        task = SEOTask.objects.create(
            url="https://example.com",
            domain="example.com",
            status="completed",
        )
        page_audit = SEOPageAudit.objects.create(
            task=task,
            url="https://example.com/about",
            final_url="https://example.com/about",
            status_code=200,
            title_tag="About",
            title_tag_length=5,
        )
        SEOResult.objects.create(
            task=task,
            final_url=task.url,
            https_status=True,
            main_status_code=200,
            main_response_time=0.25,
            health_score="82.00",
            technical_score="79.00",
            on_page_score="77.00",
            performance_score="68.00",
            discovery_score="74.00",
            ai_opportunity_score="71.00",
            total_issues=1,
            critical_issues=0,
            high_issues=1,
            medium_issues=0,
            low_issues=0,
            pages_crawled=1,
            internal_links_count=5,
            broken_internal_links_count=0,
            redirect_count=0,
        )
        SEOIssue.objects.create(
            task=task,
            page_audit=page_audit,
            name="Missing Canonical Tag",
            severity="high",
            category="technical",
            status="open",
            description="Canonical tag is missing.",
        )

        response = self.client.get(reverse("seo_analyzer:dashboard", args=[task.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Primary SEO Topic Intelligence")
        self.assertContains(response, "Executive Summary")
        self.assertContains(response, "Technical SEO Intelligence")
        self.assertContains(response, "Keyword Intelligence")
        self.assertContains(response, "AI SEO Insights")
        self.assertContains(response, "Action Priority")
        self.assertContains(response, "Competitor Mode")
        self.assertContains(response, "AI Visibility Potential")
        self.assertContains(response, "Download SEO Report")
        self.assertContains(response, "Open")
        self.assertContains(response, "Overall SEO Score")
        self.assertContains(response, "Website Health")
        self.assertNotContains(response, "Ready to Automate Your Success")
        self.assertContains(response, 'target="_blank"', html=False)
        html = response.content.decode("utf-8")
        self.assertLess(
            html.index("Primary SEO Topic Intelligence"),
            html.index("Health Score"),
        )

    def test_executive_kpi_dashboard_uses_real_data_and_fallbacks(self):
        User = get_user_model()
        user = User.objects.create_superuser(username="seo-admin", email="seo@example.com", password="secret123")
        self.client.force_login(user)

        task = SEOTask.objects.create(
            url="https://example.com",
            domain="example.com",
            status="completed",
        )
        SEOResult.objects.create(
            task=task,
            final_url=task.url,
            https_status=True,
            main_status_code=200,
            main_response_time=0.25,
            health_score="82.00",
            technical_score="79.00",
            on_page_score="77.00",
            performance_score="68.00",
            discovery_score="74.00",
            ai_opportunity_score="71.00",
            total_issues=2,
            pages_crawled=10,
            internal_links_count=12,
            broken_internal_links_count=1,
            sitemap_entries_found=5,
            redirect_count=2,
        )
        SEOIssue.objects.create(
            task=task,
            page_audit=None,
            name="Missing canonical tag",
            severity="high",
            category="technical",
            description="Canonical tag is missing.",
            recommended_fix="Add a canonical tag to improve crawlability.",
        )

        url_task = URLIntelligenceTask.objects.create(
            url="https://example.com/about",
            target_keyword="seo",
            domain="example.com",
            status="completed",
        )
        URLIntelligenceResult.objects.create(
            task=url_task,
            original_url=url_task.url,
            final_url=url_task.url,
            http_status_code=200,
            response_time=0.12,
            https_status=True,
            redirect_detected=False,
            redirect_count=0,
            protocol="https",
            domain="example.com",
            subdomain="",
            path="/about",
            slug="about",
            url_length=18,
            url_depth=1,
            trailing_slash=False,
            has_uppercase=False,
            has_underscores=False,
            hyphen_count=0,
            special_character_count=0,
            encoded_space_detected=False,
            numeric_slug_detected=False,
            query_params_count=0,
            tracking_params_count=0,
            functional_params_count=0,
            unnecessary_params_count=0,
            has_fragment=False,
            dynamic_url_detected=False,
            canonical_url="https://example.com/about",
            canonical_status="self",
            canonical_matches=True,
            meta_robots="",
            x_robots_tag="",
            indexability_status="indexable",
            health_score="88.00",
            structure_score="84.00",
            technical_score="86.00",
            canonical_score="90.00",
            indexability_score="87.00",
            seo_friendliness_score="85.00",
            keyword_relevance_score="80.00",
            keyword_match_status="partial",
            critical_issues=0,
            high_issues=1,
            medium_issues=0,
            low_issues=0,
            informational_issues=0,
            total_issues=1,
            redirect_chain=[],
            parameters_payload={},
            structure_payload={},
            quality_checks=[],
            recommendations_payload=[{"title": "Tighten keyword focus"}],
            optimized_url_payload={},
        )

        SEOMonitoringSnapshot.objects.create(
            source_identifier="link:external-1",
            website="https://example.com",
            domain="example.com",
            analysis_type="external",
            health_score="74.00",
            broken_links=2,
            redirects=1,
            external_links=7,
            issues_count=4,
            metadata={"recommendations": ["Replace redirecting outbound links."]},
        )

        response = self.client.get(reverse("seo_analyzer:executive_kpi_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enterprise SEO KPI Dashboard")
        self.assertContains(response, "Website Checker")
        self.assertContains(response, "82")
        self.assertContains(response, "URL Intelligence")
        self.assertContains(response, "88")
        self.assertContains(response, "Not Connected")
        self.assertContains(response, "Not Available")

    @patch("seo_analyzer.views.crawl")
    @patch("seo_analyzer.views.analyze")
    def test_failed_crawl_does_not_run_analyzer_and_blocks_pdf(
        self, mock_analyze, mock_crawl
    ):
        def fake_crawl(task):
            task.status = "failed"
            task.error_message = "The website did not respond within the allowed timeout period."
            task.save()
            return {
                "crawl_succeeded": False,
                "error_type": "Connection Timeout",
                "error_message": task.error_message,
            }

        mock_crawl.side_effect = fake_crawl

        response = self.client.post(
            reverse("seo_analyzer:checker"),
            {"url": "https://example.com", "max_pages": 5},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Audit Failed")
        self.assertContains(
            response,
            "The website did not respond within the allowed timeout period.",
        )
        mock_analyze.assert_not_called()

        task = SEOTask.objects.latest("created_at")
        pdf_response = self.client.get(
            reverse("seo_analyzer:download_report", args=["website", task.id])
        )
        self.assertEqual(pdf_response.status_code, 404)

    @patch("seo_analyzer.views.analyze_links")
    def test_internal_link_checker_route_and_pdf_download(self, mock_analyze_links):
        mock_analyze_links.return_value = self._build_link_report("internal")

        response = self.client.post(
            reverse("seo_analyzer:link_checker"),
            {"url": "https://example.com", "analysis_type": "internal"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Internal Links Report")
        self.assertContains(response, "Primary SEO Topic Intelligence")
        self.assertContains(response, "Download Link Report")
        self.assertTrue(
            SEOMonitoringSnapshot.objects.filter(
                analysis_type="internal",
                domain="example.com",
            ).exists()
        )

        report_path = response.request["PATH_INFO"]
        task_id = report_path.rstrip("/").split("/")[-1]
        pdf_response = self.client.get(
            reverse("seo_analyzer:download_report", args=["link", task_id])
        )
        self.assertEqual(pdf_response.status_code, 200)
        self.assertEqual(pdf_response["Content-Type"], "application/pdf")
        self.assertTrue(pdf_response.content.startswith(b"%PDF"))
        self.assertIn(b"Primary SEO Topic Intelligence", pdf_response.content)

    def test_link_checker_page_shows_required_inputs(self):
        response = self.client.get(reverse("seo_analyzer:link_checker"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Analyze Links")
        self.assertContains(response, "Internal Links")
        self.assertContains(response, "External Links")
        self.assertContains(response, "Backlinks")
        self.assertContains(response, "Real-Time Pipeline")
        self.assertContains(response, "Links Found")
        self.assertContains(response, "Estimated Remaining")

    @patch("seo_analyzer.views.start_link_analysis", return_value="11111111-1111-1111-1111-111111111111")
    def test_ajax_link_checker_post_returns_progress_urls(self, mock_start_link_analysis):
        response = self.client.post(
            reverse("seo_analyzer:link_checker"),
            {"url": "https://example.com", "analysis_type": "internal"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )

        self.assertEqual(response.status_code, 202)
        payload = response.json()
        self.assertEqual(payload["status"], "accepted")
        self.assertIn("/seo/link/progress/11111111-1111-1111-1111-111111111111/", payload["progress_url"])
        self.assertIn("/seo/link/results/11111111-1111-1111-1111-111111111111/", payload["result_url"])
        mock_start_link_analysis.assert_called_once_with("https://example.com", "internal")

    @patch("seo_analyzer.services.link_progress.link_checker.analyze_links")
    def test_progress_endpoint_returns_live_analysis_fields(self, mock_analyze_links):
        mock_analyze_links.return_value = self._build_link_report("internal")
        task_id = start_link_analysis("https://example.com", "internal")

        for _ in range(20):
            if get_completed_link_report(task_id):
                break
            time.sleep(0.05)

        response = self.client.get(reverse("seo_analyzer:link_progress", args=[task_id]))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn(payload["status"], {"running", "completed"})
        self.assertIn("stage", payload)
        self.assertIn("percentage_completed", payload)
        self.assertIn("links_checked", payload)
        self.assertIn("elapsed_time_seconds", payload)
        self.assertIn("estimated_remaining_time_seconds", payload)

    @patch("seo_analyzer.services.link_progress.link_checker.analyze_links")
    def test_link_results_can_read_completed_async_report(self, mock_analyze_links):
        report = self._build_link_report("internal")
        mock_analyze_links.return_value = report
        task_id = start_link_analysis("https://example.com", "internal")

        for _ in range(20):
            if get_completed_link_report(task_id):
                break
            time.sleep(0.05)

        response = self.client.get(reverse("seo_analyzer:link_results", args=[task_id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Internal Links Report")
        self.assertTrue(
            SEOMonitoringSnapshot.objects.filter(source_identifier=f"link:{task_id}").exists()
        )

    def test_monitoring_dashboard_renders_comparisons_charts_and_exports(self):
        first = SEOMonitoringSnapshot.objects.create(
            source_identifier="website:1",
            website="https://example.com",
            domain="example.com",
            analysis_type="website",
            health_score="71.00",
            visibility_score="63.00",
            ai_opportunity_score="60.00",
            technical_score="69.00",
            performance_score="61.00",
            content_score="64.00",
            security_score="100.00",
            broken_links=12,
            redirects=5,
            internal_links=38,
            external_links=7,
            indexed_pages=18,
            issues_count=16,
            tracked_items={"broken_links": ["https://example.com/broken-a"], "redirect_links": [], "internal_links": [], "external_links": []},
            metadata={"word_count_total": 880},
        )
        second = SEOMonitoringSnapshot.objects.create(
            source_identifier="website:2",
            website="https://example.com",
            domain="example.com",
            analysis_type="website",
            health_score="79.00",
            visibility_score="74.00",
            ai_opportunity_score="70.00",
            technical_score="78.00",
            performance_score="68.00",
            content_score="72.00",
            security_score="100.00",
            broken_links=4,
            redirects=1,
            internal_links=61,
            external_links=11,
            indexed_pages=24,
            issues_count=8,
            tracked_items={"broken_links": [], "redirect_links": [], "internal_links": ["https://example.com/page"], "external_links": ["https://external.example/resource"]},
            metadata={"word_count_total": 1180},
        )

        response = self.client.get(reverse("seo_analyzer:monitoring"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "SEO Monitoring")
        self.assertContains(response, "Website Timeline")
        self.assertContains(response, "Current Analysis vs Previous Analysis")
        self.assertContains(response, "AI Change Detection")
        self.assertContains(response, "Export PDF")
        self.assertContains(response, "Health Score")
        self.assertContains(response, first.domain)
        self.assertContains(response, second.domain)

        csv_response = self.client.get(reverse("seo_analyzer:monitoring_export", args=["csv"]))
        xlsx_response = self.client.get(reverse("seo_analyzer:monitoring_export", args=["xlsx"]))
        pdf_response = self.client.get(reverse("seo_analyzer:monitoring_export", args=["pdf"]))

        self.assertEqual(csv_response.status_code, 200)
        self.assertEqual(csv_response["Content-Type"], "text/csv")
        self.assertIn("seo-monitoring-history.csv", csv_response["Content-Disposition"])
        self.assertEqual(
            xlsx_response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertIn("seo-monitoring-history.xlsx", xlsx_response["Content-Disposition"])
        self.assertEqual(pdf_response["Content-Type"], "application/pdf")
        self.assertTrue(pdf_response.content.startswith(b"%PDF"))

    @patch("seo_analyzer.views.analyze_links")
    def test_internal_link_results_show_excellent_status_for_healthy_report(
        self, mock_analyze_links
    ):
        healthy_summary = {
            "total_links": 100,
            "working_links_count": 100,
            "broken_links_count": 0,
            "redirect_links_count": 0,
            "error_links_count": 0,
            "total_issues": 0,
        }
        mock_analyze_links.return_value = {
            "url": "https://example.com",
            "domain": "example.com",
            "final_url": "https://example.com",
            "analysis_type": "internal",
            "analysis_type_label": "Internal Links",
            "analyzed_at": "2026-06-24T18:30:00+00:00",
            "status": "success",
            "error_type": "",
            "message": "",
            "summary": healthy_summary,
            "links": [],
            "error_links": [],
            "unavailable_details": [],
            "fallback_message": "",
            "health": build_internal_link_health(healthy_summary),
            "findings": build_internal_link_findings(healthy_summary, []),
            "status_badge": {
                "label": "Excellent",
                "class": "bg-success-subtle text-success border border-success-subtle",
            },
            "recommendations": [
                {
                    "text": "Internal linking structure is healthy.",
                    "priority": "Low",
                    "difficulty": "Easy",
                    "estimated_gain": "+3 SEO Score",
                    "business_impact": "The analyzed page already provides stable internal navigation.",
                    "estimated_time": "Ongoing monitoring",
                    "confidence": "High",
                },
            ],
            "metrics_available": True,
            "provider_required": False,
            "supported_providers": [],
            "external_insights": {},
        }

        response = self.client.post(
            reverse("seo_analyzer:link_checker"),
            {"url": "https://example.com", "analysis_type": "internal"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Status:")
        self.assertContains(response, "Excellent")
        self.assertContains(response, "Internal linking structure is healthy.")

    @patch("seo_analyzer.views.analyze_links")
    def test_internal_results_template_uses_backend_health_and_no_error_link_double_counting(
        self, mock_analyze_links
    ):
        mock_analyze_links.return_value = self._build_link_report("internal")

        response = self.client.post(
            reverse("seo_analyzer:link_checker"),
            {"url": "https://example.com", "analysis_type": "internal"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "analyzed page internal link health")
        self.assertContains(response, "Replace redirecting URLs with their final destination.")
        self.assertNotContains(response, "links.concat(errorLinks)")
        self.assertContains(response, "links.forEach((link) => {")

    @patch("seo_analyzer.views.analyze_links")
    def test_internal_results_template_uses_redirect_and_share_aware_insights(
        self, mock_analyze_links
    ):
        mock_analyze_links.return_value = self._build_link_report("internal")

        response = self.client.post(
            reverse("seo_analyzer:link_checker"),
            {"url": "https://example.com", "analysis_type": "internal"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "stats.redirectSingle + stats.redirectChains + stats.brokenRedirects === 0",
        )
        self.assertContains(
            response,
            "internal destinations require at least one redirect before resolving and should be cleaned up.",
        )
        self.assertContains(response, "topPages.length && topPageShare >= 0.45")
        self.assertContains(response, 'id="internal-links-table-shell"')
        self.assertContains(response, 'id="internal-errors-table-shell"')
        self.assertContains(response, "primaryTableShell.classList.toggle('d-none', scope === 'errors')")
        self.assertContains(response, "errorTableShell.classList.toggle('d-none', scope === 'primary')")
        self.assertContains(response, "No rows match the current search and filter settings.")

    @patch("seo_analyzer.views.analyze_links")
    def test_external_link_results_use_dedicated_external_sections(
        self, mock_analyze_links
    ):
        report = self._build_link_report("external")
        report["external_insights"] = {
            "overview_metrics": {
                "total_external_links": 2,
                "unique_external_domains": 1,
                "working_external_links": 1,
                "broken_external_links": 0,
                "redirecting_external_links": 1,
            },
            "domain_distribution": [
                {"domain": "external.example", "link_count": 2, "status": "Redirecting"}
            ],
            "security_analysis": {
                "https_external_links": 2,
                "http_external_links": 0,
                "potentially_unsafe_links": 0,
            },
            "quality_section": {
                "authority_available": "Not Available",
                "domain_diversity": "Low",
                "link_distribution": "Highly Concentrated",
            },
        }
        report["recommendations"] = [
            "Replace redirecting URLs with their final destination to improve crawl efficiency and page speed.",
            "Diversify outbound references across more external domains to reduce reliance on a narrow source set.",
        ]
        mock_analyze_links.return_value = report

        response = self.client.post(
            reverse("seo_analyzer:link_checker"),
            {"url": "https://example.com", "analysis_type": "external"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Total External Links")
        self.assertContains(response, "Unique External Domains")
        self.assertContains(response, "Domain Distribution")
        self.assertContains(response, "Security Analysis")
        self.assertContains(response, "HTTPS External Links")
        self.assertContains(response, "HTTP External Links")
        self.assertContains(response, "Potentially Unsafe Links")
        self.assertContains(response, "External Link Quality")
        self.assertContains(response, "external.example")

    @patch("seo_analyzer.views.analyze_links")
    def test_backlink_results_hide_unmeasured_counts_when_provider_is_unavailable(
        self, mock_analyze_links
    ):
        mock_analyze_links.return_value = {
            "url": "https://example.com",
            "domain": "example.com",
            "final_url": "https://example.com",
            "analysis_type": "backlinks",
            "analysis_type_label": "Backlink Intelligence",
            "analyzed_at": "2026-06-24T18:30:00+00:00",
            "status": "error",
            "error_type": "Provider Required",
            "message": "Backlink data is not available because no backlink provider is currently connected.",
            "summary": {
                "total_links": None,
                "working_links_count": None,
                "broken_links_count": None,
                "redirect_links_count": None,
                "error_links_count": None,
                "total_issues": 0,
            },
            "links": [],
            "error_links": [],
            "unavailable_details": ["No supported backlink provider is currently connected."],
            "fallback_message": BACKLINK_FALLBACK_MESSAGE,
            "recommendations": [
                "Backlink analysis requires external authority data that cannot be discovered through website crawling alone.",
            ],
            "status_badge": {
                "label": "Provider Required",
                "class": "bg-warning-subtle text-warning border border-warning-subtle",
            },
            "metrics_available": False,
            "provider_required": True,
            "supported_providers": [
                "Google Search Console",
                "Moz",
                "Ahrefs",
                "Semrush",
            ],
            "external_insights": {},
        }

        response = self.client.post(
            reverse("seo_analyzer:link_checker"),
            {"url": "https://example.com", "analysis_type": "backlinks"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Provider Required")
        self.assertContains(
            response,
            "Backlink data is not available because no backlink provider is currently connected.",
        )
        self.assertContains(response, "Google Search Console")
        self.assertNotContains(response, "Source Domain</th>", html=False)

    @patch("seo_analyzer.views.analyze_links")
    def test_backlink_results_show_table_when_provider_is_connected(
        self, mock_analyze_links
    ):
        mock_analyze_links.return_value = {
            "url": "https://example.com",
            "domain": "example.com",
            "final_url": "https://example.com",
            "analysis_type": "backlinks",
            "analysis_type_label": "Backlink Intelligence",
            "analyzed_at": "2026-06-24T18:30:00+00:00",
            "status": "success",
            "error_type": "",
            "message": "",
            "summary": {
                "total_links": 2,
                "working_links_count": 1,
                "broken_links_count": 0,
                "redirect_links_count": 1,
                "error_links_count": 0,
                "total_issues": 1,
            },
            "links": [
                {
                    "source_domain": "ref.example",
                    "source_url": "https://ref.example/post",
                    "target_url": "https://example.com",
                    "anchor_text": "Brand Name",
                    "link_type": "DoFollow",
                    "domain_authority": 42,
                    "http_status_code": 200,
                    "status": "working",
                    "status_label": "Working",
                    "status_detail": "Active",
                }
            ],
            "error_links": [],
            "unavailable_details": [],
            "fallback_message": "",
            "recommendations": [
                "Prioritize the strongest working backlinks for outreach replication and authority-building campaigns."
            ],
            "status_badge": {
                "label": "Good",
                "class": "bg-primary-subtle text-primary border border-primary-subtle",
            },
            "metrics_available": True,
            "provider_required": False,
            "supported_providers": [],
            "external_insights": {},
        }

        response = self.client.post(
            reverse("seo_analyzer:link_checker"),
            {"url": "https://example.com", "analysis_type": "backlinks"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Backlink Intelligence Table")
        self.assertContains(response, "Brand Name")

    @patch("seo_analyzer.views.build_sitemap_intelligence_report")
    def test_sitemap_view_renders_topic_intelligence_before_technical_snapshot(
        self, mock_build_report
    ):
        mock_build_report.return_value = {
            "url": "https://example.com",
            "topic_intelligence": build_topic_intelligence(
                url="https://example.com/seo-audit-guide",
                page_title="How to Run an SEO Audit",
                meta_title="How to Run an SEO Audit",
                meta_description="Learn how to run an SEO audit with a practical guide.",
                h1="How to Run an SEO Audit",
                content_text="This guide explains how to run an SEO audit and improve technical SEO performance.",
                word_count=640,
            ),
            "robots_status": "Available",
            "sitemap_status": "Available",
            "discovered_sitemap": "https://example.com/sitemap.xml",
            "checked_endpoints": [
                "https://example.com/robots.txt",
                "https://example.com/sitemap.xml",
            ],
        }

        response = self.client.post(
            reverse("seo_analyzer:sitemap"),
            {"url": "https://example.com"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Primary SEO Topic Intelligence")
        self.assertContains(response, "Sitemap Technical Snapshot")
        html = response.content.decode("utf-8")
        self.assertLess(
            html.index("Primary SEO Topic Intelligence"),
            html.index("Sitemap Technical Snapshot"),
        )


class URLIntelligenceServiceTests(TestCase):
    def _html(self, *, canonical_url=None, meta_robots="", body="URL body copy"):
        canonical_markup = (
            f'<link rel="canonical" href="{canonical_url}">' if canonical_url else ""
        )
        robots_markup = (
            f'<meta name="robots" content="{meta_robots}">' if meta_robots else ""
        )
        return (
            "<html><head>"
            f"{canonical_markup}"
            f"{robots_markup}"
            "<title>URL Intelligence Test</title>"
            "</head><body>"
            f"<h1>{body}</h1>"
            "</body></html>"
        )

    def _response(self, url, *, status_code=200, html=None, history=None, headers=None):
        payload = html or self._html(canonical_url=url)
        base_headers = {"Content-Type": "text/html; charset=utf-8"}
        if headers:
            base_headers.update(headers)
        return FakeResponse(
            url=url,
            status_code=status_code,
            headers=base_headers,
            text=payload,
            history=history or [],
        )

    def _create_url_report_via_view(
        self,
        mock_build_session,
        url,
        *,
        canonical_url="__same__",
        status_code=200,
        target_keyword="",
        headers=None,
    ):
        resolved_canonical = url if canonical_url == "__same__" else canonical_url
        session = URLIntelligenceSession(
            responses={
                url: self._response(
                    url,
                    status_code=status_code,
                    html=self._html(canonical_url=resolved_canonical),
                    headers=headers,
                )
            }
        )
        mock_build_session.return_value = session
        response = self.client.post(
            reverse("seo_analyzer:url_intelligence"),
            {"url": url, "target_keyword": target_keyword},
            follow=True,
        )
        task = URLIntelligenceTask.objects.latest("created_at")
        return response, task, task.result

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_clean_seo_friendly_url(self, mock_build_session):
        session = URLIntelligenceSession(
            responses={
                "https://example.com/digital-marketing/": self._response(
                    "https://example.com/digital-marketing/",
                    html=self._html(canonical_url="https://example.com/digital-marketing/"),
                )
            }
        )
        mock_build_session.return_value = session

        report = analyze_url("https://example.com/digital-marketing/")

        self.assertEqual(report["canonical_status"], "self")
        self.assertEqual(report["indexability_status"], "indexable")
        self.assertGreaterEqual(report["health_score"], 85)
        self.assertEqual(report["optimized_url_payload"]["status"], "no_change")

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_root_homepage_does_not_receive_slug_penalty(self, mock_build_session):
        url = "https://example.com/"
        session = URLIntelligenceSession(
            responses={url: self._response(url, html=self._html(canonical_url=url))}
        )
        mock_build_session.return_value = session

        report = analyze_url(url)

        self.assertTrue(report["is_root_homepage"])
        self.assertEqual(report["slug_clarity"], "not_applicable")
        self.assertEqual(report["seo_friendliness_score"], 100)
        self.assertIsNone(report["keyword_relevance_score"])

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_root_homepage_without_trailing_slash_is_detected_consistently(self, mock_build_session):
        input_url = "https://example.com"
        response_url = "https://example.com/"
        session = URLIntelligenceSession(
            responses={input_url: self._response(response_url, html=self._html(canonical_url=response_url))}
        )
        mock_build_session.return_value = session

        report = analyze_url(input_url)

        self.assertTrue(report["is_root_homepage"])
        self.assertEqual(report["seo_friendliness_score"], 100)

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_www_root_homepage_is_not_penalized_for_missing_slug(self, mock_build_session):
        url = "https://www.example.com/"
        session = URLIntelligenceSession(
            responses={url: self._response(url, html=self._html(canonical_url=url))}
        )
        mock_build_session.return_value = session

        report = analyze_url(url)

        self.assertTrue(report["is_root_homepage"])
        self.assertEqual(report["seo_friendliness_score"], 100)

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_subdomain_root_homepage_is_not_penalized_for_missing_slug(self, mock_build_session):
        url = "https://blog.example.com/"
        session = URLIntelligenceSession(
            responses={url: self._response(url, html=self._html(canonical_url=url))}
        )
        mock_build_session.return_value = session

        report = analyze_url(url)

        self.assertTrue(report["is_root_homepage"])
        self.assertEqual(report["seo_friendliness_score"], 100)

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_non_homepage_slug_scoring_still_applies(self, mock_build_session):
        url = "https://example.com/about/"
        session = URLIntelligenceSession(
            responses={url: self._response(url, html=self._html(canonical_url=url))}
        )
        mock_build_session.return_value = session

        report = analyze_url(url)

        self.assertFalse(report["is_root_homepage"])
        self.assertEqual(report["slug_clarity"], "fair")
        self.assertLess(report["seo_friendliness_score"], 100)

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_homepage_target_keyword_is_not_used_as_slug_penalty(self, mock_build_session):
        url = "https://example.com/"
        session = URLIntelligenceSession(
            responses={url: self._response(url, html=self._html(canonical_url=url))}
        )
        mock_build_session.return_value = session

        report = analyze_url(url, target_keyword="digital marketing")
        keyword_check = next(check for check in report["quality_checks"] if check["label"] == "Target Keyword")

        self.assertTrue(report["is_root_homepage"])
        self.assertEqual(report["keyword_match_status"], "not_applicable")
        self.assertIsNone(report["keyword_relevance_score"])
        self.assertEqual(report["seo_friendliness_score"], 100)
        self.assertEqual(keyword_check["status"], "INFO")

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_http_url_is_flagged_as_non_https(self, mock_build_session):
        session = URLIntelligenceSession(
            responses={
                "http://example.com/digital-marketing/": self._response(
                    "http://example.com/digital-marketing/",
                    html=self._html(canonical_url="http://example.com/digital-marketing/"),
                )
            }
        )
        mock_build_session.return_value = session

        report = analyze_url("http://example.com/digital-marketing/")

        self.assertFalse(report["https_status"])
        self.assertIn("Non-HTTPS URL", {issue["name"] for issue in report["issues"]})

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_homepage_http_still_affects_real_scores(self, mock_build_session):
        url = "http://example.com/"
        session = URLIntelligenceSession(
            responses={url: self._response(url, html=self._html(canonical_url=url))}
        )
        mock_build_session.return_value = session

        report = analyze_url(url)

        self.assertTrue(report["is_root_homepage"])
        self.assertLess(report["technical_score"], 100)
        self.assertIn("Non-HTTPS URL", {issue["name"] for issue in report["issues"]})

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_redirecting_url_tracks_final_destination(self, mock_build_session):
        history = [FakeResponse("https://example.com/old-page", status_code=301)]
        session = URLIntelligenceSession(
            responses={
                "https://example.com/old-page": self._response(
                    "https://example.com/new-page/",
                    html=self._html(canonical_url="https://example.com/new-page/"),
                    history=history,
                )
            }
        )
        mock_build_session.return_value = session

        report = analyze_url("https://example.com/old-page")

        self.assertTrue(report["redirect_detected"])
        self.assertEqual(report["redirect_count"], 1)
        self.assertEqual(report["final_url"], "https://example.com/new-page/")
        self.assertEqual(report["indexability_status"], "redirected")

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_url_with_uppercase_characters_is_detected(self, mock_build_session):
        session = URLIntelligenceSession(
            responses={
                "https://example.com/ProductPage/": self._response(
                    "https://example.com/ProductPage/",
                    html=self._html(canonical_url="https://example.com/ProductPage/"),
                )
            }
        )
        mock_build_session.return_value = session

        report = analyze_url("https://example.com/ProductPage/")

        self.assertTrue(report["has_uppercase"])
        self.assertIn("Uppercase Characters Detected", {issue["name"] for issue in report["issues"]})

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_url_with_underscores_is_detected(self, mock_build_session):
        session = URLIntelligenceSession(
            responses={
                "https://example.com/product_page/": self._response(
                    "https://example.com/product_page/",
                    html=self._html(canonical_url="https://example.com/product_page/"),
                )
            }
        )
        mock_build_session.return_value = session

        report = analyze_url("https://example.com/product_page/")

        self.assertTrue(report["has_underscores"])
        self.assertIn("Underscores Detected", {issue["name"] for issue in report["issues"]})

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_tracking_parameters_are_classified_separately(self, mock_build_session):
        url = "https://example.com/product/?utm_source=google&utm_campaign=summer"
        session = URLIntelligenceSession(
            responses={url: self._response(url, html=self._html(canonical_url=url))}
        )
        mock_build_session.return_value = session

        report = analyze_url(url)

        self.assertEqual(report["tracking_params_count"], 2)
        self.assertEqual(report["functional_params_count"], 0)
        self.assertEqual(report["unnecessary_params_count"], 0)

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_google_ads_tracking_parameters_are_all_classified_as_tracking(self, mock_build_session):
        url = (
            "https://example.com/article/?gclid=abc123&gbraid=test123&wbraid=test456"
            "&gad_source=1&gad_campaignid=1061187028"
        )
        canonical_url = "https://example.com/article/"
        session = URLIntelligenceSession(
            responses={url: self._response(url, html=self._html(canonical_url=canonical_url))}
        )
        mock_build_session.return_value = session

        report = analyze_url(url)
        tracking_keys = {item["key"] for item in report["parameters_payload"]["tracking"]}

        self.assertEqual(report["tracking_params_count"], 5)
        self.assertEqual(report["functional_params_count"], 0)
        self.assertEqual(report["unnecessary_params_count"], 0)
        self.assertSetEqual(
            tracking_keys,
            {"gclid", "gbraid", "wbraid", "gad_source", "gad_campaignid"},
        )

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_necessary_query_parameters_are_not_marked_as_tracking(self, mock_build_session):
        url = "https://example.com/products/?page=2&sort=asc"
        session = URLIntelligenceSession(
            responses={url: self._response(url, html=self._html(canonical_url=url))}
        )
        mock_build_session.return_value = session

        report = analyze_url(url)

        self.assertEqual(report["functional_params_count"], 2)
        self.assertEqual(report["tracking_params_count"], 0)

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_unknown_parameter_still_uses_review_needed(self, mock_build_session):
        url = "https://example.com/article/?custom_parameter=abc"
        session = URLIntelligenceSession(
            responses={url: self._response(url, html=self._html(canonical_url=url))}
        )
        mock_build_session.return_value = session

        report = analyze_url(url)

        self.assertEqual(report["tracking_params_count"], 0)
        self.assertEqual(report["functional_params_count"], 0)
        self.assertEqual(report["unnecessary_params_count"], 1)
        self.assertIn("Potentially Unnecessary Parameters", {issue["name"] for issue in report["issues"]})

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_unknown_parameter_requires_developer_validation_not_safe_optimization(self, mock_build_session):
        url = "https://example.com/article?custom_parameter=abc"
        session = URLIntelligenceSession(
            responses={url: self._response(url, status_code=404, html=self._html(canonical_url=None))}
        )
        mock_build_session.return_value = session

        report = analyze_url(url)
        recommendation_problems = {item["problem"] for item in report["recommendations"]}

        self.assertEqual(report["http_status_code"], 404)
        self.assertEqual(report["access_status"], "not_found")
        self.assertEqual(report["indexability_status"], "not_found")
        self.assertEqual(report["canonical_status"], "not_evaluated")
        self.assertEqual(report["unnecessary_params_count"], 1)
        self.assertEqual(report["optimized_url_payload"]["status"], "developer_validation_required")
        self.assertEqual(report["optimized_url_payload"]["suggested_url"], "")
        self.assertFalse(report["optimized_url_payload"]["migration_warning"])
        self.assertIn("could not be confidently determined", report["optimized_url_payload"]["message"])
        self.assertNotIn("URL structure optimization opportunity", recommendation_problems)

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_unknown_parameter_is_not_silently_removed_from_safe_candidate(self, mock_build_session):
        url = "https://example.com/article?custom_parameter=abc"
        session = URLIntelligenceSession(
            responses={url: self._response(url, html=self._html(canonical_url=url))}
        )
        mock_build_session.return_value = session

        report = analyze_url(url)

        self.assertEqual(report["optimized_url_payload"]["status"], "developer_validation_required")
        self.assertEqual(report["optimized_url_payload"]["suggested_url"], "")

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_homepage_with_tracking_parameters_still_loses_seo_friendly_points(self, mock_build_session):
        url = "https://example.com/?utm_source=google"
        session = URLIntelligenceSession(
            responses={url: self._response(url, html=self._html(canonical_url=url))}
        )
        mock_build_session.return_value = session

        report = analyze_url(url)

        self.assertTrue(report["is_root_homepage"])
        self.assertEqual(report["tracking_params_count"], 1)
        self.assertLess(report["seo_friendliness_score"], 100)

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_tracking_only_query_does_not_trigger_dynamic_url_pattern(self, mock_build_session):
        url = "https://example.com/article/?gclid=123&utm_source=google"
        canonical_url = "https://example.com/article/"
        session = URLIntelligenceSession(
            responses={url: self._response(url, html=self._html(canonical_url=canonical_url))}
        )
        mock_build_session.return_value = session

        report = analyze_url(url)

        self.assertFalse(report["dynamic_url_detected"])
        self.assertNotIn("Dynamic URL Pattern Detected", {issue["name"] for issue in report["issues"]})

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_real_dynamic_url_with_functional_parameter_is_still_detected(self, mock_build_session):
        url = "https://example.com/product?id=12345"
        session = URLIntelligenceSession(
            responses={url: self._response(url, html=self._html(canonical_url=url))}
        )
        mock_build_session.return_value = session

        report = analyze_url(url)

        self.assertTrue(report["dynamic_url_detected"])
        self.assertIn("Dynamic URL Pattern Detected", {issue["name"] for issue in report["issues"]})

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_tracking_cleanup_uses_clean_url_recommendation_without_migration_warning(
        self, mock_build_session
    ):
        url = "https://example.com/article/?gclid=123"
        clean_url = "https://example.com/article/"
        session = URLIntelligenceSession(
            responses={url: self._response(url, html=self._html(canonical_url=clean_url))}
        )
        mock_build_session.return_value = session

        report = analyze_url(url)
        optimization_recommendations = [
            item
            for item in report["recommendations"]
            if item["problem"] == "URL structure optimization opportunity"
        ]

        self.assertEqual(report["optimized_url_payload"]["status"], "clean_url")
        self.assertEqual(report["optimized_url_payload"]["suggested_url"], clean_url)
        self.assertFalse(report["optimized_url_payload"]["migration_warning"])
        self.assertEqual(len(optimization_recommendations), 0)

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_functional_parameter_is_not_silently_removed_as_tracking_cleanup(self, mock_build_session):
        url = "https://example.com/products?category=shoes"
        session = URLIntelligenceSession(
            responses={url: self._response(url, html=self._html(canonical_url=url))}
        )
        mock_build_session.return_value = session

        report = analyze_url(url)

        self.assertEqual(report["functional_params_count"], 1)
        self.assertEqual(report["optimized_url_payload"]["status"], "no_change")
        self.assertNotEqual(report["optimized_url_payload"]["status"], "clean_url")
        self.assertEqual(report["optimized_url_payload"]["suggested_url"], "")

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_tracking_plus_unknown_removes_only_tracking_parameter(self, mock_build_session):
        url = "https://example.com/article?gclid=123&custom_parameter=abc"
        expected_candidate = "https://example.com/article/?custom_parameter=abc"
        session = URLIntelligenceSession(
            responses={url: self._response(url, html=self._html(canonical_url=expected_candidate))}
        )
        mock_build_session.return_value = session

        report = analyze_url(url)

        self.assertEqual(report["tracking_params_count"], 1)
        self.assertEqual(report["unnecessary_params_count"], 1)
        self.assertEqual(report["optimized_url_payload"]["status"], "clean_url")
        self.assertEqual(report["optimized_url_payload"]["suggested_url"], expected_candidate)
        self.assertFalse(report["optimized_url_payload"]["migration_warning"])
        self.assertNotIn("gclid=", report["optimized_url_payload"]["suggested_url"])
        self.assertIn("custom_parameter=abc", report["optimized_url_payload"]["suggested_url"])

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_tracking_plus_functional_removes_only_tracking_parameter(self, mock_build_session):
        url = "https://example.com/search?q=seo&gclid=123"
        expected_candidate = "https://example.com/search/?q=seo"
        session = URLIntelligenceSession(
            responses={url: self._response(url, html=self._html(canonical_url=expected_candidate))}
        )
        mock_build_session.return_value = session

        report = analyze_url(url)

        self.assertEqual(report["tracking_params_count"], 1)
        self.assertEqual(report["functional_params_count"], 1)
        self.assertEqual(report["optimized_url_payload"]["status"], "clean_url")
        self.assertEqual(report["optimized_url_payload"]["suggested_url"], expected_candidate)
        self.assertFalse(report["optimized_url_payload"]["migration_warning"])
        self.assertIn("q=seo", report["optimized_url_payload"]["suggested_url"])
        self.assertNotIn("gclid=", report["optimized_url_payload"]["suggested_url"])

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_long_url_is_flagged(self, mock_build_session):
        slug = "very-long-seo-friendly-page-title-" * 4
        url = f"https://example.com/{slug}/"
        session = URLIntelligenceSession(
            responses={url: self._response(url, html=self._html(canonical_url=url))}
        )
        mock_build_session.return_value = session

        report = analyze_url(url)

        self.assertGreater(report["url_length"], 75)
        self.assertIn("URL Too Long", {issue["name"] for issue in report["issues"]})

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_long_url_caused_by_tracking_parameters_gets_contextual_length_guidance(self, mock_build_session):
        url = (
            "https://example.com/blog/global-seo-strategies-for-international-success/"
            "?gclid=abc123&utm_source=google&utm_campaign=summer"
        )
        clean_url = "https://example.com/blog/global-seo-strategies-for-international-success/"
        session = URLIntelligenceSession(
            responses={url: self._response(url, html=self._html(canonical_url=clean_url))}
        )
        mock_build_session.return_value = session

        report = analyze_url(url)
        length_issue = next(issue for issue in report["issues"] if issue["name"] == "URL Too Long")

        self.assertGreater(report["url_length"], 75)
        self.assertIn("base URL is already concise", length_issue["recommended_fix"])
        self.assertIn("tracking parameters", length_issue["recommended_fix"])

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_descriptive_slug_with_numeric_prefix_requires_validation_not_numeric_heavy(
        self, mock_build_session
    ):
        url = "https://paraland.tn/2612-doppel-herz-aktiv-a-z-action-durable-30-comprimes.html"
        session = URLIntelligenceSession(
            responses={url: self._response(url, html=self._html(canonical_url=url))}
        )
        mock_build_session.return_value = session

        report = analyze_url(url)
        issue_names = {issue["name"] for issue in report["issues"]}

        self.assertTrue(report["numeric_id_prefix_detected"])
        self.assertFalse(report["numeric_slug_detected"])
        self.assertIn("Numeric ID Prefix Detected", issue_names)
        self.assertNotIn("Numeric-Heavy Slug Detected", issue_names)
        self.assertEqual(report["optimized_url_payload"]["status"], "requires_validation")
        self.assertTrue(report["optimized_url_payload"]["suggested_url"])
        self.assertNotEqual(
            report["optimized_url_payload"]["message"],
            "No structural URL change is necessary.",
        )
        self.assertTrue(report["optimized_url_payload"]["migration_warning"])

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_numeric_only_slug_is_numeric_heavy(self, mock_build_session):
        url = "https://example.com/123456789/"
        session = URLIntelligenceSession(
            responses={url: self._response(url, html=self._html(canonical_url=url))}
        )
        mock_build_session.return_value = session

        report = analyze_url(url)

        self.assertTrue(report["numeric_slug_detected"])
        self.assertIn("Numeric-Heavy Slug Detected", {issue["name"] for issue in report["issues"]})

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_product_slug_with_large_numeric_suffix_is_numeric_heavy(self, mock_build_session):
        url = "https://example.com/product-928374928374/"
        session = URLIntelligenceSession(
            responses={url: self._response(url, html=self._html(canonical_url=url))}
        )
        mock_build_session.return_value = session

        report = analyze_url(url)

        self.assertTrue(report["numeric_slug_detected"])
        self.assertIn("Numeric-Heavy Slug Detected", {issue["name"] for issue in report["issues"]})

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_descriptive_slug_with_model_number_is_not_numeric_heavy(self, mock_build_session):
        url = "https://example.com/iphone-16-pro/"
        session = URLIntelligenceSession(
            responses={url: self._response(url, html=self._html(canonical_url=url))}
        )
        mock_build_session.return_value = session

        report = analyze_url(url)

        self.assertFalse(report["numeric_slug_detected"])

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_descriptive_year_slug_is_not_numeric_heavy(self, mock_build_session):
        url = "https://example.com/seo-trends-2026/"
        session = URLIntelligenceSession(
            responses={url: self._response(url, html=self._html(canonical_url=url))}
        )
        mock_build_session.return_value = session

        report = analyze_url(url)

        self.assertFalse(report["numeric_slug_detected"])

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_short_word_with_single_digit_suffix_is_not_numeric_heavy_or_actionable(self, mock_build_session):
        url = "https://www.linternaute.fr/dictionnaire/fr/definition/de-1/"
        session = URLIntelligenceSession(
            responses={url: self._response(url, html=self._html(canonical_url=url))}
        )
        mock_build_session.return_value = session

        report = analyze_url(url)
        issue_names = {issue["name"] for issue in report["issues"]}
        check_labels = {check["label"] for check in report["quality_checks"]}

        self.assertFalse(report["numeric_slug_detected"])
        self.assertFalse(report["numeric_id_prefix_detected"])
        self.assertNotIn("Numeric-Heavy Slug Detected", issue_names)
        self.assertNotIn("Numeric ID Prefix Detected", issue_names)
        self.assertNotIn("Numeric Slug Pattern", check_labels)
        self.assertEqual(report["optimized_url_payload"]["status"], "no_change")
        self.assertEqual(report["optimized_url_payload"]["suggested_url"], "")
        self.assertEqual(report["optimized_url_payload"]["migration_warning"], "")
        self.assertEqual(report["recommendations"], [])

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_iphone_15_slug_is_not_numeric_heavy(self, mock_build_session):
        url = "https://example.com/iphone-15/"
        session = URLIntelligenceSession(
            responses={url: self._response(url, html=self._html(canonical_url=url))}
        )
        mock_build_session.return_value = session

        report = analyze_url(url)

        self.assertFalse(report["numeric_slug_detected"])

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_covid_19_slug_is_not_numeric_heavy(self, mock_build_session):
        url = "https://example.com/covid-19/"
        session = URLIntelligenceSession(
            responses={url: self._response(url, html=self._html(canonical_url=url))}
        )
        mock_build_session.return_value = session

        report = analyze_url(url)

        self.assertFalse(report["numeric_slug_detected"])

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_formula_1_slug_is_not_numeric_heavy(self, mock_build_session):
        url = "https://example.com/formula-1/"
        session = URLIntelligenceSession(
            responses={url: self._response(url, html=self._html(canonical_url=url))}
        )
        mock_build_session.return_value = session

        report = analyze_url(url)

        self.assertFalse(report["numeric_slug_detected"])

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_logical_dictionary_hierarchy_is_not_flagged_as_deep_issue(self, mock_build_session):
        url = "https://dictionary.cambridge.org/fr/dictionnaire/anglais/ya"
        session = URLIntelligenceSession(
            responses={url: self._response(url, html=self._html(canonical_url=url))}
        )
        mock_build_session.return_value = session

        report = analyze_url(url)
        depth_check = next(check for check in report["quality_checks"] if check["label"] == "URL Depth")

        self.assertEqual(report["url_depth"], 4)
        self.assertEqual(report["depth_classification"], "deep_but_logical")
        self.assertIn(depth_check["status"], {"PASS", "INFO"})
        self.assertNotIn("Deep URL Structure", {issue["name"] for issue in report["issues"]})
        self.assertEqual(report["optimized_url_payload"]["status"], "no_change")

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_logical_documentation_hierarchy_is_not_flagged_as_deep_issue(self, mock_build_session):
        url = "https://example.com/en/docs/api/authentication"
        session = URLIntelligenceSession(
            responses={url: self._response(url, html=self._html(canonical_url=url))}
        )
        mock_build_session.return_value = session

        report = analyze_url(url)

        self.assertEqual(report["url_depth"], 4)
        self.assertFalse(report["depth_issue_detected"])
        self.assertNotIn("Deep URL Structure", {issue["name"] for issue in report["issues"]})

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_logical_ecommerce_hierarchy_is_not_flagged_as_deep_issue(self, mock_build_session):
        url = "https://example.com/shop/women/shoes/running"
        session = URLIntelligenceSession(
            responses={url: self._response(url, html=self._html(canonical_url=url))}
        )
        mock_build_session.return_value = session

        report = analyze_url(url)

        self.assertEqual(report["url_depth"], 4)
        self.assertFalse(report["depth_issue_detected"])
        self.assertNotIn("Deep URL Structure", {issue["name"] for issue in report["issues"]})

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_single_character_chain_is_flagged_as_excessive_depth(self, mock_build_session):
        url = "https://example.com/a/b/c/d/e/f/g/"
        session = URLIntelligenceSession(
            responses={url: self._response(url, html=self._html(canonical_url=url))}
        )
        mock_build_session.return_value = session

        report = analyze_url(url)

        self.assertEqual(report["depth_classification"], "excessive")
        self.assertTrue(report["depth_issue_detected"])
        self.assertIn("Deep URL Structure", {issue["name"] for issue in report["issues"]})

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_generated_archive_hierarchy_is_flagged_and_requires_optimization(self, mock_build_session):
        url = "https://example.com/category/subcategory/archive/2024/12/page/item"
        session = URLIntelligenceSession(
            responses={url: self._response(url, html=self._html(canonical_url=url))}
        )
        mock_build_session.return_value = session

        report = analyze_url(url)

        self.assertTrue(report["depth_issue_detected"])
        self.assertIn("Deep URL Structure", {issue["name"] for issue in report["issues"]})
        self.assertNotEqual(report["optimized_url_payload"]["status"], "no_change")
        self.assertTrue(report["optimized_url_payload"]["requires_validation"])

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_numeric_path_chain_can_trigger_depth_issue(self, mock_build_session):
        url = "https://example.com/product/12345/67890/99999"
        session = URLIntelligenceSession(
            responses={url: self._response(url, html=self._html(canonical_url=url))}
        )
        mock_build_session.return_value = session

        report = analyze_url(url)

        self.assertTrue(report["depth_issue_detected"])
        self.assertIn("Deep URL Structure", {issue["name"] for issue in report["issues"]})

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_meaningful_depth_five_hierarchy_can_remain_informational(self, mock_build_session):
        url = "https://example.com/us/california/san-francisco/hotels/boutique"
        session = URLIntelligenceSession(
            responses={url: self._response(url, html=self._html(canonical_url=url))}
        )
        mock_build_session.return_value = session

        report = analyze_url(url)
        depth_check = next(check for check in report["quality_checks"] if check["label"] == "URL Depth")

        self.assertEqual(report["url_depth"], 5)
        self.assertFalse(report["depth_issue_detected"])
        self.assertEqual(depth_check["status"], "INFO")
        self.assertEqual(report["optimized_url_payload"]["status"], "no_change")

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_canonical_mismatch_is_detected(self, mock_build_session):
        history = [FakeResponse("https://example.com/legacy-page", status_code=301)]
        session = URLIntelligenceSession(
            responses={
                "https://example.com/legacy-page": self._response(
                    "https://example.com/new-page/",
                    html=self._html(canonical_url="https://example.com/legacy-page"),
                    history=history,
                )
            }
        )
        mock_build_session.return_value = session

        report = analyze_url("https://example.com/legacy-page")

        self.assertEqual(report["canonical_status"], "conflict")
        self.assertIn("Canonical Conflict", {issue["name"] for issue in report["issues"]})

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_tracking_variant_canonical_to_clean_url_is_not_flagged_as_problem(self, mock_build_session):
        url = "https://example.com/article/?gclid=123"
        canonical_url = "https://example.com/article/"
        session = URLIntelligenceSession(
            responses={url: self._response(url, html=self._html(canonical_url=canonical_url))}
        )
        mock_build_session.return_value = session

        report = analyze_url(url)
        issue_names = {issue["name"] for issue in report["issues"]}
        canonical_check = next(check for check in report["quality_checks"] if check["label"] == "Canonical")

        self.assertEqual(report["canonical_status"], "other")
        self.assertTrue(report["canonical_to_clean_url"])
        self.assertNotIn("Canonical Points to Another URL", issue_names)
        self.assertEqual(canonical_check["status"], "PASS")
        self.assertIn("clean preferred url", canonical_check["finding"].lower())

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_real_canonical_difference_still_reports_other(self, mock_build_session):
        url = "https://example.com/page-a/"
        canonical_url = "https://example.com/page-b/"
        session = URLIntelligenceSession(
            responses={url: self._response(url, html=self._html(canonical_url=canonical_url))}
        )
        mock_build_session.return_value = session

        report = analyze_url(url)

        self.assertEqual(report["canonical_status"], "other")
        self.assertFalse(report["canonical_to_clean_url"])
        self.assertIn("Canonical Points to Another URL", {issue["name"] for issue in report["issues"]})

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_srsltid_tracking_variant_uses_clean_canonical_behavior(self, mock_build_session):
        url = (
            "https://parapharmacie.tn/shop/hygiene/hygiene-intime/"
            "coupe-menstruelle-liberty-cup-taille-1/"
            "?srsltid=AfmBOorzNgWE0sXLjR_epAD84m88_i3l1nqOKKPzUFNrKhAuMaRq5hyT"
        )
        canonical_url = (
            "https://parapharmacie.tn/shop/hygiene/hygiene-intime/"
            "coupe-menstruelle-liberty-cup-taille-1/"
        )
        session = URLIntelligenceSession(
            responses={url: self._response(url, html=self._html(canonical_url=canonical_url))}
        )
        mock_build_session.return_value = session

        report = analyze_url(url)
        issue_names = {issue["name"] for issue in report["issues"]}
        recommendation_problems = {item["problem"] for item in report["recommendations"]}
        canonical_check = next(check for check in report["quality_checks"] if check["label"] == "Canonical")

        self.assertEqual(report["tracking_params_count"], 1)
        self.assertEqual(report["unnecessary_params_count"], 0)
        self.assertEqual(report["parameters_payload"]["tracking"][0]["key"], "srsltid")
        self.assertTrue(report["tracking_only_query"])
        self.assertTrue(report["canonical_to_clean_url"])
        self.assertEqual(report["canonical_status"], "other")
        self.assertEqual(float(report["canonical_score"]), 100.0)
        self.assertFalse(report["dynamic_url_detected"])
        self.assertEqual(report["optimized_url_payload"]["status"], "clean_url")
        self.assertEqual(report["optimized_url_payload"]["suggested_url"], canonical_url)
        self.assertFalse(report["optimized_url_payload"]["migration_warning"])
        self.assertEqual(canonical_check["status"], "PASS")
        self.assertNotIn("Potentially Unnecessary Parameters", issue_names)
        self.assertNotIn("Dynamic URL Pattern Detected", issue_names)
        self.assertNotIn("Canonical Points to Another URL", issue_names)
        self.assertNotIn("Canonical Points to Another URL", recommendation_problems)
        self.assertNotIn("URL structure optimization opportunity", recommendation_problems)

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_noindex_url_is_detected(self, mock_build_session):
        url = "https://example.com/private-page/"
        session = URLIntelligenceSession(
            responses={
                url: self._response(
                    url,
                    html=self._html(canonical_url=url, meta_robots="noindex, nofollow"),
                )
            }
        )
        mock_build_session.return_value = session

        report = analyze_url(url)

        self.assertEqual(report["indexability_status"], "noindex")
        self.assertIn("URL Is Not Indexable", {issue["name"] for issue in report["issues"]})

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_access_restricted_403_is_not_treated_as_canonical_missing_or_index_error(self, mock_build_session):
        url = "https://example.com/restricted-page/"
        session = URLIntelligenceSession(
            responses={url: self._response(url, status_code=403, html=self._html(canonical_url=None))}
        )
        mock_build_session.return_value = session

        report = analyze_url(url)
        issue_names = {issue["name"] for issue in report["issues"]}
        recommendation_problems = {item["problem"] for item in report["recommendations"]}
        canonical_check = next(check for check in report["quality_checks"] if check["label"] == "Canonical")
        indexability_check = next(check for check in report["quality_checks"] if check["label"] == "Indexability")

        self.assertEqual(report["http_status_code"], 403)
        self.assertEqual(report["access_status"], "access_restricted")
        self.assertEqual(report["canonical_status"], "not_evaluated")
        self.assertEqual(report["indexability_status"], "not_evaluated_access_restricted")
        self.assertIn("Access Restricted", issue_names)
        self.assertNotIn("Canonical Missing", issue_names)
        self.assertNotIn("Canonical Missing", recommendation_problems)
        self.assertEqual(canonical_check["status"], "INFO")
        self.assertEqual(indexability_check["status"], "INFO")
        self.assertEqual(report["optimized_url_payload"]["status"], "no_change")

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_auth_required_401_is_not_evaluated(self, mock_build_session):
        url = "https://example.com/private-page/"
        session = URLIntelligenceSession(
            responses={url: self._response(url, status_code=401, html=self._html(canonical_url=None))}
        )
        mock_build_session.return_value = session

        report = analyze_url(url)

        self.assertEqual(report["access_status"], "auth_required")
        self.assertEqual(report["canonical_status"], "not_evaluated")
        self.assertEqual(report["indexability_status"], "not_evaluated_auth_required")
        self.assertIn("Authentication Required", {issue["name"] for issue in report["issues"]})

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_rate_limited_429_is_not_treated_as_permanent_failure(self, mock_build_session):
        url = "https://example.com/rate-limited-page/"
        session = URLIntelligenceSession(
            responses={url: self._response(url, status_code=429, html=self._html(canonical_url=None))}
        )
        mock_build_session.return_value = session

        report = analyze_url(url)
        issue_names = {issue["name"] for issue in report["issues"]}

        self.assertEqual(report["access_status"], "rate_limited")
        self.assertEqual(report["canonical_status"], "not_evaluated")
        self.assertEqual(report["indexability_status"], "not_evaluated_rate_limited")
        self.assertIn("Rate Limited", issue_names)
        self.assertNotIn("URL Returned an Error Status", issue_names)

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_not_found_url_is_detected_as_real_error(self, mock_build_session):
        url = "https://example.com/missing-page/"
        session = URLIntelligenceSession(
            responses={url: self._response(url, status_code=404, html=self._html())}
        )
        mock_build_session.return_value = session

        report = analyze_url(url)

        self.assertEqual(report["canonical_status"], "not_evaluated")
        self.assertEqual(report["indexability_status"], "not_found")
        self.assertIn("URL Not Found", {issue["name"] for issue in report["issues"]})

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_gone_url_is_detected_as_not_indexable(self, mock_build_session):
        url = "https://example.com/removed-page/"
        session = URLIntelligenceSession(
            responses={url: self._response(url, status_code=410, html=self._html())}
        )
        mock_build_session.return_value = session

        report = analyze_url(url)

        self.assertEqual(report["canonical_status"], "not_evaluated")
        self.assertEqual(report["indexability_status"], "gone")
        self.assertIn("URL Permanently Gone", {issue["name"] for issue in report["issues"]})

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_server_error_500_is_detected_without_canonical_false_positive(self, mock_build_session):
        url = "https://example.com/server-error/"
        session = URLIntelligenceSession(
            responses={url: self._response(url, status_code=500, html=self._html(canonical_url=None))}
        )
        mock_build_session.return_value = session

        report = analyze_url(url)
        issue_names = {issue["name"] for issue in report["issues"]}

        self.assertEqual(report["canonical_status"], "not_evaluated")
        self.assertEqual(report["indexability_status"], "server_error")
        self.assertIn("Server Error", issue_names)
        self.assertNotIn("Canonical Missing", issue_names)

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_accessible_page_without_canonical_still_reports_missing(self, mock_build_session):
        url = "https://example.com/no-canonical/"
        session = URLIntelligenceSession(
            responses={url: self._response(url, html=self._html(canonical_url=None))}
        )
        mock_build_session.return_value = session

        report = analyze_url(url)

        self.assertTrue(report["canonical_evaluated"])
        self.assertEqual(report["canonical_status"], "missing")
        self.assertIn("Canonical Missing", {issue["name"] for issue in report["issues"]})

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_accessible_page_with_canonical_still_reports_self(self, mock_build_session):
        url = "https://example.com/self-canonical/"
        session = URLIntelligenceSession(
            responses={url: self._response(url, html=self._html(canonical_url=url))}
        )
        mock_build_session.return_value = session

        report = analyze_url(url)

        self.assertTrue(report["canonical_evaluated"])
        self.assertEqual(report["canonical_status"], "self")

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_403_clean_structure_does_not_trigger_structural_optimization(self, mock_build_session):
        url = "https://example.com/clean-url/"
        session = URLIntelligenceSession(
            responses={url: self._response(url, status_code=403, html=self._html(canonical_url=None))}
        )
        mock_build_session.return_value = session

        report = analyze_url(url)

        self.assertEqual(report["optimized_url_payload"]["status"], "no_change")
        self.assertEqual(
            report["optimized_url_payload"]["message"],
            "No structural URL change is necessary.",
        )

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_403_with_independent_structural_issue_keeps_findings_separate(self, mock_build_session):
        url = "https://example.com/Product_Page/"
        session = URLIntelligenceSession(
            responses={url: self._response(url, status_code=403, html=self._html(canonical_url=None))}
        )
        mock_build_session.return_value = session

        report = analyze_url(url)
        issue_names = {issue["name"] for issue in report["issues"]}

        self.assertIn("Access Restricted", issue_names)
        self.assertIn("Uppercase Characters Detected", issue_names)
        self.assertIn("Underscores Detected", issue_names)
        self.assertNotIn("Canonical Missing", issue_names)
        self.assertNotEqual(report["optimized_url_payload"]["status"], "no_change")

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_target_keyword_match_is_scored(self, mock_build_session):
        url = "https://example.com/digital-marketing-services/"
        session = URLIntelligenceSession(
            responses={url: self._response(url, html=self._html(canonical_url=url))}
        )
        mock_build_session.return_value = session

        report = analyze_url(url, target_keyword="digital marketing")

        self.assertEqual(report["keyword_match_status"], "yes")
        self.assertEqual(report["keyword_relevance_score"], 100)

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_missing_target_keyword_does_not_invent_keyword_scoring(self, mock_build_session):
        url = "https://example.com/about-us/"
        session = URLIntelligenceSession(
            responses={url: self._response(url, html=self._html(canonical_url=url))}
        )
        mock_build_session.return_value = session

        report = analyze_url(url)

        self.assertEqual(report["keyword_match_status"], "not_provided")
        self.assertIsNone(report["keyword_relevance_score"])

    def test_score_labels_use_centralized_mapping(self):
        self.assertEqual(score_to_label(94), "Excellent")
        self.assertEqual(score_to_label(82), "Good")
        self.assertEqual(score_to_label(None), "Not Evaluated")

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_no_structural_findings_keep_no_change_message(self, mock_build_session):
        url = "https://example.com/digital-marketing/"
        session = URLIntelligenceSession(
            responses={url: self._response(url, html=self._html(canonical_url=url))}
        )
        mock_build_session.return_value = session

        report = analyze_url(url, target_keyword="digital marketing")

        self.assertEqual(report["optimized_url_payload"]["status"], "no_change")
        self.assertEqual(
            report["optimized_url_payload"]["message"],
            "No structural URL change is necessary.",
        )

    def test_equivalent_trailing_slash_formatting_does_not_create_fake_optimization(self):
        optimized = build_optimized_url(
            "https://example.com/about",
            {"functional": []},
            {
                "has_uppercase": False,
                "has_underscores": False,
                "encoded_space_detected": False,
                "numeric_id_prefix_detected": False,
                "numeric_slug_detected": False,
                "url_length": 25,
                "depth_issue_detected": False,
                "indexability_status": "indexable",
            },
        )

        self.assertEqual(optimized["status"], "no_change")
        self.assertEqual(optimized["suggested_url"], "")
        self.assertEqual(optimized["migration_warning"], "")

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_fragment_only_is_informational(self, mock_build_session):
        input_url = "https://example.com/page/#section"
        server_url = "https://example.com/page/"
        session = URLIntelligenceSession(
            responses={input_url: self._response(server_url, html=self._html(canonical_url=server_url))}
        )
        mock_build_session.return_value = session

        report = analyze_url(input_url)
        fragment_check = next(check for check in report["quality_checks"] if check["label"] == "Fragment")

        self.assertTrue(report["has_fragment"])
        self.assertEqual(fragment_check["status"], "INFO")
        self.assertIn('Fragment identifier "#section" detected.', fragment_check["finding"])
        self.assertEqual(report["issues"], [])
        self.assertGreaterEqual(report["health_score"], 98)

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_fragment_preserves_original_url_without_creating_redirect(self, mock_build_session):
        input_url = "https://example.com/page/#p=1"
        server_url = "https://example.com/page/"
        session = URLIntelligenceSession(
            responses={input_url: self._response(server_url, html=self._html(canonical_url=server_url))}
        )
        mock_build_session.return_value = session

        report = analyze_url(input_url)
        fragment_check = next(check for check in report["quality_checks"] if check["label"] == "Fragment")

        self.assertEqual(report["original_url"], input_url)
        self.assertEqual(report["final_url"], server_url)
        self.assertFalse(report["redirect_detected"])
        self.assertEqual(report["redirect_count"], 0)
        self.assertIn('#p=1', fragment_check["finding"])

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_url_without_fragment_has_pass_quality_check(self, mock_build_session):
        url = "https://example.com/page/"
        session = URLIntelligenceSession(
            responses={url: self._response(url, html=self._html(canonical_url=url))}
        )
        mock_build_session.return_value = session

        report = analyze_url(url)
        fragment_check = next(check for check in report["quality_checks"] if check["label"] == "Fragment")

        self.assertFalse(report["has_fragment"])
        self.assertEqual(fragment_check["status"], "PASS")
        self.assertEqual(fragment_check["finding"], "No URL fragment detected.")

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_fragment_only_does_not_trigger_optimization(self, mock_build_session):
        input_url = "https://example.com/page/#pricing"
        server_url = "https://example.com/page/"
        session = URLIntelligenceSession(
            responses={input_url: self._response(server_url, html=self._html(canonical_url=server_url))}
        )
        mock_build_session.return_value = session

        report = analyze_url(input_url)

        self.assertEqual(report["optimized_url_payload"]["status"], "no_change")
        self.assertEqual(
            report["optimized_url_payload"]["message"],
            "No structural URL change is necessary.",
        )
        self.assertEqual(report["recommendations"], [])

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_fragment_with_real_problems_keeps_fragment_informational(self, mock_build_session):
        input_url = "http://example.com/Very_Long_Bad_URL/#section"
        server_url = "http://example.com/Very_Long_Bad_URL/"
        session = URLIntelligenceSession(
            responses={
                input_url: self._response(
                    server_url,
                    html=self._html(canonical_url=server_url),
                )
            }
        )
        mock_build_session.return_value = session

        report = analyze_url(input_url)
        fragment_check = next(check for check in report["quality_checks"] if check["label"] == "Fragment")
        issue_names = {issue["name"] for issue in report["issues"]}

        self.assertEqual(fragment_check["status"], "INFO")
        self.assertIn("Non-HTTPS URL", issue_names)
        self.assertIn("Uppercase Characters Detected", issue_names)
        self.assertIn("Underscores Detected", issue_names)
        self.assertNotIn("Fragment Identifier Detected", issue_names)

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_structural_findings_never_return_no_change_message(self, mock_build_session):
        url = "https://example.com/Product_Page/"
        session = URLIntelligenceSession(
            responses={url: self._response(url, html=self._html(canonical_url=url))}
        )
        mock_build_session.return_value = session

        report = analyze_url(url)

        self.assertNotEqual(report["optimized_url_payload"]["status"], "no_change")
        self.assertNotEqual(
            report["optimized_url_payload"]["message"],
            "No structural URL change is necessary.",
        )

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_real_structural_optimization_still_generates_changed_url_and_migration_warning(
        self, mock_build_session
    ):
        url = "https://paraland.tn/2612-doppel-herz-aktiv-a-z-action-durable-30-comprimes.html"
        session = URLIntelligenceSession(
            responses={url: self._response(url, html=self._html(canonical_url=url))}
        )
        mock_build_session.return_value = session

        report = analyze_url(url)
        optimization_recommendations = [
            item
            for item in report["recommendations"]
            if item["problem"] == "URL structure optimization opportunity"
        ]

        self.assertNotEqual(report["optimized_url_payload"]["status"], "no_change")
        self.assertTrue(report["optimized_url_payload"]["suggested_url"])
        self.assertNotEqual(
            report["optimized_url_payload"]["suggested_url"],
            report["optimized_url_payload"]["current_url"],
        )
        self.assertTrue(report["optimized_url_payload"]["migration_warning"])
        self.assertEqual(len(optimization_recommendations), 1)

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_view_creates_url_intelligence_task_result_and_issue_records(self, mock_build_session):
        url = "https://example.com/Product_Page/?utm_source=google"
        session = URLIntelligenceSession(
            responses={url: self._response(url, html=self._html(canonical_url=url))}
        )
        mock_build_session.return_value = session

        response = self.client.post(
            reverse("seo_analyzer:url_intelligence"),
            {"url": url, "target_keyword": "product page"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "URL Intelligence Report")
        self.assertEqual(URLIntelligenceTask.objects.count(), 1)
        self.assertEqual(URLIntelligenceResult.objects.count(), 1)
        self.assertGreaterEqual(URLIntelligenceIssue.objects.count(), 2)
        self.assertContains(response, "Suggested Optimized URL")

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_results_view_renders_access_restriction_labels(self, mock_build_session):
        url = "https://example.com/restricted-page/"
        session = URLIntelligenceSession(
            responses={url: self._response(url, status_code=403, html=self._html(canonical_url=None))}
        )
        mock_build_session.return_value = session

        response = self.client.post(
            reverse("seo_analyzer:url_intelligence"),
            {"url": url, "target_keyword": ""},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Access Restricted")
        self.assertContains(response, "Not Evaluated — Access Restricted")
        self.assertContains(response, "Not Evaluated")
        self.assertNotContains(response, "Canonical Missing")

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_results_view_renders_canonical_to_clean_url_summary_label(self, mock_build_session):
        url = "https://example.com/article/?gclid=123"
        canonical_url = "https://example.com/article/"
        session = URLIntelligenceSession(
            responses={url: self._response(url, html=self._html(canonical_url=canonical_url))}
        )
        mock_build_session.return_value = session

        response = self.client.post(
            reverse("seo_analyzer:url_intelligence"),
            {"url": url, "target_keyword": ""},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Canonical to Clean URL")
        self.assertNotContains(response, "Canonical to Another URL")

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_url_intelligence_pdf_download_returns_branded_pdf_and_reuses_saved_report(self, mock_build_session):
        url = "https://example.com/digital-marketing/"
        response, task, result = self._create_url_report_via_view(
            mock_build_session,
            url,
            canonical_url=url,
            target_keyword="digital marketing",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Download PDF Report")
        mock_build_session.reset_mock()

        pdf_response = self.client.get(reverse("seo_analyzer:download_report", args=["url", task.id]))

        self.assertEqual(pdf_response.status_code, 200)
        self.assertEqual(pdf_response["Content-Type"], "application/pdf")
        self.assertIn(
            'attachment; filename="OnWebApp_URL_Intelligence_Report_example.com.pdf"',
            pdf_response["Content-Disposition"],
        )
        self.assertTrue(pdf_response.content.startswith(b"%PDF"))
        self.assertIn(b"URL Intelligence Report", pdf_response.content)
        self.assertIn(b"Executive Summary", pdf_response.content)
        self.assertIn(b"URL Quality Checks", pdf_response.content)
        self.assertIn(b"AI Recommendations", pdf_response.content)
        self.assertEqual(mock_build_session.call_count, 0)
        self.assertEqual(result.original_url, url)

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_url_intelligence_pdf_for_404_preserves_not_evaluated_states(self, mock_build_session):
        url = "https://example.com/missing-page/"
        _, task, result = self._create_url_report_via_view(
            mock_build_session,
            url,
            canonical_url=None,
            status_code=404,
        )

        pdf_response = self.client.get(reverse("seo_analyzer:download_report", args=["url", task.id]))

        self.assertEqual(result.canonical_status, "not_evaluated")
        self.assertEqual(result.indexability_status, "not_found")
        self.assertIn(b"Not Evaluated", pdf_response.content)
        self.assertIn(b"URL Not Found", pdf_response.content)

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_url_intelligence_pdf_for_tracking_only_url_preserves_clean_url_recommendation(self, mock_build_session):
        url = "https://example.com/article/?gclid=123"
        clean_url = "https://example.com/article/"
        _, task, result = self._create_url_report_via_view(
            mock_build_session,
            url,
            canonical_url=clean_url,
        )

        pdf_response = self.client.get(reverse("seo_analyzer:download_report", args=["url", task.id]))

        self.assertEqual(result.optimized_url_payload["status"], "clean_url")
        self.assertEqual(result.optimized_url_payload["suggested_url"], clean_url)
        self.assertFalse(result.optimized_url_payload["migration_warning"])
        self.assertIn(b"Clean URL Recommendation", pdf_response.content)
        self.assertNotIn(b"Changing an existing indexed URL requires a permanent 301 redirect", pdf_response.content)

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_url_intelligence_pdf_for_functional_parameter_url_preserves_parameter(self, mock_build_session):
        url = "https://example.com/search?q=seo"
        _, task, result = self._create_url_report_via_view(
            mock_build_session,
            url,
            canonical_url=url,
        )

        pdf_response = self.client.get(reverse("seo_analyzer:download_report", args=["url", task.id]))

        self.assertEqual(result.functional_params_count, 1)
        self.assertEqual(result.optimized_url_payload["status"], "no_change")
        self.assertEqual(result.optimized_url_payload["suggested_url"], "")
        self.assertIn(b"Functional", pdf_response.content)
        self.assertNotIn(b"Clean URL Recommendation", pdf_response.content)

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_url_intelligence_pdf_for_review_needed_parameter_requires_validation(self, mock_build_session):
        url = "https://example.com/article?custom_parameter=abc"
        _, task, result = self._create_url_report_via_view(
            mock_build_session,
            url,
            canonical_url=None,
            status_code=404,
        )

        pdf_response = self.client.get(reverse("seo_analyzer:download_report", args=["url", task.id]))

        self.assertEqual(result.unnecessary_params_count, 1)
        self.assertEqual(result.optimized_url_payload["status"], "developer_validation_required")
        self.assertIn(b"Developer Validation Required", pdf_response.content)
        self.assertNotIn(b"Safe Optimization Suggestion", pdf_response.content)

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_url_intelligence_pdf_for_tracking_and_functional_preserves_functional_parameter(self, mock_build_session):
        url = "https://example.com/search?q=seo&gclid=123"
        _, task, result = self._create_url_report_via_view(
            mock_build_session,
            url,
            canonical_url="https://example.com/search/?q=seo",
        )

        pdf_response = self.client.get(reverse("seo_analyzer:download_report", args=["url", task.id]))

        self.assertEqual(result.optimized_url_payload["status"], "clean_url")
        self.assertEqual(result.optimized_url_payload["suggested_url"], "https://example.com/search/?q=seo")
        self.assertIn(b"Clean URL Recommendation", pdf_response.content)

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_url_intelligence_pdf_for_tracking_and_review_needed_preserves_review_parameter(self, mock_build_session):
        url = "https://example.com/article?gclid=123&custom_parameter=abc"
        _, task, result = self._create_url_report_via_view(
            mock_build_session,
            url,
            canonical_url="https://example.com/article/?custom_parameter=abc",
        )

        pdf_response = self.client.get(reverse("seo_analyzer:download_report", args=["url", task.id]))

        self.assertEqual(result.optimized_url_payload["status"], "clean_url")
        self.assertEqual(
            result.optimized_url_payload["suggested_url"],
            "https://example.com/article/?custom_parameter=abc",
        )
        self.assertIn(b"Review Needed", pdf_response.content)
        self.assertIn(b"Clean URL Recommendation", pdf_response.content)

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_url_intelligence_pdf_for_canonical_missing_preserves_existing_finding(self, mock_build_session):
        url = "https://example.com/article/"
        _, task, result = self._create_url_report_via_view(
            mock_build_session,
            url,
            canonical_url=None,
            status_code=200,
        )

        pdf_response = self.client.get(reverse("seo_analyzer:download_report", args=["url", task.id]))

        self.assertEqual(result.canonical_status, "missing")
        self.assertIn(b"Canonical Missing", pdf_response.content)

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_url_intelligence_pdf_for_canonical_to_clean_url_displays_clean_label(self, mock_build_session):
        url = "https://example.com/article/?gclid=123"
        _, task, result = self._create_url_report_via_view(
            mock_build_session,
            url,
            canonical_url="https://example.com/article/",
        )

        pdf_response = self.client.get(reverse("seo_analyzer:download_report", args=["url", task.id]))

        self.assertTrue(result.structure_payload.get("canonical_to_clean_url"))
        self.assertIn(b"Canonical to Clean URL", pdf_response.content)
        self.assertNotIn(b"Canonical to Another URL", pdf_response.content)

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_url_intelligence_pdf_for_srsltid_tracking_variant_matches_clean_canonical(self, mock_build_session):
        url = (
            "https://parapharmacie.tn/shop/hygiene/hygiene-intime/"
            "coupe-menstruelle-liberty-cup-taille-1/"
            "?srsltid=AfmBOorzNgWE0sXLjR_epAD84m88_i3l1nqOKKPzUFNrKhAuMaRq5hyT"
        )
        canonical_url = (
            "https://parapharmacie.tn/shop/hygiene/hygiene-intime/"
            "coupe-menstruelle-liberty-cup-taille-1/"
        )
        _, task, result = self._create_url_report_via_view(
            mock_build_session,
            url,
            canonical_url=canonical_url,
        )

        pdf_response = self.client.get(reverse("seo_analyzer:download_report", args=["url", task.id]))

        self.assertEqual(result.tracking_params_count, 1)
        self.assertEqual(result.unnecessary_params_count, 0)
        self.assertTrue(result.structure_payload.get("canonical_to_clean_url"))
        self.assertEqual(result.optimized_url_payload["status"], "clean_url")
        self.assertEqual(float(result.canonical_score), 100.0)
        self.assertIn(b"srsltid", pdf_response.content)
        self.assertIn(b"Tracking", pdf_response.content)
        self.assertIn(b"Canonical to Clean URL", pdf_response.content)
        self.assertIn(b"Clean URL Recommendation", pdf_response.content)
        self.assertNotIn(b"Developer Validation Required", pdf_response.content)
        self.assertNotIn(b"Canonical to Another URL", pdf_response.content)

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_url_intelligence_pdf_for_no_change_optimization_state(self, mock_build_session):
        url = "https://example.com/clean-seo-url/"
        _, task, result = self._create_url_report_via_view(
            mock_build_session,
            url,
            canonical_url=url,
        )

        pdf_response = self.client.get(reverse("seo_analyzer:download_report", args=["url", task.id]))

        self.assertEqual(result.optimized_url_payload["status"], "no_change")
        self.assertIn(b"No structural URL change is necessary.", pdf_response.content)

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_url_intelligence_pdf_download_uses_correct_saved_analysis(self, mock_build_session):
        first_url = "https://example.com/first-report/"
        second_url = "https://example.com/second-report/"
        response_map = {
            first_url: self._response(first_url, html=self._html(canonical_url=first_url)),
            second_url: self._response(second_url, html=self._html(canonical_url=second_url)),
        }
        mock_build_session.return_value = URLIntelligenceSession(responses=response_map)

        self.client.post(reverse("seo_analyzer:url_intelligence"), {"url": first_url, "target_keyword": ""}, follow=True)
        first_task = URLIntelligenceTask.objects.get(url=first_url)
        self.client.post(reverse("seo_analyzer:url_intelligence"), {"url": second_url, "target_keyword": ""}, follow=True)

        pdf_response = self.client.get(reverse("seo_analyzer:download_report", args=["url", first_task.id]))

        self.assertEqual(pdf_response.status_code, 200)
        self.assertIn(b"first-report", pdf_response.content)

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_url_intelligence_pdf_builder_returns_pdf_for_saved_result(self, mock_build_session):
        url = "https://example.com/report-builder/"
        _, task, result = self._create_url_report_via_view(
            mock_build_session,
            url,
            canonical_url=url,
        )
        issues = list(task.issues.all().order_by("severity", "-created_at"))

        pdf_bytes = build_url_intelligence_pdf(task, result, issues)

        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        self.assertIn(b"URL Resolution", pdf_bytes)
        self.assertIn(b"Suggested Optimized URL", pdf_bytes)

    @patch("seo_analyzer.services.url_intelligence.build_http_session")
    def test_url_resolution_pdf_section_keeps_heading_with_first_block(self, mock_build_session):
        url = "https://example.com/article/?srsltid=123"
        _, task, result = self._create_url_report_via_view(
            mock_build_session,
            url,
            canonical_url="https://example.com/article/",
        )
        payload = _prepare_url_intelligence_pdf_payload(task, result, list(task.issues.all()))
        styles = _build_link_pdf_styles(_register_link_pdf_fonts())

        story = _build_url_pdf_resolution_story(payload, styles)

        self.assertIsInstance(story[0], KeepTogether)

    def test_canonical_status_label_priority_for_self_canonical(self):
        result = SimpleNamespace(canonical_status="self", structure_payload={})
        self.assertEqual(get_canonical_status_label(result), "Self-Canonical")

    def test_canonical_status_label_priority_for_clean_tracking_canonical(self):
        result = SimpleNamespace(
            canonical_status="other",
            structure_payload={"canonical_to_clean_url": True},
        )
        self.assertEqual(get_canonical_status_label(result), "Canonical to Clean URL")

    def test_canonical_status_label_priority_for_real_other_canonical(self):
        result = SimpleNamespace(
            canonical_status="other",
            structure_payload={"canonical_to_clean_url": False},
        )
        self.assertEqual(get_canonical_status_label(result), "Canonical to Another URL")

    def test_canonical_status_label_priority_for_missing_canonical(self):
        result = SimpleNamespace(canonical_status="missing", structure_payload={})
        self.assertEqual(get_canonical_status_label(result), "Canonical Missing")

    def test_canonical_status_label_priority_for_not_evaluated_canonical(self):
        result = SimpleNamespace(
            canonical_status="not_evaluated",
            structure_payload={"canonical_to_clean_url": True},
        )
        self.assertEqual(get_canonical_status_label(result), "Not Evaluated")

    def test_canonical_missing_recommendation_mentions_preferred_url_and_duplicate_signals(self):
        recommendations = build_ai_recommendations(
            [
                {
                    "name": "Canonical Missing",
                    "severity": "medium",
                    "seo_impact": "Missing canonicals can reduce clarity when alternate URL variants exist.",
                    "recommended_fix": "Add a self-referencing canonical if this URL is the preferred version.",
                }
            ],
            {"status": "no_change"},
        )

        self.assertIn("preferred-url", recommendations[0]["expected_seo_improvement"].lower())
        self.assertIn("duplicate", recommendations[0]["expected_seo_improvement"].lower())
        self.assertNotIn("readability", recommendations[0]["expected_seo_improvement"].lower())

    def test_url_too_long_recommendation_mentions_readability_or_maintainability(self):
        recommendations = build_ai_recommendations(
            [
                {
                    "name": "URL Too Long",
                    "severity": "medium",
                    "seo_impact": "Long URLs are harder to read and can be truncated in search results.",
                    "recommended_fix": "Shorten the path and remove unnecessary elements while preserving intent.",
                }
            ],
            {"status": "no_change"},
        )

        expected = recommendations[0]["expected_seo_improvement"].lower()
        self.assertTrue("readability" in expected or "maintainability" in expected)

    def test_numeric_heavy_slug_recommendation_mentions_topical_clarity(self):
        recommendations = build_ai_recommendations(
            [
                {
                    "name": "Numeric-Heavy Slug Detected",
                    "severity": "medium",
                    "seo_impact": "Numeric-heavy slugs usually communicate little topical relevance.",
                    "recommended_fix": "Replace ID-heavy slugs with descriptive words where feasible.",
                }
            ],
            {"status": "no_change"},
        )

        expected = recommendations[0]["expected_seo_improvement"].lower()
        self.assertIn("topical clarity", expected)
        self.assertIn("semantic relevance", expected)

    def test_deep_url_structure_recommendation_mentions_crawl_efficiency_or_hierarchy(self):
        recommendations = build_ai_recommendations(
            [
                {
                    "name": "Deep URL Structure",
                    "severity": "medium",
                    "seo_impact": "Deep URL paths can signal unnecessary complexity and weaker topical focus.",
                    "recommended_fix": "Flatten the URL structure where possible.",
                }
            ],
            {"status": "no_change"},
        )

        expected = recommendations[0]["expected_seo_improvement"].lower()
        self.assertTrue("crawl efficiency" in expected or "hierarchy" in expected)

    def test_access_restricted_recommendation_mentions_crawl_accessibility(self):
        recommendations = build_ai_recommendations(
            [
                {
                    "name": "Access Restricted",
                    "severity": "high",
                    "seo_impact": "If search engine crawlers receive the same 403 response, crawling and indexing may be affected.",
                    "recommended_fix": "Review access rules and verify search engine accessibility separately.",
                }
            ],
            {"status": "no_change"},
        )

        expected = recommendations[0]["expected_seo_improvement"].lower()
        self.assertIn("crawl accessibility", expected)
        self.assertNotIn("readability", expected)

    def test_not_found_recommendation_mentions_restored_crawlability_or_redirect_handling(self):
        recommendations = build_ai_recommendations(
            [
                {
                    "name": "URL Not Found",
                    "severity": "critical",
                    "seo_impact": "A 404 response prevents the URL from being indexed as a live page.",
                    "recommended_fix": "Restore the page or redirect it appropriately.",
                }
            ],
            {"status": "no_change"},
        )

        expected = recommendations[0]["expected_seo_improvement"].lower()
        self.assertTrue("crawlability" in expected or "redirect" in expected)

    def test_server_error_recommendation_mentions_reliability_or_availability(self):
        recommendations = build_ai_recommendations(
            [
                {
                    "name": "Server Error",
                    "severity": "critical",
                    "seo_impact": "Server-side failures can block crawling and destabilize indexing if they persist.",
                    "recommended_fix": "Restore a stable successful response.",
                }
            ],
            {"status": "no_change"},
        )

        expected = recommendations[0]["expected_seo_improvement"].lower()
        self.assertTrue("reliability" in expected or "availability" in expected)

    def test_redirect_chain_recommendation_mentions_reduced_crawl_hops(self):
        recommendations = build_ai_recommendations(
            [
                {
                    "name": "Redirect Chain",
                    "severity": "medium",
                    "seo_impact": "Redirect chains add unnecessary hops.",
                    "recommended_fix": "Link directly to the final destination.",
                }
            ],
            {"status": "no_change"},
        )

        expected = recommendations[0]["expected_seo_improvement"].lower()
        self.assertIn("crawl hops", expected)

    def test_unknown_issue_type_uses_neutral_technical_seo_fallback(self):
        recommendations = build_ai_recommendations(
            [
                {
                    "name": "Custom Unknown Issue",
                    "severity": "medium",
                    "seo_impact": "Unknown issue impact.",
                    "recommended_fix": "Unknown fix.",
                }
            ],
            {"status": "no_change"},
        )

        self.assertEqual(
            recommendations[0]["expected_seo_improvement"],
            "Improved technical SEO consistency after resolving the detected issue.",
        )

    def test_not_evaluated_factor_does_not_generate_unsupported_recommendation(self):
        recommendations = build_ai_recommendations([], {"status": "no_change"}) 

        self.assertEqual(recommendations, [])


class SEOIntelligenceAccessControlTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        from django.utils import timezone
        from users.models import UserSubscription
        from payments.models import PaymentPlan

        User = get_user_model()

        # Create test users
        self.anonymous_client = self.client
        self.unsubscribed_user = User.objects.create_user(
            username="unsubscribed",
            email="unsubscribed@example.com",
            password="testpass123"
        )
        self.subscribed_user = User.objects.create_user(
            username="subscribed",
            email="subscribed@example.com",
            password="testpass123"
        )
        self.wrong_plan_user = User.objects.create_user(
            username="wrongplan",
            email="wrongplan@example.com",
            password="testpass123"
        )

        # Create SEO Intelligence plan
        self.seo_plan, _ = PaymentPlan.objects.get_or_create(
            plan_type="seo_intelligence",
            defaults={
                "name": "SEO Intelligence Suite",
                "price": 50.00,
                "description": "Complete SEO analysis suite",
                "duration_days": 365,
                "is_active": True
            }
        )

        # Create subscriptions
        UserSubscription.objects.create(
            user=self.subscribed_user,
            plan=self.seo_plan,
            is_active=True,
            start_date=timezone.now(),
            end_date=timezone.now() + timezone.timedelta(days=365)
        )

        # Create a different plan for wrong plan user
        self.wrong_plan, _ = PaymentPlan.objects.get_or_create(
            plan_type="basic",
            defaults={
                "name": "Basic Plan",
                "price": 499.00,
                "description": "Basic website plan",
                "duration_days": 365,
                "is_active": True
            }
        )
        UserSubscription.objects.create(
            user=self.wrong_plan_user,
            plan=self.wrong_plan,
            is_active=True,
            start_date=timezone.now(),
            end_date=timezone.now() + timezone.timedelta(days=365)
        )

    def test_anonymous_user_redirected_to_login(self):
        protected_routes = [
            reverse("seo_analyzer:checker"),
            reverse("seo_analyzer:link_checker"),
            reverse("seo_analyzer:backlinks"),
            reverse("seo_analyzer:url_intelligence"),
        ]

        for route in protected_routes:
            response = self.anonymous_client.get(route)
            self.assertEqual(response.status_code, 302)
            self.assertIn("/users/login/", response.url)

    def test_authenticated_user_without_seo_plan_can_access_routes(self):
        self.client.force_login(self.unsubscribed_user)
        protected_routes = [
            reverse("seo_analyzer:checker"),
            reverse("seo_analyzer:link_checker"),
            reverse("seo_analyzer:backlinks"),
            reverse("seo_analyzer:url_intelligence"),
        ]

        for route in protected_routes:
            response = self.client.get(route)
            self.assertEqual(response.status_code, 200)
            self.assertNotEqual(response.status_code, 402)

    def test_authenticated_user_with_active_seo_plan_can_access_routes(self):
        self.client.force_login(self.subscribed_user)
        protected_routes = [
            reverse("seo_analyzer:checker"),
            reverse("seo_analyzer:link_checker"),
            reverse("seo_analyzer:backlinks"),
            reverse("seo_analyzer:url_intelligence"),
        ]

        for route in protected_routes:
            response = self.client.get(route)
            self.assertEqual(response.status_code, 200)

    def test_user_with_wrong_plan_can_access_seo_tools(self):
        self.client.force_login(self.wrong_plan_user)
        protected_routes = [
            reverse("seo_analyzer:checker"),
            reverse("seo_analyzer:link_checker"),
            reverse("seo_analyzer:backlinks"),
            reverse("seo_analyzer:url_intelligence"),
        ]

        for route in protected_routes:
            response = self.client.get(route)
            self.assertEqual(response.status_code, 200)
            self.assertNotEqual(response.status_code, 402)
