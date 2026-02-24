from rest_framework.test import APITestCase
from rest_framework import status
from django.urls import reverse
from users.models import UserProfile, UserStats
from executives.models import Executive, ExecutiveStats, ExecutiveToken
from calls.models import AgoraCallHistory
from rest_framework_simplejwt.tokens import RefreshToken
from datetime import timedelta
from django.utils import timezone
import logging

class EndCallAPITests(APITestCase):
    def setUp(self):
        logging.getLogger('calls').setLevel(logging.CRITICAL)  # Suppress logs for tests
        
        # Setup User
        self.user = UserProfile.objects.create(mobile_number="1234567890", name="Test User")
        self.user.stats.coin_balance = 1000
        self.user.stats.save()
        
        # Setup Executive
        self.executive = Executive.objects.create(
            mobile_number="0987654321", name="Test Exec", executive_id="EXE007"
        )
        ExecutiveStats.objects.create(executive=self.executive, amount_per_min=10.0, coins_per_second=2.0)
        self.exec_token_obj = ExecutiveToken.generate(self.executive)
        self.exec_token = self.exec_token_obj.access_token
        
        # Calls
        self.call_user = AgoraCallHistory.objects.create(
            user=self.user,
            executive=self.executive,
            channel_name="test_user_chan",
            token="test-token-1",
            executive_token="test-exec-token-1",
            uid=123,
            status="joined",
            is_active=True,
            joined_at=timezone.now() - timedelta(minutes=5),
            coins_per_second=2.0,
            amount_per_min=10.0
        )

        self.call_exec = AgoraCallHistory.objects.create(
            user=self.user,
            executive=self.executive,
            channel_name="test_exec_chan",
            token="test-token-2",
            executive_token="test-exec-token-2",
            uid=124,
            status="joined",
            is_active=True,
            joined_at=timezone.now() - timedelta(minutes=5),
            coins_per_second=2.0,
            amount_per_min=10.0
        )

    def test_user_end_call_success(self):
        url = reverse('user-end-call', kwargs={'call_id': self.call_user.id})
        self.client.force_authenticate(user=self.user)
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['ok'])
        self.assertEqual(response.data['message'], "Call ended by user")
        
        self.call_user.refresh_from_db()
        self.assertEqual(self.call_user.status, "ended")
        self.assertEqual(self.call_user.ended_by, "user")
        self.assertFalse(self.call_user.is_active)

    def test_user_end_call_insufficient_balance(self):
        self.user.stats.coin_balance = 0
        self.user.stats.save()
        
        url = reverse('user-end-call', kwargs={'call_id': self.call_user.id})
        self.client.force_authenticate(user=self.user)
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['ok'])
        self.assertEqual(response.data['message'], "Insufficient balance, call ended automatically")
        
        self.call_user.refresh_from_db()
        self.assertEqual(self.call_user.status, "ended")
        self.assertEqual(self.call_user.ended_by, "system")
        self.assertFalse(self.call_user.is_active)

    def test_executive_end_call_success(self):
        url = reverse('executive-end-call', kwargs={'call_id': self.call_exec.id})
        self.client.credentials(HTTP_X_EXECUTIVE_TOKEN=self.exec_token)
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['ok'])
        self.assertEqual(response.data['message'], "Call ended by executive")
        
        self.call_exec.refresh_from_db()
        self.assertEqual(self.call_exec.status, "ended")
        self.assertEqual(self.call_exec.ended_by, "executive")
        self.assertFalse(self.call_exec.is_active)
