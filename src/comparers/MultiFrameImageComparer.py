import hashlib
from typing import Tuple
from PIL import Image, UnidentifiedImageError

"""
Content-based comparison for multi-frame images.
Images are decoded with Pillow and fingerprinted from the normalized pixels,
dimensions and duration of every frame.
Container metadata and file format therefore do not affect the result.
Compare images by the SHA256 fingerprint of their decoded frame data.

This class provides the following functions:
    -> is_valid_multi_frame_image(pathToImg) => True/False
    -> image_to_sha256(pathToImg) => sha256_hash
    -> compare_two_images(pathToImg1, pathToImg2) => True/False
    -> compare_image_and_list(pathToImg, listOfPaths) => (equal_images, disequal_images)

ATTENTION!!!!!
FOR PERFORMANCE REASONS, image_to_sha256() AND THE TWO COMPARISON FUNCTIONS DO NOT CHECK WHETHER THE IMAGE IS VALID.
Please make sure to check if the image is valid first with is_valid_multi_frame_image() before calling these functions.

Static images (single frame) are not supported by this class. They are managed in a different class.
Only multi-frame images are supported, including animated GIFs, animated WEBPs and multi-frame TIFFs.
"""

class MultiFrameImageComparer:
    def __init__(self):
        pass

    # Check whether the file is a valid image containing multiple frames.
    def is_valid_multi_frame_image(self, pathToImg) -> bool:
        try:
            with Image.open(pathToImg) as img:
                # Single-frame images are managed by StaticImageComparer.
                if getattr(img, "n_frames", 1) == 1:
                    return False
                img.verify()
            return True
        except (UnidentifiedImageError, FileNotFoundError, OSError):
            return False

    # Hash the normalized pixels, dimensions and duration of every frame.
    # The caller must validate the file first with
    # is_valid_multi_frame_image() to avoid repeating expensive work.
    def image_to_sha256(self, pathToImg) -> str:
        with Image.open(pathToImg) as img:
            digest = hashlib.sha256()
            for frame_index in range(img.n_frames):
                img.seek(frame_index)

                duration = img.info.get("duration")
                encoded_duration = -1 if duration is None else duration

                frame = img.convert("RGBA")  # Normalize the decoded pixels.
                width, height = frame.size
                pixel_data = frame.tobytes()
                digest.update(pixel_data)
                digest.update(width.to_bytes(8, 'big'))
                digest.update(height.to_bytes(8, 'big'))
                digest.update(encoded_duration.to_bytes(8, 'big', signed=True))

            return digest.hexdigest()

    # Compare frame count and looping behavior before computing the hashes.
    def compare_two_images(self, pathToImg1, pathToImg2) -> bool:
        with Image.open(pathToImg1) as img1, Image.open(pathToImg2) as img2:
            if img1.n_frames != img2.n_frames or img1.info.get("loop") != img2.info.get("loop"):
                return False

        hash1 = self.image_to_sha256(pathToImg1)
        hash2 = self.image_to_sha256(pathToImg2)
        return hash1 == hash2

    # Return separate lists for equal and different multi-frame images.
    def compare_image_and_list(self, pathToImg, listOfPaths) -> Tuple[list, list]:
        equal_images = []
        disequal_images = []

        with Image.open(pathToImg) as img:
            loop1 = img.info.get("loop")
            n_frames1 = img.n_frames
        hash1 = self.image_to_sha256(pathToImg)

        for img2 in listOfPaths:
            with Image.open(img2) as img:
                loop2 = img.info.get("loop")
                n_frames2 = img.n_frames

            if loop1 == loop2 and n_frames1 == n_frames2:
                hash2 = self.image_to_sha256(img2)
                if hash1 == hash2:
                    equal_images.append(img2)
                else:
                    disequal_images.append(img2)
            else:
                disequal_images.append(img2)

        return equal_images, disequal_images
