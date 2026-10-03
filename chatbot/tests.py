import json
import tempfile

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from chatbot import search as site_search
from chatbot.corpus import PUBLIC, access_for_user, iter_page_sources, user_can_read
from chatbot.indexer import build_and_save, build_index, chunk_page
from chatbot.text_utils import html_to_sections, split_sentences, tokenize
from chatbot.views import generate_response

User = get_user_model()


class TextUtilsTests(TestCase):
    def test_html_to_sections_keeps_copy_and_drops_chrome(self):
        markup = """
        <html><head><title>Ignored</title></head><body>
          <nav class="navbar"><a href="/">Home</a><a href="/blog/">Blog</a></nav>
          <h1>Website Automation</h1>
          <p>We automate browser tasks for real businesses.</p>
          <h2>Data Extraction</h2>
          <p>We pull structured data from any website you can log into.</p>
          <script>var tracking = 1;</script>
          <footer>All rights reserved.</footer>
        </body></html>
        """
        sections = html_to_sections(markup)
        text = ' '.join(body for _, body in sections)

        self.assertIn('We automate browser tasks', text)
        self.assertIn('Data Extraction', ' '.join(h for h, _ in sections))
        self.assertNotIn('Blog', text)
        self.assertNotIn('tracking', text)
        self.assertNotIn('All rights reserved', text)

    def test_tokenize_drops_question_words_and_stems(self):
        self.assertEqual(tokenize('Do you offer integrations?'), ['integration'])
        self.assertEqual(tokenize('Do you offer internships?'), ['internship'])

    def test_split_sentences_ignores_fragments(self):
        self.assertEqual(len(split_sentences('Short. A full sentence here now.')), 1)


class ChunkingTests(TestCase):
    def test_chunk_page_keeps_heading_and_marks_nav_runs(self):
        markup = """
        <html><body>
          <h2>SEO Services</h2>
          <p>We run technical audits, keyword research and on-page optimisation
             for growing businesses across many countries and industries.</p>
          <p>Home Articles Research Careers Pricing Contact</p>
        </body></html>
        """
        chunks = chunk_page('seo:home', 'SEO', '/seo/', PUBLIC, markup)

        self.assertTrue(chunks)
        self.assertTrue(all(c['access'] == PUBLIC for c in chunks))
        # The link-label run is chrome, not copy.
        self.assertFalse(any('Careers' in c['text'] for c in chunks))


class AccessTests(TestCase):
    def setUp(self):
        self.member = User.objects.create_user('member', 'm@example.com', 'pw')
        self.staff = User.objects.create_user('staff', 's@example.com', 'pw',
                                              is_staff=True)

    def test_access_levels(self):
        from django.contrib.auth.models import AnonymousUser

        self.assertEqual(access_for_user(None), 'public')
        self.assertEqual(access_for_user(AnonymousUser()), 'public')
        self.assertEqual(access_for_user(self.member), 'auth')
        self.assertEqual(access_for_user(self.staff), 'staff')

    def test_user_can_read(self):
        self.assertTrue(user_can_read(None, PUBLIC))
        self.assertFalse(user_can_read(None, 'auth'))
        self.assertTrue(user_can_read(self.member, 'auth'))
        self.assertFalse(user_can_read(self.member, 'staff'))
        self.assertTrue(user_can_read(self.staff, 'staff'))


class RetrievalTests(TestCase):
    """The index is built once for the class; it crawls the whole site."""

    @classmethod
    def setUpTestData(cls):
        # A privileged user must exist or the gated pages render as logins.
        User.objects.create_superuser('crawler', 'crawler@example.com', 'pw')
        cls.index = build_index()

    def test_index_contains_public_content(self):
        self.assertGreater(self.index['total_docs'], 50)
        self.assertIn('public', {c['access'] for c in self.index['chunks']})

    def test_answers_known_questions(self):
        cases = {
            'do you offer rpa': '/automation/rpa-bpa/',
            'what is smart factory': '/services/smart-factory/',
            'what is data integration': '/integration/data/',
        }
        for question, expected_url in cases.items():
            with self.subTest(question=question):
                result = site_search.answer(question, index=self.index)
                self.assertNotEqual(result['confidence'], 'none')
                self.assertTrue(result['response'].strip())
                self.assertIn(expected_url, [l['url'] for l in result['links']])

    def test_refuses_questions_the_site_does_not_cover(self):
        # Every word here is absent from the site, so there is nothing honest
        # to extract and the bot must say so rather than quote something close.
        for question in ('do you sell bicycles to children?',
                         'what is the name of your office dog?',
                         'asdkjh qwe zxc',
                         'can you arrange a helicopter landing?'):
            with self.subTest(question=question):
                result = site_search.answer(question, index=self.index)
                self.assertEqual(result['confidence'], 'none')

    def test_private_content_is_hidden_from_anonymous_visitors(self):
        private = [c for c in self.index['chunks'] if c['access'] in ('auth', 'staff')]
        self.assertTrue(private, 'expected some gated content to be indexed')

        questions = {c['title'] for c in private if c['title']}
        for question in questions:
            with self.subTest(question=question):
                result = site_search.answer(question, user=None, index=self.index)
                for link in result['links']:
                    self.assertNotIn(link['url'], private_urls(self.index))

    def test_staff_content_is_hidden_from_members(self):
        staff_urls = {c['url'] for c in self.index['chunks'] if c['access'] == 'staff'}
        if not staff_urls:
            self.skipTest('no staff pages rendered')
        member = User.objects.create_user('plain', 'p@example.com', 'pw')
        for question in ('crm dashboard', 'projects dashboard'):
            with self.subTest(question=question):
                result = site_search.answer(question, user=member, index=self.index)
                for link in result['links']:
                    self.assertNotIn(link['url'], staff_urls)


def private_urls(index):
    return {c['url'] for c in index['chunks'] if c['access'] in ('auth', 'staff')}


class ChatbotResponseTests(TestCase):
    def setUp(self):
        User.objects.create_superuser('crawler2', 'crawler2@example.com', 'pw')
        # Keep the index cache inside the test run instead of the project dir,
        # then prime it so the view never crawls the site mid-request.
        self._index_dir = tempfile.TemporaryDirectory()
        patcher = override_settings(CHATBOT_INDEX_DIR=self._index_dir.name)
        patcher.enable()
        self.addCleanup(patcher.disable)
        self.addCleanup(self._index_dir.cleanup)
        build_and_save()

    def post(self, message):
        response = self.client.post(
            reverse('chatbot:chatbot_suggestions'),
            data=json.dumps({'message': message}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_endpoint_shape(self):
        data = self.post('what is rpa')

        self.assertIn('reply', data)
        self.assertIn('session_id', data)
        self.assertIsInstance(data['links'], list)
        for link in data['links']:
            self.assertEqual(set(link), {'title', 'url'})
        for chip in data['suggestions']:
            self.assertIn('title', chip)

    def test_endpoint_returns_renderable_reply_parts(self):
        data = self.post('what is rpa')

        self.assertIn('reply_parts', data)
        self.assertIn(data['reply_format'], ('paragraphs', 'bullets'))
        self.assertTrue(data['reply_parts'])
        # Every part must be a real slice of the answer, never invented text.
        for part in data['reply_parts']:
            self.assertIsInstance(part, str)
            self.assertIn(part, data['reply'])

    def test_reply_parts_reassemble_to_the_reply(self):
        for message in ('what is rpa', 'tell me about the blog', 'what is web 4.0'):
            with self.subTest(message=message):
                data = self.post(message)
                separator = ' ' if data['reply_format'] == 'paragraphs' else '\n'
                joined = separator.join(data['reply_parts'])
                self.assertEqual(
                    ' '.join(joined.split()), ' '.join(data['reply'].split())
                )

    def test_every_suggested_link_actually_works(self):
        for question in ('what is rpa', 'do you build ecommerce',
                         'what is social intelligence', 'tell me about the forum'):
            with self.subTest(question=question):
                data = self.post(question)
                self.assertTrue(data['links'])
                for link in data['links']:
                    self.assertEqual(self.client.get(link['url']).status_code, 200,
                                     '%s is broken' % link['url'])

    def test_gated_pages_are_not_offered_to_anonymous_visitors(self):
        # The curated answers link pages by URL name; a signed-in-only page must
        # not be handed to a visitor who would only be bounced to the login page.
        gated = {
            path for _name, _title, path, access in iter_page_sources()
            if access != PUBLIC
        }
        self.assertTrue(gated, 'no gated pages in the corpus to check against')

        for question in ('what is smart factory', 'what is keyword research',
                         'do you do industrial automation', 'what is ux design'):
            with self.subTest(question=question):
                data = self.post(question)
                for link in data['links']:
                    self.assertNotIn(link['url'], gated)

    def test_greeting_needs_a_word_boundary(self):
        # "bicycles" contains "hi": it must not be read as a greeting.
        data = self.post('do you sell bicycles to children?')
        self.assertNotIn('smart guide', data['reply'].lower())

        greeting = self.post('hi there')
        self.assertIn('smart guide', greeting['reply'].lower())

    def test_greeting_must_open_the_message(self):
        data = self.post('this is a hi-tech question about iot')
        self.assertNotIn('smart guide', data['reply'].lower())

    def test_order_question_asks_for_login(self):
        data = self.post('where is my order 1234')
        self.assertIn('log in', data['reply'].lower())

    def test_unknown_question_still_returns_valid_payload(self):
        data = self.post('asdkjh qwe zxc')
        self.assertTrue(data['reply'].strip())
        for link in data['links']:
            self.assertEqual(self.client.get(link['url']).status_code, 200)


class GenerateResponseUnitTests(TestCase):
    """No crawling here: these exercise the routing inside the view."""

    def setUp(self):
        self.session = type('S', (), {'user': None, 'user_id': None})()

    def test_returns_three_tuple(self):
        reply, suggestions, links = generate_response('hello', self.session)
        self.assertTrue(reply)
        self.assertIsInstance(suggestions, list)
        self.assertIsInstance(links, list)


class SplitAnswerTests(TestCase):
    """The chat bubble renders one bubble per answer, so the answer is cut into
    pieces for display. Splitting must never change the words."""

    def test_prose_splits_on_sentences(self):
        parts, fmt = site_search.split_answer(
            'Web 4.0 is the next stage of the web. It is user owned. It is open.'
        )

        self.assertEqual(fmt, 'paragraphs')
        self.assertEqual(len(parts), 3)

    def test_single_sentence_stays_one_part(self):
        parts, fmt = site_search.split_answer('Short one sentence answer.')

        self.assertEqual(fmt, 'paragraphs')
        self.assertEqual(parts, ['Short one sentence answer.'])

    def test_dash_list_keeps_its_lead_in(self):
        parts, fmt = site_search.split_answer(
            'Here is what you can do:\n- Start a discussion\n- Ask for help'
        )

        self.assertEqual(fmt, 'bullets')
        self.assertEqual(parts, ['Here is what you can do:',
                                 'Start a discussion', 'Ask for help'])

    def test_numbered_list_keeps_every_item(self):
        # Regression: the first line was being dropped as a false "lead-in".
        parts, fmt = site_search.split_answer(
            '1. First thing\n2. Second thing\n3. Third thing'
        )

        self.assertEqual(fmt, 'bullets')
        self.assertEqual(parts, ['First thing', 'Second thing', 'Third thing'])

    def test_one_dash_is_prose_not_a_list(self):
        parts, fmt = site_search.split_answer(
            'Our services are many.\n- and one of them is RPA'
        )

        self.assertEqual(fmt, 'paragraphs')
        self.assertEqual(len(parts), 1)

    def test_empty_answer(self):
        self.assertEqual(site_search.split_answer(''), ([], 'paragraphs'))
        self.assertEqual(site_search.split_answer(None), ([], 'paragraphs'))

    def test_no_words_are_added_or_lost(self):
        original = 'One two three. Four five six. Seven eight nine.'
        parts, _ = site_search.split_answer(original)

        self.assertEqual(' '.join(' '.join(parts).split()),
                         ' '.join(original.split()))


class NavbarSearchTests(TestCase):
    """The navbar search box reuses the chatbot index, so it inherits its
    permission filtering and its refusal to link broken pages."""

    def setUp(self):
        User.objects.create_superuser('crawler3', 'crawler3@example.com', 'pw')
        self._index_dir = tempfile.TemporaryDirectory()
        patcher = override_settings(CHATBOT_INDEX_DIR=self._index_dir.name)
        patcher.enable()
        self.addCleanup(patcher.disable)
        self.addCleanup(self._index_dir.cleanup)
        build_and_save()

    def api(self, query):
        response = self.client.get(reverse('chatbot:search_api'), {'q': query})
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_api_returns_matches_for_a_known_topic(self):
        data = self.api('rpa')
        self.assertTrue(data['results'])
        first = data['results'][0]
        self.assertEqual(set(first), {'title', 'url', 'heading', 'snippet'})
        self.assertTrue(first['url'].startswith('/'))
        self.assertTrue(first['snippet'])

    def test_api_ignores_queries_that_are_too_short(self):
        for query in ('', 'r'):
            self.assertEqual(self.api(query)['results'], [])

    def test_api_rejects_non_get(self):
        response = self.client.post(reverse('chatbot:search_api'))
        self.assertEqual(response.status_code, 405)

    def test_results_are_unique_and_openable(self):
        data = self.api('automation')
        urls = [r['url'] for r in data['results']]
        self.assertEqual(len(urls), len(set(urls)), 'a page was listed twice')
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 200)

    def test_gated_pages_are_hidden_from_anonymous_visitors(self):
        gated = {path for _n, _t, path, access in iter_page_sources()
                 if access != PUBLIC}
        self.assertTrue(gated)
        for query in ('keyword research', 'industrial automation', 'erpnext'):
            with self.subTest(query=query):
                for result in self.api(query)['results']:
                    self.assertNotIn(result['url'], gated)

    def test_snippets_do_not_leak_markup(self):
        data = self.api('automation')
        for result in data['results']:
            self.assertNotIn('<', result['snippet'])

    def test_results_page_renders(self):
        response = self.client.get(reverse('chatbot:search'), {'q': 'rpa'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'rpa')

    def test_results_page_handles_a_blank_query(self):
        response = self.client.get(reverse('chatbot:search'), {'q': ''})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'What are you looking for?')

    def test_navbar_carries_the_search_box_on_every_page(self):
        for path in ('/', '/chatbot/', '/automation/'):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                body = response.content.decode('utf-8')
                # Desktop form plus the mobile one inside the collapse menu.
                self.assertIn('navSearch', body)
                self.assertIn('navSearchMobile', body)
                self.assertIn(reverse('chatbot:search_api'), body)
