from django.test import TestCase
from django.urls import reverse


class ChatbotTemplateTests(TestCase):
    def test_chatbot_page_closes_dom_content_loaded_script(self):
        response = self.client.get(reverse("chatbot:chatbot"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="chatbot-form"')
        self.assertContains(response, 'id="chatbot-message-input"')
        self.assertContains(response, "const form = document.getElementById('chatbot-form');")
        self.assertContains(response, "const input = document.getElementById('chatbot-message-input');")
        self.assertContains(response, "document.addEventListener('DOMContentLoaded', function() {")
        self.assertContains(response, "\n    });\n    </script>")
