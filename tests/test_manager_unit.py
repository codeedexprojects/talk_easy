"""
test_manager_unit.py — Comprehensive unit tests for the unified 'manager' role.

Run with:
    python manage.py test tests.test_manager_unit --verbosity=2

URL reference (accounts/ prefix from talkeasy/urls.py):
    POST /accounts/managers/create/              → ManagerCreateView
    POST /accounts/managers/login/               → ManagerLoginView
    GET  /accounts/managers/                     → ManagerListView
    GET  /accounts/managers/<pk>/               → ManagerDetailView
    PATCH /accounts/permissions/<pk>/update/     → UpdateAdminPermissionsView
    DELETE /accounts/manager-executives/<pk>/delete/   → ManagerExecutiveDeleteView
    DELETE /accounts/manager-users/<pk>/delete/        → ManagerUserDeleteView
    POST /accounts/create-manager/              → Legacy ManagerExecutiveCreateView
    POST /accounts/login-manager/               → Legacy ManagerExecutiveLoginView
    POST /accounts/create-manager-user/         → Legacy ManagerUserCreateView
    POST /accounts/login-manager-user/          → Legacy ManagerUserLoginView

Coverage:
  - Model helper properties: is_manager, is_manager_executive, is_manager_user
  - ROLE_CHOICES: no longer contains manager_user / manager_executive
  - ManagerCreateSerializer: create exec/user level, default level, invalid level
  - ManagerLoginSerializer: happy path, wrong role, banned, inactive
  - API views: create, login, list, detail, delete, permissions update
  - Legacy endpoints still produce role='manager'
  - QuerySet filtering after migration
  - Bulk create 10 managers
  - Edge cases: duplicate email, missing fields
"""

import unittest
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from accounts.models import Admin, AdminSession
from accounts.serializers import (
    ManagerCreateSerializer,
    ManagerLoginSerializer,
    ManagerExecutiveCreateSerializer,
    ManagerUserCreateSerializer,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_superuser(email='super@test.com', password='Admin@123'):
    su = Admin.objects.create(email=email, name='Superuser', mobile_number='+910000000001')
    su.set_password(password)
    su.role = 'superuser'
    su.is_superuser = True
    su.is_staff = True
    su.save()
    return su


def _make_manager(email='mgr@test.com', level='executive', mobile='+910000000002', password='Mgr@12345'):
    mgr = Admin.objects.create(
        email=email,
        name='Test Manager',
        mobile_number=mobile,
        role='manager',
        custom_permissions={'manager_level': level},
    )
    mgr.set_password(password)
    mgr.save()
    return mgr


# ─────────────────────────────────────────────────────────────────────────────
# Model Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestAdminModelManagerProperties(TestCase):
    """Tests for Admin model helper properties."""

    def test_role_choices_no_longer_has_manager_user(self):
        choices_values = [c[0] for c in Admin.ROLE_CHOICES]
        self.assertNotIn('manager_user', choices_values)

    def test_role_choices_no_longer_has_manager_executive(self):
        choices_values = [c[0] for c in Admin.ROLE_CHOICES]
        self.assertNotIn('manager_executive', choices_values)

    def test_role_choices_has_manager(self):
        choices_values = [c[0] for c in Admin.ROLE_CHOICES]
        self.assertIn('manager', choices_values)

    def test_is_manager_true_for_manager_role(self):
        mgr = _make_manager(email='m1@test.com', mobile='+91111')
        self.assertTrue(mgr.is_manager)

    def test_is_manager_false_for_superuser(self):
        su = _make_superuser(email='su1@test.com')
        self.assertFalse(su.is_manager)

    def test_is_manager_false_for_other(self):
        admin = Admin.objects.create(
            email='other@test.com', name='Other', mobile_number='+91222', role='other',
        )
        self.assertFalse(admin.is_manager)

    def test_is_manager_executive_true(self):
        mgr = _make_manager(email='me1@test.com', level='executive', mobile='+91333')
        self.assertTrue(mgr.is_manager_executive)
        self.assertFalse(mgr.is_manager_user)

    def test_is_manager_user_true(self):
        mgr = _make_manager(email='mu1@test.com', level='user', mobile='+91444')
        self.assertTrue(mgr.is_manager_user)
        self.assertFalse(mgr.is_manager_executive)

    def test_is_manager_executive_false_when_custom_permissions_is_list(self):
        """Legacy data: custom_permissions is a list — properties degrade gracefully."""
        mgr = Admin.objects.create(
            email='legacy@test.com', name='Legacy', mobile_number='+91555',
            role='manager', custom_permissions=[],
        )
        self.assertTrue(mgr.is_manager)
        self.assertFalse(mgr.is_manager_executive)
        self.assertFalse(mgr.is_manager_user)

    def test_is_manager_executive_false_when_no_level_set(self):
        """Manager with empty dict custom_permissions has no level — both are False."""
        mgr = Admin.objects.create(
            email='nolevel@test.com', name='NoLevel', mobile_number='+91666',
            role='manager', custom_permissions={},
        )
        self.assertTrue(mgr.is_manager)
        self.assertFalse(mgr.is_manager_executive)
        self.assertFalse(mgr.is_manager_user)


# ─────────────────────────────────────────────────────────────────────────────
# Serializer Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestManagerCreateSerializer(TestCase):

    def test_create_executive_level(self):
        data = {
            'name': 'Exec Mgr', 'email': 'exec@test.com',
            'mobile_number': '+919000000001', 'password': 'Pass@1234',
            'manager_level': 'executive',
        }
        ser = ManagerCreateSerializer(data=data)
        self.assertTrue(ser.is_valid(), ser.errors)
        mgr = ser.save()
        self.assertEqual(mgr.role, 'manager')
        self.assertEqual(mgr.custom_permissions.get('manager_level'), 'executive')
        self.assertTrue(mgr.is_manager_executive)

    def test_create_user_level(self):
        data = {
            'name': 'User Mgr', 'email': 'usermgr@test.com',
            'mobile_number': '+919000000002', 'password': 'Pass@1234',
            'manager_level': 'user',
        }
        ser = ManagerCreateSerializer(data=data)
        self.assertTrue(ser.is_valid(), ser.errors)
        mgr = ser.save()
        self.assertEqual(mgr.role, 'manager')
        self.assertEqual(mgr.custom_permissions.get('manager_level'), 'user')
        self.assertTrue(mgr.is_manager_user)

    def test_default_level_is_user(self):
        data = {
            'name': 'Default Mgr', 'email': 'default@test.com',
            'mobile_number': '+919000000003', 'password': 'Pass@1234',
        }
        ser = ManagerCreateSerializer(data=data)
        self.assertTrue(ser.is_valid(), ser.errors)
        mgr = ser.save()
        self.assertEqual(mgr.custom_permissions.get('manager_level'), 'user')

    def test_invalid_manager_level(self):
        data = {
            'name': 'Bad Mgr', 'email': 'bad@test.com',
            'mobile_number': '+919000000004', 'password': 'Pass@1234',
            'manager_level': 'god_mode',
        }
        ser = ManagerCreateSerializer(data=data)
        self.assertFalse(ser.is_valid())
        self.assertIn('manager_level', ser.errors)

    def test_missing_email_invalid(self):
        data = {'name': 'No Email', 'mobile_number': '+919000000005', 'password': 'Pass@1234'}
        ser = ManagerCreateSerializer(data=data)
        self.assertFalse(ser.is_valid())
        self.assertIn('email', ser.errors)

    def test_duplicate_email_invalid(self):
        Admin.objects.create(
            email='dup@test.com', name='Existing', mobile_number='+919000000006',
        )
        data = {
            'name': 'Dup Mgr', 'email': 'dup@test.com',
            'mobile_number': '+919000000099', 'password': 'Pass@1234',
        }
        ser = ManagerCreateSerializer(data=data)
        self.assertFalse(ser.is_valid())
        self.assertIn('email', ser.errors)


class TestManagerLoginSerializer(TestCase):

    def setUp(self):
        self.mgr = _make_manager(email='login_mgr@test.com', level='executive', mobile='+919100000001')

    def test_valid_login_returns_tokens(self):
        data = {'email': 'login_mgr@test.com', 'password': 'Mgr@12345'}
        ser = ManagerLoginSerializer(data=data)
        self.assertTrue(ser.is_valid(), ser.errors)
        result = ser.validated_data
        self.assertIn('access_token', result)
        self.assertIn('refresh_token', result)
        self.assertEqual(result['role'], 'manager')
        self.assertEqual(result['manager_level'], 'executive')

    def test_wrong_role_rejected(self):
        su = _make_superuser(email='super_login@test.com')
        data = {'email': 'super_login@test.com', 'password': 'Admin@123'}
        ser = ManagerLoginSerializer(data=data)
        self.assertFalse(ser.is_valid())

    def test_invalid_password_rejected(self):
        data = {'email': 'login_mgr@test.com', 'password': 'WrongPass@1'}
        ser = ManagerLoginSerializer(data=data)
        self.assertFalse(ser.is_valid())

    def test_inactive_manager_rejected(self):
        self.mgr.is_active = False
        self.mgr.save()
        data = {'email': 'login_mgr@test.com', 'password': 'Mgr@12345'}
        ser = ManagerLoginSerializer(data=data)
        self.assertFalse(ser.is_valid())

    def test_banned_manager_rejected(self):
        self.mgr.is_banned = True
        self.mgr.save()
        data = {'email': 'login_mgr@test.com', 'password': 'Mgr@12345'}
        ser = ManagerLoginSerializer(data=data)
        self.assertFalse(ser.is_valid())


class TestBackwardCompatAliases(TestCase):
    """Deprecated alias serializers must still produce role='manager'."""

    def test_executive_alias_creates_manager_role(self):
        data = {
            'name': 'Alias Exec', 'email': 'alias_exec@test.com',
            'mobile_number': '+919200000001', 'password': 'Pass@1234',
        }
        ser = ManagerExecutiveCreateSerializer(data=data)
        self.assertTrue(ser.is_valid(), ser.errors)
        mgr = ser.save()
        self.assertEqual(mgr.role, 'manager')
        self.assertEqual(mgr.custom_permissions.get('manager_level'), 'executive')

    def test_user_alias_creates_manager_role(self):
        data = {
            'name': 'Alias User', 'email': 'alias_user@test.com',
            'mobile_number': '+919200000002', 'password': 'Pass@1234',
        }
        ser = ManagerUserCreateSerializer(data=data)
        self.assertTrue(ser.is_valid(), ser.errors)
        mgr = ser.save()
        self.assertEqual(mgr.role, 'manager')
        self.assertEqual(mgr.custom_permissions.get('manager_level'), 'user')


# ─────────────────────────────────────────────────────────────────────────────
# API / View Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestManagerCreateViewAPI(TestCase):
    """POST /accounts/managers/create/"""

    def setUp(self):
        self.client = APIClient()
        self.su = _make_superuser()
        resp = self.client.post(
            '/accounts/admin/login/',
            {'email': 'super@test.com', 'password': 'Admin@123'},
            format='json',
        )
        self.su_token = resp.data.get('access_token', '')

    def _auth(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.su_token}')

    def test_create_executive_level_manager(self):
        self._auth()
        resp = self.client.post('/accounts/managers/create/', {
            'name': 'APIExecMgr', 'email': 'apiexec@test.com',
            'mobile_number': '+919300000001', 'password': 'Pass@1234',
            'manager_level': 'executive',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['data']['role'], 'manager')
        self.assertEqual(resp.data['data']['manager_level'], 'executive')

    def test_create_user_level_manager(self):
        self._auth()
        resp = self.client.post('/accounts/managers/create/', {
            'name': 'APIUserMgr', 'email': 'apiuser@test.com',
            'mobile_number': '+919300000002', 'password': 'Pass@1234',
            'manager_level': 'user',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['data']['manager_level'], 'user')

    def test_non_superuser_cannot_create(self):
        mgr = _make_manager(email='restrictedmgr@test.com', mobile='+919300000003')
        self.client.force_authenticate(user=mgr)
        resp = self.client.post('/accounts/managers/create/', {
            'name': 'Fail', 'email': 'fail@test.com',
            'mobile_number': '+919300000004', 'password': 'Pass@1234',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_cannot_create(self):
        resp = self.client.post('/accounts/managers/create/', {
            'name': 'Unauth', 'email': 'unauth@test.com',
            'mobile_number': '+919300000005', 'password': 'Pass@1234',
        }, format='json')
        self.assertIn(resp.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])


class TestManagerLoginViewAPI(TestCase):
    """POST /accounts/managers/login/"""

    def setUp(self):
        self.client = APIClient()
        self.mgr = _make_manager(email='loginapi@test.com', level='user', mobile='+919400000001')

    def test_successful_login(self):
        resp = self.client.post('/accounts/managers/login/', {
            'email': 'loginapi@test.com', 'password': 'Mgr@12345',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn('access_token', resp.data['data'])
        self.assertEqual(resp.data['data']['manager_level'], 'user')

    def test_wrong_role_rejected(self):
        _make_superuser(email='su_login_test@test.com')
        resp = self.client.post('/accounts/managers/login/', {
            'email': 'su_login_test@test.com', 'password': 'Admin@123',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_banned_manager_cannot_login(self):
        self.mgr.is_banned = True
        self.mgr.save()
        resp = self.client.post('/accounts/managers/login/', {
            'email': 'loginapi@test.com', 'password': 'Mgr@12345',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_inactive_manager_cannot_login(self):
        self.mgr.is_active = False
        self.mgr.save()
        resp = self.client.post('/accounts/managers/login/', {
            'email': 'loginapi@test.com', 'password': 'Mgr@12345',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class TestManagerListViewAPI(TestCase):
    """GET /accounts/managers/"""

    def setUp(self):
        self.client = APIClient()
        self.su = _make_superuser()
        self.mgr1 = _make_manager(email='list1@test.com', level='executive', mobile='+919500000001')
        self.mgr2 = _make_manager(email='list2@test.com', level='user', mobile='+919500000002')

    def test_list_returns_all_managers(self):
        self.client.force_authenticate(user=self.su)
        resp = self.client.get('/accounts/managers/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        emails = [m['email'] for m in resp.data]
        self.assertIn('list1@test.com', emails)
        self.assertIn('list2@test.com', emails)

    def test_list_does_not_include_superuser(self):
        self.client.force_authenticate(user=self.su)
        resp = self.client.get('/accounts/managers/')
        emails = [m['email'] for m in resp.data]
        self.assertNotIn('super@test.com', emails)

    def test_unauthenticated_rejected(self):
        resp = self.client.get('/accounts/managers/')
        self.assertIn(resp.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])


class TestManagerDetailViewAPI(TestCase):
    """GET /accounts/managers/<pk>/"""

    def setUp(self):
        self.client = APIClient()
        self.su = _make_superuser()
        self.mgr = _make_manager(email='detail@test.com', level='executive', mobile='+919600000001')

    def test_get_manager_detail(self):
        self.client.force_authenticate(user=self.su)
        resp = self.client.get(f'/accounts/managers/{self.mgr.id}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['data']['email'], 'detail@test.com')

    def test_404_for_non_manager(self):
        self.client.force_authenticate(user=self.su)
        resp = self.client.get(f'/accounts/managers/{self.su.id}/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_404_for_nonexistent_id(self):
        self.client.force_authenticate(user=self.su)
        resp = self.client.get('/accounts/managers/99999/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


class TestManagerDeleteViewAPI(TestCase):
    """DELETE /accounts/manager-executives/<pk>/delete/ and /accounts/manager-users/<pk>/delete/"""

    def setUp(self):
        self.client = APIClient()
        self.su = _make_superuser()

    def test_delete_via_executive_endpoint(self):
        mgr = _make_manager(email='del_exec@test.com', level='executive', mobile='+919700000001')
        self.client.force_authenticate(user=self.su)
        resp = self.client.delete(f'/accounts/manager-executives/{mgr.id}/delete/')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Admin.objects.filter(id=mgr.id).exists())

    def test_delete_via_user_endpoint(self):
        mgr = _make_manager(email='del_user@test.com', level='user', mobile='+919700000002')
        self.client.force_authenticate(user=self.su)
        resp = self.client.delete(f'/accounts/manager-users/{mgr.id}/delete/')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Admin.objects.filter(id=mgr.id).exists())

    def test_non_superuser_cannot_delete(self):
        mgr_a = _make_manager(email='del_a@test.com', level='user', mobile='+919700000003')
        mgr_b = _make_manager(email='del_b@test.com', level='user', mobile='+919700000004')
        self.client.force_authenticate(user=mgr_a)
        resp = self.client.delete(f'/accounts/manager-users/{mgr_b.id}/delete/')
        self.assertIn(resp.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_401_UNAUTHORIZED])


class TestUpdateAdminPermissionsViewAPI(TestCase):
    """PATCH /accounts/permissions/<pk>/update/"""

    def setUp(self):
        self.client = APIClient()
        self.su = _make_superuser()
        self.mgr = _make_manager(email='perm_mgr@test.com', level='user', mobile='+919800000001')

    def test_superuser_can_update_permissions(self):
        self.client.force_authenticate(user=self.su)
        resp = self.client.patch(
            f'/accounts/permissions/{self.mgr.id}/update/',
            {'custom_permissions': {'manager_level': 'executive', 'can_view_reports': True}},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.mgr.refresh_from_db()
        self.assertEqual(self.mgr.custom_permissions.get('manager_level'), 'executive')
        self.assertTrue(self.mgr.custom_permissions.get('can_view_reports'))

    def test_non_superuser_cannot_update_permissions(self):
        other_mgr = _make_manager(email='other_perm@test.com', mobile='+919800000002')
        self.client.force_authenticate(user=other_mgr)
        resp = self.client.patch(
            f'/accounts/permissions/{self.mgr.id}/update/',
            {'custom_permissions': {'manager_level': 'executive'}},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class TestBulkManagerCreation(TestCase):
    """Create 10 managers and verify all retain correct role and permissions."""

    def test_bulk_create_10_managers(self):
        for i in range(10):
            level = 'executive' if i % 2 == 0 else 'user'
            data = {
                'name': f'BulkMgr{i}',
                'email': f'bulk{i}@test.com',
                'mobile_number': f'+9195000{i:05d}',
                'password': 'Pass@1234',
                'manager_level': level,
            }
            ser = ManagerCreateSerializer(data=data)
            self.assertTrue(ser.is_valid(), ser.errors)
            mgr = ser.save()
            self.assertEqual(mgr.role, 'manager')
            self.assertEqual(mgr.custom_permissions.get('manager_level'), level)

        self.assertEqual(Admin.objects.filter(role='manager').count(), 10)
        self.assertEqual(Admin.objects.filter(role='manager_user').count(), 0)
        self.assertEqual(Admin.objects.filter(role='manager_executive').count(), 0)


class TestLegacyEndpointsStillWork(TestCase):
    """Old URL paths still produce role='manager' after migration."""

    def setUp(self):
        self.client = APIClient()
        self.su = _make_superuser()

    def test_legacy_executive_create_endpoint(self):
        # POST /accounts/create-manager/ → ManagerExecutiveCreateView
        self.client.force_authenticate(user=self.su)
        resp = self.client.post('/accounts/create-manager/', {
            'name': 'LegacyExec', 'email': 'legacyexec@test.com',
            'mobile_number': '+919900000001', 'password': 'Pass@1234',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        mgr = Admin.objects.get(email='legacyexec@test.com')
        self.assertEqual(mgr.role, 'manager')
        self.assertEqual(mgr.custom_permissions.get('manager_level'), 'executive')

    def test_legacy_user_create_endpoint(self):
        # POST /accounts/create-manager-user/ → ManagerUserCreateView
        self.client.force_authenticate(user=self.su)
        resp = self.client.post('/accounts/create-manager-user/', {
            'name': 'LegacyUser', 'email': 'legacyuser@test.com',
            'mobile_number': '+919900000002', 'password': 'Pass@1234',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        mgr = Admin.objects.get(email='legacyuser@test.com')
        self.assertEqual(mgr.role, 'manager')
        self.assertEqual(mgr.custom_permissions.get('manager_level'), 'user')

    def test_legacy_executive_login_endpoint(self):
        # POST /accounts/login-manager/ → ManagerExecutiveLoginView
        _make_manager(email='legloginexec@test.com', level='executive', mobile='+919900000003')
        resp = self.client.post('/accounts/login-manager/', {
            'email': 'legloginexec@test.com', 'password': 'Mgr@12345',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_legacy_user_login_endpoint(self):
        # POST /accounts/login-manager-user/ → ManagerUserLoginView
        _make_manager(email='legloginuser@test.com', level='user', mobile='+919900000004')
        resp = self.client.post('/accounts/login-manager-user/', {
            'email': 'legloginuser@test.com', 'password': 'Mgr@12345',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)


class TestQueryFilteringAfterMigration(TestCase):
    """Verify that ORM queries work correctly after the migration."""

    def setUp(self):
        _make_superuser()
        _make_manager(email='qf1@test.com', level='executive', mobile='+919910000001')
        _make_manager(email='qf2@test.com', level='user', mobile='+919910000002')

    def test_startswith_manager_query_finds_all_managers(self):
        managers = Admin.objects.filter(role__startswith='manager')
        self.assertEqual(managers.count(), 2)

    def test_exact_manager_role_query(self):
        self.assertEqual(Admin.objects.filter(role='manager').count(), 2)

    def test_old_roles_return_zero(self):
        self.assertEqual(Admin.objects.filter(role='manager_user').count(), 0)
        self.assertEqual(Admin.objects.filter(role='manager_executive').count(), 0)

    def test_filter_executive_by_custom_permissions(self):
        exec_managers = Admin.objects.filter(
            role='manager',
            custom_permissions__manager_level='executive',
        )
        self.assertEqual(exec_managers.count(), 1)

    def test_filter_user_by_custom_permissions(self):
        user_managers = Admin.objects.filter(
            role='manager',
            custom_permissions__manager_level='user',
        )
        self.assertEqual(user_managers.count(), 1)


if __name__ == '__main__':
    import unittest
    unittest.main()
