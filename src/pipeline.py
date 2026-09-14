import asyncio
import logging
import time
from pathlib import Path
from typing import Callable, Awaitable, Optional, Dict, Any, List
from pydantic import BaseModel
from config.settings import settings
from src.generator.gemini_director import GeminiDirector, VideoPlan
from src.audio.tts_service import TTSService, AudioResult
from src.visuals.video_generator import AIVideoGenerator
from src.composer.subtitles import SubtitleGenerator
from src.composer.video_composer import VideoComposer
from src.tiktok.publisher import TikTokPublisher, TikTokPublishResult

logger = logging.getLogger(__name__)

# Callback signature: (stage_name, progress_percent_0_to_100, status_message, optional_metadata)
ProgressCallback = Callable[[str, int, str, Optional[Dict[str, Any]]], Awaitable[None]]

class PipelineResult(BaseModel):
    video_id: str
    video_path: str
    video_url: str
    duration: float
    plan: VideoPlan
    publish_result: Optional[TikTokPublishResult] = None
    created_at: float

class AutoPostPipeline:
    def __init__(self):
        self.director = GeminiDirector()
        self.tts = TTSService()
        self.visuals = AIVideoGenerator()
        self.composer = VideoComposer()
        self.publisher = TikTokPublisher()

    async def run(
        self,
        prompt: str,
        auto_publish: bool = False,
        max_scene_duration: float = 4.0,
        max_scenes: int = 5,
        max_video_duration: float = 30.0,
        progress_cb: Optional[ProgressCallback] = None,
    ) -> PipelineResult:
        """
        Executes the entire end-to-end automated pipeline.
        """
        job_id = f"vid_{int(time.time())}"
        job_dir = settings.output_path / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        async def update(stage: str, progress: int, msg: str, meta: Optional[Dict] = None):
            logger.info(f"[{job_id}] [{stage} {progress}%] {msg}")
            if progress_cb:
                await progress_cb(stage, progress, msg, meta)

        # STAGE 1: Script & Scene Blueprint Generation with Gemini
        logger.info("\n" + "#" * 70)
        logger.info(f"### [JOB {job_id}] STAGE 1: SCRIPT & SCENE GENERATION")
        logger.info("#" * 70)
        await update("SCRIPTING", 10, f"Brainstorming viral hook and writing script (Max Scenes: {max_scenes}, Max Video: {max_video_duration}s)...")
        plan = self.director.generate_plan(
            prompt,
            max_scene_duration=max_scene_duration,
            max_scenes=max_scenes,
            max_video_duration=max_video_duration,
        )
        await update(
            "SCRIPTING",
            25,
            f"Generated {len(plan.scenes)} scenes. Hook: '{plan.hook}'",
            {"plan": plan.model_dump()},
        )

        # STAGE 2: Audio Synthesis & Word-Level Timestamp Extraction
        logger.info("\n" + "#" * 70)
        logger.info(f"### [JOB {job_id}] STAGE 2: NEURAL AUDIO & WORD TIMESTAMPS")
        logger.info("#" * 70)
        await update("AUDIO", 35, "Generating neural voiceover and aligning word timestamps...")
        audio_file = job_dir / "voiceover.mp3"
        audio_res = await self.tts.generate_speech(plan.full_narration, audio_file)
        await update(
            "AUDIO",
            50,
            f"Voiceover generated ({audio_res.duration}s, {len(audio_res.word_timestamps)} words)",
        )

        # STAGE 3: AI Video Scene Generation
        logger.info("\n" + "#" * 70)
        logger.info(f"### [JOB {job_id}] STAGE 3: AI VIDEO SCENE SYNTHESIS")
        logger.info("#" * 70)
        await update("VISUALS", 55, "Generating 9:16 vertical AI video clips for each scene...")
        scene_files: List[Path] = []
        total_scenes = len(plan.scenes)
        # Calculate duration per scene constrained by max_scene_duration and target video duration
        target_total_audio = min(audio_res.duration, float(max_video_duration))
        calculated_dur = target_total_audio / max(1, total_scenes)
        duration_per_scene = min(float(max_scene_duration), max(2.0, calculated_dur))
        logger.info(f"[{job_id}] Pacing: {total_scenes} scenes, audio={audio_res.duration:.1f}s, max_video={max_video_duration}s -> {duration_per_scene:.1f}s per scene (max: {max_scene_duration}s)")

        for idx, scene in enumerate(plan.scenes):
            progress_pct = 55 + int((idx / total_scenes) * 20)
            await update(
                "VISUALS",
                progress_pct,
                f"Synthesizing Scene {scene.scene_id}/{total_scenes}: {scene.camera_movement} ({duration_per_scene:.1f}s)...",
            )
            scene_path = job_dir / f"scene_{scene.scene_id}.mp4"
            await self.visuals.generate_scene_video(scene, duration_per_scene, scene_path)
            scene_files.append(scene_path)

        # STAGE 4: Subtitles & Final Video Compositing
        logger.info("\n" + "#" * 70)
        logger.info(f"### [JOB {job_id}] STAGE 4: COMPOSITING & RETENTION SUBTITLES")
        logger.info("#" * 70)
        await update("COMPOSITING", 78, "Generating animated word-by-word highlighted captions...")
        ass_file = job_dir / "subtitles.ass"
        SubtitleGenerator.generate_ass(audio_res.word_timestamps, ass_file)

        await update("COMPOSITING", 85, "Rendering final vertical 1080x1920 MP4 video...")
        final_mp4 = job_dir / f"{job_id}_final.mp4"
        await self.composer.compose(
            scene_video_paths=scene_files,
            voiceover_audio_path=audio_file,
            subtitle_ass_path=ass_file,
            output_mp4_path=final_mp4,
            target_duration=float(max_video_duration),
        )

        publish_res: Optional[TikTokPublishResult] = None
        # STAGE 5: TikTok Publishing (or Dry-Run / Draft)
        if auto_publish:
            logger.info("\n" + "#" * 70)
            logger.info(f"### [JOB {job_id}] STAGE 5: TIKTOK PUBLISHING")
            logger.info("#" * 70)
            await update("PUBLISHING", 92, "Connecting to TikTok Content Posting API...")
            publish_res = await self.publisher.publish_video(
                video_path=final_mp4,
                title=plan.tiktok_title,
                caption=plan.tiktok_caption,
                hashtags=plan.hashtags,
            )
            await update("PUBLISHING", 100, f"TikTok Status: {publish_res.status} ({publish_res.mode})")
        else:
            await update("COMPLETED", 100, "Video generated successfully! Ready for preview and publishing.")

        return PipelineResult(
            video_id=job_id,
            video_path=str(final_mp4),
            video_url=f"/api/video/{job_id}",
            duration=audio_res.duration,
            plan=plan,
            publish_result=publish_res,
            created_at=time.time(),
        )
