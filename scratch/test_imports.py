import sys
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_imports")

try:
    logger.info("Importing PyTorch...")
    import torch
    logger.info(f"PyTorch imported successfully. Version: {torch.__version__}")
except Exception as e:
    logger.error(f"PyTorch import failed: {e}")

try:
    logger.info("Importing sentence_transformers...")
    import sentence_transformers
    logger.info("sentence_transformers imported successfully.")
except Exception as e:
    logger.error(f"sentence_transformers import failed: {e}")

try:
    logger.info("Importing chromadb...")
    import chromadb
    logger.info("chromadb imported successfully.")
except Exception as e:
    logger.error(f"chromadb import failed: {e}")

try:
    logger.info("Importing langchain...")
    import langchain
    logger.info("langchain imported successfully.")
except Exception as e:
    logger.error(f"langchain import failed: {e}")

logger.info("Done.")
