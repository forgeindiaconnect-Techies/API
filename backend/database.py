from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING, DESCENDING
from config import settings
import logging

logger = logging.getLogger(__name__)

client: AsyncIOMotorClient = None
db = None


async def connect_db():
    global client, db
    try:
        client = AsyncIOMotorClient(settings.MONGODB_URL)
        db = client[settings.MONGODB_DB_NAME]
        # Ping to verify connection
        await db.command("ping")
        logger.info(f"Connected to MongoDB: {settings.MONGODB_DB_NAME}")
        await create_indexes()
    except Exception as e:
        logger.warning(f"MongoDB connection failed: {e}. Using in-memory store.")
        # Fallback: use a simple dict store for development
        db = MockDB()


async def disconnect_db():
    global client
    if client:
        client.close()
        logger.info("Disconnected from MongoDB")


async def create_indexes():
    """Create indexes for performance"""
    try:
        await db.users.create_index([("email", ASCENDING)], unique=True)
        await db.datasets.create_index([("user_id", ASCENDING)])
        await db.datasets.create_index([("created_at", DESCENDING)])
        await db.models.create_index([("user_id", ASCENDING)])
        await db.chat_history.create_index([("user_id", ASCENDING)])
        await db.chat_history.create_index([("conversation_id", ASCENDING)])
        await db.api_keys.create_index([("key_hash", ASCENDING)], unique=True)
        await db.api_keys.create_index([("user_id", ASCENDING)])
        await db.training_logs.create_index([("job_id", ASCENDING)])
        await db.analytics.create_index([("user_id", ASCENDING), ("timestamp", DESCENDING)])
        logger.info("Database indexes created")
    except Exception as e:
        logger.error(f"Failed to create indexes: {e}")


def get_db():
    return db


class MockDB:
    """Simple in-memory database for development without MongoDB"""
    def __init__(self):
        self._collections = {}

    def __getattr__(self, name):
        if name not in self._collections:
            self._collections[name] = MockCollection(name)
        return self._collections[name]

    async def command(self, cmd):
        return {"ok": 1}


class MockCollection:
    def __init__(self, name):
        self.name = name
        self._data = []
        self._id_counter = 1

    async def insert_one(self, doc):
        doc["_id"] = str(self._id_counter)
        self._id_counter += 1
        self._data.append(doc.copy())

        class Result:
            inserted_id = doc["_id"]
        return Result()

    async def find_one(self, query):
        for doc in self._data:
            if all(doc.get(k) == v for k, v in query.items() if not k.startswith("$")):
                return doc.copy()
        return None

    def find(self, query=None, *args, **kwargs):
        return MockCursor(self._data, query or {})

    async def update_one(self, query, update, upsert=False):
        for doc in self._data:
            if all(doc.get(k) == v for k, v in query.items()):
                if "$set" in update:
                    doc.update(update["$set"])
                return

        class Result:
            modified_count = 1
        return Result()

    async def delete_one(self, query):
        for i, doc in enumerate(self._data):
            if all(doc.get(k) == v for k, v in query.items()):
                self._data.pop(i)
                break

        class Result:
            deleted_count = 1
        return Result()

    async def count_documents(self, query=None):
        if not query:
            return len(self._data)
        return sum(1 for d in self._data if all(d.get(k) == v for k, v in query.items()))

    async def create_index(self, *args, **kwargs):
        pass


class MockCursor:
    def __init__(self, data, query):
        self._data = [d for d in data if all(d.get(k) == v for k, v in query.items() if not k.startswith("$"))]
        self._sort_key = None
        self._limit_val = None
        self._skip_val = 0

    def sort(self, key, direction=None):
        self._sort_key = key
        return self

    def limit(self, n):
        self._limit_val = n
        return self

    def skip(self, n):
        self._skip_val = n
        return self

    def __aiter__(self):
        data = self._data[self._skip_val:]
        if self._limit_val:
            data = data[:self._limit_val]
        return iter(data).__aiter__() if hasattr(iter(data), '__aiter__') else _AsyncIter(data)


class _AsyncIter:
    def __init__(self, data):
        self._iter = iter(data)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration
