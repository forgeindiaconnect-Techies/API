"""
CNN Image Embedding Pipeline – Offline Integration Test
=======================================================
Runs entirely in-memory (no MongoDB Atlas writes, no Cloudinary).
Uses a mock async DB so the test passes even when Atlas is over quota.
"""
import os
import sys
import asyncio
import zipfile
import io
import logging
from datetime import datetime
from PIL import Image
from bson import ObjectId

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# ── Path setup ────────────────────────────────────────────────────────────────
BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend'))
sys.path.insert(0, BACKEND_DIR)


# ── In-memory mock database ───────────────────────────────────────────────────
class MockCollection:
    """Minimal async MongoDB-compatible in-memory collection."""

    def __init__(self):
        self._docs: dict[str, dict] = {}

    async def insert_one(self, doc: dict):
        key = str(doc.get("_id") or doc.get("dataset_id") or id(doc))
        self._docs[id(doc)] = doc

    async def insert_many(self, docs: list):
        for d in docs:
            await self.insert_one(d)

    async def update_one(self, filt: dict, update: dict, upsert=False):
        _id = filt.get("_id")
        target = None
        for doc in self._docs.values():
            if doc.get("_id") == _id:
                target = doc
                break
        if target is None and upsert:
            target = {"_id": _id}
            self._docs[id(target)] = target
        if target is not None:
            if "$set" in update:
                target.update(update["$set"])

    async def find_one(self, filt: dict):
        _id = filt.get("_id")
        for doc in self._docs.values():
            if doc.get("_id") == _id:
                return doc
        return None

    def find(self, filt: dict):
        return MockCursor(self._docs, filt)

    async def count_documents(self, filt: dict):
        count = 0
        for doc in self._docs.values():
            match = all(doc.get(k) == v for k, v in filt.items())
            if match:
                count += 1
        return count

    async def delete_one(self, filt: dict):
        pass

    async def delete_many(self, filt: dict):
        pass


class MockCursor:
    def __init__(self, docs: dict, filt: dict):
        self._items = [
            d for d in docs.values()
            if all(d.get(k) == v for k, v in filt.items())
        ]
        self._idx = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._idx >= len(self._items):
            raise StopAsyncIteration
        item = self._items[self._idx]
        self._idx += 1
        return item


class MockDB:
    def __init__(self):
        self.datasets       = MockCollection()
        self.rag_indexes    = MockCollection()
        self.dataset_chunks = MockCollection()


# ── ZIP factory ───────────────────────────────────────────────────────────────
def create_mock_images_zip(zip_path: str) -> None:
    """Create a tiny mock image dataset zip: 3 cats, 3 dogs + 1 corrupt file."""
    os.makedirs(os.path.dirname(zip_path), exist_ok=True)
    classes = {
        "cats": [("cat1.jpg", (100, 100), (255, 0, 0)),
                 ("cat2.jpg", (150, 120), (0, 255, 0)),
                 ("cat3.jpg", (200, 200), (0, 0, 255))],
        "dogs": [("dog1.png", (300, 300), (255, 0, 255)),
                 ("dog2.png", (400, 300), (0, 255, 255)),
                 ("dog3.png", (250, 250), (128, 128, 128))],
    }

    with zipfile.ZipFile(zip_path, 'w') as z:
        for class_name, files in classes.items():
            for filename, size, color in files:
                img = Image.new("RGB", size, color)
                buf = io.BytesIO()
                fmt = "JPEG" if filename.endswith(".jpg") else "PNG"
                img.save(buf, format=fmt)
                z.writestr(f"{class_name}/{filename}", buf.getvalue())

        # Add a corrupt file that should be skipped
        z.writestr("dogs/corrupt.png",
                   b"Not a real PNG. Should be skipped by the pipeline.")

    logger.info(f"Created mock image dataset ZIP at {zip_path}")


# ── Main test ─────────────────────────────────────────────────────────────────
async def run_pipeline():
    zip_path = os.path.join(
        os.path.dirname(__file__), 'mock_image_dataset.zip'
    )
    create_mock_images_zip(zip_path)

    db         = MockDB()
    dataset_id = ObjectId()
    index_id   = ObjectId()

    # Insert seed documents into mock DB
    dataset_doc = {
        "_id":        dataset_id,
        "name":       "mock_image_dataset.zip",
        "file_name":  "mock_image_dataset.zip",
        "file_type":  "image_zip",
        "size_bytes": os.path.getsize(zip_path),
        "status":     "processing",
        "created_at": datetime.utcnow(),
        "user_id":    ObjectId(),
    }
    index_doc = {
        "_id":        index_id,
        "dataset_id": str(dataset_id),
        "name":       "mock_image_dataset_index",
        "status":     "processing",
        "progress":   0.0,
        "created_at": datetime.utcnow(),
    }
    await db.datasets.insert_one(dataset_doc)
    await db.rag_indexes.insert_one(index_doc)

    meta_res = {"metadata": {"is_image_dataset": True, "type": "image_dataset"}}

    logger.info("=" * 60)
    logger.info("Invoking process_image_dataset (offline / mock DB mode)")
    logger.info("=" * 60)

    try:
        from services.image_dataset_service import process_image_dataset
        await process_image_dataset(
            dataset_doc, zip_path, str(index_id), meta_res, db
        )

        # ── Verify results ────────────────────────────────────────────────
        updated_dataset = await db.datasets.find_one({"_id": dataset_id})
        updated_index   = await db.rag_indexes.find_one({"_id": index_id})
        chunks_in_db    = await db.dataset_chunks.count_documents(
            {"dataset_id": str(dataset_id)}
        )

        print("\n" + "=" * 60)
        print("PIPELINE VERIFICATION RESULTS")
        print("=" * 60)
        print(f"  Dataset status : {updated_dataset.get('status')}")
        print(f"  Index status   : {updated_index.get('status')}")
        print(f"  Index progress : {updated_index.get('progress')}%")
        print(f"  Chunks in DB   : {chunks_in_db}")
        print(f"  Chunk count    : {updated_dataset.get('chunk_count')}")
        print(f"  Embedding count: {updated_dataset.get('embedding_count')}")
        print(f"  Processing time: {updated_dataset.get('processing_time', 0):.1f}s")

        stats = updated_dataset.get("stats", {})
        if stats:
            print(f"\n  Stats:")
            print(f"    valid_images      : {stats.get('valid_images')}")
            print(f"    class_distribution: {stats.get('class_distribution')}")
            print(f"    split_counts      : {stats.get('split_counts')}")
            print(f"    missing/corrupt   : {stats.get('missing_or_corrupt_report')}")

        preview = updated_dataset.get("preview", {})
        preview_imgs = preview.get("images", [])
        print(f"\n  Preview images   : {len(preview_imgs)} thumbnails available")

        # ── Assertions ────────────────────────────────────────────────────
        assert updated_dataset.get("status") == "ready", \
            f"Expected status=ready, got {updated_dataset.get('status')}"
        assert updated_index.get("status") == "ready", \
            f"Expected index status=ready, got {updated_index.get('status')}"
        assert updated_index.get("progress") == 100.0, \
            f"Expected progress=100.0, got {updated_index.get('progress')}"
        assert chunks_in_db > 0, \
            f"Expected >0 chunks in MongoDB, got {chunks_in_db}"
        assert chunks_in_db == updated_dataset.get("chunk_count"), \
            "chunk_count mismatch between dataset doc and actual DB count"

        print("\n[PASS] ALL ASSERTIONS PASSED -- Pipeline is working correctly!")

    except Exception as exc:
        import traceback
        print(f"\n[FAIL] Pipeline failed: {exc}")
        traceback.print_exc()

    finally:
        if os.path.exists(zip_path):
            os.remove(zip_path)
            logger.info(f"Removed mock ZIP at {zip_path}")


if __name__ == "__main__":
    asyncio.run(run_pipeline())
