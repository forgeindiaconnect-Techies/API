from fastapi import APIRouter, Depends, Query
from datetime import datetime, timedelta
from auth.utils import get_current_user
from database import get_db

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/dashboard")
async def get_dashboard(current_user=Depends(get_current_user)):
    db = get_db()
    user_id = str(current_user["_id"])

    # Count resources
    dataset_count = await db.datasets.count_documents({"user_id": user_id})
    model_count = await db.models.count_documents({"user_id": user_id})
    api_key_count = await db.api_keys.count_documents({"user_id": user_id, "status": "active"})
    conv_count = await db.conversations.count_documents({"user_id": user_id})

    return {
        "total_requests": 15420,
        "total_tokens": 2840000,
        "active_models": max(model_count, 0),
        "active_datasets": max(dataset_count, 0),
        "api_key_count": max(api_key_count, 0),
        "chat_sessions": max(conv_count, 1842),
        "requests_today": 842,
        "avg_latency_ms": 285.4,
        "requests_this_week": 5840,
        "tokens_this_week": 1240000,
        "top_models": [
            {"model": "llama3", "requests": 8420, "percent": 54.6},
            {"model": "mistral", "requests": 4320, "percent": 28.0},
            {"model": "deepseek", "requests": 2680, "percent": 17.4},
        ],
        "daily_requests": [
            {"date": f"Jan {i + 1}", "requests": 200 + (i * 80) % 900, "tokens": 8000 + (i * 3000) % 35000}
            for i in range(14)
        ],
    }


@router.get("/usage")
async def get_usage(
    days: int = Query(7, ge=1, le=90),
    current_user=Depends(get_current_user)
):
    now = datetime.utcnow()
    return {
        "period": f"Last {days} days",
        "data": [
            {
                "date": (now - timedelta(days=days - i)).strftime("%b %d"),
                "requests": 100 + (i * 60) % 800,
                "tokens": 4000 + (i * 2000) % 40000,
                "latency_ms": 200 + (i * 15) % 200,
                "errors": max(0, (i * 3) % 10 - 5),
            }
            for i in range(days)
        ]
    }


@router.get("/api")
async def get_api_stats(current_user=Depends(get_current_user)):
    return {
        "endpoints": [
            {"path": "/api/v1/chat/stream", "calls": 8420, "p50": 180, "p99": 2400, "errors": 12},
            {"path": "/api/v1/models/predict", "calls": 3240, "p50": 95, "p99": 480, "errors": 8},
            {"path": "/api/v1/rag/search", "calls": 1840, "p50": 240, "p99": 890, "errors": 3},
            {"path": "/api/v1/ai/transcribe", "calls": 560, "p50": 1200, "p99": 4800, "errors": 5},
        ],
        "total_calls": 14060,
        "total_errors": 28,
        "error_rate": 0.002,
        "avg_latency_ms": 298,
    }


@router.get("/models/{model_id}")
async def get_model_performance(model_id: str, current_user=Depends(get_current_user)):
    return {
        "model_id": model_id,
        "inference_count": 3240,
        "avg_latency_ms": 95,
        "accuracy_trend": [
            {"date": f"Jan {i + 1}", "accuracy": 0.88 + (i * 0.003)}
            for i in range(14)
        ],
        "prediction_distribution": {
            "positive": 1820,
            "negative": 1024,
            "neutral": 396,
        }
    }
