import asyncio
import tempfile
import unittest

from fastapi import HTTPException
from starlette.datastructures import UploadFile

from app.routes.files import upload_file
from app.services import storage


class UploadRouteTests(unittest.TestCase):
    def test_api_rejects_files_over_100_mib(self):
        uploaded_file = tempfile.TemporaryFile()
        uploaded_file.truncate(storage.MAX_FILE_SIZE + 1)
        uploaded_file.seek(0)
        upload = UploadFile(file=uploaded_file, filename="too-large.bin")

        with self.assertRaises(HTTPException) as raised:
            asyncio.run(upload_file(upload))

        self.assertEqual(raised.exception.status_code, 413)


if __name__ == "__main__":
    unittest.main()
