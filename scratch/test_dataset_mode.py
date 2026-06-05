import sys
import os
import asyncio
from datetime import datetime

# Add backend to path so we can import things
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from database import connect_db, get_db
from models import StreamRequest
from api.routes.chat import stream_message
from bson import ObjectId

async def main():
    print("Connecting to DB...")
    await connect_db()
    db = get_db()
    
    # Check dialogs.txt dataset
    dataset = await db.datasets.find_one({"name": "dialogs.txt"})
    if not dataset:
        print("dialogs.txt dataset not found in database! Let's check available datasets:")
        async for d in db.datasets.find({}):
            print(f"- ID: {d['_id']}, Name: {d['name']}, Path: {d.get('file_path')}")
        return
    
    print(f"Found dataset: {dataset['name']} with ID: {dataset['_id']}")
    
    # Create or find a test conversation
    conversation = await db.conversations.find_one({"user_id": dataset["user_id"]})
    if not conversation:
        doc = {
            "title": "Test Chat",
            "model": "llama3",
            "user_id": dataset["user_id"],
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        res = await db.conversations.insert_one(doc)
        conversation_id = str(res.inserted_id)
    else:
        conversation_id = str(conversation["_id"])
        
    print(f"Using conversation ID: {conversation_id}")
    
    # Mock user
    current_user = {"_id": ObjectId(dataset["user_id"])}
    
    # Create StreamRequest
    req = StreamRequest(
        content="hi, how are you doing?",
        model="llama3",
        dataset_id=str(dataset["_id"]),
        mode="dataset_only"
    )
    
    print("\n--- Testing Stream in Dataset Only Mode (User query: 'hi, how are you doing?') ---")
    
    try:
        response = await stream_message(conversation_id, req, current_user)
        # Iterate over the generator
        async for chunk in response.body_iterator:
            print(chunk, end="")
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
