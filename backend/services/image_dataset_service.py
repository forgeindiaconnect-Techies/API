import os
import io
import base64
import shutil
import tempfile
import hashlib
import logging
import asyncio
import random
import zipfile
from datetime import datetime
from PIL import Image, ImageEnhance
from typing import Dict, Any, List
from bson import ObjectId

logger = logging.getLogger(__name__)

# Constants
TARGET_SIZE = (224, 224)
THUMBNAIL_SIZE = (96, 96)
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

async def process_image_dataset(dataset_doc: dict, zip_path: str, index_id: str, meta_res: dict, db):
    """
    CNN Image Preprocessing & Feature Extraction Pipeline
    Status transitions: UPLOADED -> EXTRACTED -> PREPROCESSED -> EMBEDDED -> READY
    """
    dataset_id = str(dataset_doc["_id"])
    file_name = dataset_doc.get("file_name") or dataset_doc.get("name", "dataset.zip")
    start_time = datetime.utcnow()
    
    logger.info(f"Starting Image Dataset Preprocessing Pipeline for ID: {dataset_id}")
    
    # Create temporary directories for processing
    tmp_extract_dir = tempfile.mkdtemp(prefix=f"extract_{dataset_id}_")
    tmp_preprocess_dir = tempfile.mkdtemp(prefix=f"preprocess_{dataset_id}_")
    
    try:
        # ─── STEP 1: UPLOADED ─────────────────────────────────────────────
        logger.info("[Step 1/5] ZIP Archive Uploaded. Initializing status...")
        await update_status(db, dataset_id, index_id, "uploaded", 15.0)
        
        # ─── STEP 2: EXTRACTED ────────────────────────────────────────────
        logger.info("[Step 2/5] Extracting ZIP contents and validating images...")
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(tmp_extract_dir)
            logger.info(f"Extracted zip to {tmp_extract_dir}")
        except Exception as e:
            logger.error(f"Failed to extract ZIP archive: {e}")
            raise Exception(f"ZIP Extraction Failure: {e}")
            
        # Discover files, validate format/corruptions, de-duplicate
        seen_md5s = set()
        valid_images = []
        corrupted_files = []
        duplicate_files = []
        resolution_widths = []
        resolution_heights = []
        class_groups = {}  # class_name -> list of paths
        
        for root, _, files in os.walk(tmp_extract_dir):
            for file in files:
                file_path = os.path.join(root, file)
                ext = os.path.splitext(file)[1].lower()
                if ext not in IMAGE_EXTENSIONS:
                    continue
                    
                # 1. Check Duplication (MD5 Hash check)
                try:
                    with open(file_path, 'rb') as f:
                        file_bytes = f.read()
                    md5_val = hashlib.md5(file_bytes).hexdigest()
                    if md5_val in seen_md5s:
                        duplicate_files.append(file)
                        os.remove(file_path)
                        continue
                    seen_md5s.add(md5_val)
                except Exception as md5_err:
                    logger.warning(f"Failed to compute MD5 for {file}: {md5_err}")
                    
                # 2. Check Corruption (PIL Load test) and Record Resolutions
                try:
                    with Image.open(file_path) as img:
                        img.verify()
                    # Re-open after verify() since verify() closes the file context
                    with Image.open(file_path) as img:
                        w, h = img.size
                        fmt = img.format
                        resolution_widths.append(w)
                        resolution_heights.append(h)
                        
                        # Detect Class from directory layout
                        rel_dir = os.path.relpath(root, tmp_extract_dir)
                        class_name = rel_dir.replace("\\", "/").split("/")[0] if rel_dir != "." else "default"
                        if not class_name or class_name.strip() == "":
                            class_name = "default"
                            
                        valid_images.append({
                            "original_path": file_path,
                            "filename": file,
                            "class": class_name,
                            "width": w,
                            "height": h,
                            "format": fmt
                        })
                        
                        if class_name not in class_groups:
                            class_groups[class_name] = []
                        class_groups[class_name].append(valid_images[-1])
                except Exception as err:
                    logger.warning(f"Skipping corrupted image '{file}': {err}")
                    corrupted_files.append(f"{file} ({str(err)})")
                    try:
                        os.remove(file_path)
                    except Exception:
                        pass
                        
        if not valid_images:
            raise Exception("No valid image files found in the uploaded ZIP archive.")
            
        logger.info(f"Validation summary: {len(valid_images)} valid, {len(corrupted_files)} corrupted, {len(duplicate_files)} duplicates.")
        await update_status(db, dataset_id, index_id, "extracted", 35.0)
        
        # ─── STEP 3: PREPROCESSED ─────────────────────────────────────────
        logger.info("[Step 3/5] Preprocessing and splitting image dataset...")
        
        # Split image lists stratified by class: 70% train, 15% val, 15% test
        train_list = []
        val_list = []
        test_list = []
        
        for class_name, images in class_groups.items():
            random.shuffle(images)
            n = len(images)
            n_train = int(n * 0.70)
            n_val = int(n * 0.15)
            
            # Slice lists
            cls_train = images[:n_train]
            cls_val = images[n_train:n_train+n_val]
            cls_test = images[n_train+n_val:]
            
            # Make sure splits are not empty if there are very few files
            if not cls_train and images:
                cls_train = [images[0]]
                if len(images) > 1:
                    cls_val = [images[1]]
                if len(images) > 2:
                    cls_test = images[2:]
            
            train_list.extend(cls_train)
            val_list.extend(cls_val)
            test_list.extend(cls_test)
            
        # Process and save images into split/class directories
        splits = {"train": train_list, "val": val_list, "test": test_list}
        
        for split_name, img_items in splits.items():
            for item in img_items:
                # Prepare directories
                cls_dir = os.path.join(tmp_preprocess_dir, split_name, item["class"])
                os.makedirs(cls_dir, exist_ok=True)
                
                try:
                    with Image.open(item["original_path"]) as img:
                        # 1. Convert to RGB
                        img_rgb = img.convert("RGB")
                        
                        # 2. Resize to 224x224
                        img_resized = img_rgb.resize(TARGET_SIZE, Image.Resampling.LANCZOS)
                        
                        # Save original preprocessed image
                        target_file_name = f"{os.path.splitext(item['filename'])[0]}.jpg"
                        target_path = os.path.join(cls_dir, target_file_name)
                        img_resized.save(target_path, format="JPEG", quality=90)
                        
                        # Record target path for feature extraction
                        item["preprocessed_path"] = target_path
                        item["split"] = split_name
                        
                        # 3. Apply Data Augmentation for training split
                        if split_name == "train":
                            augmented_img = apply_augmentation(img_resized)
                            aug_file_name = f"{os.path.splitext(item['filename'])[0]}_augmented.jpg"
                            aug_path = os.path.join(cls_dir, aug_file_name)
                            augmented_img.save(aug_path, format="JPEG", quality=90)
                except Exception as preprocess_err:
                    logger.error(f"Failed to preprocess image {item['filename']}: {preprocess_err}")
                    corrupted_files.append(f"{item['filename']} (preprocess: {str(preprocess_err)})")
                    
        # Compress preprocessed directory into zip
        preprocessed_zip_local = os.path.join(os.path.dirname(tmp_preprocess_dir), f"preprocessed_{dataset_id}.zip")
        with zipfile.ZipFile(preprocessed_zip_local, 'w', zipfile.ZIP_DEFLATED) as zip_out:
            for root, _, files in os.walk(tmp_preprocess_dir):
                for file in files:
                    file_full_path = os.path.join(root, file)
                    arc_name = os.path.relpath(file_full_path, tmp_preprocess_dir)
                    zip_out.write(file_full_path, arc_name)
                    
        # Backup preprocessed ZIP to GridFS
        gridfs_id = None
        try:
            with open(preprocessed_zip_local, 'rb') as f:
                zip_bytes = f.read()
            from services.dataset_service import upload_file_to_gridfs
            gridfs_id = await upload_file_to_gridfs(zip_bytes, f"preprocessed_{file_name}", "application/zip")
            logger.info(f"Uploaded preprocessed dataset ZIP to GridFS with ID: {gridfs_id}")
        except Exception as upload_err:
            logger.error(f"Failed to upload preprocessed ZIP to GridFS: {upload_err}")
            
        await update_status(db, dataset_id, index_id, "preprocessed", 60.0)
        
        # ─── STEP 4: EMBEDDED ─────────────────────────────────────────────
        logger.info("[Step 4/5] Loading pretrained CNN model and generating image embeddings...")
        
        # Pre-select Model: MobileNetV2 is extremely lightweight and fast for CPU
        model_name = "google/mobilenet_v2_1.0_224"
        logger.info(f"Loading feature extractor: {model_name}...")
        try:
            from transformers import AutoImageProcessor, AutoModel
            import torch
            
            processor = AutoImageProcessor.from_pretrained(model_name)
            model = AutoModel.from_pretrained(model_name)
            model.eval()
            logger.info("Model loaded successfully")
        except Exception as model_err:
            logger.error(f"Failed to load pretrained CNN model: {model_err}")
            raise Exception(f"Pretrained Model Loading Failure: {model_err}")
            
        # Extract features for all valid preprocessed images
        logger.info("Extracting embeddings...")
        all_meta_images = train_list + val_list + test_list
        # Filter items that successfully wrote a preprocessed image
        all_meta_images = [item for item in all_meta_images if "preprocessed_path" in item]
        
        # ChromaDB setup
        from vector_db.store import VectorStore
        store = VectorStore(backend="chroma", collection_name=index_id)
        try:
            await store.delete_store()
        except Exception:
            pass
        await store.ensure_initialized()
        
        batch_size = 16
        chunk_docs = []
        preview_items = []  # Save first 24 for UI previews
        
        for idx in range(0, len(all_meta_images), batch_size):
            batch_items = all_meta_images[idx:idx+batch_size]
            batch_pils = []
            batch_filenames = []
            batch_classes = []
            batch_splits = []
            
            # Load batch PIL images
            for item in batch_items:
                try:
                    p_img = Image.open(item["preprocessed_path"])
                    batch_pils.append(p_img)
                    batch_filenames.append(item["filename"])
                    batch_classes.append(item["class"])
                    batch_splits.append(item["split"])
                except Exception as load_err:
                    logger.warning(f"Failed to load preprocessed image {item['filename']} for feature extraction: {load_err}")
                    
            if not batch_pils:
                continue
                
            # Extract feature vectors using model
            try:
                inputs = processor(images=batch_pils, return_tensors="pt")
                with torch.no_grad():
                    outputs = model(**inputs)
                    # MobileNetV2 uses average pooled features
                    embeddings = outputs.last_hidden_state.mean(dim=[2, 3])
                    embeddings_list = embeddings.squeeze().tolist()
                    if len(batch_pils) == 1:
                        embeddings_list = [embeddings_list]
            except Exception as extract_err:
                logger.error(f"Embeddings generation failed for batch {idx}-{idx+len(batch_pils)}: {extract_err}")
                continue
                
            # Insert into Vector Store and MongoDB Chunks
            vector_docs = []
            vector_embeds = []
            vector_metadatas = []
            vector_ids = []
            
            for b_idx, pil_img in enumerate(batch_pils):
                filename = batch_filenames[b_idx]
                class_name = batch_classes[b_idx]
                split_name = batch_splits[b_idx]
                embedding = embeddings_list[b_idx]
                chunk_id = f"{index_id}_{idx + b_idx}"
                
                # 1. Generate 96x96 Base64 Thumbnail
                thumb_img = pil_img.copy()
                thumb_img.thumbnail(THUMBNAIL_SIZE)
                buf = io.BytesIO()
                thumb_img.save(buf, format="JPEG", quality=80)
                base64_thumb = base64.b64encode(buf.getvalue()).decode("utf-8")
                
                # Metadata for ChromaDB
                metadata = {
                    "dataset_id": dataset_id,
                    "filename": filename,
                    "class": class_name,
                    "split": split_name,
                    "is_image": True
                }
                
                vector_docs.append(f"[Class: {class_name}] [Split: {split_name}] {filename}")
                vector_embeds.append(embedding)
                vector_metadatas.append(metadata)
                vector_ids.append(chunk_id)
                
                # MongoDB Chunks Document
                chunk_doc = {
                    "dataset_id": dataset_id,
                    "index_id": index_id,
                    "chunk_id": chunk_id,
                    "source_file": filename,
                    "chunk_text": f"[Class: {class_name}] [Split: {split_name}] {filename}",
                    "thumbnail": base64_thumb,
                    "metadata": {"class": class_name, "split": split_name},
                    "created_at": datetime.utcnow()
                }
                chunk_docs.append(chunk_doc)
                
                # Keep first 24 images for preview tab
                if len(preview_items) < 24:
                    preview_items.append({
                        "filename": filename,
                        "class_name": class_name,
                        "thumbnail": base64_thumb
                    })
                    
            # Insert vectors to ChromaDB
            try:
                await store.add_documents(vector_docs, vector_embeds, vector_metadatas, vector_ids)
            except Exception as vector_err:
                logger.error(f"ChromaDB insert failed for batch {idx}: {vector_err}")
                
            # Yield to event loop
            await asyncio.sleep(0.01)
            
        # Store metadata chunks in MongoDB in batches of 1,000
        if chunk_docs:
            db_batch_size = 1000
            for start_idx in range(0, len(chunk_docs), db_batch_size):
                batch = chunk_docs[start_idx:start_idx + db_batch_size]
                await db.dataset_chunks.insert_many(batch)
            logger.info(f"Stored {len(chunk_docs)} chunk records in MongoDB collection 'dataset_chunks'")
            
        await update_status(db, dataset_id, index_id, "embedded", 85.0)
        
        # ─── STEP 5: READY & STATS ───────────────────────────────────────
        logger.info("[Step 5/5] Compiling final report and resolution statistics...")
        
        # Compute Resolution stats
        res_w = sorted(resolution_widths)
        res_h = sorted(resolution_heights)
        n_res = len(res_w)
        mean_w = round(sum(res_w) / n_res, 1) if n_res > 0 else 0
        mean_h = round(sum(res_h) / n_res, 1) if n_res > 0 else 0
        
        resolution_stats = {
            "min_width": res_w[0] if n_res > 0 else 0,
            "max_width": res_w[-1] if n_res > 0 else 0,
            "mean_width": mean_w,
            "min_height": res_h[0] if n_res > 0 else 0,
            "max_height": res_h[-1] if n_res > 0 else 0,
            "mean_height": mean_h
        }
        
        class_dist = {cls: len(imgs) for cls, imgs in class_groups.items()}
        
        eda_stats = {
            "is_image_dataset": True,
            "total_images": len(resolution_widths) + len(corrupted_files),
            "valid_images": len(valid_images),
            "class_distribution": class_dist,
            "resolution_stats": resolution_stats,
            "missing_or_corrupt_report": corrupted_files,
            "split_counts": {
                "train": len(train_list),
                "val": len(val_list),
                "test": len(test_list)
            }
        }
        
        preview_data = {
            "is_image_dataset": True,
            "images": preview_items
        }
        
        processing_time = (datetime.utcnow() - start_time).total_seconds()
        
        # Save preprocessed ZIP path details in dataset document
        await db.datasets.update_one(
            {"_id": dataset_doc["_id"]},
            {"$set": {
                "status": "ready",
                "rows": len(valid_images),
                "cols": None,
                "columns": list(class_dist.keys()),
                "stats": eda_stats,
                "preview": preview_data,
                "preprocessed_zip_path": preprocessed_zip_local,
                "gridfs_id": str(gridfs_id) if gridfs_id else None,
                "processed_at": datetime.utcnow(),
                "error_message": None,
                "chunk_count": len(chunk_docs),
                "embedding_count": len(chunk_docs),
                "processing_time": processing_time
            }}
        )
        
        await db.rag_indexes.update_one(
            {"_id": ObjectId(index_id)},
            {"$set": {
                "status": "ready",
                "progress": 100.0,
                "chunk_count": len(chunk_docs),
                "error": None
            }}
        )
        
        logger.info(f"Image dataset {dataset_id} preprocessing completed successfully in {processing_time:.1f}s.")
        
    except Exception as e:
        logger.exception(f"Image preprocessing pipeline failed for dataset {dataset_id}:")
        processing_time = (datetime.utcnow() - start_time).total_seconds()
        
        await db.datasets.update_one(
            {"_id": dataset_doc["_id"]},
            {"$set": {
                "status": "error",
                "error_message": str(e),
                "processing_time": processing_time
            }}
        )
        await db.rag_indexes.update_one(
            {"_id": ObjectId(index_id)},
            {"$set": {
                "status": "failed",
                "progress": 0.0,
                "error": str(e)
            }}
        )
        raise
    finally:
        # Cleanup temporary extraction & preprocess folders cleanly
        try:
            shutil.rmtree(tmp_extract_dir)
            shutil.rmtree(tmp_preprocess_dir)
            logger.info("Cleaned up temporary workspace directories.")
        except Exception as cleanup_err:
            logger.warning(f"Failed to clean up directories: {cleanup_err}")
            
        # Clean up users cache
        user_id = dataset_doc.get("user_id")
        if user_id:
            try:
                from utils.cache import cache_clear_user
                await cache_clear_user(str(user_id))
            except Exception:
                pass


async def update_status(db, dataset_id: str, index_id: str, status_str: str, progress_val: float):
    """Update dataset status in MongoDB"""
    await db.datasets.update_one(
        {"_id": ObjectId(dataset_id)},
        {"$set": {"status": status_str}}
    )
    await db.rag_indexes.update_one(
        {"_id": ObjectId(index_id)},
        {"$set": {"status": status_str, "progress": progress_val}}
    )
    logger.info(f"Status transition -> {status_str.upper()} ({progress_val}%)")


def apply_augmentation(img: Image.Image) -> Image.Image:
    """Apply data augmentation: rotation, horizontal flip, zoom, brightness, translation"""
    # 1. Random rotation (±20°)
    angle = random.uniform(-20, 20)
    img = img.rotate(angle, resample=Image.Resampling.BILINEAR)
    
    # 2. Horizontal flip
    if random.choice([True, False]):
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
        
    # 3. Brightness adjustment (0.8 to 1.2)
    enhancer = ImageEnhance.Brightness(img)
    img = enhancer.enhance(random.uniform(0.8, 1.2))
    
    # 4. Random zoom / crop (85% to 100%) and resize back to 224x224
    w, h = img.size
    scale = random.uniform(0.85, 1.0)
    new_w = int(w * scale)
    new_h = int(h * scale)
    x_offset = random.randint(0, w - new_w)
    y_offset = random.randint(0, h - new_h)
    img = img.crop((x_offset, y_offset, x_offset + new_w, y_offset + new_h))
    img = img.resize(TARGET_SIZE, Image.Resampling.BILINEAR)
    
    # 5. Width/height translation shift (±10% translations)
    shift_w = int(w * random.uniform(-0.1, 0.1))
    shift_h = int(h * random.uniform(-0.1, 0.1))
    img = img.transform(TARGET_SIZE, Image.Transform.AFFINE, (1, 0, shift_w, 0, 1, shift_h))
    
    return img
