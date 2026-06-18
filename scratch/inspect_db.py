import os
import sys
import asyncio
import logging
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("inspect_db")

from database import connect_db, get_db

async def inspect():
    await connect_db()
    db = get_db()
    
    collections = ["users", "datasets", "models", "chat_history", "messages", "rag_indexes", "api_keys", "training_logs", "conversations"]
    
    for col_name in collections:
        col = getattr(db._db, col_name)
        count = await col.count_documents({})
        logger.info(f"Collection: {col_name}, Count: {count}")
        try:
            indexes = await col.index_information()
            logger.info(f"  Indexes: {list(indexes.keys())}")
        except Exception as e:
            logger.error(f"  Failed to get indexes for {col_name}: {e}")
            
    # Measure get_dashboard query times
    current_user = {
        "_id": "6a2a8ce94af4f2be830e5d28",
        "username": "demo@aistudio.com"
    }
    user_id = str(current_user["_id"])
    
    logger.info("Timing queries for user_id: %s", user_id)
    
    # 1. Datasets count
    t0 = time.time()
    await db.datasets.count_documents({"user_id": user_id})
    logger.info(f"datasets.count_documents: {(time.time() - t0)*1000:.2f} ms")
    
    # 2. Models count
    t0 = time.time()
    await db.models.count_documents({"user_id": user_id})
    logger.info(f"models.count_documents: {(time.time() - t0)*1000:.2f} ms")
    
    # 3. API keys count
    t0 = time.time()
    await db.api_keys.count_documents({
        "user_id": user_id,
        "$or": [
            {"is_active": True},
            {"is_active": {"$exists": False}, "status": "active"}
        ]
    })
    logger.info(f"api_keys.count_documents: {(time.time() - t0)*1000:.2f} ms")
    
    # 4. Conversations count
    t0 = time.time()
    await db.conversations.count_documents({"user_id": user_id})
    logger.info(f"conversations.count_documents: {(time.time() - t0)*1000:.2f} ms")
    
    # 5. Messages count
    t0 = time.time()
    await db.messages.count_documents({"user_id": user_id, "role": "user"})
    logger.info(f"messages.count_documents: {(time.time() - t0)*1000:.2f} ms")
    
    # 6. Total tokens aggregation
    t0 = time.time()
    pipeline_all = [
        {"$match": {"user_id": user_id, "role": "user"}},
        {"$group": {
            "_id": None,
            "total_tokens": {
                "$sum": {
                    "$ifNull": [
                        "$tokens_used",
                        {"$max": [1, {"$floor": {"$divide": [{"$strLenCP": {"$ifNull": ["$content", ""]}}, 4]}}]}
                    ]
                }
            }
        }}
    ]
    cursor = db.messages.aggregate(pipeline_all)
    await cursor.to_list(1)
    logger.info(f"messages tokens aggregation: {(time.time() - t0)*1000:.2f} ms")
    
    # 7. 14-day stats aggregation
    t0 = time.time()
    from datetime import datetime, timedelta
    fourteen_days_ago = datetime.utcnow() - timedelta(days=14)
    msg_query = {
        "user_id": user_id,
        "role": "user",
        "$or": [
            {"created_at": {"$gte": fourteen_days_ago}},
            {"created_at": {"$gte": fourteen_days_ago.isoformat()}}
        ]
    }
    pipeline = [
        {"$match": msg_query},
        {
            "$project": {
                "date": {
                    "$cond": {
                        "if": {"$eq": [{"$type": "$created_at"}, "string"]},
                        "then": {"$toDate": "$created_at"},
                        "else": "$created_at"
                    }
                },
                "tokens": {
                    "$ifNull": [
                        "$tokens_used",
                        {"$max": [1, {"$floor": {"$divide": [{"$strLenCP": {"$ifNull": ["$content", ""]}}, 4]}}]}
                    ]
                }
            }
        },
        {
            "$group": {
                "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$date"}},
                "requests": {"$sum": 1},
                "tokens": {"$sum": "$tokens"}
            }
        }
    ]
    cursor = db.messages.aggregate(pipeline)
    await cursor.to_list(None)
    logger.info(f"14-day stats aggregation: {(time.time() - t0)*1000:.2f} ms")

if __name__ == "__main__":
    asyncio.run(inspect())
