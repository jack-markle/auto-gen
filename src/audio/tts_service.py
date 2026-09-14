import asyncio
import logging
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel
from config.settings import settings

logger = logging.getLogger(__name__)

class WordTimestamp(BaseModel):
    word: str
    start: float  # in seconds
    end: float    # in seconds

class AudioResult(BaseModel):
    audio_path: str
    duration: float
    word_timestamps: List[WordTimestamp]

class TTSService:
    def __init__(
        self,
        voice: Optional[str] = None,
        rate: Optional[str] = None,
        pitch: Optional[str] = None,
    ):
        self.voice = voice or settings.VOICE_NAME
        self.rate = rate or settings.VOICE_RATE
        self.pitch = pitch or settings.VOICE_PITCH

    async def generate_speech(self, text: str, output_filepath: Path) -> AudioResult:
        """
        Synthesizes text into high quality voiceover and collects word-level timestamps.
        """
        output_filepath.parent.mkdir(parents=True, exist_ok=True)
        word_timestamps: List[WordTimestamp] = []
        words = text.split()

        import time
        start_time = time.time()
        logger.info("=" * 70)
        logger.info(f"[STAGE 2: AUDIO] 🎙️ Starting Neural Voiceover Synthesis")
        logger.info(f"[STAGE 2: AUDIO] 🔊 Voice: {self.voice} | Rate: {self.rate} | Pitch: {self.pitch}")
        logger.info(f"[STAGE 2: AUDIO] 📄 Script ({len(words)} words, {len(text)} chars): '{text[:80]}...'")
        logger.info("=" * 70)

        try:
            import edge_tts

            logger.info(f"[STAGE 2: AUDIO] 📡 Connecting to Edge-TTS engine...")
            communicate = edge_tts.Communicate(
                text=text,
                voice=self.voice,
                rate=self.rate,
                pitch=self.pitch,
            )

            # Edge-TTS streams audio chunks and metadata
            audio_data = bytearray()
            async for chunk in communicate.stream():
                chunk_type = chunk.get("type", "")
                if chunk_type == "audio":
                    data_bytes = chunk.get("data", b"")
                    if data_bytes:
                        audio_data.extend(data_bytes)
                elif chunk_type in ("WordBoundary", "word_boundary"):
                    # offset and duration in 100-nanosecond units (ticks)
                    # 1 second = 10,000,000 ticks
                    start_sec = chunk.get("offset", 0) / 10_000_000.0
                    duration_sec = chunk.get("duration", 0) / 10_000_000.0
                    end_sec = start_sec + duration_sec
                    word_text = chunk.get("text", "")
                    if word_text:
                        word_timestamps.append(
                            WordTimestamp(
                                word=word_text,
                                start=round(start_sec, 3),
                                end=round(end_sec, 3),
                            )
                        )

            # If communicate.stream() didn't return audio bytes, try direct communicate.save()
            if len(audio_data) < 100:
                logger.warning(f"[STAGE 2: AUDIO] ⚠️ Edge-TTS stream returned empty buffer ({len(audio_data)} bytes). Retrying with communicate.save()...")
                await communicate.save(str(output_filepath))
                if output_filepath.exists() and output_filepath.stat().st_size > 100:
                    audio_data = bytearray(output_filepath.read_bytes())
                else:
                    raise RuntimeError("Edge-TTS save yielded an empty audio file")
            else:
                with open(output_filepath, "wb") as f:
                    f.write(audio_data)

            elapsed = time.time() - start_time
            file_size_kb = len(audio_data) / 1024.0

            # Calculate total duration
            if word_timestamps:
                total_duration = word_timestamps[-1].end + 0.3
            else:
                total_duration = max(3.0, len(words) / 2.5)

            # If no word boundaries emitted, interpolate evenly across words
            if not word_timestamps:
                logger.warning(f"[STAGE 2: AUDIO] ⚠️ No native word boundaries in stream; interpolating timestamps for {len(words)} words.")
                if words:
                    w_dur = total_duration / len(words)
                    for i, w in enumerate(words):
                        word_timestamps.append(
                            WordTimestamp(
                                word=w,
                                start=round(i * w_dur, 3),
                                end=round((i + 1) * w_dur, 3),
                            )
                        )

            logger.info(f"[STAGE 2: AUDIO] ✅ Voiceover synthesized in {elapsed:.2f}s:")
            logger.info(f"   • File: {output_filepath.name} ({file_size_kb:.1f} KB)")
            logger.info(f"   • Duration: {total_duration:.2f} seconds")
            logger.info(f"   • Timestamps: {len(word_timestamps)} word-level markers captured")

            return AudioResult(
                audio_path=str(output_filepath),
                duration=round(total_duration, 2),
                word_timestamps=word_timestamps,
            )

        except Exception as e:
            elapsed = time.time() - start_time
            logger.error("=" * 70)
            logger.error(f"[STAGE 2: AUDIO] ❌ TTS synthesis error after {elapsed:.2f}s: {type(e).__name__}: {e}", exc_info=True)
            logger.error("=" * 70)
            return await self._generate_fallback_audio(text, output_filepath)

    async def _generate_fallback_audio(self, text: str, output_filepath: Path) -> AudioResult:
        """Generates a valid MP3 audio file if edge-tts fails (using gTTS or FFmpeg tone/silence)."""
        words = text.split()
        estimated_duration = max(4.0, len(words) * 0.35)
        word_duration = estimated_duration / max(1, len(words))

        timestamps = []
        current_time = 0.0
        for w in words:
            timestamps.append(
                WordTimestamp(
                    word=w,
                    start=round(current_time, 2),
                    end=round(current_time + word_duration, 2),
                )
            )
            current_time += word_duration

        # Option 1: Try gTTS if available
        gtts_success = False
        try:
            from gtts import gTTS
            tts = gTTS(text=text, lang="en")
            tts.save(str(output_filepath))
            if output_filepath.exists() and output_filepath.stat().st_size > 500:
                gtts_success = True
                logger.info(f"[STAGE 2: AUDIO] ✅ Generated speech via gTTS fallback ({output_filepath.stat().st_size/1024:.1f} KB)")
        except Exception:
            gtts_success = False

        # Option 2: Synthesize valid MP3 silent audio track using FFmpeg so video encoding doesn't break
        if not gtts_success:
            import subprocess
            logger.info(f"[STAGE 2: AUDIO] ⚙️ Generating valid {estimated_duration:.1f}s MP3 audio placeholder via FFmpeg...")
            cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi",
                "-i", f"anullsrc=r=44100:cl=stereo",
                "-t", f"{estimated_duration:.2f}",
                "-c:a", "libmp3lame",
                "-b:a", "128k",
                str(output_filepath)
            ]
            try:
                proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
                await proc.communicate()
            except Exception:
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        return AudioResult(
            audio_path=str(output_filepath),
            duration=round(estimated_duration, 2),
            word_timestamps=timestamps,
        )
