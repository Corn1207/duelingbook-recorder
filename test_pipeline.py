"""Script temporal para probar el pipeline completo. Borrar después."""
import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

from recorder.pipeline import RecordingPipeline

pipeline = RecordingPipeline(obs_password="123456", obs_scene="Grabar DB")
final_path = pipeline.run(replay_id="578530-80432376")
print(f"\nListo. Video final: {final_path}")
