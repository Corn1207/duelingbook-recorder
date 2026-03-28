"""
music_mixer.py

Mixes background music into a recorded replay video.

Behavior:
- Scans the music folder for .mp3 files recursively
- Shuffles them randomly
- Concatenates them in order until the video duration is covered
- Adds a fadeout at the end of the music track
- Mixes music at a low volume under the original game audio
- Outputs a final .mp4 file

Usage:
    from postprocess.music_mixer import MusicMixer

    mixer = MusicMixer(music_folder="/Volumes/SSD Rodrigo/Mac Externo/Music")
    output_path = mixer.mix(
        video_path="output/raw/2026-03-28 09-26-13.mkv",
        output_dir="output/final",
    )
"""

import logging
import os
import random
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# Volume of background music relative to game audio (0.0 - 1.0)
MUSIC_VOLUME = 0.30

# Duration of the fadeout at the end of the music (seconds)
FADEOUT_DURATION = 4


class MusicMixer:
    def __init__(
        self,
        music_folder: str,
        music_volume: float = MUSIC_VOLUME,
        fadeout_duration: int = FADEOUT_DURATION,
    ):
        self.music_folder = Path(music_folder)
        self.music_volume = music_volume
        self.fadeout_duration = fadeout_duration

    def mix(self, video_path: str, output_dir: str) -> str:
        """
        Mixes background music into the video.

        Args:
            video_path: Path to the raw recorded .mkv file.
            output_dir: Directory where the final .mp4 will be saved.

        Returns:
            Absolute path to the final mixed .mp4 file.
        """
        video_path = Path(video_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        output_path = output_dir / (video_path.stem + "_mixed.mp4")

        video_duration = self._get_duration(str(video_path))
        logger.info(f"Video duration: {video_duration:.1f}s")

        mp3_files = self._get_shuffled_mp3s()
        if not mp3_files:
            raise FileNotFoundError(f"No .mp3 files found in {self.music_folder}")
        logger.info(f"Found {len(mp3_files)} mp3 files.")

        # Build a playlist long enough to cover the full video duration
        playlist = self._build_playlist(mp3_files, video_duration)
        logger.info(f"Playlist: {len(playlist)} tracks selected.")

        # Write a temporary concat file for ffmpeg
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            concat_file = f.name
            for track in playlist:
                # ffmpeg concat demuxer requires escaped paths
                escaped = str(track).replace("'", "'\\''")
                f.write(f"file '{escaped}'\n")

        try:
            self._run_ffmpeg(str(video_path), concat_file, video_duration, str(output_path))
        finally:
            os.unlink(concat_file)

        logger.info(f"Mixed video saved to: {output_path}")
        return str(output_path)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_shuffled_mp3s(self) -> list[Path]:
        """Scans the music folder recursively for .mp3 files and shuffles them."""
        files = list(self.music_folder.rglob("*.mp3"))
        if not files:
            return []
        random.shuffle(files)
        return files

    def _build_playlist(self, mp3_files: list[Path], required_duration: float) -> list[Path]:
        """
        Cycles through the shuffled mp3 list, adding tracks until the
        total duration covers the video. Re-shuffles and continues if
        we run out of tracks before covering the video.
        """
        playlist = []
        total = 0.0
        pool = list(mp3_files)

        while total < required_duration:
            if not pool:
                pool = list(mp3_files)
                random.shuffle(pool)
            track = pool.pop(0)
            duration = self._get_duration(str(track))
            if duration > 0:
                playlist.append(track)
                total += duration
                logger.debug(f"Added: {track.name} ({duration:.1f}s) — total: {total:.1f}s")

        return playlist

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

        duration = _probe(["-show_entries", "format=duration"])
        if duration > 0:
            return duration

        duration = _probe(["-select_streams", "v:0", "-show_entries", "stream=duration"])
        if duration > 0:
            return duration

        logger.warning(f"Could not read duration for {file_path}")
        return 0.0

    def _run_ffmpeg(
        self,
        video_path: str,
        concat_file: str,
        video_duration: float,
        output_path: str,
    ) -> None:
        """
        Runs ffmpeg to mix the concatenated music playlist into the video.

        Filter graph:
          - Concatenates all music tracks into one audio stream
          - Applies fadeout at the end
          - Mixes with game audio at reduced volume
          - Cuts music at video end (duration=first)
          - Re-encodes audio to AAC, copies video stream unchanged
        """
        fadeout_start = max(0, video_duration - self.fadeout_duration)

        filter_complex = (
            # Concat all music tracks into a single audio stream
            f"[1:a]concat=n=1:v=0:a=1[music_raw];"
            # Apply fadeout at the end
            f"[music_raw]afade=t=out:st={fadeout_start:.2f}:d={self.fadeout_duration}[music_faded];"
            # Lower music volume
            f"[music_faded]volume={self.music_volume}[music];"
            # Mix game audio + music, output stops when video ends
            f"[0:a][music]amix=inputs=2:duration=first:dropout_transition=3[aout]"
        )

        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-f", "concat", "-safe", "0", "-i", concat_file,
            "-filter_complex", filter_complex,
            "-map", "0:v",
            "-map", "[aout]",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            output_path,
        ]

        logger.info("Running ffmpeg mix...")
        logger.debug(f"ffmpeg command: {' '.join(cmd)}")

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            logger.error(f"ffmpeg stderr:\n{result.stderr}")
            raise RuntimeError(f"ffmpeg failed with return code {result.returncode}")
