from unittest import mock

from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate
from rest_framework_simplejwt.tokens import AccessToken

from users.authentication import UserProfileJWTAuthentication
from users.models import UserProfile
from users.utils import create_tokens_for_userprofile, is_token_blacklisted
from users.views import LogoutView


@mock.patch("users.views.clear_fcm_token", wraps=lambda instance, topics: (
    setattr(instance, "fcm_token", None) or True
))
class UserLogoutTestCase(TestCase):
    """FCM topic calls are mocked out — Firebase isn't reachable from tests."""

    def setUp(self):
        self.user = UserProfile.objects.create(
            mobile_number="9000000001",
            name="Logout Test User",
            is_verified=True,
            is_loginned=True,
            is_online=True,
            fcm_token="device-token-abc",
        )
        self.tokens = create_tokens_for_userprofile(self.user)
        self.factory = APIRequestFactory()

    def logout(self, body=None, user=None, token=None):
        request = self.factory.post("/users/logout/", body or {}, format="json")
        force_authenticate(
            request,
            user=user or self.user,
            token=token or AccessToken(self.tokens["access"]),
        )
        return LogoutView.as_view()(request)

    def test_logout_revokes_tokens_clears_fcm_and_marks_offline(self, _mock_clear):
        access = AccessToken(self.tokens["access"])

        response = self.logout({"refresh_token": self.tokens["refresh"]}, token=access)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["access_token_revoked"])
        self.assertTrue(response.data["refresh_token_revoked"])
        self.assertTrue(response.data["fcm_token_cleared"])

        # Both the presented access token and the refresh token stop authenticating.
        self.assertTrue(is_token_blacklisted(access.payload["jti"]))

        self.user.refresh_from_db()
        self.assertIsNone(self.user.fcm_token)
        self.assertFalse(self.user.is_loginned)
        self.assertFalse(self.user.is_online)

    def test_logout_leaves_account_active(self, _mock_clear):
        """Logging out ends a session — it must not deactivate the account."""
        self.logout({"refresh_token": self.tokens["refresh"]})

        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)

    def test_revoked_access_token_is_rejected_on_next_request(self, _mock_clear):
        access = AccessToken(self.tokens["access"])
        self.logout({"refresh_token": self.tokens["refresh"]}, token=access)

        auth = UserProfileJWTAuthentication()
        follow_up = self.factory.get(
            "/users/me/", HTTP_AUTHORIZATION=f"Bearer {self.tokens['access']}"
        )

        with self.assertRaises(Exception) as ctx:
            auth.authenticate(follow_up)

        self.assertIn("blacklisted", str(ctx.exception).lower())

    def test_logout_without_refresh_token_still_revokes_access(self, _mock_clear):
        response = self.logout({})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["access_token_revoked"])
        self.assertFalse(response.data["refresh_token_revoked"])

    def test_invalid_refresh_token_is_rejected(self, _mock_clear):
        response = self.logout({"refresh_token": "not-a-real-token"})

        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertEqual(self.user.fcm_token, "device-token-abc")

    def test_cannot_revoke_another_users_refresh_token(self, _mock_clear):
        other = UserProfile.objects.create(mobile_number="9000000002", name="Other")
        other_tokens = create_tokens_for_userprofile(other)

        response = self.logout({"refresh_token": other_tokens["refresh"]})

        self.assertEqual(response.status_code, 403)
        other.refresh_from_db()
        self.assertTrue(other.is_active)
