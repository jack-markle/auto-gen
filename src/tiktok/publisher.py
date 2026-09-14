import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional
import httpx
from pydantic import BaseModel
from config.settings import settings

logger = logging.getLogger(__name__)

class TikTokPublishResult(BaseModel):
    success: bool
    publish_id: str
    status: str
    mode: str
    message: str
    payload: Dict[str, Any]

class TikTokPublisher:
    """
    Publisher supporting TikTok Content Posting API v2 with support for Direct Post,
    Inbox Drafts, and Dry-Run simulations when credentials are not yet configured.
    """

    BASE_URL = "https://open.tiktokapis.com/v2/post/publish"

    def __init__(
        self,
        access_token: Optional[str] = None,
        dry_run: Optional[bool] = None,
        post_mode: Optional[str] = None,
    ):
        self.access_token = access_token or settings.TIKTOK_ACCESS_TOKEN
        self.dry_run = dry_run if dry_run is not None else settings.TIKTOK_DRY_RUN
        self.post_mode = post_mode or settings.TIKTOK_POST_MODE

    async def publish_video(
        self,
        video_path: Path,
        title: str,
        caption: str,
        hashtags: list[str],
        privacy_level: str = "PUBLIC_TO_EVERYONE",  # Options: PUBLIC_TO_EVERYONE, MUTUAL_FOLLOW_FRIENDS, SELF_ONLY
        disable_duet: bool = False,
        disable_stitch: bool = False,
        disable_comment: bool = False,
    ) -> TikTokPublishResult:
        """
        Uploads and publishes a video according to TikTok Content Posting API v2.
        """
        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found at {video_path}")

        file_size = video_path.stat().st_size
        full_text = f"{caption} {' '.join(hashtags)}"

        # Prepare payload according to TikTok Content Posting API v2 specs
        payload = {
            "post_info": {
                "title": title[:150],
                "description": full_text[:2200],
                "privacy_level": privacy_level,
                "disable_duet": disable_duet,
                "disable_stitch": disable_stitch,
                "disable_comment": disable_comment,
                "video_cover_timestamp_ms": 1000,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": file_size,
                "chunk_size": file_size,
                "total_chunk_count": 1,
            },
        }

        logger.info("=" * 70)
        logger.info(f"[STAGE 5: TIKTOK] 🚀 Preparing TikTok Publication ({self.post_mode})")
        logger.info(f"[STAGE 5: TIKTOK] 📌 Title: '{title}'")
        logger.info(f"[STAGE 5: TIKTOK] 📝 Caption ({len(full_text)} chars): '{full_text[:80]}...'")
        logger.info(f"[STAGE 5: TIKTOK] 📁 Video: {video_path.name} ({file_size / (1024*1024):.2f} MB)")
        logger.info(f"[STAGE 5: TIKTOK] 🔒 Privacy: {privacy_level}")
        logger.info("=" * 70)

        # Check if dry-run or credentials missing
        is_simulated = self.dry_run or not self.access_token or self.access_token in ("", "your_user_oauth_access_token_here")

        if is_simulated:
            logger.info("[STAGE 5: TIKTOK] 🧪 [Dry-Run Mode Active] Simulating TikTok Content Posting API v2:")
            logger.info(f"   • Endpoint: {self.BASE_URL}/{'video' if self.post_mode == 'DIRECT_POST' else 'inbox/video'}/init/")
            logger.info(f"   • Payload generated: {json.dumps(payload, indent=2)}")
            await asyncio.sleep(1.0)  # Realistic network latency simulation
            pub_id = f"dryrun_{os.urandom(6).hex()}"
            logger.info(f"[STAGE 5: TIKTOK] ✅ Dry-Run Publish Successful (Mock Publish ID: {pub_id})")
            return TikTokPublishResult(
                success=True,
                publish_id=pub_id,
                status="DRAFT_PREVIEW",
                mode=self.post_mode,
                message=(
                    f"Dry Run successful! Prepared TikTok payload for '{title}'. "
                    "When ready to post live, add your TIKTOK_ACCESS_TOKEN to .env and toggle TIKTOK_DRY_RUN=False."
                ),
                payload=payload,
            )

        # Real TikTok API Publishing flow
        try:
            async with httpx.AsyncClient() as client:
                endpoint = (
                    f"{self.BASE_URL}/video/init/"
                    if self.post_mode == "DIRECT_POST"
                    else f"{self.BASE_URL}/inbox/video/init/"
                )

                headers = {
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json; charset=UTF-8",
                }

                logger.info(f"[STAGE 5: TIKTOK] 📡 Sending POST {endpoint}...")
                response = await client.post(endpoint, json=payload, headers=headers)
                data = response.json()
                logger.info(f"[STAGE 5: TIKTOK] 📩 Response HTTP {response.status_code}: {data}")

                if response.status_code != 200 or data.get("error", {}).get("code") != "ok":
                    error_msg = data.get("error", {}).get("message", "Unknown TikTok API error")
                    logger.error(f"[STAGE 5: TIKTOK] ❌ TikTok API error: {error_msg}")
                    return TikTokPublishResult(
                        success=False,
                        publish_id="",
                        status="ERROR",
                        mode=self.post_mode,
                        message=f"TikTok API error: {error_msg}",
                        payload=payload,
                    )

                publish_id = data["data"]["publish_id"]
                upload_url = data["data"]["upload_url"]
                logger.info(f"[STAGE 5: TIKTOK] 📤 Uploading video bytes to TikTok CDN ({upload_url[:60]}...)...")

                with open(video_path, "rb") as vf:
                    video_bytes = vf.read()

                upload_headers = {
                    "Content-Type": "video/mp4",
                    "Content-Range": f"bytes 0-{file_size - 1}/{file_size}",
                }
                upload_resp = await client.put(upload_url, content=video_bytes, headers=upload_headers)
                logger.info(f"[STAGE 5: TIKTOK] 📩 Upload CDN response HTTP {upload_resp.status_code}")

                if upload_resp.status_code not in (200, 201):
                    logger.error(f"[STAGE 5: TIKTOK] ❌ Video upload failed with HTTP {upload_resp.status_code}")
                    return TikTokPublishResult(
                        success=False,
                        publish_id=publish_id,
                        status="UPLOAD_FAILED",
                        mode=self.post_mode,
                        message=f"Video chunk upload failed with HTTP {upload_resp.status_code}",
                        payload=payload,
                    )

                logger.info(f"[STAGE 5: TIKTOK] ✅ Video uploaded successfully to TikTok! Publish ID: {publish_id}")
                return TikTokPublishResult(
                    success=True,
                    publish_id=publish_id,
                    status="PROCESSING",
                    mode=self.post_mode,
                    message="Video uploaded to TikTok! TikTok is currently processing the post.",
                    payload=payload,
                )

        except Exception as e:
            logger.error(f"[STAGE 5: TIKTOK] ❌ Exception during TikTok publishing: {type(e).__name__}: {e}", exc_info=True)
            return TikTokPublishResult(
                success=False,
                publish_id="",
                status="EXCEPTION",
                mode=self.post_mode,
                message=str(e),
                payload=payload,
            )
