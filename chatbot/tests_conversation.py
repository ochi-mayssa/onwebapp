"""The page-aware guide: context, qualification and the handover to a lead.

These cover the layer that sits between "the visitor said something" and the
existing answer pipeline — plus the two endpoints behind it. The rules worth
guarding are the business rules: one question at a time, a summary made only
of what was actually said, browser automation never sold as a product, and no
turn left without a way forward.
"""
import json
import re

from django.test import TestCase
from django.urls import reverse

from chatbot import conversation
from chatbot import page_context
from chatbot.models import CallRequest, ChatLead, ChatSession
from chatbot.views import generate_response


def suggestions_payload(**extra):
    body = {'message': 'hello', 'session_id': 'payload'}
    body.update(extra)
    return json.dumps(body)


class ConversationEngineTests(TestCase):
    """``handle_turn`` decides: this message is mine, or the pipeline's."""

    def setUp(self):
        self.session = ChatSession.objects.create(session_id='engine-test')

    def turn(self, message):
        flags = {}
        return conversation.handle_turn(message, self.session, flags=flags), flags

    def test_a_requirement_becomes_one_recommendation_and_one_question(self):
        result, flags = self.turn('I need a custom dashboard for my sales team')

        self.assertIsNotNone(result)
        reply, suggestions, links = result
        self.assertIn('dashboard', reply.lower())
        # One question at a time: a questionnaire is what we are not doing.
        self.assertEqual(reply.count('?'), 1)
        self.assertTrue(links)
        for link in links:
            self.assertEqual(set(link), {'title', 'url'})
        for chip in suggestions:
            self.assertIn('title', chip)

        structured = flags['structured']
        self.assertEqual(structured['intent'], 'dashboard')
        self.assertEqual(structured['stage'], 'qualifying')

    def test_informational_questions_are_left_to_the_answer_pipeline(self):
        for message in ('what is rpa', 'what is your project process?'):
            with self.subTest(message=message):
                result, _ = self.turn(message)
                self.assertIsNone(result)

    def test_a_detour_reoffers_the_pending_question_instead_of_dropping_it(self):
        conversation.handle_turn('I need a website for my business', self.session,
                                 flags={})

        flags = {}
        result = conversation.handle_turn('tell me more about your process',
                                          self.session, flags=flags)

        self.assertIsNone(result)
        self.assertIn('pending_question', flags)
        self.assertTrue(flags['pending_question'].endswith('?'))

    def test_browser_automation_is_a_capability_not_a_product(self):
        result, flags = self.turn('I need browser automation for scraping')

        self.assertIsNotNone(result)
        reply = result[0].lower()
        self.assertIn('capability', reply)
        self.assertIn('rather than a product sold on its own', reply)
        # It is carried into the service that actually covers the work.
        self.assertEqual(flags['structured']['intent'], 'automation')
        self.assertNotIn('price', reply)

    def test_a_new_project_restarts_the_answers_but_keeps_the_business(self):
        conversation.handle_turn('I need a website for my business', self.session,
                                 flags={})
        conversation.handle_turn('we are a logistics company', self.session,
                                 flags={})

        result, _ = self.turn('I also need an online store')

        self.assertIsNotNone(result)
        self.assertEqual(self.session.state['intent'], 'ecommerce')
        self.assertEqual(self.session.state['answers'], {})
        self.assertEqual(self.session.state['slots']['business_type'], 'logistics')

    def test_enough_answers_produce_a_summary_of_only_what_was_said(self):
        for message in ('I need a custom dashboard for my sales team',
                        'we are a retail company with 10 people',
                        'sales and marketing',
                        'our website and a CRM'):
            conversation.handle_turn(message, self.session, flags={})

        state = self.session.state
        self.assertEqual(state['stage'], 'ready')
        summary = conversation.lead_summary(state)
        self.assertIsNotNone(summary)
        joined = ' '.join(summary['bullets']).lower()
        self.assertIn('retail', joined)
        self.assertIn('sales, marketing', joined)
        # Nothing is padded in: every bullet traces back to an answer.
        self.assertNotIn('healthcare', joined)
        self.assertEqual(state['answers']['data_sources'], 'sales and marketing')

    def test_an_explicit_ask_skips_the_questionnaire(self):
        conversation.handle_turn('I need a dashboard for my sales team',
                                 self.session, flags={})

        flags = {}
        result = conversation.handle_turn('how much does it cost?',
                                          self.session, flags=flags)

        self.assertIsNotNone(result)
        self.assertEqual(self.session.state['stage'], 'ready')
        self.assertIn('cta', flags['structured'])
        self.assertEqual(flags['structured']['cta']['action'], 'lead')


class GenerateResponseStillRoutesAroundTheEngine(TestCase):
    """The conversation layer must not swallow the turns it does not own."""

    def test_the_three_tuple_contract_is_unchanged(self):
        session = ChatSession.objects.create(session_id='contract')
        reply, suggestions, links = generate_response('what is rpa', session)
        self.assertTrue(reply)
        self.assertIsInstance(suggestions, list)
        self.assertIsInstance(links, list)

    def test_a_need_is_answered_by_the_engine_not_the_index(self):
        session = ChatSession.objects.create(session_id='need')
        flags = {}
        reply, suggestions, links = generate_response(
            'I need a custom dashboard', session, flags=flags)

        self.assertEqual(flags['structured']['intent'], 'dashboard')
        self.assertIn('dashboard', reply.lower())
        self.assertTrue(links)

    def test_the_state_lives_on_the_session_and_is_saved_by_the_view(self):
        session = ChatSession.objects.create(session_id='state')
        generate_response('I need an ERP for my company', session)

        self.assertEqual(session.state['intent'], 'erp')
        session.save()
        session.refresh_from_db()
        self.assertEqual(session.state['stage'], 'qualifying')


class PageContextEndpointTests(TestCase):
    def get(self, **params):
        response = self.client.get(reverse('chatbot:page_context'), params)
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_a_service_page_comes_back_with_its_own_questions(self):
        data = self.get(path='/software/dashboard-development/')

        self.assertEqual(data['service'], 'dashboard')
        self.assertTrue(data['welcome'])
        self.assertTrue(data['suggestions'])
        for chip in data['suggestions']:
            self.assertEqual(set(chip), {'title'})
        self.assertEqual(data['path'], '/software/dashboard-development')

    def test_a_page_nobody_wrote_an_entry_for_still_gets_a_context(self):
        data = self.get(path='/services/smart-factory/')

        self.assertTrue(data['welcome'])
        self.assertTrue(data['suggestions'])
        self.assertEqual(data['category'], 'Services')

    def test_a_blank_path_falls_back_to_the_default_context(self):
        data = self.get(path='')

        self.assertTrue(data['welcome'])
        self.assertTrue(data['suggestions'])
        self.assertEqual(data['service'], '')

    def test_the_page_is_remembered_for_the_conversation(self):
        ChatSession.objects.create(session_id='page-memory')

        self.get(path='/software/web-development/', session_id='page-memory')

        session = ChatSession.objects.get(session_id='page-memory')
        self.assertEqual(session.state['page']['path'], '/software/web-development')
        self.assertEqual(session.state['page']['title'], 'Web Development')

    def test_only_get_and_post_are_allowed(self):
        response = self.client.put(reverse('chatbot:page_context'))
        self.assertEqual(response.status_code, 405)


class LeadEndpointTests(TestCase):
    def post(self, payload):
        return self.client.post(reverse('chatbot:request_lead'),
                                json.dumps(payload),
                                content_type='application/json')

    def qualify(self, session_id, messages):
        session = ChatSession.objects.create(session_id=session_id)
        for message in messages:
            conversation.handle_turn(message, session, flags={})
        session.save()
        return session

    def test_a_session_with_nothing_to_say_is_refused(self):
        self.assertEqual(self.post({}).status_code, 400)

        ChatSession.objects.create(session_id='quiet')
        response = self.post({'session_id': 'quiet'})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(ChatLead.objects.exists())

    def test_a_confirmed_request_becomes_a_lead_the_team_can_read(self):
        session = self.qualify('lead-flow', [
            'I need a custom dashboard for my sales team',
            'we are a retail company with 10 people',
            'sales and marketing',
        ])

        response = self.post({'session_id': 'lead-flow'})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['reply'])
        lead = ChatLead.objects.get(session=session)
        self.assertEqual(lead.intent, 'dashboard')
        self.assertTrue(lead.solution)
        self.assertIn('Lead intent:', lead.summary)
        self.assertIn('retail', lead.summary.lower())
        self.assertEqual(lead.status, ChatLead.STATUS_NEW)
        # The summary the team reads is built from the answers, verbatim.
        self.assertEqual(lead.data['answers']['data_sources'], 'sales and marketing')

        # The confirmation is part of the transcript the agent reads.
        self.assertEqual(session.messages.filter(sender='BOT').count(), 1)
        # And the queue knows there is a person waiting behind this one.
        ticket = CallRequest.objects.get(session=session)
        self.assertEqual(ticket.channel, 'form')
        self.assertTrue(ticket.is_open)

    def test_confirming_twice_updates_the_same_lead(self):
        self.qualify('lead-twice', [
            'I need a website for my business',
            'we are a healthcare clinic',
        ])

        self.post({'session_id': 'lead-twice'})
        self.post({'session_id': 'lead-twice'})

        self.assertEqual(ChatLead.objects.count(), 1)
        self.assertEqual(CallRequest.objects.filter(
            session__session_id='lead-twice').count(), 1)

    def test_an_unknown_session_never_reaches_the_queue(self):
        response = self.post({'session_id': 'nobody-home'})

        self.assertEqual(response.status_code, 400)
        self.assertFalse(CallRequest.objects.exists())


class PageAwareSuggestionsTests(TestCase):
    """The widget posts the page it is on; the answer remembers it."""

    def setUp(self):
        self.session_id = 'page-aware'

    def post(self, **extra):
        payload = {'message': extra.pop('message'),
                   'session_id': self.session_id}
        payload.update(extra)
        response = self.client.post(reverse('chatbot:chatbot_suggestions'),
                                    json.dumps(payload),
                                    content_type='application/json')
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_a_need_on_a_service_page_comes_back_structured(self):
        data = self.post(
            message='I need a custom dashboard',
            page={'path': '/software/dashboard-development/',
                  'title': 'Custom Business Dashboards'},
        )

        self.assertIsNotNone(data['structured'])
        self.assertEqual(data['structured']['intent'], 'dashboard')
        self.assertEqual(data['structured']['stage'], 'qualifying')
        # The reply is still cut into renderable pieces, question included.
        separator = ' ' if data['reply_format'] == 'paragraphs' else '\n'
        self.assertEqual(' '.join(separator.join(data['reply_parts']).split()),
                         ' '.join(data['reply'].split()))

        session = ChatSession.objects.get(session_id=self.session_id)
        self.assertEqual(session.state['page']['path'],
                         '/software/dashboard-development')
        self.assertEqual(session.state['stage'], 'qualifying')

    def test_a_turn_the_engine_does_not_own_has_no_structured_payload(self):
        data = self.post(message='what is rpa')

        self.assertIsNone(data['structured'])
        self.assertTrue(data['reply'])


class LeadTranscriptTests(TestCase):
    """The press and its confirmation are recorded in the log, once each."""

    def qualify(self, session_id):
        session = ChatSession.objects.create(session_id=session_id)
        for message in (
            'I need a custom dashboard for my sales team',
            'we are a retail company with 10 people',
            'sales and marketing',
        ):
            conversation.handle_turn(message, session, flags={})
        session.save()
        return session

    def post(self, session_id, label='Request a Consultation'):
        return self.client.post(
            reverse('chatbot:request_lead'),
            json.dumps({'session_id': session_id, 'label': label}),
            content_type='application/json')

    def test_what_was_pressed_and_what_was_promised_are_both_there(self):
        self.qualify('lead-transcript')

        self.post('lead-transcript')

        session = ChatSession.objects.get(session_id='lead-transcript')
        contents = list(session.messages.order_by('timestamp')
                         .values_list('sender', 'content'))
        self.assertEqual([sender for sender, _ in contents],
                         ['USER', 'BOT'])
        self.assertEqual(contents[0][1], 'Request a Consultation')
        self.assertIn('Thank you', contents[1][1])

    def test_confirming_twice_does_not_replay_the_conversation(self):
        self.qualify('lead-once')

        self.post('lead-once')
        self.post('lead-once')

        session = ChatSession.objects.get(session_id='lead-once')
        self.assertEqual(session.messages.count(), 2)

    def test_a_label_the_widget_never_sent_falls_back_to_the_button(self):
        self.qualify('lead-unlabelled')

        response = self.post('lead-unlabelled', label='')

        self.assertEqual(response.status_code, 200)
        session = ChatSession.objects.get(session_id='lead-unlabelled')
        self.assertEqual(session.messages.filter(sender='USER').count(), 1)
        self.assertEqual(session.messages.filter(sender='USER')
                         .values_list('content', flat=True).get(),
                         'Request a consultation')


class RenderedDefaultsTests(TestCase):
    """The page carries the guide's opening copy before any request is made."""

    def rendered_defaults(self, path, script_id):
        html = self.client.get(path).content.decode()
        match = re.search(
            r'<script id="%s" type="application/json">(.*?)</script>' % script_id,
            html, re.S)
        self.assertIsNotNone(match, 'the page must render its chatbot defaults')
        return html, json.loads(match.group(1))

    def test_a_service_page_renders_its_own_questions(self):
        html, defaults = self.rendered_defaults(
            '/software/dashboard-development/', 'owa-chat-widget-defaults')

        expected = page_context.static_context('/software/dashboard-development/')
        self.assertEqual(defaults['path'], '/software/dashboard-development')
        self.assertEqual(defaults['welcome'], expected['welcome'])
        self.assertEqual(defaults['page_intro'], expected['page_intro'])
        self.assertEqual(defaults['suggestions'], expected['suggestions'])
        # Nothing that needs a permission check is baked into the page: calls
        # to action are only ever shown once the endpoint has verified them.
        self.assertNotIn('ctas', defaults)
        # The endpoints it will refine that copy with are in the markup.
        self.assertIn(reverse('chatbot:page_context'), html)
        self.assertIn(reverse('chatbot:request_lead'), html)

    def test_the_home_page_renders_the_default_greeting(self):
        html, defaults = self.rendered_defaults('/', 'owa-chat-widget-defaults')

        self.assertEqual(defaults['path'], '/')
        self.assertEqual(defaults['welcome'],
                         page_context.DEFAULT_CONTEXT['welcome'])

    def test_the_opening_line_is_the_same_on_every_page(self):
        # Whatever page the visitor lands on, the first thing they read is
        # one sentence they can answer; the page introduces itself in the
        # second message and in the questions offered underneath it.
        for path in ('/', '/software/dashboard-development/',
                     '/services/erp/', '/automation/rpa-bpa/'):
            self.assertEqual(page_context.static_context(path)['welcome'],
                             'Hello, how can I help you today?')
        self.assertEqual(page_context.DEFAULT_CONTEXT['welcome'],
                         page_context.WELCOME)

    def test_the_page_introduces_itself_in_the_second_message(self):
        # The greeting never changes; the line after it always belongs to the
        # page being read, and a page nobody wrote an entry for says nothing.
        web = page_context.static_context('/software/web-development/')
        self.assertEqual(web['welcome'], page_context.WELCOME)
        self.assertIn('Web Development', web['page_intro'])

        unwritten = page_context.static_context('/nowhere/in/particular/')
        self.assertEqual(unwritten['welcome'], page_context.WELCOME)
        self.assertNotIn('page_intro', unwritten)

    def test_every_registered_page_has_its_own_second_line(self):
        for url_name, entry in page_context.PAGE_CONTEXTS.items():
            with self.subTest(page=url_name):
                self.assertTrue(entry.get('page_intro'))

    def test_the_full_page_renders_its_defaults_too(self):
        html, defaults = self.rendered_defaults(
            reverse('chatbot:chatbot'), 'owa-chat-page-defaults')

        self.assertIn(reverse('chatbot:page_context'), html)
        self.assertTrue(defaults['suggestions'])

    def test_every_page_on_the_site_gets_the_defaults(self):
        # The context processor runs on every template, so a page that has
        # nothing of its own to say still renders the guide's generic copy.
        context = self.client.get('/services/erp/').context
        self.assertEqual(context['chat_defaults']['path'], '/services/erp')
        self.assertTrue(context['chat_defaults']['welcome'])
