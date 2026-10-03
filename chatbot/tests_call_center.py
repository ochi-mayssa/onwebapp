import json
import re
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from chatbot.models import CallRequest, ChatMessage, ChatSession


FULL_CC = {
    "ENABLED": True, "PHONE": "+15551234567", "PHONE_DISPLAY": "+1 (555) 123-4567",
    "WHATSAPP": "15551234567", "EMAIL": "help@onwebapp.com",
    "HOURS": "Monday to Friday, 9:00 - 18:00",
}


def ask(client, message, session_id="cc-test"):
    response = client.post(
        reverse("chatbot:chatbot_suggestions"),
        data=json.dumps({"message": message, "session_id": session_id}),
        content_type="application/json",
    )
    return response.status_code, response.json()


class CallButtonTests(TestCase):
    def test_the_button_says_call_not_talk_to_a_person(self):
        for path in ("/", "/chatbot/"):
            with self.subTest(path=path):
                html = self.client.get(path).content.decode()
                self.assertIn("data-chat-handoff", html)
                self.assertIn("fa-phone", html)

                # Read the button's visible text rather than matching raw markup:
                # the payload it posts still says "talk to a person".
                buttons = re.findall(
                    r"<button[^>]*data-chat-handoff[^>]*>(.*?)</button>", html, re.S)
                self.assertTrue(buttons, "no handoff button rendered")
                for inner in buttons:
                    label = re.sub(r"<[^>]+>", "", inner).strip()
                    self.assertEqual(label, "Call")
                    self.assertNotIn("person", label.lower())

    def test_the_button_still_sends_a_request_for_a_person(self):
        html = self.client.get("/").content.decode()
        self.assertIn('data-chat-handoff="I would like to talk to a person"', html)

    def test_status_endpoint_is_wired_up(self):
        for path in ("/", "/chatbot/"):
            with self.subTest(path=path):
                html = self.client.get(path).content.decode()
                self.assertIn("data-chat-status-endpoint", html)
                self.assertIn(reverse("chatbot:session_status"), html)


class CallButtonVisibilityTests(TestCase):
    """The button is a signal, so it may only appear when it means something."""

    @override_settings(CALL_CENTER=FULL_CC)
    def test_asking_for_details_offers_the_call(self):
        for message in ("I want more details", "can you tell me more about RPA",
                        "give me the pricing details", "can I get a demo",
                        "what does it cost", "send me a quote"):
            with self.subTest(message=message):
                status, data = ask(self.client, message, session_id=f"d-{len(message)}")
                self.assertEqual(status, 200)
                self.assertTrue(data["offer_call"])
                # Offered, not forced: nobody is put in the queue for asking.
                self.assertFalse(data["call"]["escalated"])
                self.assertTrue(data["actions"])

    @override_settings(CALL_CENTER=FULL_CC)
    def test_asking_about_the_call_centre_offers_the_call(self):
        for message in ("where is your call centre", "what is the support line number",
                        "can I speak to a human"):
            with self.subTest(message=message):
                status, data = ask(self.client, message, session_id=f"c-{len(message)}")
                self.assertEqual(status, 200)
                self.assertTrue(data["offer_call"])
                self.assertTrue(data["call"]["escalated"])

    @override_settings(CALL_CENTER=FULL_CC)
    def test_a_question_the_bot_cannot_answer_offers_the_call(self):
        status, data = ask(self.client, "zzzqqq flurble wozzle")
        self.assertEqual(status, 200)
        self.assertTrue(data["offer_call"])
        self.assertTrue(data["actions"])

    @override_settings(CALL_CENTER=FULL_CC)
    def test_a_normal_answer_offers_nothing(self):
        for message in ("hello", "what is rpa", "what is browser automation"):
            with self.subTest(message=message):
                status, data = ask(self.client, message, session_id=f"n-{len(message)}")
                self.assertEqual(status, 200)
                self.assertFalse(data["offer_call"])
                self.assertEqual(data["actions"], [])

    @override_settings(CALL_CENTER={"ENABLED": False})
    def test_a_switched_off_call_centre_shows_no_button_anywhere(self):
        for message in ("I want more details", "talk to a human"):
            with self.subTest(message=message):
                status, data = ask(self.client, message, session_id=f"o-{len(message)}")
                self.assertEqual(status, 200)
                self.assertFalse(data["offer_call"])
                self.assertEqual(data["actions"], [])

    @override_settings(CALL_CENTER=FULL_CC)
    def test_the_script_only_reveals_it_when_the_server_says_so(self):
        js = (Path(settings.BASE_DIR) / "static" / "js" / "chatbot.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("data-chat-offer", js)
        self.assertIn("data.offer_call", js)
        # A page that renders the button visible on load would defeat all of it.
        self.assertIn("setCallOffer(false)", js)


class QueueCreationTests(TestCase):
    @override_settings(CALL_CENTER=FULL_CC)
    def test_explicit_request_opens_one_ticket(self):
        status, data = ask(self.client, "please call me")
        self.assertEqual(status, 200)
        self.assertTrue(data["call"]["escalated"])
        self.assertEqual(data["call"]["status"], CallRequest.STATUS_NEW)

        ticket = CallRequest.objects.get()
        self.assertEqual(ticket.reason, "please call me")
        self.assertEqual(ticket.channel, "call")
        self.assertIsNone(ticket.requested_by)

    @override_settings(CALL_CENTER=FULL_CC)
    def test_greeting_then_request_still_escalates(self):
        status, data = ask(self.client, "hello, please call me")
        self.assertEqual(status, 200)
        self.assertTrue(data["call"]["escalated"])

    @override_settings(CALL_CENTER=FULL_CC)
    def test_a_bare_greeting_does_not_escalate(self):
        status, data = ask(self.client, "hello!")
        self.assertEqual(status, 200)
        self.assertFalse(data["call"]["escalated"])
        self.assertFalse(CallRequest.objects.exists())

    @override_settings(CALL_CENTER=FULL_CC)
    def test_repeat_request_reuses_the_same_ticket(self):
        ask(self.client, "call me")
        ask(self.client, "actually call me now")
        self.assertEqual(CallRequest.objects.count(), 1)
        self.assertEqual(CallRequest.objects.get().reason, "actually call me now")

    @override_settings(CALL_CENTER=FULL_CC)
    def test_resolved_request_reopens_instead_of_duplicating(self):
        ask(self.client, "call me")
        ticket = CallRequest.objects.get()
        ticket.resolve("done")

        ask(self.client, "call me again")
        ticket.refresh_from_db()
        self.assertEqual(CallRequest.objects.count(), 1)
        self.assertEqual(ticket.status, CallRequest.STATUS_NEW)
        self.assertIsNone(ticket.resolved_at)

    @override_settings(CALL_CENTER=FULL_CC)
    def test_ordinary_questions_do_not_create_tickets(self):
        for message in ("what is rpa", "hello", "price of plans"):
            with self.subTest(message=message):
                ask(self.client, message, session_id=f"s-{abs(hash(message))}")
        self.assertEqual(CallRequest.objects.count(), 0)

    @override_settings(CALL_CENTER=FULL_CC)
    def test_low_confidence_fallback_offers_a_person_without_opening_a_ticket(self):
        status, data = ask(self.client, "zzzqqq flurble wozzle")
        self.assertEqual(status, 200)
        self.assertTrue(data["actions"])
        self.assertFalse(data["call"]["escalated"])
        self.assertEqual(CallRequest.objects.count(), 0)

    @override_settings(CALL_CENTER=FULL_CC)
    def test_authenticated_visitor_is_attached_to_the_ticket(self):
        User.objects.create_user("visitor", "visitor@example.com", "pw")
        self.client.login(username="visitor", password="pw")
        ask(self.client, "call me")
        ticket = CallRequest.objects.get()
        self.assertEqual(ticket.requested_by.username, "visitor")


class AgentHandoffTests(TestCase):
    def setUp(self):
        self.agent = User.objects.create_user("agent1", "agent1@example.com", "pw")
        self.agent.is_staff = True
        self.agent.save()
        self.other = User.objects.create_user("agent2", "agent2@example.com", "pw")
        self.other.is_staff = True
        self.other.save()

    @override_settings(CALL_CENTER=FULL_CC)
    def test_agent_reply_lands_in_the_visitor_transcript(self):
        ask(self.client, "call me", session_id="live-1")
        ticket = CallRequest.objects.get()

        self.client.force_login(self.agent)
        self.client.post(reverse("chatbot:call_center_reply", args=[ticket.pk]),
                         {"message": "Hi, this is Sam. What can I help with?"})

        message = ChatMessage.objects.filter(sender=ChatMessage.SENDER_AGENT).get()
        self.assertEqual(message.session.session_id, "live-1")
        self.assertEqual(message.agent, self.agent)
        self.assertEqual(message.agent_label(), "agent1")

        # The whole conversation, bot included, is what the agent sees.
        self.assertEqual(ticket.transcript.count(), 3)

    @override_settings(CALL_CENTER=FULL_CC)
    def test_replying_claims_the_ticket(self):
        ask(self.client, "call me", session_id="live-2")
        ticket = CallRequest.objects.get()
        self.client.force_login(self.agent)
        self.client.post(reverse("chatbot:call_center_reply", args=[ticket.pk]),
                         {"message": "on it"})
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, CallRequest.STATUS_CLAIMED)
        self.assertEqual(ticket.assigned_to, self.agent)

    @override_settings(CALL_CENTER=FULL_CC)
    def test_send_and_resolve(self):
        ask(self.client, "call me", session_id="live-3")
        ticket = CallRequest.objects.get()
        self.client.force_login(self.agent)
        self.client.post(reverse("chatbot:call_center_reply", args=[ticket.pk]),
                         {"message": "sorted", "resolve": "1"})
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, CallRequest.STATUS_RESOLVED)
        self.assertEqual(ticket.resolution, "sorted")

    def test_claim_is_idempotent_and_release_returns_to_queue(self):
        session = ChatSession.objects.create(session_id="live-4")
        ticket = CallRequest.objects.create(session=session)
        self.client.force_login(self.agent)

        self.client.post(reverse("chatbot:call_center_claim", args=[ticket.pk]))
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, CallRequest.STATUS_CLAIMED)
        self.assertEqual(ticket.assigned_to, self.agent)

        self.client.post(reverse("chatbot:call_center_release", args=[ticket.pk]))
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, CallRequest.STATUS_NEW)
        self.assertIsNone(ticket.assigned_to)

    def test_claiming_a_resolved_request_is_refused(self):
        session = ChatSession.objects.create(session_id="live-5")
        ticket = CallRequest.objects.create(session=session)
        ticket.resolve()
        self.client.force_login(self.agent)
        self.client.post(reverse("chatbot:call_center_claim", args=[ticket.pk]))
        ticket.refresh_from_db()
        self.assertIsNone(ticket.assigned_to)
        self.assertEqual(ticket.status, CallRequest.STATUS_RESOLVED)


class VisitorStatusEndpointTests(TestCase):
    def setUp(self):
        self.agent = User.objects.create_user("agent9", "agent9@example.com", "pw")
        self.agent.is_staff = True
        self.agent.save()

    def test_unknown_session_returns_nothing(self):
        response = self.client.get(reverse("chatbot:session_status"),
                                   {"session_id": "nope"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["messages"], [])
        self.assertFalse(response.json()["escalated"])

    def test_missing_session_is_a_400(self):
        self.assertEqual(
            self.client.get(reverse("chatbot:session_status")).status_code, 400)

    @override_settings(CALL_CENTER=FULL_CC)
    def test_agent_message_reaches_the_waiting_visitor(self):
        ask(self.client, "call me", session_id="live-poll")
        ticket = CallRequest.objects.get()
        self.client.force_login(self.agent)
        self.client.post(reverse("chatbot:call_center_reply", args=[ticket.pk]),
                         {"message": "Sam here, how can I help?"})
        self.client.logout()

        response = self.client.get(reverse("chatbot:session_status"),
                                   {"session_id": "live-poll"})
        data = response.json()
        self.assertTrue(data["escalated"])
        self.assertEqual(data["status"], CallRequest.STATUS_CLAIMED)
        self.assertEqual(len(data["messages"]), 1)
        self.assertEqual(data["messages"][0]["content"], "Sam here, how can I help?")
        self.assertEqual(data["messages"][0]["agent"], "agent9")

    @override_settings(CALL_CENTER=FULL_CC)
    def test_since_filters_out_what_was_already_seen(self):
        ask(self.client, "call me", session_id="live-since")
        ticket = CallRequest.objects.get()
        self.client.force_login(self.agent)
        self.client.post(reverse("chatbot:call_center_reply", args=[ticket.pk]),
                         {"message": "first"})
        self.client.logout()

        data = self.client.get(reverse("chatbot:session_status"),
                               {"session_id": "live-since"}).json()
        newest = max(m["timestamp"] for m in data["messages"])
        import datetime
        cutoff = (datetime.datetime.fromisoformat(newest)
                  + datetime.timedelta(seconds=1)).timestamp()
        again = self.client.get(reverse("chatbot:session_status"),
                                {"session_id": "live-since",
                                 "since": cutoff}).json()
        self.assertEqual(again["messages"], [])

    def test_bot_messages_are_never_returned_to_the_visitor(self):
        session = ChatSession.objects.create(session_id="live-bot-only")
        CallRequest.objects.create(session=session)
        ChatMessage.objects.create(session=session, sender="BOT", content="internal")
        ChatMessage.objects.create(session=session, sender="USER", content="mine")
        data = self.client.get(reverse("chatbot:session_status"),
                               {"session_id": "live-bot-only"}).json()
        self.assertEqual(data["messages"], [])


class CallCenterDashboardTests(TestCase):
    def setUp(self):
        self.agent = User.objects.create_user("agentA", "a@example.com", "pw")
        self.agent.is_staff = True
        self.agent.save()
        self.plain = User.objects.create_user("plain", "p@example.com", "pw")

    def make(self, name, **kwargs):
        session = ChatSession.objects.create(session_id=name)
        return CallRequest.objects.create(session=session, reason=name, **kwargs)

    def test_anonymous_visitors_are_sent_to_login(self):
        for name in ("chatbot:call_center", "chatbot:call_center_api"):
            with self.subTest(name=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 302)
                self.assertIn("login", response["Location"])

    def test_queue_renders_for_staff(self):
        self.make("one")
        self.make("two", status=CallRequest.STATUS_RESOLVED)
        self.client.force_login(self.agent)
        response = self.client.get(reverse("chatbot:call_center"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["tickets"]), 1)
        self.assertEqual(response.context["open_total"], 1)

    def test_filters(self):
        self.make("open-one")
        mine = self.make("mine-one", status=CallRequest.STATUS_CLAIMED,
                         assigned_to=self.agent)
        self.make("resolved-one", status=CallRequest.STATUS_RESOLVED)
        self.client.force_login(self.agent)

        get = lambda f: self.client.get(reverse("chatbot:call_center"), {"filter": f})
        self.assertEqual(len(get("open").context["tickets"]), 2)
        self.assertEqual(len(get("new").context["tickets"]), 1)
        self.assertEqual([t.pk for t in get("mine").context["tickets"]], [mine.pk])
        self.assertEqual(len(get("resolved").context["tickets"]), 1)
        self.assertEqual(len(get("all").context["tickets"]), 3)

    def test_search_matches_reason_and_session_id(self):
        self.make("findme")
        self.make("other")
        self.client.force_login(self.agent)
        response = self.client.get(reverse("chatbot:call_center"), {"q": "findme"})
        self.assertEqual(len(response.context["tickets"]), 1)

    def test_detail_shows_the_full_transcript(self):
        ticket = self.make("detail-one")
        ChatMessage.objects.create(session=ticket.session, sender="USER", content="hi")
        ChatMessage.objects.create(session=ticket.session, sender="BOT", content="hello")
        self.client.force_login(self.agent)
        response = self.client.get(
            reverse("chatbot:call_center_detail", args=[ticket.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["transcript"]), 2)
        self.assertContains(response, "hi")
        self.assertContains(response, "hello")

    def test_queue_api_counts(self):
        self.make("api-one")
        self.make("api-two", status=CallRequest.STATUS_RESOLVED)
        self.client.force_login(self.agent)
        data = self.client.get(reverse("chatbot:call_center_api"),
                               {"scope": "open"}).json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["counts"]["resolved"], 1)
        self.assertEqual(data["oldest_waiting"], "Under 5 min")

    def test_a_regular_user_only_sees_their_own_requests(self):
        mine = self.make("mine-only", requested_by=self.plain)
        self.make("someone-else")
        self.client.force_login(self.plain)

        response = self.client.get(reverse("chatbot:call_center"))
        self.assertEqual([t.pk for t in response.context["tickets"]], [mine.pk])

        # And cannot read someone else's transcript.
        other = CallRequest.objects.exclude(pk=mine.pk).get()
        self.assertEqual(
            self.client.get(reverse("chatbot:call_center_detail",
                                    args=[other.pk])).status_code, 404)

    def test_non_staff_cannot_post_notes_for_another_person(self):
        theirs = self.make("theirs")
        self.client.force_login(self.plain)
        response = self.client.post(
            reverse("chatbot:call_center_detail", args=[theirs.pk]),
            {"notes": "tampered"}, follow=True)
        self.assertEqual(response.status_code, 404)
        theirs.refresh_from_db()
        self.assertEqual(theirs.notes, "")

    def test_a_regular_user_cannot_answer_their_own_request(self):
        # They are allowed to read their own conversation, but posting as
        # OnWebApp staff into it would let them forge agent messages.
        theirs = self.make("theirs", requested_by=self.plain)
        self.client.force_login(self.plain)

        for name in ("chatbot:call_center_claim", "chatbot:call_center_release",
                     "chatbot:call_center_reply"):
            with self.subTest(name=name):
                response = self.client.post(reverse(name, args=[theirs.pk]),
                                            {"message": "trust me, staff here"},
                                            follow=True)
                self.assertEqual(response.status_code, 200)

        theirs.refresh_from_db()
        self.assertEqual(theirs.status, CallRequest.STATUS_NEW)
        self.assertIsNone(theirs.assigned_to)
        self.assertFalse(ChatMessage.objects.filter(
            sender=ChatMessage.SENDER_AGENT).exists())

    def test_one_agent_cannot_steal_a_claimed_request(self):
        ticket = self.make("taken")
        other_staff = User.objects.create_user("staff2", "s2@example.com", "pw",
                                               is_staff=True)
        ticket.claim(self.agent)

        self.client.force_login(other_staff)
        self.client.post(reverse("chatbot:call_center_claim", args=[ticket.pk]))
        ticket.refresh_from_db()
        self.assertEqual(ticket.assigned_to, self.agent)
        self.assertFalse(ticket.claim(other_staff))


class ChatLogTests(TestCase):
    """The log that makes every conversation visible, not just the escalated ones."""

    def setUp(self):
        self.agent = User.objects.create_user("agentL", "l@example.com", "pw")
        self.agent.is_staff = True
        self.agent.save()
        self.visitor = User.objects.create_user("visitorL", "v@example.com", "pw")

    def make_chat(self, name, texts, user=None, escalated=False):
        session = ChatSession.objects.create(session_id=name, user=user)
        for sender, content in texts:
            ChatMessage.objects.create(session=session, sender=sender, content=content)
        if escalated:
            CallRequest.objects.create(session=session, reason=session.messages
                                       .filter(sender="USER").values_list("content", flat=True)
                                       .first() or name)
        return session

    def test_a_chat_that_never_escalated_still_appears(self):
        plain = self.make_chat("bot-only", [("USER", "what is rpa"),
                                            ("BOT", "RPA is robotic process automation")])
        self.client.force_login(self.agent)
        response = self.client.get(reverse("chatbot:call_center_chats"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "bot-only")
        # The row previews the newest line, not the whole transcript.
        self.assertContains(response, "RPA is robotic process automation")
        self.assertEqual(list(response.context["chats"]), [plain])
        self.assertFalse(response.context["chats"][0].has_ticket)
        # And the queue is untouched: it is still only real requests.
        self.assertEqual(
            self.client.get(reverse("chatbot:call_center")).context["paginator"].count, 0)

    def test_the_log_lists_both_kinds_side_by_side(self):
        self.make_chat("escalated-one", [("USER", "call me")], escalated=True)
        self.make_chat("quiet-one", [("USER", "thanks"), ("BOT", "any time")])
        self.client.force_login(self.agent)
        response = self.client.get(reverse("chatbot:call_center_chats"))
        self.assertContains(response, "Escalated")
        self.assertContains(response, "Bot only")
        self.assertEqual(response.context["total_chats"], 2)
        self.assertEqual(response.context["escalated_total"], 1)

    def test_filter_splits_escalated_from_plain(self):
        self.make_chat("has-ticket", [("USER", "call me")], escalated=True)
        self.make_chat("no-ticket", [("USER", "hello")])
        self.client.force_login(self.agent)

        escalated = self.client.get(reverse("chatbot:call_center_chats"),
                                    {"filter": "escalated"})
        self.assertEqual([c.session_id for c in escalated.context["chats"]], ["has-ticket"])

        plain = self.client.get(reverse("chatbot:call_center_chats"),
                                {"filter": "plain"})
        self.assertEqual([c.session_id for c in plain.context["chats"]], ["no-ticket"])

    def test_search_matches_what_they_actually_typed(self):
        self.make_chat("first", [("USER", "do you do blockchain")])
        self.make_chat("second", [("USER", "what is rpa")])
        self.client.force_login(self.agent)

        response = self.client.get(reverse("chatbot:call_center_chats"),
                                   {"q": "blockchain"})
        self.assertEqual([c.session_id for c in response.context["chats"]], ["first"])

        by_email = self.client.get(reverse("chatbot:call_center_chats"),
                                   {"q": "v@example.com"})
        self.assertEqual(by_email.context["chats"], [])

    def test_a_regular_user_only_ever_sees_their_own_chats(self):
        self.make_chat("mine", [("USER", "hello")], user=self.visitor)
        self.make_chat("someone-elses", [("USER", "secret question")])
        self.client.force_login(self.visitor)

        response = self.client.get(reverse("chatbot:call_center_chats"))
        self.assertEqual([c.session_id for c in response.context["chats"]], ["mine"])

        forbidden = self.client.get(
            reverse("chatbot:call_center_chat", args=["someone-elses"]))
        self.assertEqual(forbidden.status_code, 404)

    def test_anonymous_visitors_are_sent_to_login(self):
        for name in ("chatbot:call_center_chats",):
            with self.subTest(name=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 302)
                self.assertIn("login", response["Location"])

    def test_the_transcript_renders_and_offers_no_reply_box(self):
        session = self.make_chat("read-me", [("USER", "can I get a demo"),
                                            ("BOT", "sure, here is the page")])
        self.client.force_login(self.agent)
        response = self.client.get(
            reverse("chatbot:call_center_chat", args=[session.session_id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "can I get a demo")
        self.assertContains(response, "sure, here is the page")
        # Read-only: replies are posted to the ticket endpoint, which must not
        # appear anywhere on a transcript that has no ticket.
        self.assertNotContains(response, "/reply/")
        self.assertContains(response, reverse("chatbot:call_center_escalate",
                                              args=[session.session_id]))

    def test_escalate_creates_one_ticket_from_the_visitor_own_words(self):
        session = self.make_chat("needs-a-human",
                                 [("USER", "what happens after I sign up"),
                                  ("BOT", "here is the process")])
        self.client.force_login(self.agent)

        response = self.client.post(
            reverse("chatbot:call_center_escalate", args=[session.session_id]))
        self.assertEqual(response.status_code, 302)
        ticket = CallRequest.objects.get()
        self.assertEqual(ticket.session.session_id, session.session_id)
        self.assertEqual(ticket.reason, "what happens after I sign up")
        self.assertEqual(ticket.channel, "staff")
        self.assertEqual(ticket.status, CallRequest.STATUS_NEW)
        self.assertRedirects(response, reverse("chatbot:call_center_detail",
                                               args=[ticket.pk]))

    def test_escalating_twice_does_not_duplicate_the_ticket(self):
        session = self.make_chat("once-only", [("USER", "call me")])
        self.client.force_login(self.agent)
        url = reverse("chatbot:call_center_escalate", args=[session.session_id])
        self.client.post(url)
        self.client.post(url)
        self.assertEqual(CallRequest.objects.count(), 1)

    def test_escalate_needs_a_post_and_a_staff_account(self):
        session = self.make_chat("guarded", [("USER", "hello")])
        url = reverse("chatbot:call_center_escalate", args=[session.session_id])

        self.client.force_login(self.visitor)
        self.assertEqual(self.client.get(url).status_code, 405)
        self.client.post(url)
        self.assertEqual(CallRequest.objects.count(), 0)

        self.client.force_login(self.agent)
        self.client.post(url)
        self.assertEqual(CallRequest.objects.count(), 1)

    def test_the_queue_only_ever_lists_tickets(self):
        self.make_chat("silent", [("USER", "hello"), ("BOT", "hi")])
        self.make_chat("loud", [("USER", "call me")], escalated=True)
        self.client.force_login(self.agent)
        response = self.client.get(reverse("chatbot:call_center"))
        self.assertEqual([t.session.session_id for t in response.context["tickets"]],
                         ["loud"])


class WaitingLabelTests(TestCase):
    def test_labels_and_priority_follow_the_wait(self):
        from datetime import timedelta

        from django.utils import timezone

        session = ChatSession.objects.create(session_id="age-1")
        ticket = CallRequest.objects.create(session=session)
        cases = [(60, 'Under 5 min', CallRequest.PRIORITY_UNDER_5),
                 (600, '5 to 15 min', CallRequest.PRIORITY_5_TO_15),
                 (2000, 'Over 15 min', CallRequest.PRIORITY_OVER_15)]
        for seconds, label, priority in cases:
            with self.subTest(seconds=seconds):
                ticket.escalated_at = timezone.now() - timedelta(seconds=seconds)
                self.assertEqual(ticket.waiting_label, label)
                self.assertEqual(ticket.priority, priority)

    def test_waiting_stops_at_resolution(self):
        from datetime import timedelta

        from django.utils import timezone

        session = ChatSession.objects.create(session_id="age-2")
        ticket = CallRequest.objects.create(session=session)
        # Resolved ten seconds after it was escalated, two hours ago. The clock
        # must read the resolution time, not the age of the ticket.
        ticket.escalated_at = timezone.now() - timedelta(hours=2)
        ticket.resolved_at = ticket.escalated_at + timedelta(seconds=10)
        self.assertEqual(ticket.waiting_seconds, 10)
