from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from executives.models import Executive, ExecutiveToken
from calls.models import AgoraCallHistory
from users.models import UserProfile, Rating
from django.utils import timezone
from datetime import timedelta
import uuid

class ExecutiveUpdateAPITestCase(APITestCase):
    def setUp(self):
        # Create Executive
        self.executive = Executive.objects.create(
            mobile_number="+919999999999",
            name="Test Executive",
            executive_id="TEY0001",
            is_verified=True
        )
        self.executive.set_password("execpass")
        self.executive.save()

        # Generate Token for Executive
        self.token = ExecutiveToken.objects.create(
            executive=self.executive,
            access_token=str(uuid.uuid4()),
            refresh_token=str(uuid.uuid4()),
            expires_at=timezone.now() + timedelta(days=1)
        )
        self.headers = {'HTTP_X_EXECUTIVE_TOKEN': self.token.access_token}

        # Create User
        self.user = UserProfile.objects.create(
            mobile_number="+918888888888",
            name="Test User"
        )

        # The URL in urls.py is path('executive/<int:id>/update/', ExecutiveUpdateByIDAPIView.as_view(), name='executive-update-by-id')
        self.url = f'/executives/executive/{self.executive.id}/update/'

    def test_no_calls_returns_zero(self):
        response = self.client.get(self.url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Check standard executive fields
        self.assertEqual(response.data['name'], "Test Executive")
        # Check aggregated fields
        self.assertEqual(response.data['total_calls'], 0)
        self.assertEqual(response.data['completed_calls'], 0)
        self.assertEqual(response.data['total_call_minutes'], 0.0)
        self.assertEqual(response.data['total_earnings'], 0.0)
        self.assertEqual(response.data['earnings_today'], 0.0)
        self.assertEqual(response.data['average_rating'], 0.0)

    def test_total_call_count_and_calculations(self):
        # Create completed call 1
        AgoraCallHistory.objects.create(
            user=self.user,
            executive=self.executive,
            channel_name="test_channel_1",
            status="ended",
            duration_seconds=120, # 2 minutes
            executive_earnings=10.50,
            uid=123
        )
        # Create missed call
        AgoraCallHistory.objects.create(
            user=self.user,
            executive=self.executive,
            channel_name="test_channel_2",
            status="missed",
            uid=124
        )
        # Create another completed call
        AgoraCallHistory.objects.create(
            user=self.user,
            executive=self.executive,
            channel_name="test_channel_3",
            status="ended",
            duration_seconds=90, # 1.5 minutes
            executive_earnings=5.25,
            uid=125
        )

        # Create rating
        Rating.objects.create(
            user=self.user,
            executive=self.executive,
            rating=4,
            comment="Good"
        )

        response = self.client.get(self.url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total_calls'], 3)
        self.assertEqual(response.data['completed_calls'], 2)
        self.assertEqual(response.data['missed_calls'], 1)
        self.assertEqual(response.data['total_call_minutes'], 3.5) # (120+90)/60 = 3.5
        self.assertEqual(response.data['total_earnings'], 15.75) # 10.50 + 5.25
        self.assertEqual(response.data['earnings_today'], 15.75) # both calls are today
        self.assertEqual(response.data['average_rating'], 4.0)

    def test_earnings_today_only_counts_todays_calls(self):
        """Calls from yesterday must NOT appear in earnings_today."""
        # Yesterday's completed call
        yesterday_call = AgoraCallHistory.objects.create(
            user=self.user,
            executive=self.executive,
            channel_name="yesterday_channel",
            status="ended",
            duration_seconds=60,
            executive_earnings=20.00,
            uid=200
        )
        # Back-date created_at to yesterday
        AgoraCallHistory.objects.filter(pk=yesterday_call.pk).update(
            created_at=timezone.now() - timedelta(days=1)
        )

        # Today's completed call
        AgoraCallHistory.objects.create(
            user=self.user,
            executive=self.executive,
            channel_name="today_channel",
            status="ended",
            duration_seconds=60,
            executive_earnings=5.00,
            uid=201
        )

        response = self.client.get(self.url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total_earnings'], 25.00)   # 20 + 5
        self.assertEqual(response.data['earnings_today'], 5.00)    # only today's call

    def test_permission_denied(self):
        # Unauthenticated
        response = self.client.get(self.url)
        # ExecutiveTokenAuthentication returns None if no header, then IsAuthenticated returns 403 or 401 depending on DRF configuration
        # Base on authentication.py: it returns None if no token.
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
