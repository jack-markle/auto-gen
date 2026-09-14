"""
Command-line interface for AutoPost AI
Usage:
    python -m src.cli --prompt "3 psychological tricks" [--publish]
"""
import argparse
import asyncio
import sys
from src.pipeline import AutoPostPipeline

async def async_main():
    parser = argparse.ArgumentParser(description="AutoPost AI TikTok CLI")
    parser.add_argument("--prompt", "-p", type=str, required=True, help="Topic or prompt for the video")
    parser.add_argument("--publish", action="store_true", help="Automatically post to TikTok")
    parser.add_argument("--voice", type=str, default=None, help="TTS Voice (e.g. en-US-ChristopherNeural)")
    args = parser.parse_args()

    pipeline = AutoPostPipeline()
    if args.voice:
        pipeline.tts.voice = args.voice

    async def cli_progress(stage, percent, msg, meta=None):
        print(f"[{percent:3d}%] [{stage:12s}] {msg}")

    print(f"\n🎬 Starting pipeline for prompt: '{args.prompt}'\n")
    result = await pipeline.run(prompt=args.prompt, auto_publish=args.publish, progress_cb=cli_progress)

    print("\n" + "=" * 60)
    print("✅ Generation Complete!")
    print(f"📁 Video Path:    {result.video_path}")
    print(f"⏱  Duration:      {result.duration:.1f}s")
    print(f"📌 TikTok Title:  {result.plan.tiktok_title}")
    print(f"📝 TikTok Caption:{result.plan.tiktok_caption}")
    print(f"🏷  Hashtags:      {' '.join(result.plan.hashtags)}")
    if result.publish_result:
        print(f"🚀 TikTok Status: {result.publish_result.status} ({result.publish_result.message})")
    print("=" * 60 + "\n")

def main():
    asyncio.run(async_main())

if __name__ == "__main__":
    main()
