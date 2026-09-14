# AutoPost AI — Automated TikTok Video Pipeline 🎬

An automated pipeline that generates vertical short-form AI videos from a prompt and publishes them directly to TikTok. Built with **Google Gemini** for viral script direction, **Google Veo / AI Motion Engine** for vertical visual scenes, **Neural TTS** for voiceover with word-level timestamps, and **TikTok Content Posting API v2** for automated publishing.

---

## Features

- **Google Gemini Director**: Formats an attention-grabbing 3-second hook, spoken narration, scene breakdown, and viral hashtags.
- **AI Video Generation**: 1080x1920 (9:16) vertical video scenes generated for each scene directive (Google Veo / Imagen with dynamic motion synthesis fallback).
- **Retention Subtitles**: Alex Hormozi / CapCut-style animated word-by-word highlighted subtitles synced with speech timestamps.
- **TikTok Content Posting API v2**: Supports direct publishing, creator inbox drafts, and built-in **Dry-Run mode** for testing without live credentials.
- **Lightweight Studio UI**: Web dashboard with prompt input, real-time 5-stage progress tracker (via Server-Sent Events), live 9:16 smartphone preview player, and TikTok publication trigger.

---

## Quickstart Guide

### 1. Install Dependencies
Make sure you have [FFmpeg](https://ffmpeg.org/) installed and available in your system PATH, then install the Python requirements:

```bash
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Open `.env` (or copy `.env.example` to `.env`) and add your keys:

```env
# Google Gemini API Key (Get from https://aistudio.google.com/)
GEMINI_API_KEY=your_gemini_api_key_here

# TikTok Developer Credentials (https://developers.tiktok.com/)
# Keep TIKTOK_DRY_RUN=True while testing without developer approval
TIKTOK_DRY_RUN=True
TIKTOK_CLIENT_KEY=your_tiktok_client_key_here
TIKTOK_CLIENT_SECRET=your_tiktok_client_secret_here
TIKTOK_ACCESS_TOKEN=your_user_oauth_access_token_here
```

### 3. Run with Docker (Recommended)

You don't need to manually install FFmpeg, fonts, or Python dependencies on your host. Simply run:

```bash
# Build and start container in the background
docker compose up -d --build
```

Then open **[http://localhost:8000](http://localhost:8000)** in your browser.

To view container logs:
```bash
docker compose logs -f
```

To stop the container:
```bash
docker compose down
```

---

### Alternative: Run Locally (Without Docker)

Make sure you have [FFmpeg](https://ffmpeg.org/) installed and available in your system PATH, then:

```bash
pip install -r requirements.txt
python run.py
```
Open **[http://localhost:8000](http://localhost:8000)**.

---

## CLI Usage (Headless Mode)

You can also run the pipeline directly from your terminal:

```bash
# Generate video and inspect preview
python -m src.cli --prompt "5 psychological paradoxes that break your brain"

# Generate and auto-post to TikTok
python -m src.cli --prompt "The secret history of the Colosseum" --publish
```

---

## Architecture Breakdown

```
 [Prompt in Web UI or CLI]
             │
             ▼
 1. Google Gemini Director  ──> Hook, Script, Scene Directives, TikTok Tags
             │
             ├──> 2. Neural TTS Engine ──────> Voiceover + Word-level Timestamps
             │
             └──> 3. AI Video Engine   ──────> 9:16 Vertical Video Scenes
                          │
                          ▼
             4. Video Composer & Subtitles ──> 1080x1920 MP4 + Highlighted Captions
                          │
                          ▼
             5. TikTok Publisher      ──────> Direct Post or Inbox Draft
```

---

## Project Structure

```
auto-post/
├── .env.example                  # Template for API keys
├── .env                          # Local environment configuration
├── requirements.txt              # Project dependencies
├── run.py                        # Web dashboard launcher
├── config/
│   └── settings.py               # Pydantic configuration loader
├── src/
│   ├── cli.py                    # Command-line interface
│   ├── pipeline.py               # Master pipeline orchestrator & SSE reporter
│   ├── generator/
│   │   └── gemini_director.py    # Google Gemini script & scene prompt generator
│   ├── audio/
│   │   └── tts_service.py        # Neural voiceover & word-level timestamping
│   ├── visuals/
│   │   └── video_generator.py    # Google Veo & 9:16 dynamic motion video engine
│   ├── composer/
│   │   ├── subtitles.py          # ASS subtitle generator with word highlighting
│   │   └── video_composer.py     # FFmpeg vertical video compiler & audio mixer
│   ├── tiktok/
│   │   └── publisher.py          # TikTok Content Posting API v2 & Dry-run
│   └── web/
│       ├── app.py                # FastAPI REST & SSE progress server
│       └── static/
│           ├── index.html        # Modern Studio interface
│           ├── style.css         # Dark-mode styling & smartphone mockup
│           └── app.js            # Real-time event listener & preview handler
└── output/                       # Auto-generated videos, audio, and subtitles
```
