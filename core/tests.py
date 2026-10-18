
from django.test import TestCase
from django.urls import reverse


class HomePageTest(TestCase):
    def test_home_page_returns_welcome_message(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Welcome to SmartStudy AI!")
        self.assertContains(
            response,
            "Your personal AI-powered study assistant."
        )
