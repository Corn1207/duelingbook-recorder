"""
outro.py

Appends a closing image to a video with a cross dissolve transition.

The image is shown for a configurable duration after the main video ends.
The dissolve transition overlaps the last second of the main video with
the first second of the outro image.

Audio during the outro fades to silence over the dissolve duration.

Usage:
    from postprocess.outro import OutroAdder

    adder = OutroAdder(image_path="assets/outro.png")
    final_path = adder.add(
        video_path="output/final/replay_mixed.mp4",
        output_dir="output/final",
    )
"""

import logging
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

OUTRO_IMAGE = "assets/Thanks for watching Pantalla Final.png"
OUTRO_DURATION = 10      # seconds the outro image is shown
DISSOLVE_DURATION = 1    # seconds for the cross dissolve effect

# Logo overlay — set to None to disable
# Covers the replay controls panel in the bottom-left (play/pause/next/watchers)
LOGO_IMAGE = "assets/logo.png"
LOGO_X = 64             # pixels from left edge
LOGO_Y = 781            # pixels from top edge
LOGO_W = 380            # width to scale the logo to (pixels)
LOGO_H = 295            # height to scale the logo to (pixels)


class OutroAdder:
    def __init__(
        self,
        image_path: str = OUTRO_IMAGE,
        outro_duration: int = OUTRO_DURATION,
        dissolve_duration: int = DISSOLVE_DURATION,
        logo_path: Optional[str] = LOGO_IMAGE,
        logo_x: int = LOGO_X,
        logo_y: int = LOGO_Y,
        logo_w: int = LOGO_W,
        logo_h: int = LOGO_H,
    ):
        self.image_path = image_path
        self.outro_duration = outro_duration
        self.dissolve_duration = dissolve_duration
        self.logo_path = logo_path
        self.logo_x = logo_x
        self.logo_y = logo_y
        self.logo_w = logo_w
        self.logo_h = logo_h

    def add(self, video_path: str, output_dir: str) -> str:
        """
        Appends the outro image to the video with a cross dissolve.

        Args:
            video_path: Path to the mixed video (.mp4).
            output_dir: Directory where the final video will be saved.

        Returns:
            Absolute path to the video with outro (.mp4).
        """
        video_path = Path(video_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        output_path = output_dir / (video_path.stem + "_outro.mp4")

        video_duration = self._get_duration(str(video_path))
        logger.info(f"Adding outro to video ({video_duration:.1f}s)...")

        # Transition starts 1 second before the main video ends
        xfade_offset = max(0, video_duration - self.dissolve_duration)

        # Total outro clip length = dissolve overlap + display time
        outro_clip_duration = self.dissolve_duration + self.outro_duration

        # Audio fade out starts at the same time as the dissolve
        audio_fade_start = xfade_offset

        use_logo = self.logo_path and Path(self.logo_path).exists()
        logo_input_index = 2 if use_logo else None

        if use_logo:
            filter_complex = (
                # Normalize main video timebase to 1/30 so xfade accepts both inputs
                f"[0:v]fps=30,settb=1/30[main_v];"
                # Scale logo and overlay it on the main video only (before xfade)
                f"[{logo_input_index}:v]scale={self.logo_w}:{self.logo_h}[logo];"
                f"[main_v][logo]overlay={self.logo_x}:{self.logo_y},settb=1/30[main_with_logo];"
                # Scale outro image to 1920x1080 with black bars, same timebase
                f"[1:v]scale=1920:1080:force_original_aspect_ratio=decrease,"
                f"pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=black,"
                f"setsar=1,fps=30,settb=1/30[outro_v];"
                # Cross dissolve: logo disappears as outro fades in
                f"[main_with_logo][outro_v]xfade=transition=dissolve:"
                f"duration={self.dissolve_duration}:offset={xfade_offset:.3f}[vout];"
                # Fade audio to silence at the dissolve point, pad with silence for outro duration
                f"[0:a]afade=t=out:st={audio_fade_start:.3f}:d={self.dissolve_duration},"
                f"apad=whole_dur={video_duration + self.outro_duration}[aout]"
            )
        else:
            filter_complex = (
                f"[0:v]fps=30,settb=1/30[main_v];"
                f"[1:v]scale=1920:1080:force_original_aspect_ratio=decrease,"
                f"pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=black,"
                f"setsar=1,fps=30,settb=1/30[outro_v];"
                f"[main_v][outro_v]xfade=transition=dissolve:"
                f"duration={self.dissolve_duration}:offset={xfade_offset:.3f}[vout];"
                f"[0:a]afade=t=out:st={audio_fade_start:.3f}:d={self.dissolve_duration},"
                f"apad=whole_dur={video_duration + self.outro_duration}[aout]"
            )

        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            # -loop 1 makes ffmpeg treat the image as infinite, -t limits its duration
            "-loop", "1", "-t", str(outro_clip_duration), "-i", self.image_path,
        ]
        if use_logo:
            cmd += ["-i", self.logo_path]
        cmd += [
            "-filter_complex", filter_complex,
            "-map", "[vout]",
            "-map", "[aout]",
            "-c:v", "libx264",
            "-c:a", "aac",
            "-b:a", "192k",
            str(output_path),
        ]

        logger.info("Running ffmpeg outro...")
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            logger.error(f"ffmpeg stderr:\n{result.stderr}")
            raise RuntimeError(f"ffmpeg outro failed with return code {result.returncode}")

        logger.info(f"Outro added: {output_path}")
        return str(output_path)

    def _get_duration(self, file_path: str) -> float:
        """Returns the duration of a media file in seconds using ffprobe.

        Tries format duration first (fast), then falls back to stream duration
        (needed for MKV files from OBS that lack container-level duration).
        """
        def _probe(extra_args: list) -> float:
            result = subprocess.run(
                ["ffprobe", "-v", "error"] + extra_args + [
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    file_path,
                ],
                capture_output=True,
                text=True,
            )
            try:
                return float(result.stdout.strip())
            except ValueError:
                return 0.0

        # 1. Try container-level duration (fast, works for mp4/mkv with index)
        duration = _probe(["-show_entries", "format=duration"])
        if duration > 0:
            return duration

        # 2. Fallback: read video stream duration
        duration = _probe(["-select_streams", "v:0", "-show_entries", "stream=duration"])
        if duration > 0:
            return duration

        # 3. Last resort: decode and count frames (slow but always works)
        logger.warning(f"Falling back to frame count for duration of {file_path}")
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-count_packets",
                "-show_entries", "stream=nb_read_packets,r_frame_rate",
                "-of", "default=noprint_wrappers=1:nokey=1",
                file_path,
            ],
            capture_output=True,
            text=True,
        )
        lines = result.stdout.strip().splitlines()
        try:
            fps_parts = lines[0].split("/")
            fps = float(fps_parts[0]) / float(fps_parts[1])
            frames = float(lines[1])
            return frames / fps
        except Exception:
            logger.warning(f"Could not read duration for {file_path}")
            return 0.0
