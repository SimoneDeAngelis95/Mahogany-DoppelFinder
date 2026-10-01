from scan_parallel import media_threads
import json
import os
import shutil
import subprocess
from collections import deque
from pathlib import Path

"""
This class provides an adapter for FFmpeg, allowing for easy integration and usage of FFmpeg functionalities

Functions:
    ffmpeg_available() => True/False
    ffprobe_available() => True/False
    get_media_info(pathToMedia) => dict with keys:
        format_name
        audio_stream_count
        video_stream_count
    get_audio_info(pathToAudio) => dict with keys:
        format_name
        codec_name
        bit_depth
        sample_rate
        channels
        channel_layout
        duration
    get_audio_sha256(pathToAudio) => sha256_hash
    get_video_info(pathToVideo) => dict with keys:
        format_name
        codec_name
        profile
        width
        height
        pixel_format
        bit_depth
        time_base
        real_frame_rate
        average_frame_rate
        start_time
        duration
        frame_count
    iter_video_framehash(pathToVideo) => iterator of frame information
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

    # Resolve the bundled executable first, then fall back to PATH.
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

    @staticmethod
    def _positive_int(value):
        """Convert a value to a positive integer, or return None."""
        try:
            parsed_value = int(value)
        except (TypeError, ValueError):
            return None
        return parsed_value if parsed_value > 0 else None

    @staticmethod
    def _optional_float(value):
        """Convert a value to a float, or return None."""
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _validate_stream_index(stream_index):
        """Validate and return a non-negative relative stream index."""
        if isinstance(stream_index, bool) or not isinstance(stream_index, int):
            raise TypeError("stream_index must be an integer.")
        if stream_index < 0:
            raise ValueError("stream_index cannot be negative.")
        return stream_index

    @staticmethod
    def _is_valid_sha256(value):
        """Return True when value is a lowercase or uppercase SHA256 hash."""
        if not isinstance(value, str) or len(value) != 64:
            return False
        return all(character.lower() in "0123456789abcdef" for character in value)

    @staticmethod
    def _parse_framehash_time_base(line):
        """Parse a '#tb <stream>: <time_base>' framehash header."""
        try:
            header, time_base = line.split(":", 1)
            stream_index = int(header.split()[1])
        except (IndexError, ValueError):
            return None
        return stream_index, time_base.strip()

    @classmethod
    def _parse_framehash_record(cls, line, output_time_bases):
        """Parse one FFmpeg framehash data line into a normalized dict."""
        fields = [field.strip() for field in line.split(",")]
        if len(fields) != 6:
            return None

        try:
            stream, dts, pts, duration, size = map(int, fields[:5])
        except ValueError:
            return None

        sha256_hash = fields[5].lower()
        if not cls._is_valid_sha256(sha256_hash):
            return None

        return {
            "stream_index": stream,
            "time_base": output_time_bases.get(stream),
            "dts": dts,
            "pts": pts,
            "duration": duration,
            "size": size,
            "sha256": sha256_hash,
        }

    @staticmethod
    def _executable_available(executable_path):
        """Return True only when an executable can actually be launched."""
        if executable_path is None:
            return False

        try:
            result = subprocess.run(
                [executable_path, "-version"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False

        return result.returncode == 0

    def _run_ffprobe(self, pathToMedia, show_entries, select_streams=None):
        """Run FFprobe once and return its parsed JSON response."""
        media_path = self._validate_file_path(pathToMedia)

        if self.ffprobe_path is None:
            raise RuntimeError(
                "ffprobe is neither bundled with the application "
                "nor available in PATH."
            )

        command = [
            self.ffprobe_path,
            "-v", "error",
        ]

        if select_streams is not None:
            command.extend(["-select_streams", select_streams])

        command.extend([
            "-show_entries", show_entries,
            "-of", "json",
            media_path,
        ])

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=15,
            check=False,
        )

        if result.returncode != 0:
            error_message = (
                result.stderr.strip()
                or "ffprobe could not analyze the file."
            )
            raise ValueError(error_message)

        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise ValueError("ffprobe returned invalid JSON.") from error

    def ffmpeg_available(self) -> bool:
        return self._executable_available(self.ffmpeg_path)

    def ffprobe_available(self) -> bool:
        return self._executable_available(self.ffprobe_path)

    def get_media_info(self, pathToMedia) -> dict:
        """Return container information and audio/video stream counts."""
        probe_data = self._run_ffprobe(
            pathToMedia,
            (
                "format=format_name:"
                "stream=codec_type:"
                "stream_disposition=attached_pic,timed_thumbnails,still_image"
            ),
        )
        streams = probe_data.get("streams", [])

        return {
            "format_name": probe_data.get("format", {}).get("format_name"),
            "audio_stream_count": sum(
                stream.get("codec_type") == "audio"
                for stream in streams
            ),
            "video_stream_count": sum(
                stream.get("codec_type") == "video"
                and not stream.get("disposition", {}).get("attached_pic", 0)
                and not stream.get("disposition", {}).get(
                    "timed_thumbnails", 0
                )
                and not stream.get("disposition", {}).get("still_image", 0)
                for stream in streams
            ),
        }

    def get_audio_info(self, pathToAudio, stream_index=0) -> dict:
        """Return normalized information about one relative audio stream."""
        stream_index = self._validate_stream_index(stream_index)
        probe_data = self._run_ffprobe(
            pathToAudio,
            (
                "format=format_name,duration:"
                "stream=codec_name,bits_per_sample,bits_per_raw_sample,"
                "sample_rate,channels,channel_layout,time_base,start_time,"
                "duration"
            ),
            select_streams=f"a:{stream_index}",
        )
        streams = probe_data.get("streams", [])
        if not streams:
            raise ValueError(
                f"The media file does not contain audio stream a:{stream_index}."
            )

        stream = streams[0]
        format_info = probe_data.get("format", {})
        bit_depth = (
            self._positive_int(stream.get("bits_per_raw_sample"))
            or self._positive_int(stream.get("bits_per_sample"))
        )
        duration = self._optional_float(stream.get("duration"))
        if duration is None:
            duration = self._optional_float(format_info.get("duration"))

        return {
            "format_name": format_info.get("format_name"),
            "codec_name": stream.get("codec_name"),
            "bit_depth": bit_depth,
            "sample_rate": self._positive_int(stream.get("sample_rate")),
            "channels": self._positive_int(stream.get("channels")),
            "channel_layout": stream.get("channel_layout"),
            "time_base": stream.get("time_base"),
            "start_time": self._optional_float(stream.get("start_time")),
            "duration": duration,
        }

    def get_audio_sha256(self, pathToAudio, stream_index=0) -> str:
        """Return the PCM SHA256 hash of one relative audio stream."""
        stream_index = self._validate_stream_index(stream_index)
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
            "-map", f"0:a:{stream_index}",
            "-c:a", "pcm_s32le",
            "-f", "hash",
            "-hash", "sha256",
            "-",
        ]

        if media_threads() is not None:
            command[1:1] = ["-threads", str(media_threads())]
            command[-1:-1] = ["-threads", str(media_threads())]

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
        if not self._is_valid_sha256(sha256_hash):
            raise ValueError("ffmpeg returned an invalid SHA256 hash.")

        return sha256_hash

    def get_video_info(self, pathToVideo, stream_index=0) -> dict:
        """Return normalized information about one relative video stream."""
        stream_index = self._validate_stream_index(stream_index)
        probe_data = self._run_ffprobe(
            pathToVideo,
            (
                "format=format_name,duration:"
                "stream=codec_name,profile,width,height,pix_fmt,"
                "bits_per_raw_sample,time_base,r_frame_rate,avg_frame_rate,"
                "start_time,duration,nb_frames"
            ),
            # Uppercase V excludes attached pictures and thumbnails.
            select_streams=f"V:{stream_index}",
        )
        streams = probe_data.get("streams", [])
        if not streams:
            raise ValueError(
                f"The media file does not contain video stream v:{stream_index}."
            )

        stream = streams[0]
        format_info = probe_data.get("format", {})
        duration = self._optional_float(stream.get("duration"))
        if duration is None:
            duration = self._optional_float(format_info.get("duration"))

        return {
            "format_name": format_info.get("format_name"),
            "codec_name": stream.get("codec_name"),
            "profile": stream.get("profile"),
            "width": self._positive_int(stream.get("width")),
            "height": self._positive_int(stream.get("height")),
            "pixel_format": stream.get("pix_fmt"),
            "bit_depth": self._positive_int(
                stream.get("bits_per_raw_sample")
            ),
            "time_base": stream.get("time_base"),
            "real_frame_rate": stream.get("r_frame_rate"),
            "average_frame_rate": stream.get("avg_frame_rate"),
            "start_time": self._optional_float(stream.get("start_time")),
            "duration": duration,
            "frame_count": self._positive_int(stream.get("nb_frames")),
        }

    def iter_video_framehash(self, pathToVideo, stream_index=0):
        """Yield timing data and SHA256 for each decoded video frame."""
        stream_index = self._validate_stream_index(stream_index)
        video_path = self._validate_file_path(pathToVideo)

        if self.ffmpeg_path is None:
            raise RuntimeError(
                "ffmpeg is neither bundled with the application "
                "nor available in PATH."
            )

        command = [
            self.ffmpeg_path,
            "-hide_banner",
            "-v", "error",
            "-copyts",
            "-i", video_path,
            # Uppercase V excludes attached pictures and thumbnails.
            "-map", f"0:V:{stream_index}",
            "-fps_mode", "passthrough",
            "-f", "framehash",
            "-hash", "sha256",
            "-",
        ]

        # This generator starts one FFmpeg process and keeps it alive for the
        # entire iteration. Each call to next() resumes this function, reads
        # the next frame produced by that same process and pauses again at
        # yield. Therefore, the video is not reopened for every frame.
        # Closing the generator enters the finally block below, where the
        # pipe is closed and the still-running FFmpeg process is terminated.

        # STDERR is merged into STDOUT to prevent a full error pipe from
        # blocking FFmpeg while frames are consumed progressively.
        if media_threads() is not None:
            command[1:1] = ["-threads", str(media_threads())]
            command[-1:-1] = ["-threads", str(media_threads())]

        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            stdin=subprocess.DEVNULL,
            bufsize=1,
        )

        # Retain only the most recent diagnostics so a broken input cannot
        # grow this buffer indefinitely.
        error_lines = deque(maxlen=20)
        output_time_bases = {}

        try:
            if process.stdout is None:
                raise RuntimeError("Could not read FFmpeg framehash output.")

            for line in process.stdout:
                stripped_line = line.strip()

                if not stripped_line:
                    continue

                # FFmpeg expresses DTS, PTS and duration in the output stream
                # time base declared by a "#tb <index>: <value>" header.
                if stripped_line.startswith("#tb "):
                    parsed_time_base = self._parse_framehash_time_base(
                        stripped_line
                    )
                    if parsed_time_base is None:
                        error_lines.append(stripped_line)
                    else:
                        output_stream_index, time_base = parsed_time_base
                        output_time_bases[output_stream_index] = time_base
                    continue

                # Other framehash headers start with '#' and carry no frame.
                if stripped_line.startswith("#"):
                    continue

                frame_info = self._parse_framehash_record(
                    stripped_line,
                    output_time_bases,
                )
                if frame_info is None:
                    error_lines.append(stripped_line)
                    continue

                yield frame_info

            return_code = process.wait()
            if return_code != 0:
                error_message = (
                    "\n".join(error_lines)
                    or "ffmpeg could not decode the video stream."
                )
                raise ValueError(error_message)
        finally:
            if process.stdout is not None:
                process.stdout.close()

            # Closing the iterator early must also stop the FFmpeg process.
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
