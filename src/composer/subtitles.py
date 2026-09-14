from pathlib import Path
from typing import List
from src.audio.tts_service import WordTimestamp

class SubtitleGenerator:
    """
    Generates ASS (Advanced SubStation Alpha) subtitle files styled for high retention
    TikTok/Reels vertical videos with active word-highlighting.
    """

    @staticmethod
    def generate_ass(
        word_timestamps: List[WordTimestamp],
        output_path: Path,
        font_name: str = "Arial",
        font_size: int = 24,
        primary_color: str = "&H00FFFFFF",      # White (AABBGGRR)
        highlight_color: str = "&H0000E6FF",    # Vibrant Yellow/Amber
        outline_color: str = "&H00000000",      # Black outline
        words_per_group: int = 3,
    ) -> Path:
        """
        Groups words into short, punchy 2-4 word bursts and highlights the active word.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},72,{primary_color},{highlight_color},{outline_color},&H80000000,-1,0,0,0,100,100,1,0,1,8,4,2,60,60,540,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

        events = []
        # Group words into small chunks for high readability
        if not word_timestamps:
            output_path.write_text(header, encoding="utf-8")
            return output_path

        # Group words into clusters of ~3 words
        groups = []
        current_group = []
        for wt in word_timestamps:
            current_group.append(wt)
            if len(current_group) >= words_per_group:
                groups.append(current_group)
                current_group = []
        if current_group:
            groups.append(current_group)

        for group in groups:
            for active_idx, active_word in enumerate(group):
                start_str = SubtitleGenerator._format_time(active_word.start)
                end_str = SubtitleGenerator._format_time(active_word.end)

                # Format text with highlighted current word
                chunk_parts = []
                for idx, w in enumerate(group):
                    if idx == active_idx:
                        # Highlight active word with bright yellow and slight scale
                        chunk_parts.append(f"{{\\c{highlight_color}\\b1}}{w.word.upper()}{{\\r}}")
                    else:
                        chunk_parts.append(f"{{\\c{primary_color}\\b1}}{w.word.upper()}{{\\r}}")

                line_text = " ".join(chunk_parts)
                events.append(f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{line_text}")

        content = header + "\n".join(events) + "\n"
        output_path.write_text(content, encoding="utf-8")
        return output_path

    @staticmethod
    def _format_time(seconds: float) -> str:
        """Converts float seconds to ASS format: H:MM:SS.cs"""
        hrs = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        csecs = int(round((seconds - int(seconds)) * 100))
        return f"{hrs}:{mins:02d}:{secs:02d}.{csecs:02d}"
