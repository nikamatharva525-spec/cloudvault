import unittest
import uuid
from unittest.mock import Mock, patch
from urllib.parse import quote

from app.services import storage


class StorageValidationTests(unittest.TestCase):
    def test_sanitize_filename_removes_path_components(self):
        self.assertEqual(storage.sanitize_filename(r"..\folder\report.txt"), "report.txt")

    def test_sanitize_filename_rejects_empty_names(self):
        with self.assertRaises(ValueError):
            storage.sanitize_filename("../")

    def test_github_repo_url_is_normalized_to_a_repository_slug(self):
        with patch.object(storage, "GITHUB_REPO", "https://github.com/example/cloudvault.git"):
            self.assertEqual(storage._github_repository_slug(), "example/cloudvault")

    def test_github_repo_rejects_non_github_hosts(self):
        with patch.object(storage, "GITHUB_REPO", "https://example.com/owner/repo"):
            with self.assertRaises(storage.StorageConfigurationError):
                storage._github_repository_slug()


class S3PresignTests(unittest.TestCase):
    def test_presign_accepts_the_exact_100_mib_limit(self):
        client = Mock()
        client.generate_presigned_url.return_value = "https://s3.example/upload"
        with (
            patch.object(storage, "STORAGE_BACKEND", "s3"),
            patch.object(storage, "AWS_S3_BUCKET", "test-bucket"),
            patch.object(storage, "_s3_client", return_value=client),
        ):
            result = storage.presign_s3_upload(
                "test.bin",
                storage.MAX_FILE_SIZE,
                "application/octet-stream",
            )

        self.assertEqual(result["size"], 100 * 1024 * 1024)
        self.assertEqual(result["upload_url"], "https://s3.example/upload")
        self.assertEqual(result["headers"]["x-amz-meta-cloudvault-size"], str(storage.MAX_FILE_SIZE))
        client.generate_presigned_url.assert_called_once()

    def test_presign_rejects_oversized_and_empty_files(self):
        with patch.object(storage, "STORAGE_BACKEND", "s3"):
            for size in (0, storage.MAX_FILE_SIZE + 1):
                with self.subTest(size=size), self.assertRaises(ValueError):
                    storage.presign_s3_upload("test.bin", size, "application/octet-stream")

    def test_completed_upload_checks_the_stored_size(self):
        file_id = f"{uuid.uuid4()}-test.bin"
        client = Mock()
        client.head_object.return_value = {
            "ContentLength": 4,
            "Metadata": {
                "cloudvault-size": "4",
                "original-filename": quote("test.bin", safe=""),
            },
        }
        with (
            patch.object(storage, "STORAGE_BACKEND", "s3"),
            patch.object(storage, "AWS_S3_BUCKET", "test-bucket"),
            patch.object(storage, "_s3_client", return_value=client),
        ):
            result = storage.verify_s3_upload(file_id, 4)

        self.assertEqual(result["name"], "test.bin")
        self.assertEqual(result["size"], 4)
        client.delete_object.assert_not_called()

    def test_completed_upload_deletes_objects_that_exceed_the_limit(self):
        file_id = f"{uuid.uuid4()}-test.bin"
        client = Mock()
        client.head_object.return_value = {
            "ContentLength": storage.MAX_FILE_SIZE + 1,
            "Metadata": {
                "cloudvault-size": str(storage.MAX_FILE_SIZE),
                "original-filename": quote("test.bin", safe=""),
            },
        }
        with (
            patch.object(storage, "STORAGE_BACKEND", "s3"),
            patch.object(storage, "AWS_S3_BUCKET", "test-bucket"),
            patch.object(storage, "_s3_client", return_value=client),
        ):
            with self.assertRaises(ValueError):
                storage.verify_s3_upload(file_id, storage.MAX_FILE_SIZE)

        client.delete_object.assert_called_once_with(Bucket="test-bucket", Key=file_id)


if __name__ == "__main__":
    unittest.main()
