from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection
from pymongo import ASCENDING, DESCENDING
from config import settings
from bson import ObjectId
from bson.errors import InvalidId
from typing import Any, Optional
import logging

logger = logging.getLogger(__name__)

client: Optional[AsyncIOMotorClient] = None
db: Any = None


def convert_id(val: Any) -> Any:
    if isinstance(val, str) and len(val) == 24:
        try:
            return ObjectId(val)
        except InvalidId:
            return val
    elif isinstance(val, dict):
        return {k: convert_id(v) for k, v in val.items()}
    elif isinstance(val, list):
        return [convert_id(x) for x in val]
    return val


def clean_query(query: Any) -> Any:
    if not isinstance(query, dict):
        return query
    new_query = {}
    for k, v in query.items():
        if k == "_id":
            new_query[k] = convert_id(v)
        elif isinstance(v, dict):
            new_query[k] = clean_query(v)
        else:
            new_query[k] = v
    return new_query


class CollectionWrapper:
    def __init__(self, collection):
        self._collection = collection

    def __getattr__(self, name):
        return getattr(self._collection, name)

    async def insert_one(self, document, *args, **kwargs):
        return await self._collection.insert_one(document, *args, **kwargs)

    async def find_one(self, filter, *args, **kwargs):
        return await self._collection.find_one(clean_query(filter), *args, **kwargs)

    def find(self, filter=None, *args, **kwargs):
        cleaned = clean_query(filter) if filter is not None else None
        return self._collection.find(cleaned, *args, **kwargs)

    async def update_one(self, filter, update, *args, **kwargs):
        return await self._collection.update_one(clean_query(filter), update, *args, **kwargs)

    async def update_many(self, filter, update, *args, **kwargs):
        return await self._collection.update_many(clean_query(filter), update, *args, **kwargs)

    async def delete_one(self, filter, *args, **kwargs):
        return await self._collection.delete_one(clean_query(filter), *args, **kwargs)

    async def delete_many(self, filter, *args, **kwargs):
        return await self._collection.delete_many(clean_query(filter), *args, **kwargs)

    async def count_documents(self, filter, *args, **kwargs):
        return await self._collection.count_documents(clean_query(filter), *args, **kwargs)


class DatabaseWrapper:
    def __init__(self, db_obj):
        self._db = db_obj

    def __getattr__(self, name):
        attr = getattr(self._db, name)
        if isinstance(attr, AsyncIOMotorCollection) or attr.__class__.__name__ == "MockCollection":
            return CollectionWrapper(attr)
        return attr

    def __getitem__(self, name):
        return CollectionWrapper(self._db[name])


async def connect_db():
    global client, db
    try:
        client = AsyncIOMotorClient(settings.MONGODB_URL, serverSelectionTimeoutMS=5000)
        raw_db = client[settings.MONGODB_DB_NAME]
        # Ping to verify connection
        await raw_db.command("ping")
        logger.info(f"Connected to MongoDB: {settings.MONGODB_DB_NAME}")
        db = DatabaseWrapper(raw_db)
        await create_indexes()
    except Exception as e:
        logger.warning(f"MongoDB connection failed: {e}. Using in-memory store.")
        # Fallback: use a simple dict store for development
        db = DatabaseWrapper(MockDB())


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
        await db.messages.create_index([("user_id", ASCENDING)])
        await db.messages.create_index([("conversation_id", ASCENDING)])
        await db.messages.create_index([("created_at", DESCENDING)])
        await db.rag_indexes.create_index([("user_id", ASCENDING)])
        await db.rag_indexes.create_index([("dataset_id", ASCENDING)])
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
        return _AsyncIter(data)


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
