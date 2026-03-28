"""
pipeline.py

Orchestrates the full recording flow:
  1. Connect to OBS
  2. Switch to the recording scene
  3. Launch Brave and navigate to the replay URL
  4. Start OBS recording (waits until OBS confirms it's active)
  5. Wait for replay data to load, then advance via next_btn clicks
  6. Stop OBS recording when the replay finishes
  7. Close the browser
  8. Mix background music into the raw recording
  9. Return the path to the final mixed video

Usage:
    from recorder.pipeline import RecordingPipeline

    pipeline = RecordingPipeline(obs_password="123456", obs_scene="Grabar DB")
    final_video_path = pipeline.run(replay_id="578530-80432376")
"""

import logging
from pathlib import Path

from recorder.browser import ReplayBrowser
from recorder.obs_controller import OBSController
from recorder.replay_monitor import ReplayMonitor
from postprocess.music_mixer import MusicMixer
from postprocess.outro import OutroAdder

logger = logging.getLogger(__name__)

MUSIC_FOLDER = "/Volumes/SSD Rodrigo/Mac Externo/Music"
RAW_OUTPUT_DIR = "./output/raw"
FINAL_OUTPUT_DIR = "./output/final"


class RecordingPipeline:
    def __init__(
        self,
        obs_password: str = "",
        obs_host: str = "localhost",
        obs_port: int = 4455,
        obs_scene: str = "Grabar DB",
        music_folder: str = MUSIC_FOLDER,
    ):
        self.obs_password = obs_password
        self.obs_host = obs_host
        self.obs_port = obs_port
        self.obs_scene = obs_scene
        self.music_folder = music_folder

    def run(self, replay_id: str) -> str:
        """
        Records a duelingbook replay and mixes background music into it.

        Args:
            replay_id: The duelingbook replay ID (e.g. "578530-80432376").

        Returns:
            Absolute path to the final mixed video (.mp4).
        """
        logger.info(f"Starting recording pipeline for replay: {replay_id}")
        raw_path = None

        with OBSController(self.obs_host, self.obs_port, self.obs_password) as obs:
            logger.info(f"Switching OBS to scene: {self.obs_scene}")
            obs._client.set_current_program_scene(self.obs_scene)

            with ReplayBrowser() as browser:
                page = browser.open(replay_id)
                obs.start_recording()

                try:
                    monitor = ReplayMonitor(page)
                    monitor.wait_for_replay_start()
                    monitor.run()
                except Exception as e:
                    logger.error(f"Error during replay playback: {e}")
                    raise
                finally:
                    if obs.is_recording():
                        raw_path = obs.stop_recording()
                        logger.info(f"Raw recording saved: {raw_path}")

        # Add outro image with cross dissolve (before music so music covers full duration)
        logger.info("Adding outro...")
        outro = OutroAdder()
        outro_path = outro.add(video_path=raw_path, output_dir=FINAL_OUTPUT_DIR)

        # Mix music into the video with outro (music now covers recording + outro)
        logger.info("Mixing background music...")
        mixer = MusicMixer(music_folder=self.music_folder)
        mixed_path = mixer.mix(video_path=outro_path, output_dir=FINAL_OUTPUT_DIR)

        # Rename to clean final name: strip _outro_mixed → _final
        final_path = Path(mixed_path).with_name(
            Path(mixed_path).name.replace("_outro_mixed", "_final")
        )
        Path(mixed_path).rename(final_path)
        final_path = str(final_path)

        logger.info(f"Done. Final video: {final_path}")
        return final_path
