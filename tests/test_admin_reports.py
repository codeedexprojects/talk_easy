from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from users.models import UserProfile, Report
from executives.models import Executive
from payments.models import UserRecharge, RechargePlan, RechargePlanCatogary
from calls.models import AgoraCallHistory
from accounts.models import Admin
from rest_framework_simplejwt.tokens import RefreshToken
from django.utils import timezone
from datetime import timedelta

class AdminReportSummaryTestCase(APITestCase):
    def setUp(self):
        # Create Admin
        self.admin = Admin.objects.create(
            email="admin@test.com",
            mobile_number="+911234567890",
            name="Super Admin",
            is_staff=True,
            is_superuser=True,
            role="superuser"
        )
        self.admin.set_password("adminpass")
        self.admin.save()
        
        refresh = RefreshToken.for_user(self.admin)
        self.admin_token = str(refresh.access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.admin_token}')

        # Advance User ID so it doesn't match admin ID
        for i in range(5):
             UserProfile.objects.create(mobile_number=f"000000000{i}")

        # Non-admin user
        self.regular_user = UserProfile.objects.create(
            mobile_number="9876543210", 
            name="Regular User",
            is_active=True
        )
        
        # User 2
        self.banned_user = UserProfile.objects.create(
            mobile_number="9876543211", 
            name="Banned",
            is_banned=True,
            is_active=True
        )

        # Executive
        self.exec_user = Executive.objects.create(
            mobile_number="9998887776",
            name="Active Exec",
            executive_id="EX-01",
            status="active"
        )
        
        self.inactive_exec = Executive.objects.create(
            mobile_number="9998887775",
            name="Inactive Exec",
            executive_id="EX-02",
            status="inactive"
        )

        # Payments
        category = RechargePlanCatogary.objects.create(name="Cat 1")
        plan = RechargePlan.objects.create(plan_name="Plan 1", coin_package=100, base_price=10.0, category_id=category)
        
        self.recharge_success = UserRecharge.objects.create(
            user=self.regular_user,
            plan=plan,
            coins_added=100,
            amount_paid=10.00,
            payment_status='successful',
            is_successful=True
        )
        
        self.recharge_fail = UserRecharge.objects.create(
            user=self.regular_user,
            plan=plan,
            coins_added=100,
            amount_paid=10.00,
            payment_status='failed',
            is_successful=False
        )

        # Calls
        self.call_ended = AgoraCallHistory.objects.create(
            user=self.regular_user,
            executive=self.exec_user,
            channel_name="ch_1",
            token="token1",
            executive_token="exec1",
            uid=1,
            status="ended"
        )
        self.call_ended.start_time = timezone.now() - timedelta(days=2)
        self.call_ended.save()
        
        self.call_missed = AgoraCallHistory.objects.create(
            user=self.regular_user,
            executive=self.exec_user,
            channel_name="ch_2",
            token="token2",
            executive_token="exec2",
            uid=2,
            status="missed"
        )

        # Reports
        self.report_pending = Report.objects.create(
            reporter_user=self.regular_user,
            reported_executive=self.inactive_exec,
            reason="Spam",
            status="pending"
        )
        
        self.report_resolved = Report.objects.create(
            reporter_user=self.regular_user,
            reported_executive=self.exec_user,
            reason="Fraud",
            status="resolved"
        )
        
        # Override dates for filtering test
        self.report_pending.created_at = timezone.now() - timedelta(days=5)
        self.report_pending.save()
        
        # Test endpoint
        self.url = '/users/admin/reports/'

    def test_permission_denied_for_non_admin(self):
        self.client.credentials()  # Remove auth
        # Try as unauthenticated
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        
        # Try as regular user
        from users.utils import create_tokens_for_userprofile
        user_tokens = create_tokens_for_userprofile(self.regular_user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {user_tokens['access']}")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_admin_report_summary_counts(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        data = response.json()
        self.assertIn('summary', data)
        self.assertIn('reports', data)
        
        # Verify summaries
        summary = data['summary']
        self.assertEqual(summary['users']['total'], 7)
        self.assertEqual(summary['users']['active'], 6)
        self.assertEqual(summary['users']['banned'], 1)
        
        self.assertEqual(summary['executives']['total'], 2)
        self.assertEqual(summary['executives']['active'], 1)
        self.assertEqual(summary['executives']['inactive'], 1)
        
        self.assertEqual(summary['payments']['total_transactions'], 2)
        self.assertEqual(summary['payments']['successful'], 1)
        self.assertEqual(summary['payments']['failed'], 1)
        # amount_paid is 10.0 for successful
        self.assertEqual(summary['payments']['total_amount'], 10.0)
        
        self.assertEqual(summary['calls']['total_calls'], 2)
        self.assertEqual(summary['calls']['completed'], 1)
        self.assertEqual(summary['calls']['missed'], 1)
        
        # Verify reports pagination
        reports = data['reports']
        self.assertEqual(reports['count'], 2)

    def test_status_filtering(self):
        response = self.client.get(self.url + '?status=resolved')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        
        self.assertEqual(data['reports']['count'], 1)
        self.assertEqual(data['reports']['results'][0]['status'], 'resolved')

    def test_date_filtering(self):
        # We set one report to -5 days ago. Now is 0 days.
        # Start date = today
        start_date = timezone.now().date().isoformat()
        response = self.client.get(f"{self.url}?start_date={start_date}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        
        # Report -5 days ago should be excluded
        self.assertEqual(data['reports']['count'], 1) # only resolved report is from today
        self.assertEqual(data['reports']['results'][0]['status'], 'resolved')
        
        # Verify date filtering applies to summary as well
        # We set one call to -2 days ago
        self.assertEqual(data['summary']['calls']['completed'], 0) # since the ended call was 2 days ago
        self.assertEqual(data['summary']['calls']['missed'], 1) # missed call is from today
