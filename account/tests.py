from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()


class AuthFlowTestCase(TestCase):
    """Test custom registration, login, and logout."""

    def _get_csrf(self, response):
        """Extract CSRF token from response cookies."""
        return response.cookies.get("csrftoken").value if response.cookies.get("csrftoken") else None

    def test_register_page_loads(self):
        r = self.client.get(reverse("account:register"))
        self.assertEqual(r.status_code, 200)
        self.assertIn("form", r.context)
        self.assertContains(r, "Sign Up")
        self.assertContains(r, "Create Account")

    def test_login_page_loads(self):
        r = self.client.get(reverse("account:login"))
        self.assertEqual(r.status_code, 200)
        self.assertIn("form", r.context)
        self.assertContains(r, "Enter Workspace")

    def test_register_login_logout_flow(self):
        # 1. GET register page to obtain CSRF token
        get_resp = self.client.get(reverse("account:register"))
        self.assertEqual(get_resp.status_code, 200)
        csrf = self._get_csrf(get_resp)
        self.assertIsNotNone(csrf)

        # 2. POST registration
        post_data = {
            "csrfmiddlewaretoken": csrf,
            "first_name": "Test",
            "email": "test@example.com",
            "password1": "SecurePass123!",
            "password2": "SecurePass123!",
        }
        reg_resp = self.client.post(reverse("account:register"), post_data, follow=True)
        self.assertEqual(reg_resp.status_code, 200)
        self.assertTrue(reg_resp.wsgi_request.user.is_authenticated)
        self.assertEqual(reg_resp.wsgi_request.user.email, "test@example.com")

        # 3. Logout (use view; client loses session)
        self.client.get(reverse("account:logout"), follow=True)
        check = self.client.get(reverse("landing"))
        self.assertFalse(check.wsgi_request.user.is_authenticated)

        # 4. GET login page for CSRF
        login_get = self.client.get(reverse("account:login"))
        csrf = self._get_csrf(login_get)

        # 5. POST login
        login_resp = self.client.post(
            reverse("account:login"),
            {
                "csrfmiddlewaretoken": csrf,
                "email": "test@example.com",
                "password": "SecurePass123!",
            },
            follow=True,
        )
        self.assertEqual(login_resp.status_code, 200)
        self.assertTrue(login_resp.wsgi_request.user.is_authenticated)

    def test_login_redirects_when_authenticated(self):
        User.objects.create_user(email="u@x.com", password="pass")
        self.client.login(username="u@x.com", password="pass")
        r = self.client.get(reverse("account:login"), follow=False)
        self.assertEqual(r.status_code, 302)
        self.client.get(reverse("account:logout"))

    def test_register_redirects_when_authenticated(self):
        User.objects.create_user(email="u2@x.com", password="pass")
        self.client.login(username="u2@x.com", password="pass")
        r = self.client.get(reverse("account:register"), follow=False)
        self.assertEqual(r.status_code, 302)
