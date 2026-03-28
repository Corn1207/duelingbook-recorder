"""
obs_controller.py

Controls OBS Studio via WebSocket v5 (built into OBS 28+).
Handles connecting, starting/stopping recording, and querying status.

Usage:
    from recorder.obs_controller import OBSController

    with OBSController(host="localhost", port=4455, password="secret") as obs:
        obs.start_recording()
        # ... wait for replay to finish ...
        output_path = obs.stop_recording()
        print(f"Saved to: {output_path}")
"""

import logging
import time

import obsws_python as obs
from obsws_python.error import OBSSDKRequestError

logger = logging.getLogger(__name__)

# Seconds between each retry attempt when connecting
CONNECT_RETRY_INTERVAL = 2.0
CONNECT_MAX_RETRIES = 5

# Seconds to poll until OBS confirms recording is active after start_record()
RECORDING_START_TIMEOUT = 10.0
RECORDING_POLL_INTERVAL = 0.5


class OBSConnectionError(Exception):
    """Raised when unable to connect to OBS WebSocket after all retries."""


class OBSController:
    """
    Thin wrapper around obsws-python for the recording workflow.
    Use as a context manager to ensure the connection is always closed.
    """

    def __init__(self, host: str = "localhost", port: int = 4455, password: str = ""):
        self.host = host
        self.port = port
        self.password = password
        self._client: obs.ReqClient | None = None

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "OBSController":
        self.connect()
        return self

    def __exit__(self, *_) -> None:
        self.disconnect()

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """
        Connects to the OBS WebSocket server with retry logic.
        Raises OBSConnectionError if all attempts fail.
        """
        last_error = None
        for attempt in range(1, CONNECT_MAX_RETRIES + 1):
            try:
                logger.info(f"Connecting to OBS at {self.host}:{self.port} (attempt {attempt}/{CONNECT_MAX_RETRIES})...")
                self._client = obs.ReqClient(
                    host=self.host,
                    port=self.port,
                    password=self.password,
                    timeout=5,
                )
                logger.info("Connected to OBS successfully.")
                return
            except Exception as e:
                last_error = e
                logger.warning(f"OBS connection attempt {attempt} failed: {e}")
                if attempt < CONNECT_MAX_RETRIES:
                    time.sleep(CONNECT_RETRY_INTERVAL)

        raise OBSConnectionError(
            f"Could not connect to OBS at {self.host}:{self.port} "
            f"after {CONNECT_MAX_RETRIES} attempts. "
            f"Make sure OBS is open and WebSocket server is enabled. "
            f"Last error: {last_error}"
        )

    def disconnect(self) -> None:
        """Closes the WebSocket connection. Safe to call if not connected."""
        try:
            if self._client:
                self._client.disconnect()
                logger.info("Disconnected from OBS.")
        except Exception as e:
            logger.warning(f"Error disconnecting from OBS: {e}")
        finally:
            self._client = None

    # ------------------------------------------------------------------
    # Recording control
    # ------------------------------------------------------------------

    def start_recording(self) -> None:
        """
        Starts OBS recording and waits until OBS confirms it is active.
        This guarantees OBS is writing frames before the replay begins.

        Raises RuntimeError if recording doesn't start within the timeout.
        """
        self._require_connected()
        logger.info("Starting OBS recording...")
        self._client.start_record()

        # Poll until OBS confirms recording is active
        deadline = time.time() + RECORDING_START_TIMEOUT
        while time.time() < deadline:
            if self.is_recording():
                logger.info("OBS recording is active.")
                return
            time.sleep(RECORDING_POLL_INTERVAL)

        raise RuntimeError(
            f"OBS recording did not become active within {RECORDING_START_TIMEOUT}s."
        )

    def stop_recording(self) -> str:
        """
        Stops OBS recording.

        Returns:
            Absolute path to the recorded file (provided by OBS WebSocket).

        Raises RuntimeError if OBS is not currently recording.
        """
        self._require_connected()

        if not self.is_recording():
            raise RuntimeError("Cannot stop recording — OBS is not currently recording.")

        logger.info("Stopping OBS recording...")
        response = self._client.stop_record()
        output_path = response.output_path
        logger.info(f"Recording saved to: {output_path}")
        return output_path

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def is_recording(self) -> bool:
        """Returns True if OBS is currently recording."""
        self._require_connected()
        try:
            status = self._client.get_record_status()
            return status.output_active
        except Exception as e:
            logger.warning(f"Could not get recording status: {e}")
            return False

    def get_recording_stats(self) -> dict:
        """
        Returns current recording stats.

        Returns:
            dict with keys: active (bool), paused (bool), bytes (int), duration_ms (int)
        """
        self._require_connected()
        status = self._client.get_record_status()
        return {
            "active": status.output_active,
            "paused": status.output_paused,
            "bytes": status.output_bytes,
            "duration_ms": status.output_duration,
        }

    def get_version(self) -> str:
        """Returns the OBS Studio version string."""
        self._require_connected()
        resp = self._client.get_version()
        return resp.obs_version

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _require_connected(self) -> None:
        if self._client is None:
            raise RuntimeError("Not connected to OBS. Call connect() first.")
