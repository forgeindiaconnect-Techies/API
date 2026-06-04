@echo off
echo Starting Personal AI Studio...

:: Backend
cd backend
if not exist "venv" (
    python -m venv venv
    echo Virtual environment created
)
call venv\Scripts\activate
pip install -r requirements.txt -q
if not exist ".env" copy .env.example .env
start "AI Studio Backend" cmd /k "venv\Scripts\activate && uvicorn main:app --reload --port 8000"
cd ..

:: Frontend
cd frontend
if not exist "node_modules" npm install -q
start "AI Studio Frontend" cmd /k "npm run dev"
cd ..

echo.
echo =========================================
echo  Personal AI Studio is starting...
echo.
echo  Frontend:  http://localhost:3000
echo  Backend:   http://localhost:8000
echo  API Docs:  http://localhost:8000/api/docs
echo =========================================
pause
