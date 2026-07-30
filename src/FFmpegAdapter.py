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

import json
import os
import shutil
import subprocess


class FFmpegAdapter:
    def __init__(self):
        pass

    def ffmpeg_available(self) -> bool:
        return shutil.which("ffmpeg") is not None

    def ffprobe_available(self) -> bool:
        return shutil.which("ffprobe") is not None

    def get_audio_info(self, pathToAudio) -> dict:
        """Return normalized information about the first audio stream."""
        audio_path = os.fspath(pathToAudio)

        if not os.path.exists(audio_path):
            raise FileNotFoundError(audio_path)
        if not os.path.isfile(audio_path):
            raise IsADirectoryError(audio_path)

        ffprobe_path = shutil.which("ffprobe")
        if ffprobe_path is None:
            raise RuntimeError("ffprobe is not installed or is not available in PATH.")

        command = [
            ffprobe_path,
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