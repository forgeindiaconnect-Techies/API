import asyncio
import sys
import os
from bson import ObjectId

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))
os.environ["MONGODB_URL"] = "mongodb+srv://danish_ai:Danish%4021@cluster0.e8trmtg.mongodb.net/?appName=Cluster0"
os.environ["MONGODB_DB_NAME"] = "personal_ai_studio"

from database import connect_db, get_db

async def check():
    await connect_db()
    db = get_db()
    d = await db.datasets.find_one({'_id': ObjectId('6a326c6aa92e442a38f061fe')})
    print("Dataset doc in DB:", d)
    
    # Let's also check if there is an index document in rag_indexes
    idx = await db.rag_indexes.find_one({'dataset_id': '6a326c6aa92e442a38f061fe'})
    print("RAG Index doc in DB:", idx)

if __name__ == "__main__":
    asyncio.run(check())
