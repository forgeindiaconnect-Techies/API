import asyncio
import logging
import time
import math
from datetime import datetime
from typing import Dict, Any

logger = logging.getLogger(__name__)


async def start_training_job(job_id: str, model_id: str, config: Dict[str, Any], db):
    """Simulate or run actual training job"""
    try:
        logger.info(f"Starting training job {job_id}")
        await _log(db, job_id, f"Training started: {config.get('name')}")
        await _log(db, job_id, f"Base model: {config.get('base_model')}")
        await _log(db, job_id, f"Technique: {config.get('technique')}")
        await _log(db, job_id, f"Dataset: {config.get('dataset_id')}")

        epochs = config.get("epochs", 3)
        steps_per_epoch = 50  # Simulated

        for epoch in range(1, epochs + 1):
            await _log(db, job_id, f"=== Epoch {epoch}/{epochs} ===")

            for step in range(1, steps_per_epoch + 1):
                # Check if stopped
                job = await db.training_jobs.find_one({"_id": job_id})
                if job and job.get("status") == "stopped":
                    await _log(db, job_id, "Training stopped by user")
                    await db.models.update_one(
                        {"_id": model_id},
                        {"$set": {"status": "stopped"}}
                    )
                    return

                progress = ((epoch - 1) * steps_per_epoch + step) / (epochs * steps_per_epoch) * 100
                train_loss = 2.3 * math.exp(-progress / 40) + 0.1 + (0.02 * (1 - progress / 100))
                val_loss = train_loss + 0.05

                await db.training_jobs.update_one(
                    {"_id": job_id},
                    {"$set": {
                        "progress": round(progress, 1),
                        "current_epoch": epoch,
                        "current_step": (epoch - 1) * steps_per_epoch + step,
                        "train_loss": round(train_loss, 4),
                        "val_loss": round(val_loss, 4),
                    }}
                )

                if step % 10 == 0:
                    await _log(
                        db, job_id,
                        f"Epoch {epoch} | Step {step}/{steps_per_epoch} | "
                        f"loss={train_loss:.4f} | val_loss={val_loss:.4f}"
                    )

                await asyncio.sleep(0.1)

            await _log(db, job_id, f"Epoch {epoch} complete | train_loss={train_loss:.4f}")

        # Final metrics
        final_accuracy = 0.85 + (0.1 * (1 - math.exp(-epochs / 3)))
        final_f1 = final_accuracy - 0.01
        metrics = {
            "accuracy": round(final_accuracy, 4),
            "f1_score": round(final_f1, 4),
            "precision": round(final_f1 + 0.005, 4),
            "recall": round(final_f1 - 0.005, 4),
        }

        # Mark job complete
        await db.training_jobs.update_one(
            {"_id": job_id},
            {"$set": {
                "status": "ready",
                "progress": 100.0,
                "metrics": metrics,
                "completed_at": datetime.utcnow(),
            }}
        )

        # Update model
        await db.models.update_one(
            {"_id": model_id},
            {"$set": {
                "status": "ready",
                "accuracy": metrics["accuracy"],
                "f1_score": metrics["f1_score"],
                "trained_at": datetime.utcnow(),
            }}
        )

        await _log(db, job_id, f"Training complete! Accuracy: {metrics['accuracy']:.2%} | F1: {metrics['f1_score']:.4f}")
        logger.info(f"Training job {job_id} completed successfully")

    except Exception as e:
        logger.error(f"Training job {job_id} failed: {e}")
        await db.training_jobs.update_one(
            {"_id": job_id},
            {"$set": {"status": "error", "error": str(e), "completed_at": datetime.utcnow()}}
        )
        await db.models.update_one(
            {"_id": model_id},
            {"$set": {"status": "error"}}
        )


async def _log(db, job_id: str, message: str, level: str = "INFO"):
    await db.training_logs.insert_one({
        "job_id": job_id,
        "message": message,
        "level": level,
        "timestamp": datetime.utcnow(),
    })
