import asyncio
import sys
import os

# Add backend directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from database import connect_db, get_db
from api.routes.models_router import list_models

async def run_fallback_test():
    await connect_db()
    db = get_db()
    
    # Check if a user exists to mock
    user = await db.users.find_one({})
    if not user:
        # Create a mock user if none exists
        print("No users found in database. Creating a mock user for testing...")
        user_doc = {
            "email": "test_fallback@example.com",
            "name": "Test Fallback User",
        }
        await db.users.insert_one(user_doc)
        user = await db.users.find_one({"email": "test_fallback@example.com"})
        
    print(f"Mocking request for user: {user.get('email')} (ID: {user.get('_id')})")
    
    try:
        # Call the endpoint directly with mock user
        print("Calling list_models endpoint...")
        models = await list_models(current_user=user)
        print("SUCCESS: Endpoint returned models successfully!")
        print(f"Fetched {len(models)} models:")
        for m in models[:3]:
            print(f"  - {m.get('name')} (Status: {m.get('status')})")
            
    except Exception as e:
        print(f"FAIL: Endpoint crashed with error: {e}")

if __name__ == "__main__":
    asyncio.run(run_fallback_test())
