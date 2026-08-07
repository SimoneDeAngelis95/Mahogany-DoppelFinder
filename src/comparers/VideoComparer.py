import subprocess
from FFmpegAdapter import FFmpegAdapter
from itertools import zip_longest

"""
Content-based comparison for video files.
Video files are decoded and fingerprinted from their raw video data.
Container metadata do not affect the result, but the container format
and the essential video properties must match.
Compare video files by the SHA256 fingerprint of their decoded video data.

This class provides the following functions:
    -> is_valid_video_file(pathToVideo) => True/False
    -> iter_video_framehash(pathToVideo, stream_index) => iterator of frame information
    -> compare_two_video_files(pathToVideo1, pathToVideo2) => True/False
    -> compare_video_and_list(pathToVideo, listOfPaths) => (equal_videos, different_videos)

ATTENTION!!!!!
FOR PERFORMANCE REASONS, THE FUNCTION iter_video_framehash() and the two comparison functions DO NOT CHECK IF THE VIDEO FILE IS VALID.
Please make sure to check if the video file is valid first with is_valid_video_file() before calling these functions.
"""

class VideoComparer:
    def __init__(self):
        self.ffmpeg_adapter = FFmpegAdapter()

    def is_valid_video_file(self, pathToVideo) -> bool:
        try:
            media_info = self.ffmpeg_adapter.get_media_info(pathToVideo)

            # This comparer currently supports files containing one or more video streams
            if media_info["video_stream_count"] < 1:
                return False

            format_name = media_info.get("format_name")
            if format_name is None:
                return False

            # FFmpeg also exposes static and animated images as video streams.
            image_formats = {
                "image2",
                "image2pipe",
                "jpeg_pipe",
                "png_pipe",
                "bmp_pipe",
                "tiff_pipe",
                "webp_pipe",
                "gif",
                "apng",
            }

            detected_formats = set(format_name.split(","))

            if detected_formats & image_formats:
                return False

            required_properties = (
                "format_name",
                "codec_name",
                "width",
                "height",
                "pixel_format",
                "time_base",
            )

            # Every real video stream must expose the properties required by
            # the progressive frame comparison.
            for stream_index in range(media_info["video_stream_count"]):
                video_info = self.ffmpeg_adapter.get_video_info(
                    pathToVideo,
                    stream_index,
                )

                for property_name in required_properties:
                    if video_info.get(property_name) is None:
                        return False

            return True

        except (TypeError, ValueError, OSError, subprocess.TimeoutExpired):
            return False

    def iter_video_framehash(self, pathToVideo, stream_index):
        return self.ffmpeg_adapter.iter_video_framehash(pathToVideo, stream_index)

    def compare_two_video_files(self, pathToVideo1, pathToVideo2) -> bool:
        media_info1 = self.ffmpeg_adapter.get_media_info(pathToVideo1)
        media_info2 = self.ffmpeg_adapter.get_media_info(pathToVideo2)

        # Compare the container format and the number of audio/video streams.
        media_properties = (
            "format_name",
            "audio_stream_count",
            "video_stream_count",
        )

        for property_name in media_properties:
            if media_info1.get(property_name) != media_info2.get(property_name):
                return False

        # Compare every audio stream.
        audio_properties = (
            "codec_name",
            "bit_depth",
            "sample_rate",
            "channels",
            "channel_layout",
            "time_base",
            "start_time",
            "duration",
        )

        for stream_index in range(media_info1["audio_stream_count"]):
            audio_info1 = self.ffmpeg_adapter.get_audio_info(
                pathToVideo1,
                stream_index,
            )
            audio_info2 = self.ffmpeg_adapter.get_audio_info(
                pathToVideo2,
                stream_index,
            )

            for property_name in audio_properties:
                if audio_info1.get(property_name) != audio_info2.get(property_name):
                    return False

            audio_hash1 = self.ffmpeg_adapter.get_audio_sha256(
                pathToVideo1,
                stream_index,
            )
            audio_hash2 = self.ffmpeg_adapter.get_audio_sha256(
                pathToVideo2,
                stream_index,
            )

            if audio_hash1 != audio_hash2:
                return False

        # Compare every video stream.
        video_properties = (
            "codec_name",
            "profile",
            "width",
            "height",
            "pixel_format",
            "bit_depth",
            "time_base",
            "real_frame_rate",
            "average_frame_rate",
            "start_time",
            "duration",
            "frame_count",
        )

        for stream_index in range(media_info1["video_stream_count"]):
            video_info1 = self.ffmpeg_adapter.get_video_info(
                pathToVideo1,
                stream_index,
            )
            video_info2 = self.ffmpeg_adapter.get_video_info(
                pathToVideo2,
                stream_index,
            )

            for property_name in video_properties:
                if video_info1.get(property_name) != video_info2.get(property_name):
                    return False

            frames1 = self.iter_video_framehash(pathToVideo1, stream_index)
            frames2 = self.iter_video_framehash(pathToVideo2, stream_index)

            missing_frame = object()

            try:
                for frame1, frame2 in zip_longest(
                    frames1,
                    frames2,
                    fillvalue=missing_frame,
                ):
                    # One video stream contains more frames than the other.
                    if frame1 is missing_frame or frame2 is missing_frame:
                        return False

                    # Hash, timestamps, duration or frame size are different.
                    if frame1 != frame2:
                        return False
            finally:
                frames1.close()
                frames2.close()

        return True
    
    def compare_video_and_list(self, pathToVideo, listOfPaths) -> tuple[list, list]:
        equal_videos = []
        different_videos = []

        for path in listOfPaths:
            if self.compare_two_video_files(pathToVideo, path):
                equal_videos.append(path)
            else:
                different_videos.append(path)

        return equal_videos, different_videos
####################
#TESTING

if __name__ == "__main__":
    video_comparer = VideoComparer()

    # Test with a valid video file
    video1 = "/Users/simone/Desktop/test1.mp4"
    video2 = "/Users/simone/Desktop/test2.mp4"
    video3 = "/Users/simone/Desktop/test3.mp4"
    video_list = [video1, video2, video3]
    equal_videos, different_videos = video_comparer.compare_video_and_list(video1, video_list)
    print("Equal videos:", equal_videos)
    print("Different videos:", different_videos)
