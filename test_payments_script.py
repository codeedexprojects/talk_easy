
import os
import django
import requests
import sys
import uuid
import argparse
from datetime import timedelta
from django.utils import timezone
import hmac
import hashlib

# Add the project root to sys.path
sys.path.append('/home/muhammed-fazal/Desktop/talk_easy')

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'talkeasy.settings')
django.setup()

from django.conf import settings
from users.models import UserProfile
from users.utils import create_tokens_for_userprofile
from payments.models import RechargePlan, RechargePlanCatogary, RedemptionOption
from executives.models import Executive, ExecutiveStats, ExecutiveToken
from accounts.models import Admin
from rest_framework_simplejwt.tokens import RefreshToken

# --- Parse Arguments ---
parser = argparse.ArgumentParser(description='Test TalkEasy Payment APIs')
parser.add_argument('--production', action='store_true', help='Test against production URL')
parser.add_argument('--url', type=str, help='Custom base URL to test against')
parser.add_argument('--token', type=str, help='Bearer token for production testing')
args = parser.parse_args()

# --- Constants ---
if args.url:
    BASE_URL = args.url.rstrip('/')  # Remove trailing slash if present
elif args.production:
    BASE_URL = "https://core.koottuapp.in"
else:
    BASE_URL = "http://127.0.0.1:8000"

USER_MOBILE = '9876543210'
EXECUTIVE_MOBILE = '9876543211'

print(f"\n{'='*60}")
print(f"Testing against: {BASE_URL}")
print(f"Mode: {'PRODUCTION' if args.production or args.url else 'LOCAL'}")
print(f"{'='*60}\n")

def header_print(text):
    print(f"\n{'='*60}\n{text}\n{'='*60}")

def sub_header_print(text):
    print(f"\n--- {text} ---")

# --- Setup Helpers ---

def setup_user_data():
    header_print("SETTING UP USER DATA")
    
    # 1. Create Plan
    print("Creating/Getting Test Plan...")
    category, _ = RechargePlanCatogary.objects.get_or_create(name="Test Category")
    plan, created = RechargePlan.objects.get_or_create(
        plan_name="Test Plan 100",
        defaults={
            'base_price': 100.0,
            'coin_package': 1000,
            'is_active': True,
            'category_id': category
        }
    )
    print(f"Plan ID: {plan.id}")

    # 2. Create User
    print("Creating/Getting Test User...")
    user = UserProfile.objects.filter(mobile_number=USER_MOBILE).first()
    if not user:
        user = UserProfile.objects.create(
            mobile_number=USER_MOBILE,
            name='Test User',
            email='test@example.com'
        )
    print(f"User ID: {user.id}")

    # 3. Generate Token
    print("Generating User Token...")
    tokens = create_tokens_for_userprofile(user)
    return user, tokens['access'], plan

def setup_executive_data():
    header_print("SETTING UP EXECUTIVE DATA")
    
    # 1. Create Executive
    print("Creating/Getting Test Executive...")
    executive = Executive.objects.filter(mobile_number=EXECUTIVE_MOBILE).first()
    if not executive:
        executive = Executive.objects.create(
            mobile_number=EXECUTIVE_MOBILE,
            name='Test Executive',
            email_id='exec@example.com',
            is_verified=True,
            executive_id='TEY-TEST'
        )
        executive.set_password('password123')
        executive.save()
    
    # Ensure Stats Exist
    stats, _ = ExecutiveStats.objects.get_or_create(executive=executive)
    # Add sufficient funds for redemption test
    stats.pending_payout = 5000.00
    stats.save()
    
    print(f"Executive ID: {executive.id}")

    # 2. Generate Token (Manual DB creation as per logic)
    print("Generating Executive Token...")
    access_token = str(uuid.uuid4())
    ExecutiveToken.objects.create(
        executive=executive,
        access_token=access_token,
        refresh_token=str(uuid.uuid4()),
        expires_at=timezone.now() + timedelta(days=1)
    )
    
    # 3. Create Redemption Option
    print("Creating/Getting Redemption Option...")
    option, _ = RedemptionOption.objects.get_or_create(
        amount=500.00,
        defaults={'is_active': True}
    )

    return executive, access_token, option

def setup_admin_data():
    header_print("SETTING UP ADMIN DATA")
    email = "admin@test.com"
    password = "adminpassword"
    admin, created = Admin.objects.get_or_create(email=email)
    
    admin.name = "Super Admin"
    if created:
        admin.set_password(password)
    admin.is_superuser = True
    admin.is_staff = True
    admin.role = 'superuser'
    admin.save()
    
    print(f"Admin ID: {admin.id}")
    
    # Generate Token
    refresh = RefreshToken.for_user(admin)
    return admin, str(refresh.access_token)

# --- User Tests ---

def user_flow(user_token):
    header_print("STARTING USER SIDE TESTS")
    headers = {
        "Authorization": f"Bearer {user_token}",
        "Content-Type": "application/json"
    }

    # 1. Get Plans
    sub_header_print("1. Get Plans")
    url = f"{BASE_URL}/payments/recharge-plan-list/"
    print(f"Testing URL: {url}")
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        print(f"Response Status: {resp.status_code}")
        if resp.status_code == 200:
            print("SUCCESS: Plans Retrieved")
            plans = resp.json()
            # print(plans)
            plan_id = plans[0]['id'] if plans else None
        else:
            print(f"FAILED: {resp.status_code}")
            print(f"Response: {resp.text[:500]}")  # First 500 chars
            return
    except requests.exceptions.RequestException as e:
        print(f"REQUEST ERROR: {e}")
        return
    except Exception as e:
        print(f"ERROR: {e}")
        return

    if not plan_id:
        print("SKIP: No plans found to test recharge.")
        return

    # 2. Initiate Payment (Recharge)
    sub_header_print("2. Initiate Recharge")
    url = f"{BASE_URL}/payments/recharge/initiate/"
    print(f"Testing URL: {url}")
    data = {"plan_id": plan_id}
    order_id = None
    try:
        resp = requests.post(url, json=data, headers=headers, timeout=30)
        print(f"Response Status: {resp.status_code}")
        if resp.status_code == 200:
            print("SUCCESS: Recharge Initiated")
            order_id = resp.json().get('order_id')
            print(f"Order ID: {order_id}")
        else:
            print(f"FAILED: {resp.status_code}")
            print(f"Response: {resp.text[:500]}")  # First 500 chars
            return
    except requests.exceptions.RequestException as e:
        print(f"REQUEST ERROR: {e}")
        return
    except Exception as e:
        print(f"ERROR: {e}")
        return

    # 3. Verify Payment
    if order_id:
        sub_header_print("3. Verify Payment")
        fake_payment_id = "pay_" + order_id
        secret = settings.RAZORPAY_KEY_SECRET
        msg = f"{order_id}|{fake_payment_id}"
        signature = hmac.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest()

        url = f"{BASE_URL}/payments/recharge/verify/"
        data = {
            "razorpay_order_id": order_id,
            "razorpay_payment_id": fake_payment_id,
            "razorpay_signature": signature
        }
        
        try:
            resp = requests.post(url, json=data, headers=headers)
            if resp.status_code == 200:
                print("SUCCESS: Payment Verified")
                # print(resp.json())
            else:
                print(f"FAILED: {resp.status_code} - {resp.text}")
        except Exception as e:
            print(f"ERROR: {e}")

    # 4. Payment History
    sub_header_print("4. Payment History")
    url = f"{BASE_URL}/payments/recharge-history/"
    try:
        resp = requests.get(url, headers=headers)
        if resp.status_code == 200:
            print("SUCCESS: History Retrieved")
            print(f"Count: {len(resp.json())}")
        else:
            print(f"FAILED: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"ERROR: {e}")


# --- Executive Tests ---

def executive_flow(exec_token, option):
    header_print("STARTING EXECUTIVE SIDE TESTS")
    # Note: Executive uses X-EXECUTIVE-TOKEN header
    headers = {
        "X-EXECUTIVE-TOKEN": exec_token,
        "Content-Type": "application/json"
    }

    # 1. Get Wallet (Status)
    sub_header_print("1. Get Wallet (Status)")
    url = f"{BASE_URL}/executives/executives/status/" # As found in executives/urls.py path("executives/status/", ExecutiveStatusAPIView.as_view(), ...) - Wait, the url path in file was "executives/status/" but included in urlpatterns so it is /executives/executives/status/ ?
    # Let's check executives/urls.py again. 
    # urlpatterns = [ path("executives/status/", ... ) ]
    # If the app url is /executives/, then full path is /executives/executives/status/
    # I will assume project urls include executives with prefix 'executives/'
    
    # In many django projects: path('executives/', include('executives.urls'))
    # Let's try both likely paths if one fails, or just assume the standard convention.
    # Given the previous `test_payments_script.py` used `/payments/...` I assume app name is prefix.
    # But let's act based on standard django `urls.py` structure.
    
    url = f"{BASE_URL}/executives/executives/status/" 
    
    try:
        resp = requests.get(url, headers=headers)
        if resp.status_code == 200:
            print("SUCCESS: Wallet/Status Retrieved")
            data = resp.json()
            stats = data.get('stats', {})
            print(f"Pending Payout: {stats.get('pending_payout')}")
        else:
            print(f"FAILED: {resp.status_code} - {resp.text}")
            # Fallback check
            url_alt = f"{BASE_URL}/executives/status/"
            resp = requests.get(url_alt, headers=headers)
            if resp.status_code == 200:
                 print("SUCCESS (Alt URL): Wallet/Status Retrieved")
            
    except Exception as e:
        print(f"ERROR: {e}")

    # 2. Get Redemption Plans
    sub_header_print("2. Get Redemption Plans")
    url = f"{BASE_URL}/payments/redemption-list/"
    try:
        resp = requests.get(url, headers=headers)
        if resp.status_code == 200:
            print("SUCCESS: Redemption Plans Retrieved")
            # print(resp.json())
        else:
            print(f"FAILED: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"ERROR: {e}")

    # 3. Request Wallet Amount (Redeem)
    sub_header_print("3. Request Redeem")
    url = f"{BASE_URL}/payments/executive/redeem/"
    data = {
        "redemption_option": option.id, 
        "upi_details": "test@upi",
        "account_number": "123456789",
        "ifsc_code": "TEST0001"
    }
    try:
        resp = requests.post(url, json=data, headers=headers)
        if resp.status_code == 201:
            print("SUCCESS: Redeem Requested")
            print(resp.json())
        else:
            print(f"FAILED: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"ERROR: {e}")

    # 4. Payment History (Redeem History)
    sub_header_print("4. Redeem History")
    url = f"{BASE_URL}/payments/executive/redeem/history/"
    try:
        resp = requests.get(url, headers=headers)
        if resp.status_code == 200:
            print("SUCCESS: Redeem History Retrieved")
            # print(resp.json())
        else:
            print(f"FAILED: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"ERROR: {e}")


def admin_flow(admin_token, user_id, executive_id):
    header_print("STARTING ADMIN SIDE TESTS")
    headers = {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json"
    }

    # 1. Create Manager User
    sub_header_print("1. Create Manager User")
    url = f"{BASE_URL}/accounts/create-manager-user/"
    data = {
        "name": "Manager User 1",
        "email": f"manager{uuid.uuid4()}@test.com",
        "password": "managerpass",
        "mobile_number": "1231231234"
    }
    try:
        resp = requests.post(url, json=data, headers=headers)
        if resp.status_code == 201:
            print("SUCCESS: Manager User Created")
            manager_id = resp.json()['data']['id']
    
            # Delete it
            requests.delete(f"{BASE_URL}/accounts/manager-users/{manager_id}/delete/", headers=headers)
            print("SUCCESS: Manager User Deleted")
        else:
             print(f"FAILED: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"ERROR: {e}")

    # 2. List Managers
    sub_header_print("2. List Managers")
    url = f"{BASE_URL}/accounts/managers/"
    try:
        resp = requests.get(url, headers=headers)
        if resp.status_code == 200:
             print("SUCCESS: Managers Listed")
        else:
             print(f"FAILED: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"ERROR: {e}")

    # 3. Reports
    sub_header_print("3. Reports Handling")
    # First create a report as a user (need user token, but let's assume valid data for admin list first)
    # Admin list reports
    url = f"{BASE_URL}/users/admin/reports/"
    try:
        resp = requests.get(url, headers=headers)
        if resp.status_code == 200:
            print("SUCCESS: Reports Listed")
        else:
            print(f"FAILED: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"ERROR: {e}")

    # 4. Reviews
    sub_header_print("4. Reviews Handling")
    url = f"{BASE_URL}/users/admin/reviews/"
    try:
        resp = requests.get(url, headers=headers)
        if resp.status_code == 200:
            print("SUCCESS: Reviews Listed")
        else:
            print(f"FAILED: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"ERROR: {e}")

    # 5. RedemptionOption CRUD
    sub_header_print("5. RedemptionOption CRUD Operations")
    
    # 5.1 Create RedemptionOption
    print("\n5.1 Create RedemptionOption")
    url = f"{BASE_URL}/payments/redemption-options/"
    test_amount = 1500.00
    data = {
        "amount": test_amount,
        "is_active": True
    }
    redemption_option_id = None
    try:
        resp = requests.post(url, json=data, headers=headers)
        if resp.status_code == 201:
            print("SUCCESS: RedemptionOption Created")
            redemption_option_id = resp.json().get('id')
            print(f"Created RedemptionOption ID: {redemption_option_id}")
        else:
            print(f"FAILED: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"ERROR: {e}")

    # 5.2 List RedemptionOptions
    print("\n5.2 List RedemptionOptions")
    url = f"{BASE_URL}/payments/redemption-options/"
    try:
        resp = requests.get(url, headers=headers)
        if resp.status_code == 200:
            print("SUCCESS: RedemptionOptions Listed")
            options = resp.json()
            print(f"Total options: {len(options)}")
        else:
            print(f"FAILED: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"ERROR: {e}")

    if redemption_option_id:
        # 5.3 Retrieve RedemptionOption
        print("\n5.3 Retrieve Single RedemptionOption")
        url = f"{BASE_URL}/payments/redemption-options/{redemption_option_id}/"
        try:
            resp = requests.get(url, headers=headers)
            if resp.status_code == 200:
                print("SUCCESS: RedemptionOption Retrieved")
                option_data = resp.json()
                print(f"Amount: ₹{option_data.get('amount')}")
            else:
                print(f"FAILED: {resp.status_code} - {resp.text}")
        except Exception as e:
            print(f"ERROR: {e}")

        # 5.4 Update RedemptionOption (PATCH)
        print("\n5.4 Update RedemptionOption")
        url = f"{BASE_URL}/payments/redemption-options/{redemption_option_id}/"
        data = {
            "is_active": False
        }
        try:
            resp = requests.patch(url, json=data, headers=headers)
            if resp.status_code == 200:
                print("SUCCESS: RedemptionOption Updated")
                print(f"is_active: {resp.json().get('is_active')}")
            else:
                print(f"FAILED: {resp.status_code} - {resp.text}")
        except Exception as e:
            print(f"ERROR: {e}")

        # 5.5 Delete RedemptionOption (Soft Delete)
        print("\n5.5 Delete RedemptionOption (Soft Delete)")
        url = f"{BASE_URL}/payments/redemption-options/{redemption_option_id}/"
        try:
            resp = requests.delete(url, headers=headers)
            if resp.status_code == 204:
                print("SUCCESS: RedemptionOption Deleted (Soft Delete)")
            else:
                print(f"FAILED: {resp.status_code} - {resp.text}")
        except Exception as e:
            print(f"ERROR: {e}")

        # 5.6 Verify Deletion
        print("\n5.6 Verify Deletion")
        url = f"{BASE_URL}/payments/redemption-options/{redemption_option_id}/"
        try:
            resp = requests.get(url, headers=headers)
            if resp.status_code == 404:
                print("SUCCESS: Deleted option not found (as expected)")
            elif resp.status_code == 200:
                print(f"INFO: Option still accessible after delete")
            else:
                print(f"Response: {resp.status_code} - {resp.text}")
        except Exception as e:
            print(f"ERROR: {e}")


if __name__ == "__main__":
    try:
        # If production mode with custom token, use it directly
        if (args.production or args.url) and args.token:
            header_print("PRODUCTION MODE - Using Provided Token")
            print("Testing with provided authentication token...")
            
            # Test with provided token
            user_flow(args.token)
            
            print("\n" + "="*60)
            print("Production testing completed!")
            print("Review the output above for any failures.")
            print("="*60)
        else:
            # Local mode - setup data and run full tests
            header_print("LOCAL MODE - Setting Up Test Data")
            
            # Setup Data
            user, user_token, plan = setup_user_data()
            exec_user, exec_token, option = setup_executive_data()
            
            # Run Tests
            user_flow(user_token)
            executive_flow(exec_token, option)
            
            admin_user, admin_token = setup_admin_data()
            admin_flow(admin_token, user.id, exec_user.id)
            
            print("\n" + "="*60)
            print("Local testing completed!")
            print("="*60)
        
    except Exception as e:
        print(f"\nCRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()
