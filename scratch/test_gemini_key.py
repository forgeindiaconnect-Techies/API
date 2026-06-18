import os
import sys
import asyncio

# Add backend directory to path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, backend_dir)

from database import connect_db
from config import settings

async def main():
    print(f"Testing GEMINI_API_KEY value: {settings.GEMINI_API_KEY}")
    if not settings.GEMINI_API_KEY:
        print("Error: GEMINI_API_KEY is not set!")
        return
        
    try:
        import google.generativeai as genai
        genai.configure(api_key=settings.GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-2.5-flash")
        
        print("Calling generate_content synchronous...")
        response = model.generate_content("Hello, write a single test sentence.")
        print(f"Success! Response: {response.text}")
    except Exception as e:
        print(f"Error testing Gemini key: {e}")

if __name__ == "__main__":
    # Load .env file manually first to make sure settings picks it up
    from dotenv import load_dotenv
    load_dotenv(os.path.join(backend_dir, ".env"))
    
    # Re-import settings to make sure variables are fresh
    import importlib
    import config
    importlib.reload(config)
    from config import settings
    
    asyncio.run(main())
