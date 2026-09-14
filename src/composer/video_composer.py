import asyncio
import logging
import os
import subprocess
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

class VideoComposer:
    """
    Stitches scene video clips, attaches voiceover audio, and burns ASS subtitles
    into a polished 9:16 vertical MP4 ready for TikTok.
    """

    @staticmethod
    async def compose(
        scene_video_paths: List[Path],
        voiceover_audio_path: Path,
        subtitle_ass_path: Optional[Path],
        output_mp4_path: Path,
        target_duration: Optional[float] = None,
    ) -> Path:
        import time
        start_time = time.time()
        logger.info("=" * 70)
        logger.info(f"[STAGE 4: COMPOSITING] 🎬 Starting Final Video Assembly")
        logger.info(f"[STAGE 4: COMPOSITING] 📹 Scene clips to stitch: {len(scene_video_paths)}")
        for i, p in enumerate(scene_video_paths, 1):
            sz = p.stat().st_size / 1024 if p.exists() else 0
            logger.info(f"   • Scene {i}: {p.name} ({sz:.1f} KB)")
        logger.info(f"[STAGE 4: COMPOSITING] 🎵 Voiceover Audio: {voiceover_audio_path.name}")
        logger.info(f"[STAGE 4: COMPOSITING] 📝 Subtitles File: {subtitle_ass_path.name if subtitle_ass_path else 'None'}")
        logger.info("=" * 70)

        output_mp4_path.parent.mkdir(parents=True, exist_ok=True)
        temp_dir = output_mp4_path.parent / "composer_temp"
        temp_dir.mkdir(parents=True, exist_ok=True)

        # 1. Create concat file for scene clips
        concat_file = temp_dir / "concat_list.txt"
        with open(concat_file, "w", encoding="utf-8") as f:
            for p in scene_video_paths:
                safe_path = str(p.resolve()).replace("\\", "/")
                f.write(f"file '{safe_path}'\n")

        # Step A: Concatenate all video clips into a single video track
        concatenated_video = temp_dir / "concatenated_raw.mp4"
        logger.info(f"[STAGE 4: COMPOSITING] 🔄 Concatenating {len(scene_video_paths)} scene clips...")
        concat_cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_file),
            "-c", "copy",
            str(concatenated_video),
        ]
        await VideoComposer._run_ffmpeg(concat_cmd, "Scene Concatenation")

        # Step B: Check if concatenated video has an audio stream (e.g. from Google Veo)
        has_video_audio = await VideoComposer._has_audio_stream(concatenated_video)
        logger.info(f"[STAGE 4: COMPOSITING] 🔊 Video track native audio detected: {has_video_audio}")

        # Step C: Merge video, voiceover, and any video audio, plus burn ASS subtitles
        vf_filters = ["scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"]

        if subtitle_ass_path and subtitle_ass_path.exists():
            escaped_sub = str(subtitle_ass_path.resolve()).replace("\\", "/").replace(":", "\\:")
            vf_filters.append(f"ass='{escaped_sub}'")
            logger.info(f"[STAGE 4: COMPOSITING] 🔤 Burning ASS animated word subtitles...")
        else:
            logger.warning(f"[STAGE 4: COMPOSITING] ⚠️ Subtitle ASS file not found at {subtitle_ass_path}")

        filter_v_str = ",".join(vf_filters)

        # Check if voiceover audio has valid non-zero content
        has_voiceover = voiceover_audio_path.exists() and voiceover_audio_path.stat().st_size > 100

        render_cmd = ["ffmpeg", "-y", "-i", str(concatenated_video)]

        if has_voiceover:
            render_cmd.extend(["-i", str(voiceover_audio_path)])

        if has_video_audio and has_voiceover:
            # Mix both audio streams together:
            # [0:a] video audio at 70% volume, [1:a] voiceover boosted to 100% volume
            logger.info(f"[STAGE 4: COMPOSITING] 🎚️ Mixing Veo video audio (70%) with voiceover narration (100%)...")
            filter_complex = (
                f"[0:v]{filter_v_str}[v_out];"
                f"[0:a]volume=0.7[a_video];"
                f"[1:a]volume=1.0[a_voice];"
                f"[a_video][a_voice]amix=inputs=2:duration=longest:dropout_transition=2[a_out]"
            )
            render_cmd.extend([
                "-filter_complex", filter_complex,
                "-map", "[v_out]",
                "-map", "[a_out]",
            ])
        elif has_voiceover:
            # Voiceover only
            render_cmd.extend([
                "-vf", filter_v_str,
                "-map", "0:v",
                "-map", "1:a",
            ])
        elif has_video_audio:
            # Video native audio only
            render_cmd.extend([
                "-vf", filter_v_str,
                "-map", "0:v",
                "-map", "0:a",
            ])
        else:
            # Silent fallback audio
            render_cmd.extend([
                "-vf", filter_v_str,
                "-map", "0:v",
            ])

        render_cmd.extend([
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "22",
            "-c:a", "aac",
            "-b:a", "192k",
            "-pix_fmt", "yuv420p",
        ])

        if target_duration and target_duration > 0:
            render_cmd.extend(["-t", f"{target_duration:.2f}"])
        else:
            render_cmd.append("-shortest")

        render_cmd.append(str(output_mp4_path))

        logger.info(f"[STAGE 4: COMPOSITING] ⚙️  Encoding final 1080x1920 MP4 with H.264 & AAC...")
        await VideoComposer._run_ffmpeg(render_cmd, "Final Video Rendering")

        elapsed = time.time() - start_time
        final_size_mb = output_mp4_path.stat().st_size / (1024 * 1024) if output_mp4_path.exists() else 0
        logger.info(f"[STAGE 4: COMPOSITING] ✅ Final Video Render Complete in {elapsed:.2f}s:")
        logger.info(f"   • Path: {output_mp4_path}")
        logger.info(f"   • Size: {final_size_mb:.2f} MB")
        logger.info("=" * 70)
        return output_mp4_path

    @staticmethod
    async def _run_ffmpeg(cmd: List[str], step_name: str = "FFmpeg"):
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()
            if process.returncode != 0:
                err_msg = stderr.decode("utf-8", errors="ignore")
                logger.error(f"[FFmpeg] ❌ {step_name} failed with exit code {process.returncode}:")
                logger.error(f"{err_msg[:600]}")
            else:
                logger.info(f"[FFmpeg] ✅ {step_name} finished successfully.")
        except Exception as e:
            logger.error(f"[FFmpeg] ❌ {step_name} execution failed: {type(e).__name__}: {e}", exc_info=True)
            subprocess.run(cmd, capture_output=True)

    @staticmethod
    async def _has_audio_stream(video_path: Path) -> bool:
        """Checks if a video file contains an audio stream using ffprobe."""
        if not video_path.exists():
            return False
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=codec_type",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            return "audio" in stdout.decode("utf-8", errors="ignore").strip().lower()
        except Exception:
            return False
