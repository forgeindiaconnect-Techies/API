import asyncio
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))
os.environ["MONGODB_URL"] = "mongodb+srv://danish_ai:Danish%4021@cluster0.e8trmtg.mongodb.net/?appName=Cluster0"
os.environ["MONGODB_DB_NAME"] = "personal_ai_studio"

from database import connect_db, get_db

async def check():
    await connect_db()
    db = get_db()
    u = await db.users.find_one({'email': 'demo@aistudio.com'})
    print("User demo@aistudio.com in DB:", u)

if __name__ == "__main__":
    asyncio.run(check())
