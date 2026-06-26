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
import torch
import gc
from datetime import datetime
from PIL import Image, ImageEnhance
from typing import Dict, Any, List
from bson import ObjectId

logger = logging.getLogger(__name__)

# Constants
TARGET_SIZE = (224, 224)
THUMBNAIL_SIZE = (96, 96)
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

async def process_image_dataset(dataset_doc: dict, zip_path: str, index_id: str, meta_res: dict, db, is_retry=False):
    """
    CNN Image Preprocessing & Feature Extraction Pipeline
    Status transitions: UPLOADED -> EXTRACTED -> PREPROCESSED -> EMBEDDED -> READY
    """
    dataset_id = str(dataset_doc["_id"])
    file_name = dataset_doc.get("file_name") or dataset_doc.get("name", "dataset.zip")
    start_time = datetime.utcnow()
    
    logger.info(f"Starting Image Dataset Preprocessing Pipeline for ID: {dataset_id} (is_retry={is_retry})")
    
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
            if not os.path.exists(tmp_extract_dir) or not os.listdir(tmp_extract_dir):
                raise Exception("ZIP extraction folder is empty or does not exist.")
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
        total_extracted_images = 0

        # Count total extracted images with supported extensions first
        for root, _, files in os.walk(tmp_extract_dir):
            # Check rel_dir to skip dot folders and __MACOSX
            rel_dir = os.path.relpath(root, tmp_extract_dir)
            dir_parts = rel_dir.replace("\\", "/").split("/")
            if any(p == "__MACOSX" or p.startswith(".") for p in dir_parts if p):
                continue
            for file in files:
                if file.startswith("."):
                    continue
                ext = os.path.splitext(file)[1].lower()
                if ext in IMAGE_EXTENSIONS:
                    total_extracted_images += 1

        logger.info(f"[DEBUG LOG] Total extracted images: {total_extracted_images}")
        
        file_idx = 0
        for root, _, files in os.walk(tmp_extract_dir):
            # Check rel_dir to skip dot folders and __MACOSX
            rel_dir = os.path.relpath(root, tmp_extract_dir)
            dir_parts = rel_dir.replace("\\", "/").split("/")
            if any(p == "__MACOSX" or p.startswith(".") for p in dir_parts if p):
                continue
            for file in files:
                if file.startswith("."):
                    continue
                file_idx += 1
                if file_idx % 50 == 0:
                    await asyncio.sleep(0.001)
                file_path = os.path.join(root, file)
                ext = os.path.splitext(file)[1].lower()
                if ext not in IMAGE_EXTENSIONS:
                    # Remove unsupported file formats from extract folder
                    try:
                        os.remove(file_path)
                    except Exception:
                        pass
                    continue
                    
                # 1. Check if empty file (0 bytes)
                try:
                    if os.path.getsize(file_path) == 0:
                        raise Exception("Empty image file (0 bytes)")
                except Exception as sz_err:
                    logger.warning(f"Skipping empty/corrupted image '{file}': {sz_err}")
                    corrupted_files.append(f"{file} ({str(sz_err)})")
                    try:
                        os.remove(file_path)
                    except Exception:
                        pass
                    continue

                # Check Duplication (MD5 Hash check)
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
                        img.load()  # decode pixel data to ensure it is not corrupt
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
            raise Exception("No valid images available for embedding generation (validImages = 0).")
            
        logger.info(f"Total valid images found: {len(valid_images)}")
        logger.info(f"[DEBUG LOG] Total valid images: {len(valid_images)}")
        logger.info(f"Validation summary: {len(valid_images)} valid, {len(corrupted_files)} corrupted, {len(duplicate_files)} duplicates.")
        await update_status(db, dataset_id, index_id, "extracted", 33.0)
        
        # ─── STEP 3: PREPROCESSING ─────────────────────────────────────────
        logger.info("[Step 3/5] Preprocessing and splitting image dataset...")
        await update_status(db, dataset_id, index_id, "preprocessing", 50.0)
        
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
        
        logger.info(
            f"[CNN PIPELINE METRICS]\n"
            f"  datasetId: {dataset_id}\n"
            f"  s3Key: {dataset_doc.get('s3_key')}\n"
            f"  tempPath: {zip_path}\n"
            f"  extractedPath: {tmp_extract_dir}\n"
            f"  totalFiles: {total_extracted_images}\n"
            f"  validImages: {len(valid_images)}\n"
            f"  rejectedImages: {len(corrupted_files)}\n"
            f"  duplicateImages: {len(duplicate_files)}\n"
            f"  trainCount: {len(train_list)}\n"
            f"  valCount: {len(val_list)}\n"
            f"  testCount: {len(test_list)}"
        )
        
        preprocess_idx = 0
        for split_name, img_items in splits.items():
            for item in img_items:
                preprocess_idx += 1
                if preprocess_idx % 20 == 0:
                    await asyncio.sleep(0.001)
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
                    # Convert to forward slashes for Linux compatibility
                    arc_name = arc_name.replace("\\", "/")
                    zip_out.write(file_full_path, arc_name)
                    
        # Backup preprocessed ZIP to AWS S3 (Mandatory, replacement of GridFS)
        preprocessed_s3_key = None
        preprocessed_s3_url = None
        try:
            with open(preprocessed_zip_local, 'rb') as f:
                zip_bytes = f.read()
            from services.s3_service import upload_file_to_s3
            import time
            timestamp = int(time.time())
            
            logger.info(f"Uploading preprocessed ZIP to S3: preprocessed_{file_name}")
            s3_res = await upload_file_to_s3(
                zip_bytes,
                f"preprocessed_{file_name}",
                dataset_id,
                "application/zip",
                timestamp
            )
            preprocessed_s3_key = s3_res.get("s3_key")
            preprocessed_s3_url = s3_res.get("s3_url")
            logger.info(f"Uploaded preprocessed dataset ZIP to S3 with key: {preprocessed_s3_key}")
        except Exception as upload_err:
            logger.error(f"Failed to upload preprocessed ZIP to S3: {upload_err}")
            
        # ─── STEP 4: EMBEDDING & EMBEDDED ─────────────────────────────────
        logger.info("[Step 4/5] Loading pretrained CNN model and generating image embeddings...")
        
        # Transition status to embedding
        await update_status(db, dataset_id, index_id, "embedding", 67.0)
        
        # Model loading started log
        logger.info("Model loading started")
        
        processor = None
        model = None
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        model_type = None # "clip" or "efficientnet"
        
        def load_clip():
            from transformers import CLIPProcessor, CLIPModel
            proc = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
            mod = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
            mod.eval()
            return proc, mod
            
        def load_efficientnet():
            from transformers import EfficientNetImageProcessor, EfficientNetModel
            proc = EfficientNetImageProcessor.from_pretrained("google/efficientnet-b0")
            mod = EfficientNetModel.from_pretrained("google/efficientnet-b0")
            mod.eval()
            return proc, mod

        # Try loading CLIP (ViT-B-32)
        try:
            logger.info("Attempting to load primary model CLIP (ViT-B-32)...")
            processor, model = await asyncio.wait_for(
                asyncio.to_thread(load_clip),
                timeout=60.0
            )
            model = model.to(device)
            model_type = "clip"
            logger.info("Model loaded successfully")
        except (asyncio.TimeoutError, Exception) as clip_err:
            logger.warning(f"Failed or timed out loading CLIP (ViT-B-32): {clip_err}. Falling back to EfficientNetB0...")
            try:
                logger.info("Attempting to load fallback model EfficientNetB0...")
                processor, model = await asyncio.wait_for(
                    asyncio.to_thread(load_efficientnet),
                    timeout=60.0
                )
                model = model.to(device)
                model_type = "efficientnet"
                logger.info("Model loaded successfully")
            except (asyncio.TimeoutError, Exception) as eff_err:
                logger.error(f"Failed or timed out loading fallback EfficientNetB0: {eff_err}")
                raise Exception(f"Model Loading Failure: Both CLIP (ViT-B-32) and EfficientNetB0 failed to load within 60s timeout.")

        # Confirm pretrained model loaded successfully and log device allocation
        if model is None or processor is None:
            raise Exception("Model Loading Failure: Loaded model or processor is None.")
        
        logger.info(f"[DEBUG LOG] Model successfully loaded: {model_type}")
        logger.info(f"[DEBUG LOG] Target device allocation: {device}")
        
        # Get expected dimension dynamically (run sync torch code in thread pool)
        try:
            def _detect_dim():
                dummy_img = Image.new("RGB", TARGET_SIZE)
                with torch.no_grad():
                    if model_type == "clip":
                        inputs = processor(images=dummy_img, return_tensors="pt")
                        inputs = {k: v.to(device) for k, v in inputs.items()}
                        dummy_embed = model.get_image_features(**inputs)
                    else:
                        inputs = processor(images=dummy_img, return_tensors="pt")
                        inputs = {k: v.to(device) for k, v in inputs.items()}
                        outputs = model(**inputs)
                        if hasattr(outputs, "pooler_output") and outputs.pooler_output is not None:
                            dummy_embed = outputs.pooler_output
                        else:
                            dummy_embed = outputs.last_hidden_state.mean(dim=[2, 3])
                return int(dummy_embed.squeeze().shape[-1])

            expected_dim = await asyncio.to_thread(_detect_dim)
            logger.info(f"Dynamically detected embedding dimension: {expected_dim}")
            logger.info(f"[DEBUG LOG] Embedding dimension: {expected_dim}")
        except Exception as dim_err:
            logger.error(f"Failed to detect embedding dimension: {dim_err}")
            raise Exception(f"Dimension detection failed: {dim_err}")

        # Extract features for all valid preprocessed images
        all_meta_images = train_list + val_list + test_list
        # Filter items that successfully wrote a preprocessed image
        all_meta_images = [item for item in all_meta_images if "preprocessed_path" in item]
        total_images = len(all_meta_images)
        logger.info(f"Total images found: {total_images}")
        if total_images == 0:
            raise Exception("No valid images available for embedding generation.")
        
        # Checkpoint resume logic: check existing chunks in MongoDB
        processed_chunks = []
        try:
            cursor = db.dataset_chunks.find({"dataset_id": dataset_id})
            async for chunk in cursor:
                processed_chunks.append(chunk)
        except Exception as err:
            logger.error(f"Error fetching processed chunks: {err}")
            
        processed_filenames = {c["source_file"] for c in processed_chunks}
        
        # ChromaDB setup
        from vector_db.store import VectorStore
        store = VectorStore(backend="chroma", collection_name=index_id)
        
        # Resume/Recovery check
        is_resume = len(processed_filenames) > 0
        if not is_resume:
            logger.info("Fresh run: deleting old ChromaDB store if any...")
            try:
                await store.delete_store()
            except Exception:
                pass
            await store.ensure_initialized()
        else:
            logger.info(f"Resuming run: found {len(processed_filenames)} existing chunks in MongoDB.")
            await store.ensure_initialized()
            
        # Filter out already-processed images
        images_to_process = [item for item in all_meta_images if item["filename"] not in processed_filenames]
        logger.info(f"Skipping {len(processed_filenames)} already processed images. Images remaining to process: {len(images_to_process)}")
        
        batch_size = 16
        total_remaining = len(images_to_process)
        if total_remaining > 0:
            if total_remaining < batch_size:
                logger.warning(f"Remaining image count ({total_remaining}) is less than batch size ({batch_size}). Falling back to batch size = {total_remaining}.")
                batch_size = total_remaining
        else:
            # Fallback when there are no images remaining
            batch_size = 1

        total_batches = (total_remaining + batch_size - 1) // batch_size if total_remaining > 0 else 0
        
        chunk_docs = []
        preview_items = []  # Keep track of first 24 for UI previews (we can populate from processed chunks or batch runs)
        
        # Add already processed files to preview_items so they show up
        for chunk in processed_chunks[:24]:
            preview_items.append({
                "filename": chunk["source_file"],
                "class_name": chunk.get("metadata", {}).get("class", "default"),
                "thumbnail": chunk.get("thumbnail", "")
            })
            
        processed_count = len(processed_filenames)
        start_embedding_time = datetime.utcnow()
        
        for batch_idx in range(0, total_remaining, batch_size):
            batch_num = (batch_idx // batch_size) + 1
            batch_items = images_to_process[batch_idx : batch_idx + batch_size]
            
            # Ensure loader returns non-empty batches
            if not batch_items:
                logger.warning(f"DataLoader encountered empty batch slice at index {batch_idx}")
                continue

            batch_pils = []
            batch_filenames = []
            batch_classes = []
            batch_splits = []
            
            # Detailed debugging logs
            logger.info(f"[DEBUG LOG] Total extracted images: {total_extracted_images}")
            logger.info(f"[DEBUG LOG] Total valid images: {total_images}")
            logger.info(f"[DEBUG LOG] Batch size: {batch_size}")
            logger.info(f"[DEBUG LOG] Number of batches: {total_batches}")
            logger.info(f"[DEBUG LOG] Current batch index: {batch_num}")
            logger.info(f"[DEBUG LOG] Embedding dimension: {expected_dim}")
            logger.info(f"[DEBUG LOG] Saved embeddings count: {processed_count}")
            
            # Load and validate batch PIL images
            for item in batch_items:
                try:
                    # Validate image preprocessing (Resize to TARGET_SIZE, Convert to RGB, skip corrupted)
                    p_img = Image.open(item["preprocessed_path"])
                    if p_img.size != TARGET_SIZE:
                        p_img = p_img.resize(TARGET_SIZE, Image.Resampling.LANCZOS)
                    if p_img.mode != "RGB":
                        p_img = p_img.convert("RGB")
                    
                    batch_pils.append(p_img)
                    batch_filenames.append(item["filename"])
                    batch_classes.append(item["class"])
                    batch_splits.append(item["split"])
                except Exception as load_err:
                    # Log traceback and skip corrupted image
                    import traceback
                    tb_str = traceback.format_exc()
                    logger.warning(f"Skipping corrupted image {item['filename']} during batch load: {load_err}\nTraceback: {tb_str}")
                    
            if not batch_pils:
                continue
                
            # Extract feature vectors using model (with timeout protection and retries)
            # NOTE: Torch inference is CPU-bound; we offload it to a thread pool via
            # asyncio.to_thread() so the event loop is never blocked during embedding.
            max_attempts = 3
            backoff_delay = 2.0
            embeddings_list = None

            def _sync_batch_extraction(pils, proc, mod, dev, mtype):
                """Synchronous torch inference run in a background thread."""
                inputs = proc(images=pils, return_tensors="pt")
                inputs = {k: v.to(dev) for k, v in inputs.items()}
                with torch.no_grad():
                    if mtype == "clip":
                        outputs = mod.get_image_features(**inputs)
                    else:
                        outputs = mod(**inputs)
                        if hasattr(outputs, "pooler_output") and outputs.pooler_output is not None:
                            outputs = outputs.pooler_output
                        else:
                            outputs = outputs.last_hidden_state.mean(dim=[2, 3])
                    res = outputs.squeeze().tolist()
                    if len(pils) == 1:
                        res = [res]
                return res

            for attempt in range(max_attempts):
                try:
                    embeddings_list = await asyncio.wait_for(
                        asyncio.to_thread(
                            _sync_batch_extraction,
                            batch_pils, processor, model, device, model_type
                        ),
                        timeout=60.0
                    )
                    logger.info(f"Embeddings generated: {len(embeddings_list)}")
                    break
                except asyncio.TimeoutError:
                    logger.warning(f"Batch {batch_num} embedding generation timed out (Attempt {attempt + 1}/{max_attempts})")
                    if attempt == max_attempts - 1:
                        raise Exception(f"Embedding Generation Timeout: Batch {batch_num} exceeded 60s limit after {max_attempts} attempts.")
                    await asyncio.sleep(backoff_delay * (2 ** attempt))
                except Exception as extract_err:
                    logger.warning(f"Failed embedding generation at batch {batch_num} (attempt {attempt + 1}/{max_attempts}): {extract_err}")
                    if attempt == max_attempts - 1:
                        raise Exception(f"Embedding Generation Failure: Failed to generate vectors for batch {batch_num} after {max_attempts} attempts. Details: {extract_err}")
                    await asyncio.sleep(backoff_delay * (2 ** attempt))
                
            # Insert into Vector Store and MongoDB Chunks
            vector_docs = []
            vector_embeds = []
            vector_metadatas = []
            vector_ids = []
            batch_chunk_docs = []
            
            for b_idx, pil_img in enumerate(batch_pils):
                filename = batch_filenames[b_idx]
                class_name = batch_classes[b_idx]
                split_name = batch_splits[b_idx]
                embedding = embeddings_list[b_idx]
                
                # Validate embedding dimensions before insertion
                if len(embedding) != expected_dim:
                    logger.error(f"Embedding dimension mismatch for {filename}: expected {expected_dim}, got {len(embedding)}")
                    continue
                    
                chunk_id = f"{index_id}_{processed_count}"
                
                # Generate 96x96 Base64 Thumbnail
                try:
                    thumb_img = pil_img.copy()
                    thumb_img.thumbnail(THUMBNAIL_SIZE)
                    buf = io.BytesIO()
                    thumb_img.save(buf, format="JPEG", quality=80)
                    base64_thumb = base64.b64encode(buf.getvalue()).decode("utf-8")
                except Exception as thumb_err:
                    logger.warning(f"Failed to generate thumbnail for {filename}: {thumb_err}")
                    base64_thumb = ""
                
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
                batch_chunk_docs.append(chunk_doc)
                
                # Keep first 24 images for preview tab
                if len(preview_items) < 24:
                    preview_items.append({
                        "filename": filename,
                        "class_name": class_name,
                        "thumbnail": base64_thumb
                    })
                    
                processed_count += 1
                
                # Save checkpoint every 100 images
                if processed_count % 100 == 0:
                    try:
                        await db.datasets.update_one(
                            {"_id": ObjectId(dataset_id)},
                            {"$set": {
                                "stats.checkpoint": {
                                    "processed_images": processed_count,
                                    "total_images": total_images,
                                    "timestamp": datetime.utcnow()
                                }
                            }}
                        )
                        logger.info(f"Saved checkpoint: processed {processed_count}/{total_images} images.")
                    except Exception as cp_err:
                        logger.warning(f"Failed to save checkpoint to database: {cp_err}")
                        
            # Insert vectors to ChromaDB (Batch insert with retry)
            if vector_ids:
                logger.info(f"ChromaDB insert progress: Staging {len(vector_ids)} vectors for insert")
                for attempt in range(max_attempts):
                    try:
                        await store.add_documents(vector_docs, vector_embeds, vector_metadatas, vector_ids)
                        logger.info(f"ChromaDB insertion status: Success for {len(vector_ids)} vectors")
                        break
                    except Exception as vector_err:
                        logger.warning(f"ChromaDB insert failed at batch {batch_num} (attempt {attempt + 1}/{max_attempts}): {vector_err}")
                        if attempt == max_attempts - 1:
                            logger.error(f"ChromaDB insert failed permanently for batch {batch_num}: {vector_err}")
                            raise Exception(f"ChromaDB Insertion Failure: {vector_err}")
                        await asyncio.sleep(backoff_delay * (2 ** attempt))
                        
            # Insert MongoDB chunk docs for this batch
            if batch_chunk_docs:
                try:
                    await db.dataset_chunks.insert_many(batch_chunk_docs)
                    chunk_docs.extend(batch_chunk_docs)
                except Exception as chunk_insert_err:
                    logger.error(f"Failed to insert chunk docs to MongoDB for batch: {chunk_insert_err}")
                    
            # Calculate estimated remaining time
            time_spent = (datetime.utcnow() - start_embedding_time).total_seconds()
            images_done = processed_count - len(processed_filenames)
            if images_done > 0:
                time_per_image = time_spent / images_done
                remaining_images = len(images_to_process) - images_done
                est_remaining = time_per_image * remaining_images
            else:
                est_remaining = 0.0
                
            # Real-time progress updates in MongoDB
            try:
                await db.datasets.update_one(
                    {"_id": ObjectId(dataset_id)},
                    {"$set": {
                        "status": "embedding",
                        "embedding_progress": {
                            "processed_images": processed_count,
                            "total_images": total_images,
                            "current_batch": batch_num,
                            "total_batches": total_batches,
                            "estimated_remaining_seconds": est_remaining,
                            "batch_size": batch_size
                        }
                    }}
                )
                
                # Update index progress: scale from 67% (embedding start) to 85% (embedded)
                progress_val = 67.0 + (float(processed_count) / float(total_images if total_images > 0 else 1)) * 18.0
                await db.rag_indexes.update_one(
                    {"_id": ObjectId(index_id)},
                    {"$set": {
                        "status": "embedding",
                        "progress": min(85.0, progress_val)
                    }}
                )
            except Exception as update_err:
                logger.warning(f"Failed to update real-time progress in database: {update_err}")
                
            # Release memory after batch
            del batch_pils
            del embeddings_list
            if device.type == "cuda":
                torch.cuda.empty_cache()
            import gc
            gc.collect()
            
            # Yield to event loop
            await asyncio.sleep(0.01)
            
        # Final validation
        chroma_count = await store.count()
        chunks_in_db = await db.dataset_chunks.count_documents({"dataset_id": dataset_id})
        logger.info(f"Final Validation: ChromaDB vectors count = {chroma_count}, MongoDB chunks count = {chunks_in_db}, Target valid images = {total_images}")
        
        if chunks_in_db == 0:
            raise Exception("Final Validation Failure: No embeddings were successfully generated or stored in MongoDB.")
        if chroma_count != chunks_in_db:
            logger.warning(f"Final Validation Mismatch: ChromaDB vectors ({chroma_count}) vs MongoDB chunks ({chunks_in_db})")
            
        # Update status to embedded
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
                "preprocessed_s3_key": preprocessed_s3_key,
                "preprocessed_s3_url": preprocessed_s3_url,
                "preprocessedS3Key": preprocessed_s3_key,
                "preprocessedS3Url": preprocessed_s3_url,
                "gridfs_id": None,
                "processed_at": datetime.utcnow(),
                "error_message": None,
                "chunk_count": chunks_in_db,
                "embedding_count": chunks_in_db,
                "processing_time": processing_time
            }}
        )
        
        await db.rag_indexes.update_one(
            {"_id": ObjectId(index_id)},
            {"$set": {
                "status": "ready",
                "progress": 100.0,
                "chunk_count": chunks_in_db,
                "error": None
            }}
        )
        
        logger.info(f"Image dataset {dataset_id} preprocessing completed successfully in {processing_time:.1f}s.")
        
    except Exception as e:
        err_msg = str(e)
        is_permanent_failure = "No valid images" in err_msg or "ZIP Extraction Failure" in err_msg
        
        if not is_retry and not is_permanent_failure:
            logger.warning(f"Image preprocessing pipeline failed for dataset {dataset_id}: {e}. Automatically retrying once...")
            # Clean up directories before retrying
            try:
                if os.path.exists(tmp_extract_dir):
                    shutil.rmtree(tmp_extract_dir)
                if os.path.exists(tmp_preprocess_dir):
                    shutil.rmtree(tmp_preprocess_dir)
            except Exception as cleanup_err:
                logger.warning(f"Failed to clean up directories before retry: {cleanup_err}")
                
            # Clean up vector store to avoid duplicates if partial embeds were written
            try:
                from vector_db.store import VectorStore
                store = VectorStore(backend="chroma", collection_name=index_id)
                await store.delete_store()
            except Exception:
                pass
                
            # Clear partially inserted chunks in MongoDB for dataset
            try:
                await db.dataset_chunks.delete_many({"dataset_id": dataset_id})
            except Exception:
                pass

            # Recursively call with is_retry=True
            return await process_image_dataset(dataset_doc, zip_path, index_id, meta_res, db, is_retry=True)
            
        import traceback
        error_tb = traceback.format_exc()
        logger.exception(f"Image preprocessing pipeline failed on retry for dataset {dataset_id}:")
        processing_time = (datetime.utcnow() - start_time).total_seconds()
        
        detailed_error = f"Pipeline execution failed. Detail: {str(e)}\n\nTraceback:\n{error_tb}"
        
        await db.datasets.update_one(
            {"_id": dataset_doc["_id"]},
            {"$set": {
                "status": "failed",
                "error_message": detailed_error,
                "processing_time": processing_time
            }}
        )
        await db.rag_indexes.update_one(
            {"_id": ObjectId(index_id)},
            {"$set": {
                "status": "failed",
                "progress": 0.0,
                "error": detailed_error
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
    try:
        from bson import ObjectId as BsonObjectId
        dataset_doc = await db.datasets.find_one({"_id": BsonObjectId(dataset_id)})
        if dataset_doc:
            from services.dataset_service import log_dataset_status
            log_dataset_status(
                dataset_id=str(dataset_id),
                file_path=dataset_doc.get("file_path"),
                file_type=dataset_doc.get("file_type") or dataset_doc.get("file_name", "").split(".")[-1].lower() if dataset_doc.get("file_name") else "zip",
                status=status_str,
                progress=progress_val,
                rows=dataset_doc.get("rows"),
                cols=dataset_doc.get("cols")
            )
    except Exception as log_err:
        logger.warning(f"Failed to log structured status update: {log_err}")


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
