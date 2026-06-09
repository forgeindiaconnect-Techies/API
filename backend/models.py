from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Any, Dict
from datetime import datetime
from enum import Enum


# ─── Enums ────────────────────────────────────────────────────────────────────

class DatasetStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    ready = "ready"
    error = "error"


class ModelStatus(str, Enum):
    training = "training"
    ready = "ready"
    error = "error"
    stopped = "stopped"


class TrainingTechnique(str, Enum):
    lora = "LoRA"
    qlora = "QLoRA"
    full = "Full Fine-tuning"
    adapter = "Adapter"
    prompt_tuning = "Prompt Tuning"


class UserRole(str, Enum):
    admin = "admin"
    user = "user"
    viewer = "viewer"


# ─── Auth ─────────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=6)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    role: UserRole = UserRole.user
    created_at: datetime
    avatar_url: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    bio: Optional[str] = None
    avatar_url: Optional[str] = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=6)


# ─── Chat ─────────────────────────────────────────────────────────────────────

class ConversationCreate(BaseModel):
    title: str = "New Conversation"
    model: str = "llama3"
    system_prompt: Optional[str] = None


class ConversationResponse(BaseModel):
    id: str
    title: str
    model: str
    message_count: int = 0
    created_at: datetime
    updated_at: datetime


class MessageCreate(BaseModel):
    content: str
    role: str = "user"
    attachments: Optional[List[str]] = None


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    conversation_id: str
    created_at: datetime
    tokens_used: Optional[int] = None


class StreamRequest(BaseModel):
    content: str
    model: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 2048
    context_window: int = 10
    index_id: Optional[str] = None
    dataset_id: Optional[str] = None
    mode: Optional[str] = "dataset_llm"




# ─── Datasets ─────────────────────────────────────────────────────────────────

class DatasetResponse(BaseModel):
    id: str
    name: str
    file_type: str
    size_bytes: int
    rows: Optional[int] = None
    cols: Optional[int] = None
    status: DatasetStatus
    user_id: str
    created_at: datetime
    processed_at: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None


class ProcessingOptions(BaseModel):
    handle_missing: str = "median"  # median, mean, drop, zero
    remove_duplicates: bool = True
    normalize: bool = True
    encode_categorical: bool = True
    test_size: float = 0.2
    target_column: Optional[str] = None


class EDAResponse(BaseModel):
    dataset_id: str
    rows: int
    cols: int
    missing_values: int
    missing_by_column: Dict[str, int]
    duplicates: int
    numeric_columns: List[str]
    categorical_columns: List[str]
    column_stats: Dict[str, Any]
    target_distribution: Optional[Dict[str, Any]] = None
    correlation_matrix: Optional[Dict[str, Any]] = None
    ai_summary: Optional[str] = None


# ─── Models ───────────────────────────────────────────────────────────────────

class TrainingConfig(BaseModel):
    name: str
    dataset_id: str
    base_model: str = "llama3"
    technique: TrainingTechnique = TrainingTechnique.lora
    task: str = "text-classification"
    epochs: int = Field(3, ge=1, le=100)
    batch_size: int = Field(8, ge=1, le=256)
    learning_rate: float = Field(2e-4, gt=0)
    lora_r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.05
    max_length: int = 512
    warmup_steps: int = 100
    save_steps: int = 500
    eval_steps: int = 500


class TrainingJobResponse(BaseModel):
    id: str
    model_name: str
    status: ModelStatus
    progress: float = 0.0
    current_epoch: int = 0
    current_step: int = 0
    train_loss: Optional[float] = None
    val_loss: Optional[float] = None
    metrics: Optional[Dict[str, float]] = None
    started_at: datetime
    completed_at: Optional[datetime] = None


class ModelResponse(BaseModel):
    id: str
    name: str
    base_model: str
    technique: str
    task: str
    status: ModelStatus
    accuracy: Optional[float] = None
    f1_score: Optional[float] = None
    dataset_id: str
    size_bytes: Optional[int] = None
    parameters: Optional[str] = None
    user_id: str
    created_at: datetime
    trained_at: Optional[datetime] = None


class PredictRequest(BaseModel):
    input: Any
    model_id: str
    parameters: Optional[Dict[str, Any]] = None


class PredictResponse(BaseModel):
    prediction: Any
    confidence: Optional[float] = None
    latency_ms: float
    model_id: str
    tokens_used: Optional[int] = None


# ─── RAG ──────────────────────────────────────────────────────────────────────

class IndexCreate(BaseModel):
    dataset_id: str
    name: str
    embedding_model: str = "all-MiniLM-L6-v2"
    chunk_size: int = 512
    chunk_overlap: int = 50
    index_type: str = "chroma"  # chroma, faiss


class IndexResponse(BaseModel):
    id: str
    name: str
    dataset_id: str
    embedding_model: str
    chunk_count: int
    status: str
    user_id: str
    created_at: datetime


class SearchRequest(BaseModel):
    index_id: str
    query: str
    top_k: int = Field(5, ge=1, le=20)
    score_threshold: float = 0.0


class SearchResult(BaseModel):
    content: str
    score: float
    source: str
    metadata: Dict[str, Any] = {}


class SearchResponse(BaseModel):
    results: List[SearchResult]
    query: str
    index_id: str
    latency_ms: float


class RAGChatRequest(BaseModel):
    index_id: str
    question: str
    model: str = "llama3"
    top_k: int = 5
    temperature: float = 0.3


# ─── API Keys ─────────────────────────────────────────────────────────────────

class ApiKeyCreate(BaseModel):
    name: str
    scopes: List[str] = ["chat"]
    rate_limit: int = 1000
    expires_in_days: Optional[int] = None


class ApiKeyResponse(BaseModel):
    id: str
    name: str
    key: Optional[str] = None  # Only shown on creation
    key_prefix: str
    scopes: List[str]
    rate_limit: int
    requests_count: int = 0
    status: str = "active"
    user_id: str
    created_at: datetime
    last_used_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    is_active: bool = True
    last_used: Optional[datetime] = None


class ApiKeyUpdate(BaseModel):
    name: str


# ─── Analytics ────────────────────────────────────────────────────────────────

class DashboardStats(BaseModel):
    total_requests: int
    total_tokens: int
    active_models: int
    active_datasets: int
    api_key_count: int
    chat_sessions: int
    requests_today: int
    avg_latency_ms: float


# ─── Common ───────────────────────────────────────────────────────────────────

class PaginatedResponse(BaseModel):
    items: List[Any]
    total: int
    page: int
    per_page: int
    pages: int


class ErrorResponse(BaseModel):
    detail: str
    code: Optional[str] = None
