import os
import sys
import asyncio
import zipfile
import shutil
import io
from PIL import Image
from datetime import datetime

# Add backend to path so we can import things
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from database import connect_db, get_db, disconnect_db
from bson import ObjectId

def create_mock_images_zip(zip_path: str):
    """Create a mock image dataset zip with valid, duplicate, and corrupt files"""
    # Create simple solid color PIL images to save
    os.makedirs(os.path.dirname(zip_path), exist_ok=True)
    
    # Store first image bytes to create a duplicate
    first_img_bytes = None
    
    with zipfile.ZipFile(zip_path, 'w') as z:
        # Create 4 cats, 4 dogs, 2 birds (total 10 valid)
        classes = {
            "cats": [("cat1.jpg", (100, 100), (255, 0, 0)), 
                     ("cat2.jpg", (150, 120), (0, 255, 0)),
                     ("cat3.jpg", (200, 200), (0, 0, 255)),
                     ("cat4.jpg", (224, 224), (255, 255, 0))],
            "dogs": [("dog1.png", (300, 300), (255, 0, 255)), 
                     ("dog2.png", (400, 300), (0, 255, 255)),
                     ("dog3.png", (250, 250), (128, 128, 128)),
                     ("dog4.png", (180, 180), (64, 64, 64))],
            "birds": [("bird1.webp", (320, 240), (128, 0, 0)), 
                      ("bird2.webp", (240, 320), (0, 128, 0))]
        }
        
        for class_name, files in classes.items():
            for filename, size, color in files:
                img = Image.new("RGB", size, color)
                buf = io.BytesIO()
                # Determine format from extension
                fmt = "JPEG" if filename.endswith(".jpg") else "PNG" if filename.endswith(".png") else "WEBP"
                img.save(buf, format=fmt)
                img_data = buf.getvalue()
                
                if first_img_bytes is None:
                    first_img_bytes = img_data
                
                # Write to zip in class folder
                z.writestr(f"{class_name}/{filename}", img_data)
                
        # 1. Write Duplicate File (same bytes as cat1.jpg but different name)
        z.writestr("cats/duplicate.jpg", first_img_bytes)
        
        # 2. Write Corrupt File (not a valid image format)
        z.writestr("dogs/corrupt.png", b"This is not a valid PNG image. Just some random corrupt text bytes.")
        
    print(f"Created mock image dataset ZIP at {zip_path}")

async def run_pipeline():
    zip_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'mock_image_dataset.zip'))
    create_mock_images_zip(zip_path)
    
    print("Connecting to database...")
    await connect_db()
    db = get_db()
    
    # Create mock dataset and index documents
    dataset_id = ObjectId()
    index_id = ObjectId()
    
    print(f"Creating mock dataset document with ID: {dataset_id}")
    dataset_doc = {
        "_id": dataset_id,
        "name": "mock_image_dataset.zip",
        "file_name": "mock_image_dataset.zip",
        "file_type": "image_zip",
        "size_bytes": os.path.getsize(zip_path),
        "status": "processing",
        "created_at": datetime.utcnow(),
        "user_id": ObjectId() # Dummy user ID
    }
    await db.datasets.insert_one(dataset_doc)
    
    index_doc = {
        "_id": index_id,
        "dataset_id": str(dataset_id),
        "name": "mock_image_dataset_index",
        "status": "processing",
        "progress": 0.0,
        "created_at": datetime.utcnow()
    }
    await db.rag_indexes.insert_one(index_doc)
    
    try:
        from services.image_dataset_service import process_image_dataset
        
        # Run the pipeline
        print("Invoking process_image_dataset...")
        # Make a mock meta_res dictionary
        meta_res = {
            "metadata": {
                "is_image_dataset": True,
                "type": "image_dataset"
            }
        }
        await process_image_dataset(dataset_doc, zip_path, str(index_id), meta_res, db)
        
        # Fetch updated documents and verify
        updated_dataset = await db.datasets.find_one({"_id": dataset_id})
        updated_index = await db.rag_indexes.find_one({"_id": index_id})
        
        print("\n--- Pipeline Verification Results ---")
        print(f"Dataset status: {updated_dataset.get('status')}")
        print(f"Index status: {updated_index.get('status')}")
        
        stats = updated_dataset.get("stats", {})
        print(f"Stats present: {bool(stats)}")
        if stats:
            print(f"  Valid images: {stats.get('valid_images')}")
            print(f"  Total images (valid + corrupt): {stats.get('total_images')}")
            print(f"  Class distribution: {stats.get('class_distribution')}")
            print(f"  Split counts: {stats.get('split_counts')}")
            print(f"  Resolution stats: {stats.get('resolution_stats')}")
            print(f"  Corruption report: {stats.get('missing_or_corrupt_report')}")
            
        preview = updated_dataset.get("preview", {})
        print(f"Preview present: {bool(preview)}")
        if preview:
            print(f"  Preview images count: {len(preview.get('images', []))}")
            
        print(f"Chunk count in dataset: {updated_dataset.get('chunk_count')}")
        print(f"GridFS ZIP reference: {updated_dataset.get('gridfs_id')}")
        print(f"Preprocessed local ZIP: {updated_dataset.get('preprocessed_zip_path')}")
        
        # Check ChromaDB / mongodb chunks count
        chunks_in_db = await db.dataset_chunks.count_documents({"dataset_id": str(dataset_id)})
        print(f"Number of chunks stored in MongoDB dataset_chunks: {chunks_in_db}")
        
        # Clean up database records
        print("\nCleaning up database records...")
        await db.datasets.delete_one({"_id": dataset_id})
        await db.rag_indexes.delete_one({"_id": index_id})
        await db.dataset_chunks.delete_many({"dataset_id": str(dataset_id)})
        print("Database cleanup completed.")
        
    except Exception as e:
        print(f"Error executing pipeline: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Clean up files
        if os.path.exists(zip_path):
            os.remove(zip_path)
            print(f"Removed mock ZIP at {zip_path}")
        if 'preprocessed_zip_path' in locals() or 'updated_dataset' in locals():
            p_zip = updated_dataset.get("preprocessed_zip_path") if 'updated_dataset' in locals() else None
            if p_zip and os.path.exists(p_zip):
                try:
                    os.remove(p_zip)
                    print(f"Removed preprocessed ZIP at {p_zip}")
                except Exception:
                    pass
                
        await disconnect_db()

if __name__ == "__main__":
    asyncio.run(run_pipeline())
