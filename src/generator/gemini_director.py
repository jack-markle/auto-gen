import json
import logging
from typing import List, Optional
from pydantic import BaseModel, Field
from config.settings import settings

logger = logging.getLogger(__name__)

class ScenePlan(BaseModel):
    scene_id: int
    narration_chunk: str
    visual_prompt: str
    camera_movement: str = "cinematic slow push-in"
    estimated_duration: float = 4.0

class VideoPlan(BaseModel):
    topic: str
    hook: str
    full_narration: str
    scenes: List[ScenePlan]
    tiktok_title: str
    tiktok_caption: str
    hashtags: List[str]

DIRECTOR_SYSTEM_PROMPT = """
You are an elite short-form video director and viral TikTok content creator.
Your job is to transform a user prompt/idea into a high-retention vertical (9:16) video blueprint with:
1. An irresistible 3-second hook that stops users from scrolling.
2. A fast-paced, engaging spoken narration (around 30-50 seconds total, approx 70-110 words).
3. 4 to 6 distinct, visually striking scenes. For each scene, write:
   - narration_chunk: What is spoken in this scene.
   - visual_prompt: A hyper-detailed visual prompt tailored for AI video generation (Veo/Sora/Runway style). Describe subject, lighting (cinematic, moody, volumetric), camera angle, and motion.
   - camera_movement: e.g. "slow cinematic push-in", "aerial drone reveal", "orbit pan".
   - estimated_duration: Duration in seconds (usually 3.5 to 6.0 seconds).
4. TikTok post metadata:
   - tiktok_title: Catchy title (max 50 chars).
   - tiktok_caption: Engaging caption with question/hook to drive comments.
   - hashtags: 5-7 viral and niche hashtags (include #fyp, #viral, etc.).

Return ONLY a valid JSON object matching this schema:
{
  "topic": "...",
  "hook": "...",
  "full_narration": "...",
  "scenes": [
    {
      "scene_id": 1,
      "narration_chunk": "...",
      "visual_prompt": "...",
      "camera_movement": "...",
      "estimated_duration": 4.0
    }
  ],
  "tiktok_title": "...",
  "tiktok_caption": "...",
  "hashtags": ["#fyp", "#topic", ...]
}
"""

class GeminiDirector:
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model_name = model or settings.GEMINI_MODEL

    def generate_plan(
        self,
        prompt: str,
        max_scene_duration: float = 4.0,
        max_scenes: int = 5,
        max_video_duration: float = 30.0,
    ) -> VideoPlan:
        """Generates a complete video plan using Google Gemini."""
        if not self.api_key or self.api_key.strip() in ("", "your_gemini_api_key_here"):
            logger.warning("[STAGE 1: SCRIPTING] ⚠️ No GEMINI_API_KEY found. Generating simulated fallback plan.")
            return self._generate_fallback_plan(prompt, max_scene_duration, max_scenes, max_video_duration)

        import time
        start_time = time.time()
        logger.info("=" * 70)
        logger.info(f"[STAGE 1: SCRIPTING] 🚀 Sending prompt to Google Gemini ({self.model_name})")
        logger.info(f"[STAGE 1: SCRIPTING] 📝 User Prompt: '{prompt}' (Max Scenes: {max_scenes}, Max Video Len: {max_video_duration}s, Max Scene: {max_scene_duration}s)")
        logger.info("=" * 70)

        # Estimate target spoken word count: ~2.3 words per second
        target_words = int(max_video_duration * 2.3)

        pacing_instruction = (
            f"STRICT PACING CONSTRAINTS:\n"
            f"1. Total video length MUST NOT EXCEED {max_video_duration} seconds.\n"
            f"2. Keep the full_narration to approximately {int(target_words * 0.8)} to {target_words} words total so spoken audio finishes within {max_video_duration} seconds.\n"
            f"3. Generate EXACTLY {max_scenes} distinct scenes (or fewer, minimum 3, maximum {max_scenes}).\n"
            f"4. The MAXIMUM duration of each individual scene must be {max_scene_duration} seconds."
        )

        try:
            # Suppress internal SDK AFC advisory warning if present
            logging.getLogger("google_genai.models").setLevel(logging.ERROR)

            # Try new Google GenAI SDK first
            try:
                from google import genai
                from google.genai import types

                client = genai.Client(api_key=self.api_key)
                logger.info(f"[STAGE 1: SCRIPTING] 📡 Initializing Gemini session (model={self.model_name})...")
                
                content_config = types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.7,
                )

                full_user_content = f"{DIRECTOR_SYSTEM_PROMPT}\n\n{pacing_instruction}\n\nUser Topic / Idea: {prompt}\nRespond with JSON only."

                # Use Chat interface as recommended by Google GenAI SDK to avoid AFC advisory warning
                if hasattr(client, "chats") and hasattr(client.chats, "create"):
                    chat = client.chats.create(model=self.model_name, config=content_config)
                    response = chat.send_message(full_user_content)
                else:
                    response = client.models.generate_content(
                        model=self.model_name,
                        contents=full_user_content,
                        config=content_config,
                    )
                text = response.text
                elapsed = time.time() - start_time
                logger.info(f"[STAGE 1: SCRIPTING] ✅ Received response from Gemini in {elapsed:.2f}s (Response length: {len(text)} chars)")
            except ImportError:
                # Fallback to google.generativeai
                import google.generativeai as genai

                logger.info(f"[STAGE 1: SCRIPTING] 📡 Calling google.generativeai GenerativeModel (model={self.model_name})...")
                genai.configure(api_key=self.api_key)
                model = genai.GenerativeModel(
                    self.model_name,
                    generation_config={"response_mime_type": "application/json", "temperature": 0.7}
                )
                response = model.generate_content(
                    f"{DIRECTOR_SYSTEM_PROMPT}\n\n{pacing_instruction}\n\nUser Topic / Idea: {prompt}\nRespond with JSON only."
                )
                text = response.text
                elapsed = time.time() - start_time
                logger.info(f"[STAGE 1: SCRIPTING] ✅ Received response from Gemini in {elapsed:.2f}s (Response length: {len(text)} chars)")

            # Clean JSON markdown fences if present
            cleaned = text.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            data = json.loads(cleaned.strip())

            # Enforce max_scenes constraint on returned scenes
            if "scenes" in data and len(data["scenes"]) > max_scenes:
                data["scenes"] = data["scenes"][:max_scenes]

            plan = VideoPlan(**data)

            logger.info(f"[STAGE 1: SCRIPTING] 🎯 Script Plan Generated Successfully:")
            logger.info(f"   • Hook: '{plan.hook}'")
            logger.info(f"   • Scenes: {len(plan.scenes)} total (Max Configured: {max_scenes})")
            for sc in plan.scenes:
                logger.info(f"     - Scene {sc.scene_id}: {sc.camera_movement} | Prompt: {sc.visual_prompt[:60]}...")
            logger.info(f"   • TikTok Title: '{plan.tiktok_title}'")
            logger.info(f"   • Hashtags: {' '.join(plan.hashtags)}")
            return plan

        except Exception as e:
            elapsed = time.time() - start_time
            logger.error("=" * 70)
            logger.error(f"[STAGE 1: SCRIPTING] ❌ Error calling Google Gemini API after {elapsed:.2f}s: {type(e).__name__}: {e}")
            logger.error(f"[STAGE 1: SCRIPTING] ⚠️ Falling back to high-retention procedural plan.", exc_info=True)
            logger.error("=" * 70)
            return self._generate_fallback_plan(prompt, max_scene_duration, max_scenes, max_video_duration)

    def _generate_fallback_plan(
        self,
        prompt: str,
        max_scene_duration: float = 4.0,
        max_scenes: int = 5,
        max_video_duration: float = 30.0,
    ) -> VideoPlan:
        """Provides a high-retention fallback plan when Gemini key is pending."""
        topic_clean = prompt.strip().title()
        dur = min(max_scene_duration, 4.0)
        return VideoPlan(
            topic=topic_clean,
            hook=f"Scientists just discovered something terrifying about {topic_clean}.",
            full_narration=(
                f"Did you know the secret behind {topic_clean}? "
                "For decades, researchers thought they understood how this worked. "
                "Until one unexpected experiment turned everything upside down. "
                "The findings were so shocking that they had to re-evaluate the entire theory. "
                "Drop a comment if you would ever dare to experience this yourself!"
            ),
            scenes=[
                ScenePlan(
                    scene_id=1,
                    narration_chunk=f"Did you know the secret behind {topic_clean}?",
                    visual_prompt=f"Cinematic ultra-realistic 9:16 vertical shot of mysterious futuristic laboratory studying {topic_clean}, dramatic neon blue and amber volumetric lighting, 8k resolution.",
                    camera_movement="slow cinematic push-in",
                    estimated_duration=3.5,
                ),
                ScenePlan(
                    scene_id=2,
                    narration_chunk="For decades, researchers thought they understood how this worked.",
                    visual_prompt=f"Macro cinematic view of archival scientific documents and holographic diagrams about {topic_clean}, dust particles floating in light beam.",
                    camera_movement="slow tilt down",
                    estimated_duration=4.0,
                ),
                ScenePlan(
                    scene_id=3,
                    narration_chunk="Until one unexpected experiment turned everything upside down.",
                    visual_prompt=f"Explosive glowing particle burst emanating from a crystalline core representing {topic_clean}, high speed slow-motion, vibrant cinematic tones.",
                    camera_movement="fast zoom reveal",
                    estimated_duration=4.2,
                ),
                ScenePlan(
                    scene_id=4,
                    narration_chunk="The findings were so shocking that they had to re-evaluate the entire theory.",
                    visual_prompt=f"Shocked silhouette of researcher looking at vast celestial portal or colossal computational matrix, cinematic depth of field, 9:16 vertical frame.",
                    camera_movement="slow dramatic pull-back",
                    estimated_duration=4.5,
                ),
                ScenePlan(
                    scene_id=5,
                    narration_chunk="Drop a comment if you would ever dare to experience this yourself!",
                    visual_prompt=f"Futuristic horizon with swirling glowing nebula and digital aura around {topic_clean}, cinematic breathtaking atmosphere, 8k masterwork.",
                    camera_movement="cinematic upward sweep",
                    estimated_duration=3.8,
                ),
            ][:max(1, max_scenes)],
            tiktok_title=f"The Truth About {topic_clean} 🤯",
            tiktok_caption=f"Nobody talks about the real truth behind {topic_clean}. Would you dare try this? Let me know below! 👇",
            hashtags=["#fyp", "#foryou", "#mindblown", "#science", "#learnontiktok", "#viral"],
        )
