import re

from django.test import Client, TestCase, override_settings

from chatbot.models import ChatMessage, ChatSession
from chatbot.views import HUMAN_RE, _call_center_actions, _handoff_reply, generate_response


FULL_CC = {
    "ENABLED": True, "PHONE": "+15551234567", "PHONE_DISPLAY": "+1 (555) 123-4567",
    "WHATSAPP": "15551234567", "EMAIL": "help@onwebapp.com",
    "HOURS": "Monday to Friday, 9:00 - 18:00",
}

SHOULD_ESCALATE = [
    "talk to a human", "speak to someone", "can I talk to an agent",
    "real person please", "live agent", "call me back", "call the team",
    "connect me with support", "call center", "escalate this", "transfer me",
    "request a callback", "i want a manager", "let me speak to somebody",
    "contact the support team", "what is the support line number",
]

SHOULD_NOT_ESCALATE = [
    "hello there", "what is rpa", "talk about pricing", "how do i call the api",
    "what is chat support like", "tell me about automation", "price of plans",
    "do you offer internships", "who is the project manager",
    "i need a manager dashboard", "what does the support team cover",
    "connect me to the erp system", "how do i integrate with salesforce",
    "describe your service line", "what is a help desk tool",
]


class HandoffCopyTests(TestCase):
    def test_join_phrases_reads_as_english(self):
        from chatbot.views import _join_phrases
        self.assertEqual(_join_phrases(["call us"]), "call us")
        self.assertEqual(_join_phrases(["call us", "send us a message"]),
                         "call us or send us a message")
        self.assertEqual(
            _join_phrases(["call us", "message us on WhatsApp", "send us a message"]),
            "call us, message us on WhatsApp, or send us a message")
        self.assertEqual(
            _join_phrases(["a", "b", "c", "d"]), "a, b, c, or d")

    def test_hours_are_appended_only_when_configured(self):
        from chatbot.models import ChatSession
        session = ChatSession.objects.create(session_id="copy-test")
        with override_settings(CALL_CENTER={"ENABLED": True, "PHONE": "",
                                             "WHATSAPP": "", "HOURS": ""}):
            reply, _, _, _ = _handoff_reply()
        self.assertNotIn("available", reply)
        with override_settings(CALL_CENTER={"ENABLED": True, "PHONE": "",
                                             "WHATSAPP": "", "HOURS": "9-5"}):
            reply, _, _, _ = _handoff_reply()
        self.assertIn("available 9-5", reply)


class HandoffIntentTests(TestCase):
    def test_escalation_phrases(self):
        for text in SHOULD_ESCALATE:
            with self.subTest(text=text):
                self.assertTrue(HUMAN_RE.search(text), text)

    def test_ordinary_questions_do_not_escalate(self):
        for text in SHOULD_NOT_ESCALATE:
            with self.subTest(text=text):
                self.assertFalse(HUMAN_RE.search(text), text)

    def test_actions_skip_unconfigured_channels(self):
        with override_settings(CALL_CENTER=FULL_CC):
            kinds = {a["kind"] for a in _call_center_actions()}
        self.assertEqual(kinds, {"call", "chat", "form"})

        with override_settings(CALL_CENTER={"ENABLED": True, "PHONE": "", "WHATSAPP": ""}):
            kinds = {a["kind"] for a in _call_center_actions()}
        self.assertEqual(kinds, {"form"})

        with override_settings(CALL_CENTER={"ENABLED": False}):
            self.assertEqual(_call_center_actions(), [])

        with override_settings(CALL_CENTER={}):
            self.assertIsInstance(_call_center_actions(), list)

    def test_links_are_built_from_config_not_hardcoded(self):
        with override_settings(CALL_CENTER=FULL_CC):
            call = next(a for a in _call_center_actions() if a["kind"] == "call")
            wa = next(a for a in _call_center_actions() if a["kind"] == "chat")
        self.assertEqual(call["url"], "tel:+15551234567")
        self.assertIn("wa.me/15551234567?", wa["url"])
        self.assertIn("%20", wa["url"])


class HandoffEndpointTests(TestCase):
    def post(self, message, **extra):
        response = self.client.post(
            "/chatbot/suggestions/",
            data=__import__("json").dumps({"message": message, **extra}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        return response.json()

    @override_settings(CALL_CENTER=FULL_CC)
    def test_escalation_returns_actions(self):
        data = self.post("talk to a human")
        self.assertEqual(len(data["actions"]), 3)
        self.assertTrue(all(a["url"] and a["label"] for a in data["actions"]))
        reply = data["reply"].lower()
        self.assertIn("of course", reply)
        self.assertIn("call us", reply)
        self.assertIn("whatsapp", reply)
        # Three channels must not read as a chain of "or".
        self.assertEqual(reply.count(" or "), 1)
        self.assertNotIn(" or or ", reply)

    @override_settings(CALL_CENTER={"ENABLED": True, "PHONE": "", "WHATSAPP": "",
                                     "EMAIL": "", "HOURS": ""})
    def test_only_the_contact_channel_reads_correctly(self):
        data = self.post("talk to a human")
        self.assertEqual(
            data["reply"].lower(),
            "of course - send us a message is the quickest way to reach us. "
            "i'll pass on the context of this chat so you don't have to repeat yourself."
        )

    @override_settings(CALL_CENTER=FULL_CC)
    def test_channels_are_offered_only_on_turns_that_need_a_person(self):
        for message in ("hello", "what is rpa"):
            with self.subTest(message=message):
                data = self.post(message)
                self.assertIsInstance(data["actions"], list)
                self.assertEqual(data["actions"], [])
                self.assertFalse(data["offer_call"])

        for message in ("talk to a human", "I want more details"):
            with self.subTest(message=message):
                data = self.post(message)
                self.assertTrue(data["offer_call"])
                self.assertEqual(len(data["actions"]), 3)

    @override_settings(CALL_CENTER={"ENABLED": False})
    def test_a_switched_off_call_centre_offers_no_button(self):
        data = self.post("I want more details")
        self.assertFalse(data["offer_call"])
        self.assertEqual(data["actions"], [])

    @override_settings(CALL_CENTER={"ENABLED": False})
    def test_disabled_never_leaves_a_dead_end(self):
        data = self.post("talk to a human")
        self.assertEqual(data["actions"], [])
        self.assertTrue(data["reply"])
        self.assertTrue(data["links"], "escalation must still offer the contact page")

    @override_settings(CALL_CENTER={"ENABLED": False})
    def test_disabled_contact_fallback_survives_a_stale_index(self):
        # The crawl index is empty here, which is exactly the situation that
        # used to strip the escalation reply of every link.
        data = self.post("talk to a human")
        self.assertEqual([l["url"] for l in data["links"]], ["/contact/"])

    def test_escalation_is_logged_in_the_session(self):
        with override_settings(CALL_CENTER=FULL_CC):
            self.post("talk to a human", session_id="handoff-test")
        session = ChatSession.objects.get(session_id="handoff-test")
        messages = list(session.messages.values_list("sender", "content"))
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0][0], "USER")
        self.assertIn("talk to a human", messages[0][1])
        self.assertEqual(messages[1][0], "BOT")

    @override_settings(CALL_CENTER=FULL_CC)
    def test_three_tuple_return_contract_is_unchanged(self):
        session = ChatSession.objects.create(session_id="contract-test")
        actions = []
        result = generate_response("hello", session, actions=actions)
        self.assertEqual(len(result), 3)
        self.assertIsInstance(actions, list)

    @override_settings(CALL_CENTER=FULL_CC)
    def test_greeting_is_not_treated_as_a_handoff_request(self):
        data = self.post("hello")
        self.assertFalse(data["offer_call"])
        self.assertEqual(data["actions"], [])
        self.assertNotIn("reach us", data["reply"].lower())


class HandoffMarkupTests(TestCase):
    def test_widget_and_page_expose_the_button(self):
        for path in ("/", "/chatbot/"):
            with self.subTest(path=path):
                html = self.client.get(path).content.decode()
                self.assertIn("data-chat-handoff", html)
                self.assertIn("data-chat-offer", html)
                self.assertIn("owa-chat-footer-row", html)

                # The visible control is labelled "Call" even though it posts a
                # request for a person, so read the button text, not the markup.
                buttons = re.findall(
                    r"<button[^>]*data-chat-handoff[^>]*>(.*?)</button>", html, re.S)
                self.assertTrue(buttons, "no handoff button rendered")
                for inner in buttons:
                    self.assertEqual(re.sub(r"<[^>]+>", "", inner).strip(), "Call")
                self.assertIn('data-chat-handoff="I would like to talk to a person"', html)

    def test_the_button_starts_hidden_on_both_surfaces(self):
        # It is shown by the script when a turn earns it, so a fresh page must
        # not advertise a way to call before anyone has asked for one.
        for path in ("/", "/chatbot/"):
            with self.subTest(path=path):
                html = self.client.get(path).content.decode()
                rows = re.findall(r"<div[^>]*data-chat-offer[^>]*>", html)
                self.assertTrue(rows, "no offer row rendered")
                for row in rows:
                    self.assertIn("hidden", row)

    def test_no_community_fab_came_back(self):
        html = self.client.get("/").content.decode()
        self.assertNotIn("owa-fab-community", html)
        self.assertIn("oh-topbar-new", html)
