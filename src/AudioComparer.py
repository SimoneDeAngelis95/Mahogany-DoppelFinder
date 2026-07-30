"""
Content-based comparison for audio files.
Audio files are decoded and fingerprinted from their raw audio data.
Container metadata and file format therefore do not affect the result.
Compare audio files by the SHA256 fingerprint of their decoded audio data.

This class provides the following functions:
    -> is_valid_audio_file(pathToAudio) => True/False
    -> audio_to_sha256(pathToAudio) => sha256_hash
    -> compare_two_audio_files(pathToAudio1, pathToAudio2) => True/False
    -> compare_audio_and_list(pathToAudio, listOfPaths) => (equal_audios, different_audios)

ATTENTION!!!!!
FOR PERFORMANCE REASONS, THE FUNCTION audio_to_sha256() and the two comparison functions DOES NOT CHECK IF THE AUDIO FILE IS VALID.
Please make sure to check if the audio file is valid first with is_valid_audio_file() before calling these functions.
"""

class AudioComparer:
    def __init__(self):
        pass
