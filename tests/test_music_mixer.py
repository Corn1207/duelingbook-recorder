"""
tests/test_music_mixer.py

Unit tests for MusicMixer.
Run with: pytest tests/test_music_mixer.py -v
"""

from pathlib import Path
from unittest.mock import MagicMock, patch, call
import pytest

from postprocess.music_mixer import MusicMixer


FAKE_MUSIC_FOLDER = "/fake/music"


def make_mixer(**kwargs) -> MusicMixer:
    return MusicMixer(music_folder=FAKE_MUSIC_FOLDER, **kwargs)


# ------------------------------------------------------------------
# _get_shuffled_mp3s
# ------------------------------------------------------------------

class TestGetShuffledMp3s:
    def test_returns_only_mp3_files(self, tmp_path):
        (tmp_path / "song1.mp3").touch()
        (tmp_path / "song2.mp3").touch()
        (tmp_path / "image.jpg").touch()
        (tmp_path / "subfolder").mkdir()
        (tmp_path / "subfolder" / "song3.mp3").touch()

        mixer = MusicMixer(music_folder=str(tmp_path))
        result = mixer._get_shuffled_mp3s()

        assert len(result) == 3
        assert all(f.suffix == ".mp3" for f in result)

    def test_returns_empty_when_no_mp3s(self, tmp_path):
        (tmp_path / "image.jpg").touch()
        mixer = MusicMixer(music_folder=str(tmp_path))
        assert mixer._get_shuffled_mp3s() == []


# ------------------------------------------------------------------
# _build_playlist
# ------------------------------------------------------------------

class TestBuildPlaylist:
    @patch.object(MusicMixer, "_get_duration")
    def test_covers_video_duration(self, mock_duration):
        mock_duration.return_value = 60.0  # each track = 60s
        mixer = make_mixer()
        tracks = [Path(f"/music/track{i}.mp3") for i in range(5)]

        playlist = mixer._build_playlist(tracks, required_duration=150.0)

        # Need 3 tracks of 60s to cover 150s
        assert len(playlist) == 3

    @patch.object(MusicMixer, "_get_duration")
    def test_recycles_tracks_when_pool_exhausted(self, mock_duration):
        mock_duration.return_value = 30.0
        mixer = make_mixer()
        tracks = [Path("/music/only_one.mp3")]

        # 3 tracks of 30s needed for 90s video — only 1 track available
        playlist = mixer._build_playlist(tracks, required_duration=90.0)
        assert len(playlist) == 3


# ------------------------------------------------------------------
# mix — high level
# ------------------------------------------------------------------

class TestMix:
    def test_raises_when_no_mp3s(self, tmp_path):
        mixer = MusicMixer(music_folder=str(tmp_path))  # empty folder
        with patch.object(mixer, "_get_duration", return_value=60.0):
            with pytest.raises(FileNotFoundError):
                mixer.mix(video_path="video.mkv", output_dir=str(tmp_path))

    @patch("postprocess.music_mixer.os.unlink")
    def test_calls_ffmpeg(self, mock_unlink, tmp_path):
        mixer = MusicMixer(music_folder="/music")
        with patch.object(mixer, "_get_duration", return_value=60.0), \
             patch.object(mixer, "_get_shuffled_mp3s", return_value=[Path("/music/song.mp3")]), \
             patch("postprocess.music_mixer.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            mixer.mix(video_path="video.mkv", output_dir=str(tmp_path))
            ffmpeg_call = mock_run.call_args_list[-1]
            cmd = ffmpeg_call.args[0]
            assert cmd[0] == "ffmpeg"

    @patch("postprocess.music_mixer.os.unlink")
    def test_raises_on_ffmpeg_failure(self, mock_unlink, tmp_path):
        mixer = MusicMixer(music_folder="/music")
        with patch.object(mixer, "_get_duration", return_value=60.0), \
             patch.object(mixer, "_get_shuffled_mp3s", return_value=[Path("/music/song.mp3")]), \
             patch("postprocess.music_mixer.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="ffmpeg error")
            with pytest.raises(RuntimeError, match="ffmpeg failed"):
                mixer.mix(video_path="video.mkv", output_dir=str(tmp_path))
