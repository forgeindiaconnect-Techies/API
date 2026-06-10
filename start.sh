#!/bin/bash
# Personal AI Studio — local dev startup script

set -e

# Suppress ONNX Runtime GPU device discovery warnings
export ORT_LOGGING_LEVEL=3
export ONNXRUNTIME_PROVIDERS=CPUExecutionProvider

echo "🚀 Starting Personal AI Studio..."

# ─── Check dependencies ───────────────────────────────────────────────────────
command -v node >/dev/null 2>&1 || { echo "❌ Node.js required. Install from https://nodejs.org"; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "❌ Python 3.11+ required."; exit 1; }

# ─── Backend setup ───────────────────────────────────────────────────────────
echo ""
echo "📦 Setting up backend..."
cd backend

if [ ! -d "venv" ]; then
  python3 -m venv venv
  echo "  ✅ Virtual environment created"
fi

source venv/bin/activate
pip install -r requirements.txt -q
echo "  ✅ Python dependencies installed"

if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "  ⚠️  Created .env from example — edit it with your settings"
fi

# Start FastAPI in background
uvicorn main:app --reload --port 8000 &
BACKEND_PID=$!
echo "  ✅ Backend running on http://localhost:8000"
echo "     API docs: http://localhost:8000/api/docs"

cd ..

# ─── Frontend setup ──────────────────────────────────────────────────────────
echo ""
echo "📦 Setting up frontend..."
cd frontend

if [ ! -d "node_modules" ]; then
  npm install -q
  echo "  ✅ Node dependencies installed"
fi

# Start Vite in background
npm run dev &
FRONTEND_PID=$!
echo "  ✅ Frontend running on http://localhost:3000"

cd ..

# ─── Done ────────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Personal AI Studio is ready!"
echo ""
echo "   Frontend:  http://localhost:3000"
echo "   Backend:   http://localhost:8000"
echo "   API Docs:  http://localhost:8000/api/docs"
echo ""
echo "   Demo login: demo@aistudio.com / demo1234"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Press Ctrl+C to stop all services"

# Wait for Ctrl+C
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; echo 'Stopped.'" INT
wait
