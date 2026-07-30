import json
import os
import shutil
import subprocess
from pathlib import Path

"""
This class provides an adapter for FFmpeg, allowing for easy integration and usage of FFmpeg functionalities

Functions:
    ffmpeg_available() => True/False
    ffprobe_available() => True/False
    get_audio_info(pathToAudio) => dict with keys:
        format_name
        codec_name
        bit_depth
        sample_rate
        channels
        channel_layout
        duration
    get_audio_sha256(pathToAudio) => sha256_hash
"""

class FFmpegAdapter:
    def __init__(self, bin_directory=None):
        if bin_directory is None:
            resource_path = os.environ.get("RESOURCEPATH")

            if resource_path:
                # py2app places bundled resources inside
                # MyApplication.app/Contents/Resources.
                bin_directory = Path(resource_path) / "bin"
            else:
                # During development, resolve the bin directory from this
                # source file instead of relying on the current working directory.
                project_root = Path(__file__).resolve().parent.parent
                bin_directory = project_root / "bin"

        # An explicit directory takes priority over both py2app resources
        # and the default development path.
        self.bin_directory = Path(bin_directory)
        self.ffmpeg_path = self._resolve_executable("ffmpeg")
        self.ffprobe_path = self._resolve_executable("ffprobe")

    def _resolve_executable(self, executable_name):
        executable_filename = (
            f"{executable_name}.exe"
            if os.name == "nt"
            else executable_name
        )
        bundled_path = self.bin_directory / executable_filename

        if bundled_path.is_file() and os.access(bundled_path, os.X_OK):
            return str(bundled_path)

        return shutil.which(executable_name)

    @staticmethod
    def _validate_file_path(pathToMedia):
        media_path = os.fspath(pathToMedia)

        if not os.path.exists(media_path):
            raise FileNotFoundError(media_path)
        if not os.path.isfile(media_path):
            raise IsADirectoryError(media_path)

        return media_path

    def ffmpeg_available(self) -> bool:
        return self.ffmpeg_path is not None

    def ffprobe_available(self) -> bool:
        return self.ffprobe_path is not None

    def get_audio_info(self, pathToAudio) -> dict:
        """Return normalized information about the first audio stream."""
        audio_path = self._validate_file_path(pathToAudio)

        if self.ffprobe_path is None:
            raise RuntimeError(
                "ffprobe is neither bundled with the application "
                "nor available in PATH."
            )

        command = [
            self.ffprobe_path,
            "-v", "error",
            "-select_streams", "a:0",
            "-show_entries",
            (
                "format=format_name,duration:"
                "stream=codec_name,bits_per_sample,bits_per_raw_sample,"
                "sample_rate,channels,channel_layout,duration"
            ),
            "-of", "json",
            audio_path,
        ]

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=15,
            check=False,
        )

        if result.returncode != 0:
            error_message = result.stderr.strip() or "ffprobe could not analyze the file."
            raise ValueError(error_message)

        try:
            probe_data = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise ValueError("ffprobe returned invalid JSON.") from error

        streams = probe_data.get("streams", [])
        if not streams:
            raise ValueError(f"{audio_path} does not contain an audio stream.")

        stream = streams[0]
        format_info = probe_data.get("format", {})

        def positive_int(value):
            try:
                parsed_value = int(value)
            except (TypeError, ValueError):
                return None
            return parsed_value if parsed_value > 0 else None

        def optional_float(value):
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        bit_depth = (
            positive_int(stream.get("bits_per_raw_sample"))
            or positive_int(stream.get("bits_per_sample"))
        )
        duration = optional_float(stream.get("duration"))
        if duration is None:
            duration = optional_float(format_info.get("duration"))

        return {
            "format_name": format_info.get("format_name"),
            "codec_name": stream.get("codec_name"),
            "bit_depth": bit_depth,
            "sample_rate": positive_int(stream.get("sample_rate")),
            "channels": positive_int(stream.get("channels")),
            "channel_layout": stream.get("channel_layout"),
            "duration": duration,
        }

    def get_audio_sha256(self, pathToAudio) -> str:
        """Return the SHA256 hash of the first audio stream decoded as PCM."""
        audio_path = self._validate_file_path(pathToAudio)

        if self.ffmpeg_path is None:
            raise RuntimeError(
                "ffmpeg is neither bundled with the application "
                "nor available in PATH."
            )

        command = [
            self.ffmpeg_path,
            "-v", "error",
            "-i", audio_path,
            "-map", "0:a:0",
            "-c:a", "pcm_s32le",
            "-f", "hash",
            "-hash", "sha256",
            "-",
        ]

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            check=False,
        )

        if result.returncode != 0:
            error_message = result.stderr.strip() or "ffmpeg could not decode the audio stream."
            raise ValueError(error_message)

        prefix = "SHA256="
        output = result.stdout.strip()
        if not output.startswith(prefix):
            raise ValueError("ffmpeg returned an invalid SHA256 response.")

        sha256_hash = output[len(prefix):].strip()
        if len(sha256_hash) != 64:
            raise ValueError("ffmpeg returned an invalid SHA256 hash.")

        return sha256_hash


# TESTING
if __name__ == "__main__":
    adapter = FFmpegAdapter()
    print("FFmpeg available:", adapter.ffmpeg_available())
    print("FFprobe available:", adapter.ffprobe_available())
    test_audio_path = "/Users/simone/Desktop/test.wav"  # Replace with a valid audio file path for testing
    if os.path.exists(test_audio_path):
        try:
            info = adapter.get_audio_info(test_audio_path)
            print("Audio Info:", info)
        except Exception as e:
            print("Error retrieving audio info:", e)
    else:
        print(f"Test audio file '{test_audio_path}' does not exist.")
