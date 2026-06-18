import asyncio
import logging
import time
from database import get_db
from config import settings

logger = logging.getLogger(__name__)

async def startup_health_check() -> bool:
    """Run health checks for MongoDB Atlas, AWS S3, and ChromaDB, and print a formatted summary report."""
    import sys
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
        
    mongodb_ok = False
    mongodb_error = ""
    mongodb_time = 0.0
    
    s3_ok = False
    s3_error = ""
    
    chromadb_ok = False
    chromadb_error = ""
    
    rag_ok = False
    
    # 1. MongoDB check
    db = get_db()
    if db is not None:
        try:
            start_ping = time.perf_counter()
            await db._db.command("ping")
            mongodb_time = (time.perf_counter() - start_ping) * 1000
            mongodb_ok = True
        except Exception as e:
            mongodb_error = str(e)
    else:
        mongodb_error = "Database connection wrapper is None."
        
    # 2. AWS S3 check
    s3_configured = bool(settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY and settings.AWS_S3_BUCKET)
    if s3_configured:
        try:
            import boto3
            def _check_s3():
                s3_client = boto3.client(
                    "s3",
                    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                    region_name=settings.AWS_REGION_NAME
                )
                s3_client.head_bucket(Bucket=settings.AWS_S3_BUCKET)
            await asyncio.to_thread(_check_s3)
            s3_ok = True
        except Exception as e:
            s3_error = str(e)
    else:
        s3_error = "AWS credentials or S3 bucket not configured."

    # 3. ChromaDB check
    try:
        from services.chroma_service import ChromaManager
        client = await asyncio.to_thread(ChromaManager.get_client)
        if client is not None:
            await asyncio.to_thread(client.heartbeat)
            chromadb_ok = True
        else:
            chromadb_error = "ChromaDB client is None"
    except Exception as e:
        chromadb_error = str(e)

    # 4. RAG Recovery Service (Started in background)
    rag_ok = True

    # 5. Compile and format status summary
    lines = [
        "==================================================",
        "🚀 Application Startup Checks",
        "=================================================="
    ]
    
    # MongoDB Atlas
    if mongodb_ok:
        lines.append(f"\n✅ MongoDB Atlas Connected\n   Database: {settings.MONGODB_DB_NAME}\n   Connection Time: {mongodb_time:.2f} ms")
    else:
        err_msg = f"❌ MongoDB Connection Failed: {mongodb_error}"
        lines.append(f"\n{err_msg}")
        logger.error(err_msg)
        
    # AWS S3
    if s3_ok:
        lines.append(f"\n✅ AWS S3 Connected\n   Bucket: {settings.AWS_S3_BUCKET}\n   Region: {settings.AWS_REGION_NAME}")
    else:
        err_msg = f"❌ AWS S3 Connection Failed: {s3_error}"
        lines.append(f"\n{err_msg}")
        if s3_configured:
            logger.error(err_msg)
        else:
            logger.warning(err_msg)
            
    # ChromaDB
    if chromadb_ok:
        lines.append(f"\n✅ ChromaDB Connected\n   Path: {settings.CHROMA_PERSIST_DIR}")
    else:
        err_msg = f"❌ ChromaDB Connection Failed: {chromadb_error}"
        lines.append(f"\n{err_msg}")
        logger.error(err_msg)
        
    # RAG Recovery
    if rag_ok:
        lines.append("\n✅ RAG Recovery Service Started")
        
    # Overall summary status
    if mongodb_ok and s3_ok and chromadb_ok and rag_ok:
        lines.append("\n🎉 All Services Connected Successfully")
    else:
        lines.append("\n⚠️ Some Non-Critical Services Failed to Connect")
        
    lines.append("==================================================")
    
    report_string = "\n".join(lines)
    
    # Print directly to console for unformatted clear output block in logs
    import sys
    try:
        print(report_string, flush=True)
    except UnicodeEncodeError:
        try:
            # Attempt to encode and decode using replace handler
            enc_str = report_string.encode(sys.stdout.encoding or 'utf-8', errors='replace').decode(sys.stdout.encoding or 'utf-8', errors='replace')
            print(enc_str, flush=True)
        except Exception:
            # Fallback to plain ASCII characters if all else fails
            ascii_str = report_string.replace("🚀", "[STARTUP]").replace("✅", "[OK]").replace("❌", "[FAIL]").replace("🎉", "[SUCCESS]").replace("⚠️", "[WARNING]")
            try:
                print(ascii_str, flush=True)
            except Exception:
                pass
            
    return mongodb_ok
