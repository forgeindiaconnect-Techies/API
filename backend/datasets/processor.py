import os
import asyncio
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


async def process_dataset(file_path: str, file_type: str) -> Dict[str, Any]:
    """Process uploaded dataset and extract metadata"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _process_sync, file_path, file_type)


def _process_sync(file_path: str, file_type: str) -> Dict[str, Any]:
    result = {"rows": None, "cols": None, "columns": [], "metadata": {}}

    if not os.path.exists(file_path):
        return result

    try:
        if file_type in ("csv",):
            return _process_csv(file_path)
        elif file_type in ("xlsx", "xls"):
            return _process_excel(file_path)
        elif file_type == "pdf":
            return _process_pdf(file_path)
        elif file_type in ("txt", "md"):
            return _process_text(file_path)
        elif file_type == "json":
            return _process_json(file_path)
        elif file_type in ("jpg", "jpeg", "png", "webp"):
            return _process_image(file_path)
        elif file_type in ("mp3", "wav", "m4a"):
            return _process_audio(file_path)
    except Exception as e:
        logger.error(f"Processing error for {file_type}: {e}")

    return result


def _process_csv(path: str) -> Dict[str, Any]:
    import pandas as pd
    df = pd.read_csv(path)
    return {
        "rows": len(df),
        "cols": len(df.columns),
        "columns": list(df.columns),
        "metadata": {
            "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
            "missing_total": int(df.isnull().sum().sum()),
            "memory_mb": round(df.memory_usage(deep=True).sum() / 1024 / 1024, 2),
        }
    }


def _process_excel(path: str) -> Dict[str, Any]:
    import pandas as pd
    df = pd.read_excel(path)
    return {
        "rows": len(df),
        "cols": len(df.columns),
        "columns": list(df.columns),
        "metadata": {
            "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
            "missing_total": int(df.isnull().sum().sum()),
            "sheets": 1,
        }
    }


def _process_pdf(path: str) -> Dict[str, Any]:
    try:
        import PyPDF2
        with open(path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            pages = len(reader.pages)
            text_sample = ""
            if pages > 0:
                text_sample = reader.pages[0].extract_text()[:500] if reader.pages[0].extract_text() else ""
        return {
            "rows": pages,
            "cols": None,
            "columns": [],
            "metadata": {"pages": pages, "text_sample": text_sample},
        }
    except Exception:
        return {"rows": None, "cols": None, "columns": [], "metadata": {"type": "pdf"}}


def _process_text(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    lines = content.splitlines()
    words = len(content.split())
    return {
        "rows": len(lines),
        "cols": None,
        "columns": [],
        "metadata": {
            "lines": len(lines),
            "words": words,
            "chars": len(content),
        }
    }


def _process_json(path: str) -> Dict[str, Any]:
    import json
    import pandas as pd
    with open(path) as f:
        data = json.load(f)
    if isinstance(data, list) and data and isinstance(data[0], dict):
        df = pd.DataFrame(data)
        return {
            "rows": len(df),
            "cols": len(df.columns),
            "columns": list(df.columns),
            "metadata": {},
        }
    return {"rows": None, "cols": None, "columns": [], "metadata": {}}


def _process_image(path: str) -> Dict[str, Any]:
    try:
        from PIL import Image
        with Image.open(path) as img:
            return {
                "rows": None,
                "cols": None,
                "columns": [],
                "metadata": {
                    "width": img.width,
                    "height": img.height,
                    "mode": img.mode,
                    "format": img.format,
                }
            }
    except Exception:
        return {"rows": None, "cols": None, "columns": [], "metadata": {}}


def _process_audio(path: str) -> Dict[str, Any]:
    return {
        "rows": None,
        "cols": None,
        "columns": [],
        "metadata": {"type": "audio", "path": os.path.basename(path)}
    }


async def run_eda(file_path: str, file_type: str) -> Dict[str, Any]:
    """Run Exploratory Data Analysis on tabular datasets"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _eda_sync, file_path, file_type)


def _eda_sync(file_path: str, file_type: str) -> Dict[str, Any]:
    try:
        import pandas as pd
        import numpy as np

        if file_type == "csv":
            df = pd.read_csv(file_path)
        elif file_type in ("xlsx", "xls"):
            df = pd.read_excel(file_path)
        else:
            return {"error": "EDA only supported for tabular data"}

        numeric_cols = list(df.select_dtypes(include=[np.number]).columns)
        categorical_cols = list(df.select_dtypes(exclude=[np.number]).columns)
        missing_by_col = {col: int(df[col].isnull().sum()) for col in df.columns if df[col].isnull().any()}

        col_stats = {}
        for col in numeric_cols[:10]:
            col_stats[col] = {
                "mean": round(float(df[col].mean()), 4),
                "std": round(float(df[col].std()), 4),
                "min": round(float(df[col].min()), 4),
                "max": round(float(df[col].max()), 4),
                "median": round(float(df[col].median()), 4),
                "q25": round(float(df[col].quantile(0.25)), 4),
                "q75": round(float(df[col].quantile(0.75)), 4),
                "nulls": int(df[col].isnull().sum()),
            }

        for col in categorical_cols[:5]:
            col_stats[col] = {
                "unique_values": int(df[col].nunique()),
                "top_values": df[col].value_counts().head(5).to_dict(),
                "nulls": int(df[col].isnull().sum()),
            }

        # Correlation matrix (numeric only, max 10 cols)
        corr_matrix = {}
        if len(numeric_cols) >= 2:
            corr = df[numeric_cols[:10]].corr().round(3)
            corr_matrix = corr.to_dict()

        return {
            "rows": len(df),
            "cols": len(df.columns),
            "missing_values": int(df.isnull().sum().sum()),
            "missing_by_column": missing_by_col,
            "duplicates": int(df.duplicated().sum()),
            "numeric_columns": numeric_cols,
            "categorical_columns": categorical_cols,
            "column_stats": col_stats,
            "correlation_matrix": corr_matrix,
        }
    except Exception as e:
        logger.error(f"EDA error: {e}")
        return {"error": str(e)}


def auto_preprocess(df, options: dict):
    """Auto preprocess dataframe"""
    import pandas as pd
    import numpy as np

    if options.get("remove_duplicates"):
        df = df.drop_duplicates()

    # Handle missing values
    strategy = options.get("handle_missing", "median")
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    categorical_cols = df.select_dtypes(exclude=[np.number]).columns

    for col in numeric_cols:
        if df[col].isnull().any():
            if strategy == "median":
                df[col] = df[col].fillna(df[col].median())
            elif strategy == "mean":
                df[col] = df[col].fillna(df[col].mean())
            elif strategy == "zero":
                df[col] = df[col].fillna(0)
            elif strategy == "drop":
                df = df.dropna(subset=[col])

    for col in categorical_cols:
        if df[col].isnull().any():
            df[col] = df[col].fillna(df[col].mode()[0] if len(df[col].mode()) else "unknown")

    # Encode categorical
    if options.get("encode_categorical"):
        from sklearn.preprocessing import LabelEncoder
        le = LabelEncoder()
        for col in categorical_cols:
            if df[col].nunique() <= 20:
                df[col] = le.fit_transform(df[col].astype(str))

    # Normalize numeric
    if options.get("normalize"):
        from sklearn.preprocessing import StandardScaler
        scaler = StandardScaler()
        target = options.get("target_column")
        cols_to_scale = [c for c in numeric_cols if c != target]
        if cols_to_scale:
            df[cols_to_scale] = scaler.fit_transform(df[cols_to_scale])

    return df
