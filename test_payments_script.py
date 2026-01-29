
import os
import django
import requests
import sys

# Add the project root to sys.path
sys.path.append('/home/muhammed-fazal/Desktop/talk_easy')

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'talkeasy.settings')
django.setup()

from users.models import UserProfile
from users.utils import create_tokens_for_userprofile

def get_or_create_test_user():
    print("Getting or creating test user...")
    try:
        # Try to find a user or create one
        user_id = 'TUR9999' # Custom ID if needed, but the model likely handles it
        user = UserProfile.objects.filter(mobile_number='9876543210').first()
        if not user:
            user = UserProfile.objects.create(
                mobile_number='9876543210',
                name='Test User',
                email='test@example.com'
            )
            print("Created new test user.")
        else:
            print(f"Found existing test user: {user.id}")
        return user
    except Exception as e:
        print(f"Error creating user: {e}")
        sys.exit(1)

def generate_token(user):
    print("Generating token...")
    try:
        tokens = create_tokens_for_userprofile(user)
        access_token = tokens['access']
        print(f"Token generated: {access_token[:20]}...")
        return access_token
    except Exception as e:
        print(f"Error generating token: {e}")
        # Print full traceback for debugging
        import traceback
        traceback.print_exc()
        sys.exit(1)

def test_plans_endpoint(token):
    url = "http://127.0.0.1:8000/payments/plans/"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    print(f"\nTesting URL: {url}")
    
    try:
        response = requests.get(url, headers=headers)
        print(f"Status Code: {response.status_code}")
        print("Response Body:")
        try:
            print(response.json())
        except:
            print(response.text)
        
        if response.status_code == 200:
            print("\nSUCCESS: Plans retrieved successfully.")
        else:
            print("\nFAILURE: Could not retrieve plans.")
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    try:
        user = get_or_create_test_user()
        token = generate_token(user)
        print(f"\nFULL ACCESS TOKEN:\n{token}\n")
        test_plans_endpoint(token)
    except Exception as e:
        print(f"An error occurred: {e}")
