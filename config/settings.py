import os
from pathlib import Path
from typing import Literal
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Base directory of the repository
BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env file explicitly
load_dotenv(BASE_DIR / ".env")

class Settings(BaseSettings):
    # Google AI
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GOOGLE_VIDEO_MODEL: str = "veo-3.1-lite-generate-preview"

    # Audio / TTS
    VOICE_NAME: str = "en-US-ChristopherNeural"
    VOICE_RATE: str = "+0%"
    VOICE_PITCH: str = "+0Hz"

    # TikTok Content Posting API
    TIKTOK_DRY_RUN: bool = True
    TIKTOK_CLIENT_KEY: str = ""
    TIKTOK_CLIENT_SECRET: str = ""
    TIKTOK_ACCESS_TOKEN: str = ""
    TIKTOK_CREATOR_USERNAME: str = ""
    TIKTOK_POST_MODE: Literal["DIRECT_POST", "POST_TO_INBOX"] = "DIRECT_POST"

    # Application
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    OUTPUT_DIR: str = str(BASE_DIR / "output")

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def output_path(self) -> Path:
        path = Path(self.OUTPUT_DIR)
        path.mkdir(parents=True, exist_ok=True)
        return path

settings = Settings()
