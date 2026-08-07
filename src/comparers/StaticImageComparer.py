import hashlib
from typing import Tuple
from PIL import Image, UnidentifiedImageError

"""
Content-based comparison for static images.
Images are decoded with Pillow and fingerprinted from normalized pixel data.
Container metadata and file format therefore do not affect the result.
Compare images by the SHA256 fingerprint of their decoded pixels.

This class provides the following functions:
    -> is_valid_static_image(pathToImg) => True/False
    -> image_to_sha256(pathToImg) => (sha256_hash, (width, height)) I need the size of the image to avoid false positives when comparing images with different sizes but same pixel data (e.g. a 1x2 image and a 2x1 image with the same pixels)
    -> compare_two_images(pathToImg1, pathToImg2) => True/False
    -> compare_image_and_list(pathToImg, listOfPaths) => (equal_images, disequal_images)

ATTENTION!!!!!
FOR PERFORMANCE REASONS, image_to_sha256() AND THE TWO COMPARISON FUNCTIONS DO NOT CHECK WHETHER THE IMAGE IS VALID.
Please make sure to check if the image is valid first with is_valid_static_image() before calling these functions.

Animated GIFs, animated WEBPs, multi-frame TIFFs and other multi-frame images are not supported by this class. They are managed in a different class.
Only static images (single frame) are supported by this class. Examples of supported formats: PNG, JPEG, BMP, single-frame TIFF, single-frame WEBP, etc.
"""

class StaticImageComparer:
    def __init__(self):
        pass

    # Check whether the file is a valid, single-frame image.
    def is_valid_static_image(self, pathToImg) -> bool:
        try:
            with Image.open(pathToImg) as img:
                # Multi-frame images are managed by MultiFrameImageComparer.
                if getattr(img, "n_frames", 1) != 1:
                    return False
                img.verify()
            return True
        except (UnidentifiedImageError, FileNotFoundError, OSError):
            return False

    # The caller must validate the file with is_valid_static_image() first.
    # Repeating that validation here would decode the image unnecessarily.
    def image_to_sha256(self, pathToImg) -> Tuple[str, Tuple[int, int]]:
        with Image.open(pathToImg) as img:
            img = img.convert("RGBA")  # Normalize the decoded pixels.
            pixel_data = img.tobytes()
            sha256_hash = hashlib.sha256(pixel_data).hexdigest()
            return sha256_hash, img.size

    # Compare two images by their normalized pixels and dimensions.
    def compare_two_images(self, pathToImg1, pathToImg2) -> bool:
        hash1, size1 = self.image_to_sha256(pathToImg1)
        hash2, size2 = self.image_to_sha256(pathToImg2)
        return hash1 == hash2 and size1 == size2

    # Return separate lists for equal and different images.
    def compare_image_and_list(self, pathToImg, listOfPaths) -> Tuple[list, list]:
        equal_images = []
        disequal_images = []
        hash1, size1 = self.image_to_sha256(pathToImg)

        for path in listOfPaths:
            hash2, size2 = self.image_to_sha256(path)
            if hash1 == hash2 and size1 == size2:
                equal_images.append(path)
            else:
                disequal_images.append(path)

        return equal_images, disequal_images
