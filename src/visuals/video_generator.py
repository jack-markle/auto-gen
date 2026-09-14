import asyncio
import logging
import math
import os
import subprocess
from pathlib import Path
from typing import List, Optional
from PIL import Image, ImageDraw, ImageFont
from config.settings import settings
from src.generator.gemini_director import ScenePlan

logger = logging.getLogger(__name__)

class AIVideoGenerator:
    """
    Generates 9:16 vertical AI video clips for each scene in the plan.
    Supports Google Veo / Imagen and procedural dynamic motion video fallback.
    """
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model_name = model or settings.GOOGLE_VIDEO_MODEL
        self._veo_supported = True
        self._imagen_supported = True

    async def generate_scene_video(
        self,
        scene: ScenePlan,
        duration: float,
        output_file: Path,
    ) -> Path:
        """
        Generates an individual 9:16 vertical video clip for a single scene.
        """
        output_file.parent.mkdir(parents=True, exist_ok=True)
        logger.info("-" * 55)
        logger.info(f"[STAGE 3: VISUALS] 🎬 Synthesizing Scene {scene.scene_id} ({duration:.1f}s)")
        logger.info(f"[STAGE 3: VISUALS] 📷 Camera: '{scene.camera_movement}'")
        logger.info(f"[STAGE 3: VISUALS] 🎨 Visual Directive: '{scene.visual_prompt[:90]}...'")

        # 1. Try Google Veo Video API if key is available and previously supported
        if self._veo_supported and self.api_key and self.api_key not in ("", "your_gemini_api_key_here"):
            try:
                success = await self._generate_with_google_veo(scene, duration, output_file)
                if success and output_file.exists() and output_file.stat().st_size > 1000:
                    logger.info(f"[STAGE 3: VISUALS] ✅ Scene {scene.scene_id} generated directly with Google Veo ({output_file.stat().st_size / 1024:.1f} KB)")
                    return output_file
                else:
                    self._veo_supported = False
            except Exception as e:
                logger.warning(f"[STAGE 3: VISUALS] ⚠️ Google Veo video generation failed: {type(e).__name__}: {e}. Switching to AI image + motion engine.")
                self._veo_supported = False

        # 2. Dynamic Motion Engine: generates AI frame (Google Imagen 3 or procedural) + cinematic camera movement
        await self._generate_dynamic_motion_clip(scene, duration, output_file)
        return output_file

    async def _generate_with_google_veo(
        self, scene: ScenePlan, duration: float, output_file: Path
    ) -> bool:
        """Calls Google's Video Generation model (e.g. veo-3.1-lite-generate-preview)."""
        import time
        start_time = time.time()
        logger.info(f"[STAGE 3: VISUALS] 📡 [Model Request] Submitting video prompt to Google Veo ({self.model_name})...")

        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=self.api_key)

            prompt = (
                f"{scene.visual_prompt}, camera motion: {scene.camera_movement}, "
                "vertical 9:16 aspect ratio, cinematic lighting, 4k ultra-hd"
            )

            # Check if video generation operation is available on client
            if hasattr(client.models, "generate_videos"):
                try:
                    config = types.GenerateVideosConfig(
                        aspect_ratio="9:16",
                    )
                except Exception:
                    config = {"aspect_ratio": "9:16"}

                operation = client.models.generate_videos(
                    model=self.model_name,
                    prompt=prompt,
                    config=config,
                )

                logger.info(f"[STAGE 3: VISUALS] ⏳ Veo operation initiated: {getattr(operation, 'name', 'in_progress')}. Polling for completion...")

                # Poll long-running operation until complete
                max_polls = 60  # max 5 minutes (5s intervals)
                poll_count = 0
                while not getattr(operation, "done", False) and poll_count < max_polls:
                    await asyncio.sleep(5)
                    poll_count += 1
                    try:
                        operation = client.operations.get(operation)
                        logger.info(f"[STAGE 3: VISUALS] ⏳ Veo generating Scene {scene.scene_id}... ({poll_count * 5}s elapsed)")
                    except Exception as poll_err:
                        logger.debug(f"Veo poll notice: {poll_err}")
                        break

                # Check for errors in operation
                if getattr(operation, "error", None):
                    logger.warning(f"[STAGE 3: VISUALS] ❌ Veo operation error: {operation.error}")
                    return False

                # Extract generated video
                response = getattr(operation, "response", None)
                if not response and hasattr(operation, "result"):
                    try:
                        response = operation.result()
                    except Exception:
                        pass

                if response:
                    generated_videos = getattr(response, "generated_videos", [])
                    if generated_videos:
                        first_vid = generated_videos[0]
                        vid_obj = getattr(first_vid, "video", first_vid)

                        # Option A: Direct video_bytes
                        if hasattr(vid_obj, "video_bytes") and vid_obj.video_bytes:
                            output_file.write_bytes(vid_obj.video_bytes)
                            elapsed = time.time() - start_time
                            logger.info(f"[STAGE 3: VISUALS] ✅ [Veo Video] Downloaded {len(vid_obj.video_bytes)/1024:.1f} KB in {elapsed:.2f}s")
                            return True

                        # Option B: Client file download
                        if hasattr(client, "files") and hasattr(client.files, "download"):
                            try:
                                downloaded_bytes = client.files.download(file=vid_obj)
                                if downloaded_bytes:
                                    output_file.write_bytes(downloaded_bytes)
                                    elapsed = time.time() - start_time
                                    logger.info(f"[STAGE 3: VISUALS] ✅ [Veo Video] Downloaded via client.files ({len(downloaded_bytes)/1024:.1f} KB) in {elapsed:.2f}s")
                                    return True
                            except Exception as dl_err:
                                logger.debug(f"client.files.download error: {dl_err}")

                        # Option C: Direct URI download
                        uri = getattr(vid_obj, "uri", None)
                        if uri:
                            import httpx
                            headers = {"x-goog-api-key": self.api_key}
                            async with httpx.AsyncClient(timeout=60.0) as http_client:
                                dl_resp = await http_client.get(uri, headers=headers)
                                if dl_resp.status_code == 200:
                                    output_file.write_bytes(dl_resp.content)
                                    elapsed = time.time() - start_time
                                    logger.info(f"[STAGE 3: VISUALS] ✅ [Veo Video] Downloaded via URI ({len(dl_resp.content)/1024:.1f} KB) in {elapsed:.2f}s")
                                    return True

            logger.info(f"[STAGE 3: VISUALS] ℹ️ Veo returned no downloadable video output.")
        except Exception as e:
            elapsed = time.time() - start_time
            logger.warning(f"[STAGE 3: VISUALS] ❌ [Model Error] Veo API error after {elapsed:.2f}s: {type(e).__name__}: {e}")
        return False

    async def _generate_with_google_imagen(self, scene: ScenePlan, output_image_path: Path) -> bool:
        """Generates a 9:16 AI image using Google Imagen 3 with the Gemini API key."""
        if not self._imagen_supported or not self.api_key or self.api_key in ("", "your_gemini_api_key_here"):
            return False

        import time
        start_time = time.time()
        model_name = "imagen-3.0-generate-002"
        logger.info(f"[STAGE 3: VISUALS] 📡 [Model Request] Sending image prompt to Google Imagen 3 ({model_name})...")
        logger.info(f"[STAGE 3: VISUALS] 🖼️  Prompt: '{scene.visual_prompt[:80]}...' (Aspect Ratio: 9:16)")

        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=self.api_key)
            prompt = f"{scene.visual_prompt}, cinematic vertical 9:16 shot, photorealistic, 8k"

            result = client.models.generate_images(
                model=model_name,
                prompt=prompt,
                config=types.GenerateImagesConfig(
                    number_of_images=1,
                    aspect_ratio="9:16",
                    output_mime_type="image/jpeg",
                ),
            )
            if result.generated_images:
                img_bytes = result.generated_images[0].image.image_bytes
                output_image_path.write_bytes(img_bytes)
                elapsed = time.time() - start_time
                logger.info(f"[STAGE 3: VISUALS] ✅ [Model Response] Google Imagen 3 returned image ({len(img_bytes)/1024:.1f} KB) in {elapsed:.2f}s")
                return True
            logger.warning(f"[STAGE 3: VISUALS] ⚠️ Imagen 3 returned no images.")
        except Exception as e:
            elapsed = time.time() - start_time
            self._imagen_supported = False
            logger.info(f"[STAGE 3: VISUALS] ℹ️ Google Imagen generate_images requires Vertex AI Enterprise credentials ({e}); using dynamic motion engine for remaining scenes.")
        return False

    async def _generate_with_flux(self, scene: ScenePlan, output_image_path: Path) -> bool:
        """
        Generates a photorealistic 9:16 vertical AI image using the state-of-the-art Flux model
        (free, requires no API key, works seamlessly with current setup).
        """
        import time
        import urllib.parse
        import httpx
        start_time = time.time()

        try:
            clean_prompt = scene.visual_prompt[:250]
            encoded = urllib.parse.quote(f"{clean_prompt}, cinematic vertical 9:16 shot, photorealistic, 8k, award winning")
            url = f"https://image.pollinations.ai/prompt/{encoded}?width=1080&height=1920&model=flux&nologo=true&seed={scene.scene_id * 103}"

            logger.info(f"[STAGE 3: VISUALS] 🎨 [Flux AI Model] Generating 9:16 photorealistic image for Scene {scene.scene_id}...")
            async with httpx.AsyncClient(timeout=25.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200 and len(resp.content) > 10000:
                    output_image_path.write_bytes(resp.content)
                    elapsed = time.time() - start_time
                    logger.info(f"[STAGE 3: VISUALS] ✅ [Flux AI Model] Image generated in {elapsed:.2f}s ({len(resp.content)/1024:.1f} KB)")
                    return True
                else:
                    logger.warning(f"[STAGE 3: VISUALS] ⚠️ Flux returned status {resp.status_code}")
        except Exception as e:
            elapsed = time.time() - start_time
            logger.warning(f"[STAGE 3: VISUALS] ⚠️ Flux fetch notice after {elapsed:.2f}s: {e}")
        return False

    async def _generate_dynamic_motion_clip(
        self, scene: ScenePlan, duration: float, output_file: Path
    ):
        """
        Synthesizes a 9:16 vertical cinematic motion clip using AI image art
        and FFmpeg zoompan / motion filters.
        """
        import time
        start_time = time.time()
        temp_dir = output_file.parent / f"scene_{scene.scene_id}_assets"
        temp_dir.mkdir(parents=True, exist_ok=True)
        base_image_path = temp_dir / "base_frame.png"

        # 1. Try Google Imagen 3 (if in Vertex AI mode)
        ai_image_created = await self._generate_with_google_imagen(scene, base_image_path)
        
        # 2. If Imagen 3 is unavailable on Developer API key, use Flux (free, photorealistic AI)
        if not ai_image_created or not base_image_path.exists():
            ai_image_created = await self._generate_with_flux(scene, base_image_path)

        # 3. If offline or network blocks image generation, fallback to procedural visual artwork
        if not ai_image_created or not base_image_path.exists():
            logger.info(f"[STAGE 3: VISUALS] 🎨 Synthesizing procedural high-contrast visual artwork for Scene {scene.scene_id}...")
            self._create_scene_artwork(scene, base_image_path)

        # Use FFmpeg to generate a vertical video clip with Ken Burns camera movement
        fps = 30
        total_frames = int(duration * fps)

        movement = scene.camera_movement.lower()
        if "push" in movement or "zoom" in movement:
            zoom_expr = f"min(zoom+0.0015,1.25)"
            x_expr = "iw/2-(iw/zoom/2)"
            y_expr = "ih/2-(ih/zoom/2)"
        elif "pull" in movement:
            zoom_expr = f"max(1.25-0.0015*on,1.0)"
            x_expr = "iw/2-(iw/zoom/2)"
            y_expr = "ih/2-(ih/zoom/2)"
        elif "tilt" in movement or "up" in movement:
            zoom_expr = "1.1"
            x_expr = "iw/2-(iw/zoom/2)"
            y_expr = f"(ih-ih/zoom)*(on/{total_frames})"
        else:
            zoom_expr = "1.08"
            x_expr = f"(iw-iw/zoom)*(on/{total_frames})"
            y_expr = "ih/2-(ih/zoom/2)"

        filter_chain = (
            f"zoompan=z='{zoom_expr}':x='{x_expr}':y='{y_expr}':"
            f"d={total_frames}:s=1080x1920:fps={fps}"
        )

        logger.info(f"[STAGE 3: VISUALS] ⚙️  Rendering motion clip with FFmpeg ({fps}fps, {total_frames} frames, filter='{movement}')...")

        ffmpeg_cmd = [
            "ffmpeg",
            "-y",
            "-loop", "1",
            "-i", str(base_image_path),
            "-vf", filter_chain,
            "-t", f"{duration:.2f}",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-r", str(fps),
            str(output_file),
        ]

        try:
            process = await asyncio.create_subprocess_exec(
                *ffmpeg_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()
            elapsed = time.time() - start_time
            if process.returncode != 0:
                err_text = stderr.decode('utf-8', errors='ignore')
                logger.error(f"[STAGE 3: VISUALS] ❌ FFmpeg motion error (exit {process.returncode}): {err_text[:300]}")
                self._fallback_render_direct(base_image_path, duration, output_file)
            else:
                out_size_kb = output_file.stat().st_size / 1024.0 if output_file.exists() else 0
                logger.info(f"[STAGE 3: VISUALS] ✅ Scene {scene.scene_id} motion clip rendered in {elapsed:.2f}s ({out_size_kb:.1f} KB)")
        except Exception as e:
            logger.warning(f"[STAGE 3: VISUALS] ⚠️ FFmpeg async failed: {e}. Trying direct fallback.", exc_info=True)
            self._fallback_render_direct(base_image_path, duration, output_file)

    def _create_scene_artwork(self, scene: ScenePlan, output_path: Path):
        """Creates a modern, high-contrast, moody visual frame for the scene."""
        width, height = 1080, 1920
        img = Image.new("RGB", (width, height), color=(10, 15, 26))
        draw = ImageDraw.Draw(img)

        # Palette selection based on scene_id
        palettes = [
            ((15, 23, 42), (99, 102, 241), (236, 72, 153)),  # Indigo to Pink
            ((8, 14, 28), (14, 165, 233), (168, 85, 247)),   # Cyan to Purple
            ((20, 10, 30), (244, 63, 94), (251, 146, 60)),   # Rose to Orange
            ((6, 20, 24), (20, 184, 166), (59, 130, 246)),   # Teal to Blue
            ((15, 10, 35), (139, 92, 246), (16, 185, 129)),  # Violet to Emerald
        ]
        bg_dark, primary_glow, secondary_glow = palettes[(scene.scene_id - 1) % len(palettes)]

        # 1. Subtle gradient background
        for y in range(height):
            ratio = y / height
            r = int(bg_dark[0] * (1 - ratio) + 5 * ratio)
            g = int(bg_dark[1] * (1 - ratio) + 8 * ratio)
            b = int(bg_dark[2] * (1 - ratio) + 15 * ratio)
            draw.line([(0, y), (width, y)], fill=(r, g, b))

        # 2. Glowing atmospheric shapes & geometric visual motif
        center_x, center_y = width // 2, height // 2 - 100
        for radius in range(350, 50, -25):
            alpha_ratio = 1 - (radius / 350.0)
            glow_col = (
                int(primary_glow[0] * alpha_ratio + bg_dark[0] * (1 - alpha_ratio)),
                int(primary_glow[1] * alpha_ratio + bg_dark[1] * (1 - alpha_ratio)),
                int(primary_glow[2] * alpha_ratio + bg_dark[2] * (1 - alpha_ratio)),
            )
            draw.ellipse(
                [center_x - radius, center_y - radius, center_x + radius, center_y + radius],
                outline=glow_col,
                width=3,
            )

        # 3. Floating particle dots
        import random
        random.seed(scene.scene_id * 42)
        for _ in range(60):
            px = random.randint(50, width - 50)
            py = random.randint(100, height - 100)
            p_rad = random.randint(2, 6)
            p_col = secondary_glow if random.random() > 0.5 else primary_glow
            draw.ellipse([px - p_rad, py - p_rad, px + p_rad, py + p_rad], fill=p_col)

        # 4. Scene badge & Visual Concept title
        badge_text = f"SCENE {scene.scene_id:02d}"
        draw.rectangle([center_x - 120, center_y - 250, center_x + 120, center_y - 200], fill=(20, 25, 45), outline=primary_glow, width=2)
        draw.text((center_x, center_y - 225), badge_text, fill=(255, 255, 255), anchor="mm")

        # Visual prompt description preview on card
        card_w, card_h = 920, 320
        card_x1 = (width - card_w) // 2
        card_y1 = height - 550
        card_x2 = card_x1 + card_w
        card_y2 = card_y1 + card_h

        draw.rounded_rectangle([card_x1, card_y1, card_x2, card_y2], radius=24, fill=(15, 20, 35), outline=(50, 65, 100), width=2)
        draw.text((width // 2, card_y1 + 40), "VISUAL DIRECTIVE", fill=primary_glow, anchor="mm")

        # Wrap visual prompt snippet
        words = scene.visual_prompt.split()
        lines = []
        curr = []
        for w in words:
            curr.append(w)
            if len(" ".join(curr)) > 45:
                lines.append(" ".join(curr))
                curr = []
        if curr:
            lines.append(" ".join(curr))

        for idx, line in enumerate(lines[:5]):
            draw.text((width // 2, card_y1 + 90 + idx * 36), line, fill=(210, 220, 240), anchor="mm")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(output_path, "PNG")

    def _fallback_render_direct(self, img_path: Path, duration: float, output_file: Path):
        """Synchronous FFmpeg fallback without complex zoompan filter."""
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", str(img_path),
            "-c:v", "libx264",
            "-t", f"{duration:.2f}",
            "-pix_fmt", "yuv420p",
            "-vf", "scale=1080:1920",
            str(output_file)
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
