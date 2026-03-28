"""
tests/test_obs_controller.py

Unit tests for OBSController using a mocked obsws_python client.
Run with: pytest tests/test_obs_controller.py -v
"""

from unittest.mock import MagicMock, patch, PropertyMock
import pytest

from recorder.obs_controller import OBSController, OBSConnectionError


def make_client(recording_active=False, output_path="/output/replay.mkv"):
    """Returns a mock obsws ReqClient wired with common responses."""
    client = MagicMock()

    # get_record_status
    status = MagicMock()
    status.output_active = recording_active
    status.output_paused = False
    status.output_bytes = 1024
    status.output_duration = 5000
    client.get_record_status.return_value = status

    # stop_record
    stop_resp = MagicMock()
    stop_resp.output_path = output_path
    client.stop_record.return_value = stop_resp

    # get_version
    version_resp = MagicMock()
    version_resp.obs_version = "32.1.0"
    client.get_version.return_value = version_resp

    return client


# ------------------------------------------------------------------
# connect / disconnect
# ------------------------------------------------------------------

class TestConnect:
    @patch("recorder.obs_controller.obs.ReqClient")
    def test_connect_succeeds_on_first_attempt(self, mock_req_client):
        mock_req_client.return_value = make_client()
        controller = OBSController()
        controller.connect()
        assert controller._client is not None

    @patch("recorder.obs_controller.obs.ReqClient")
    @patch("recorder.obs_controller.time.sleep")
    def test_connect_retries_on_failure(self, mock_sleep, mock_req_client):
        client = make_client()
        mock_req_client.side_effect = [Exception("refused"), Exception("refused"), client]
        controller = OBSController()
        controller.connect()
        assert mock_req_client.call_count == 3

    @patch("recorder.obs_controller.obs.ReqClient")
    @patch("recorder.obs_controller.time.sleep")
    def test_raises_after_max_retries(self, mock_sleep, mock_req_client):
        mock_req_client.side_effect = Exception("refused")
        controller = OBSController()
        with pytest.raises(OBSConnectionError):
            controller.connect()

    @patch("recorder.obs_controller.obs.ReqClient")
    def test_disconnect_clears_client(self, mock_req_client):
        client = make_client()
        mock_req_client.return_value = client
        controller = OBSController()
        controller.connect()
        controller.disconnect()
        assert controller._client is None

    @patch("recorder.obs_controller.obs.ReqClient")
    def test_disconnect_safe_when_not_connected(self, _):
        controller = OBSController()
        controller.disconnect()  # should not raise


# ------------------------------------------------------------------
# start_recording
# ------------------------------------------------------------------

class TestStartRecording:
    @patch("recorder.obs_controller.obs.ReqClient")
    @patch("recorder.obs_controller.time.sleep")
    def test_starts_and_waits_for_active(self, mock_sleep, mock_req_client):
        # First is_recording call returns False, second returns True
        client = make_client(recording_active=False)
        active_status = MagicMock()
        active_status.output_active = True
        client.get_record_status.side_effect = [
            MagicMock(output_active=False),
            MagicMock(output_active=True),
        ]
        mock_req_client.return_value = client

        controller = OBSController()
        controller.connect()
        controller.start_recording()

        client.start_record.assert_called_once()

    @patch("recorder.obs_controller.obs.ReqClient")
    @patch("recorder.obs_controller.time.sleep")
    @patch("recorder.obs_controller.time.time")
    def test_raises_if_recording_never_starts(self, mock_time, mock_sleep, mock_req_client):
        mock_time.side_effect = [0, 0, 99999]
        client = make_client(recording_active=False)
        mock_req_client.return_value = client

        controller = OBSController()
        controller.connect()
        with pytest.raises(RuntimeError, match="did not become active"):
            controller.start_recording()

    def test_requires_connection(self):
        controller = OBSController()
        with pytest.raises(RuntimeError, match="Not connected"):
            controller.start_recording()


# ------------------------------------------------------------------
# stop_recording
# ------------------------------------------------------------------

class TestStopRecording:
    @patch("recorder.obs_controller.obs.ReqClient")
    def test_returns_output_path(self, mock_req_client):
        client = make_client(recording_active=True, output_path="/output/replay.mkv")
        mock_req_client.return_value = client

        controller = OBSController()
        controller.connect()
        path = controller.stop_recording()

        assert path == "/output/replay.mkv"
        client.stop_record.assert_called_once()

    @patch("recorder.obs_controller.obs.ReqClient")
    def test_raises_if_not_recording(self, mock_req_client):
        client = make_client(recording_active=False)
        mock_req_client.return_value = client

        controller = OBSController()
        controller.connect()
        with pytest.raises(RuntimeError, match="not currently recording"):
            controller.stop_recording()

    def test_requires_connection(self):
        controller = OBSController()
        with pytest.raises(RuntimeError, match="Not connected"):
            controller.stop_recording()


# ------------------------------------------------------------------
# Context manager
# ------------------------------------------------------------------

class TestContextManager:
    @patch("recorder.obs_controller.obs.ReqClient")
    def test_connects_and_disconnects(self, mock_req_client):
        client = make_client()
        mock_req_client.return_value = client

        with OBSController() as controller:
            assert controller._client is not None

        assert controller._client is None
        client.disconnect.assert_called_once()
