from FFmpegAdapter import FFmpegAdapter
import subprocess

"""
Content-based comparison for audio files.
Audio files are decoded and fingerprinted from their raw audio data.
Container metadata do not affect the result, but the container format
and the essential audio properties must match.
Compare audio files by the SHA256 fingerprint of their decoded audio data.

This class provides the following functions:
    -> is_valid_audio_file(pathToAudio) => True/False
    -> audio_to_sha256(pathToAudio) => sha256_hash
    -> compare_two_audio_files(pathToAudio1, pathToAudio2) => True/False
    -> compare_audio_and_list(pathToAudio, listOfPaths) => (equal_audios, different_audios)

ATTENTION!!!!!
FOR PERFORMANCE REASONS, audio_to_sha256() AND THE TWO COMPARISON FUNCTIONS DO NOT CHECK WHETHER THE AUDIO FILE IS VALID.
Please make sure to check if the audio file is valid first with is_valid_audio_file() before calling these functions.
"""

class AudioComparer:
    def __init__(self):
        self.ffmpeg_adapter = FFmpegAdapter()

    def is_valid_audio_file(self, pathToAudio) -> bool:
        try:
            media_info = self.ffmpeg_adapter.get_media_info(pathToAudio)

            # This comparer currently supports files containing exactly
            # one audio stream and no actual video streams.
            if media_info["audio_stream_count"] != 1:
                return False

            if media_info["video_stream_count"] != 0:
                return False

            audio_info = self.ffmpeg_adapter.get_audio_info(pathToAudio)

            # These properties are essential for comparing the audio stream.
            required_properties = (
                "format_name",
                "codec_name",
                "sample_rate",
                "channels",
            )

            for property_name in required_properties:
                if audio_info.get(property_name) is None:
                    return False

            return True

        except (TypeError, ValueError, OSError, subprocess.TimeoutExpired):
            return False

    # The caller must validate the file with is_valid_audio_file() first.
    # Repeating that validation here would add unnecessary FFprobe calls.
    def audio_to_sha256(self, pathToAudio) -> str:
        return self.ffmpeg_adapter.get_audio_sha256(pathToAudio)

    def compare_two_audio_files(self, pathToAudio1, pathToAudio2) -> bool:
        audio_info1 = self.ffmpeg_adapter.get_audio_info(pathToAudio1)
        audio_info2 = self.ffmpeg_adapter.get_audio_info(pathToAudio2)

        properties_to_compare = ("format_name", "codec_name", "bit_depth", "sample_rate", "channels", "channel_layout")

        for property_name in properties_to_compare:
            if audio_info1.get(property_name) != audio_info2.get(property_name):
                return False

        # The essential properties match, so compare the decoded audio data.
        hash1 = self.audio_to_sha256(pathToAudio1)
        hash2 = self.audio_to_sha256(pathToAudio2)

        return hash1 == hash2

    def compare_audio_and_list(self, pathToAudio, listOfPaths) -> tuple[list, list]:
        equal_audios = []
        different_audios = []

        audio_info1 = self.ffmpeg_adapter.get_audio_info(pathToAudio)
        # Compute the source hash lazily and reuse it for every suitable candidate.
        hash1 = None
        properties_to_compare = ("format_name", "codec_name", "bit_depth", "sample_rate", "channels", "channel_layout")

        for path in listOfPaths:
            audio_info2 = self.ffmpeg_adapter.get_audio_info(path)
            keep_going = True

            for property_name in properties_to_compare:
                if audio_info1.get(property_name) != audio_info2.get(property_name):
                    different_audios.append(path)
                    keep_going = False
                    break

            if keep_going:
                if hash1 is None:
                    hash1 = self.audio_to_sha256(pathToAudio)
                hash2 = self.audio_to_sha256(path)

                if hash1 == hash2:
                    equal_audios.append(path)
                else:
                    different_audios.append(path)

        return equal_audios, different_audios
