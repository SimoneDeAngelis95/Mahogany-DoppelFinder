import hashlib
import os
from PIL import Image, ImageSequence, UnidentifiedImageError

"""
Content-based comparison for images.
Images are decoded with Pillow and fingerprinted from normalized pixel data.
Container metadata and file format therefore do not affect the result.
Compare images by the SHA256 fingerprint of their decoded pixels.
"""

class ImageComparer:
    _NORMALIZED_MODE = "RGBA"                                                           # Converts every image to the same color format, including transparency, so equivalent RGB, RGBA, grayscale and palette images can be compared.

    def image_sha256(self, image_path):
        """Return the SHA256 fingerprint of an image's normalized pixels.

        Every frame is included, so animated and multi-page images are compared
        by their complete visual content. File format and metadata are ignored.
        """
        normalized_path = self._normalize_path(image_path)
        self._validate_image_path(normalized_path)

        digest = hashlib.sha256()

        try:
            with Image.open(normalized_path) as image:
                frame_count = 0
                for frame in ImageSequence.Iterator(image):
                    normalized_frame = frame.convert(self._NORMALIZED_MODE)
                    try:
                        width, height = normalized_frame.size
                        digest.update(frame_count.to_bytes(8, "big"))
                        digest.update(width.to_bytes(8, "big"))
                        digest.update(height.to_bytes(8, "big"))
                        digest.update(normalized_frame.tobytes())
                        frame_count += 1
                    finally:
                        normalized_frame.close()

                digest.update(frame_count.to_bytes(8, "big"))
        except (UnidentifiedImageError, OSError, ValueError) as error:
            raise ValueError(f"{normalized_path} is not a valid image.") from error

        return digest.hexdigest()

    def compare_images(self, image1, image2):
        """Return True when two images contain exactly the same pixels."""
        image1_path = self._normalize_path(image1)
        image2_path = self._normalize_path(image2)
        image1_hash = self.image_sha256(image1_path)
        if self._same_file(image1_path, image2_path):
            return True
        return image1_hash == self.image_sha256(image2_path)

    def compare_image_and_list(self, image1, image_list):
        """Split valid candidates into equal and different images.

        Invalid candidates are ignored, matching the behaviour of the original
        implementation. Returned paths are always absolute and normalized.
        """
        if not isinstance(image_list, list):
            raise TypeError("The argument must be a list.")

        source_path = self._normalize_path(image1)
        source_hash = self.image_sha256(source_path)
        equal_images = []
        disequal_images = []

        for candidate in image_list:
            try:
                candidate_path = self._normalize_path(candidate)
            except (TypeError, ValueError, OSError):
                continue

            if self._same_file(source_path, candidate_path):
                continue

            try:
                candidate_hash = self.image_sha256(candidate_path)
            except (FileNotFoundError, IsADirectoryError, ValueError, OSError):
                continue

            target = equal_images if candidate_hash == source_hash else disequal_images
            target.append(candidate_path)

        return source_path, equal_images, disequal_images

    def compare_image_and_folder(self, image1, folder_path, recursive=False):
        """Compare an image with every valid image found in a folder."""
        image_list = self._list_images_in_a_folder(folder_path, recursive)
        return self.compare_image_and_list(image1, image_list)

    def _validate_image_path(self, image_path):
        if not image_path:
            raise ValueError("Image path cannot be empty.")
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"{image_path} does not exist.")
        if not os.path.isfile(image_path):
            raise IsADirectoryError(f"{image_path} is not a file.")

    def _is_image(self, file_path):
        try:
            normalized_path = self._normalize_path(file_path)
            self._validate_image_path(normalized_path)
            with Image.open(normalized_path) as image:
                image.verify()
            return True
        except (TypeError, ValueError, UnidentifiedImageError, FileNotFoundError, OSError):
            return False

    def _check_list_of_images(self, image_list):
        if not isinstance(image_list, list):
            raise TypeError("The argument must be a list.")
        return [self._normalize_path(path) for path in image_list if self._is_image(path)]

    def _list_images_in_a_folder(self, folder_path, recursive=False):
        normalized_folder = self._normalize_path(folder_path)
        if not os.path.isdir(normalized_folder):
            raise NotADirectoryError(f"{normalized_folder} is not a directory.")

        image_list = []
        for root, directories, files in os.walk(normalized_folder):
            if not recursive:
                directories.clear()

            for filename in files:
                file_path = os.path.join(root, filename)
                if self._is_image(file_path):
                    image_list.append(self._normalize_path(file_path))

        return image_list

    @staticmethod
    def _same_file(path1, path2):
        try:
            return os.path.samefile(path1, path2)
        except (FileNotFoundError, OSError):
            return path1 == path2

    @staticmethod
    def _normalize_path(path):
        return os.path.abspath(os.fspath(path))



# ========================== TESTING ==========================

source_image = "test/test1.jpg"
source_image2 = "test/test3.jpg"

ImageComparer = ImageComparer()
# Compare two images
result = ImageComparer.compare_images(source_image, source_image2)
if result:
    print(f"{source_image} and {source_image2} are the same.")
else:
    print(f"{source_image} and {source_image2} are different.")

# Compare an image with a folder
folder_path = "test"
source_image = "test/test1.jpg"
source_path, equal_images, disequal_images = ImageComparer.compare_image_and_folder(source_image, folder_path, recursive=False)
print(f"Source image: {source_path}")
print("Equal images:")
for img in equal_images:
    print(f"  {img}")
print("Disequal images:")
for img in disequal_images:
    print(f"  {img}")