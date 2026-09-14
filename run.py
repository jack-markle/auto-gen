"""
AutoPost AI Studio - One-click launcher
Usage:
    python run.py
"""
import uvicorn
from config.settings import settings

def main():
    print("=" * 60)
    print("🚀 Starting AutoPost AI - TikTok Video Automation Studio")
    print(f"📡 Web Dashboard: http://{settings.APP_HOST}:{settings.APP_PORT}")
    print(f"🤖 Gemini Model:  {settings.GEMINI_MODEL}")
    print(f"🎬 TikTok Mode:   {'Dry-Run' if settings.TIKTOK_DRY_RUN else 'Live API'}")
    print("=" * 60)

    uvicorn.run(
        "src.web.app:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=True,
    )

if __name__ == "__main__":
    main()
