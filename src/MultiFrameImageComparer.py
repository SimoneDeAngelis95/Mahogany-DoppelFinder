import hashlib
from typing import Tuple
from PIL import Image, UnidentifiedImageError

"""
Content-based comparison for multi-frame images.
Images are decoded with Pillow and fingerprinted from normalized pixel data, each frame individually.
Container metadata and file format therefore do not affect the result.
Compare images by the SHA256 fingerprint of their decoded pixels.

This class provides the following functions:
    -> is_valid_multi_frame_image(pathToImg) => True/False
    -> image_to_sha256(pathToImg) => sha256_hash
    -> compare_two_images(pathToImg1, pathToImg2) => True/False
    -> compare_image_and_list(pathToImg, listOfPaths) => (equal_images, disequal_images)

ATTENTION!!!!!
FOR PERFORMANCE REASONS, THE FUNCTION image_to_sha256() and the two comparison functions DOES NOT CHECK IF THE IMAGE IS VALID.
Please make sure to check if the image is valid first with is_valid_multi_frame_image() before calling these functions.

static images (single frame) are not supported by this class. They are managed in a different class.
Only multi-frame images (animated GIFs, animated WEBPs, multiframe TIFFs and other animated images) are supported by this class. Examples of supported formats: GIF, WEBP, TIFF
"""

class MultiFrameImageComparer:
    def __init__(self):
        pass
    
                                                                        # function to check if the image is valid and is a multi-frame image that can be treated as such
    def is_valid_multi_frame_image(self, pathToImg) -> bool:
        try:
            with Image.open(pathToImg) as img:
                if getattr(img, "n_frames", 1) == 1:                    # Check if the image is not animated or multiframe (e.g., GIF)
                    return False                                        # static images are managed in a different class, so we return False here
                img.verify()                                            # Verify that it is, in fact an image
            return True
        except (UnidentifiedImageError, FileNotFoundError, OSError):
            return False
        
                                                                        # function to compute the SHA256 hash of the image's pixel data for all frames including their size and duration
                                                                        # ATTENTION: when you call this function, make sure to check if the image is valid first with is_valid_multi_frame_image()
                                                                        # I don't check it every time for performance reasons.
    def image_to_sha256(self, pathToImg) -> str:
        with Image.open(pathToImg) as img:
            digest = hashlib.sha256()
            for frame_index in range(img.n_frames):
                img.seek(frame_index)

                duration = img.info.get("duration")
                encoded_duration = -1 if duration is None else duration

                frame = img.convert("RGBA")                              # Normalize to RGBA
                width, height = frame.size
                pixel_data = frame.tobytes()                             # Get raw pixel data
                digest.update(pixel_data)
                digest.update(width.to_bytes(8, 'big'))                  # Update with width
                digest.update(height.to_bytes(8, 'big'))                 # Update with height
                digest.update(encoded_duration.to_bytes(8, 'big', signed=True))  # Update with frame duration

            return digest.hexdigest()                                    # Return the SHA256 hash


                                                                         # function to compare two images by their SHA256 hash of pixel data
    def compare_two_images(self, pathToImg1, pathToImg2) -> bool:
        with Image.open(pathToImg1) as img1, Image.open(pathToImg2) as img2:
            if img1.n_frames != img2.n_frames or img1.info.get("loop") != img2.info.get("loop"):
                return False                                             # Different number of frames or loops, so they are not equal

        hash1 = self.image_to_sha256(pathToImg1)
        hash2 = self.image_to_sha256(pathToImg2)
        return hash1 == hash2

                                                                        # function to compare an image with a list of images.
                                                                        # Return two lists: one with equal images and one with disequal images
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