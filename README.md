# 🚀 Personal AI Studio

A production-ready full-stack AI platform with RAG, LLM fine-tuning, multimodal AI, and automatic API generation.

---

## 📋 Table of Contents

- [Features](#features)
- [Tech Stack](#tech-stack)
- [Quick Start](#quick-start)
- [Project Structure](#project-structure)
- [Configuration](#configuration)
- [API Reference](#api-reference)
- [Deployment](#deployment)

---

## ✨ Features

| Feature | Description |
|---|---|
| 🤖 **AI Chat** | Streaming ChatGPT-style interface with conversation memory |
| 📊 **Dataset Studio** | Upload CSV/Excel/PDF/Audio/Images with auto EDA |
| 🧠 **Model Training** | LoRA/QLoRA fine-tuning with live loss charts |
| 🔍 **RAG Pipeline** | Semantic search + LLM answers over your documents |
| 🎨 **Multimodal AI** | OCR, image captioning, audio transcription, image generation |
| 🔑 **API Keys** | Auto-generated secure endpoints with rate limiting |
| 📈 **Analytics** | Real-time usage dashboards and model performance |
| 🌓 **Dark/Light Mode** | Beautiful modern UI with theme switching |

---

## 🛠 Tech Stack

### Frontend
- **React 18** + Vite
- **Tailwind CSS** + custom design system
- **Framer Motion** — animations
- **Recharts** — analytics charts
- **Zustand** — global state
- **React Dropzone** — file uploads
- **Socket.IO** — realtime updates

### Backend
- **FastAPI** — async REST API
- **MongoDB** (Motor) — primary database
- **Redis** + **Celery** — background job queue
- **ChromaDB** / **FAISS** — vector databases
- **LangChain** — RAG pipeline
- **HuggingFace + PEFT** — LoRA/QLoRA training
- **Ollama** — local LLM serving (Llama3, Mistral, DeepSeek)
- **Whisper** — audio transcription
- **Stable Diffusion** — image generation

---

## ⚡ Quick Start

### Option 1 — Docker Compose (Recommended)

```bash
# Clone and start
git clone <repo>
cd personal-ai-studio
docker-compose up -d

# Pull an Ollama model
docker exec -it personal-ai-studio-ollama-1 ollama pull llama3
```

Visit: http://localhost:3000

---

### Option 2 — Local Development

#### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env with your MongoDB URL, etc.

uvicorn main:app --reload --port 8000
```

#### Frontend

```bash
cd frontend
npm install
npm run dev
# → http://localhost:3000
```

#### Optional services

```bash
# MongoDB (local)
mongod --dbpath ./data/db

# Redis
redis-server

# Celery worker
cd backend
celery -A workers.celery_app worker --loglevel=info

# Ollama
ollama serve
ollama pull llama3
```

---

## 📁 Project Structure

```
personal-ai-studio/
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── DashboardPage.jsx     # Overview & stats
│   │   │   ├── ChatPage.jsx          # AI chat interface
│   │   │   ├── DatasetsPage.jsx      # Dataset management
│   │   │   ├── DatasetDetailPage.jsx # EDA & preview
│   │   │   ├── ModelsPage.jsx        # Model registry
│   │   │   ├── TrainingPage.jsx      # Fine-tuning UI
│   │   │   ├── RAGPage.jsx           # RAG search
│   │   │   ├── MultimodalPage.jsx    # OCR/caption/transcribe
│   │   │   ├── ApiKeysPage.jsx       # API key management
│   │   │   ├── AnalyticsPage.jsx     # Usage analytics
│   │   │   └── SettingsPage.jsx      # Configuration
│   │   ├── components/
│   │   │   └── layout/
│   │   │       └── DashboardLayout.jsx
│   │   ├── services/api.js           # Axios API layer
│   │   ├── store.js                  # Zustand state
│   │   ├── App.jsx                   # Router
│   │   └── index.css                 # Design tokens
│   └── package.json
│
├── backend/
│   ├── main.py                       # FastAPI app entry
│   ├── config.py                     # Settings
│   ├── database.py                   # MongoDB connection
│   ├── models.py                     # Pydantic schemas
│   ├── api/routes/
│   │   ├── auth.py                   # JWT auth
│   │   ├── chat.py                   # Chat + streaming
│   │   ├── datasets.py               # Dataset CRUD
│   │   ├── models_router.py          # Model management
│   │   ├── rag.py                    # RAG endpoints
│   │   ├── api_keys.py               # API key CRUD
│   │   ├── analytics.py              # Usage stats
│   │   └── ai.py                     # Multimodal AI
│   ├── ai/
│   │   ├── rag/pipeline.py           # RAG pipeline
│   │   └── training/lora_trainer.py  # LoRA/QLoRA trainer
│   ├── datasets/processor.py         # Auto preprocessing + EDA
│   ├── training/trainer.py           # Background training
│   ├── vector_db/store.py            # ChromaDB/FAISS wrapper
│   ├── workers/
│   │   ├── celery_app.py             # Celery config
│   │   └── tasks.py                  # Background tasks
│   ├── requirements.txt
│   └── Dockerfile
│
└── docker-compose.yml
```

---

## ⚙️ Configuration

Copy `backend/.env.example` to `backend/.env` and configure:

| Variable | Description | Default |
|---|---|---|
| `MONGODB_URL` | MongoDB connection string | `mongodb://localhost:27017` |
| `SECRET_KEY` | JWT signing key | *(change in prod!)* |
| `OLLAMA_BASE_URL` | Ollama server URL | `http://localhost:11434` |
| `REDIS_URL` | Redis connection | `redis://localhost:6379/0` |
| `HUGGINGFACE_TOKEN` | HF token for gated models | *(optional)* |
| `OPENAI_API_KEY` | OpenAI fallback key | *(optional)* |
| `MAX_UPLOAD_SIZE_MB` | Max file upload size | `500` |

---

## 📡 API Reference

Base URL: `http://localhost:8000/api/v1`

Interactive docs: http://localhost:8000/api/docs

### Authentication
| Method | Endpoint | Description |
|---|---|---|
| POST | `/auth/register` | Create account |
| POST | `/auth/login` | Get JWT tokens |
| POST | `/auth/refresh` | Refresh access token |
| GET | `/auth/me` | Current user |

### Chat
| Method | Endpoint | Description |
|---|---|---|
| GET | `/chat/conversations` | List conversations |
| POST | `/chat/conversations` | Create conversation |
| GET | `/chat/conversations/:id/messages` | Get messages |
| POST | `/chat/conversations/:id/stream` | Stream AI response (SSE) |

### Datasets
| Method | Endpoint | Description |
|---|---|---|
| POST | `/datasets/upload` | Upload dataset |
| GET | `/datasets/` | List datasets |
| GET | `/datasets/:id/eda` | Get EDA report |
| GET | `/datasets/:id/preview` | Preview rows |

### Models
| Method | Endpoint | Description |
|---|---|---|
| POST | `/models/train` | Start fine-tuning |
| GET | `/models/training/:id` | Training status |
| POST | `/models/:id/predict` | Run inference |

### RAG
| Method | Endpoint | Description |
|---|---|---|
| POST | `/rag/index` | Create vector index |
| POST | `/rag/search` | Semantic search |
| POST | `/rag/chat` | RAG-powered Q&A |

### Public Inference (API Key required)
```
POST /api/v1/predict           → model inference
POST /api/v1/chat              → chat completion
POST /api/v1/image-generate    → image generation
POST /api/v1/audio-transcribe  → speech-to-text
```

---

## 🚀 Deployment

### Frontend → Vercel
```bash
cd frontend
npm run build
vercel deploy --prod
```

### Backend → Railway / Render
```bash
# Set env vars in Railway dashboard
# Connect MongoDB Atlas
# Connect Redis (Upstash)
railway up
```

### GPU Inference → RunPod
- Deploy Ollama container on RunPod A40/A100
- Set `OLLAMA_BASE_URL` to your RunPod endpoint

### Database → MongoDB Atlas
- Create free cluster at cloud.mongodb.com
- Set `MONGODB_URL=mongodb+srv://...`

---

## 🔐 Security Notes

- Change `SECRET_KEY` before production
- Use HTTPS in production
- Set `ALLOWED_ORIGINS` to your actual frontend URL
- Rotate API keys regularly
- Enable MongoDB authentication

---

## 📜 License

MIT — build anything you want!
