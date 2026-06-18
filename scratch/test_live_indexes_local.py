import asyncio
import sys
import os
import pymongo
from datetime import datetime

# Add backend directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from database import get_db, DatabaseWrapper
from api.routes.rag import fmt_index

async def run_local_diagnostic():
    print("Connecting directly to MongoDB Atlas cluster...")
    connection_string = 'mongodb+srv://danish_ai:Danish%4021@cluster0.e8trmtg.mongodb.net/?appName=Cluster0'
    
    # We will temporarily mock the get_db wrapper
    client = pymongo.MongoClient(connection_string)
    db = client.personal_ai_studio
    
    # Mock user_id (danish@gmail.com ID from your DB log)
    user_id = "6a213b5f4f5a5a8a0249f24b"
    
    print(f"Fetching RAG indexes for user_id: {user_id}...")
    try:
        indexes = []
        cursor = db.rag_indexes.find({"user_id": user_id})
        for i in cursor:
            print(f"Processing raw index document: {i}")
            formatted = fmt_index(i)
            print(f"  - Formatted successfully: {formatted}")
            indexes.append(formatted)
        print(f"\nSUCCESS: Retrieved and formatted {len(indexes)} indexes locally without exceptions!")
    except Exception as e:
        print(f"\nFAIL: Failed during retrieval or formatting: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(run_local_diagnostic())
