import json
import os
import re
import uuid
import base64
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlsplit
from urllib.request import Request, urlopen

from botocore.config import Config
from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    ConnectTimeoutError,
    EndpointConnectionError,
    InvalidRegionError,
    NoCredentialsError,
    PartialCredentialsError,
    ReadTimeoutError,
)
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[2]
load_dotenv(dotenv_path=BACKEND_DIR / ".env")

UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

AWS_S3_BUCKET = os.getenv("AWS_S3_BUCKET", "").strip()
AWS_REGION = os.getenv("AWS_REGION", "").strip()
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "").strip()
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "").strip()
AWS_SESSION_TOKEN = os.getenv("AWS_SESSION_TOKEN", "").strip()


class StorageConfigurationError(RuntimeError):
    pass


configured_backend = os.getenv("STORAGE_BACKEND", "").strip().lower()
STORAGE_BACKEND = configured_backend or "s3"
if STORAGE_BACKEND not in {"local", "s3", "github"}:
    raise StorageConfigurationError(
        "Unsupported STORAGE_BACKEND in backend/.env. Use one of: local, s3, github."
    )
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
GITHUB_REPO = os.getenv("GITHUB_REPO", "").strip()
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main").strip() or "main"
GITHUB_DATA_PATH = os.getenv("GITHUB_DATA_PATH", "cloudvault-data").strip().strip("/")
MAX_FILE_SIZE = 100 * 1024 * 1024

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_CONTENT_TYPE = re.compile(r"^[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+$")
_S3_KEY_PREFIX = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}-(.+)$")


def using_s3() -> bool:
    return STORAGE_BACKEND == "s3"


def using_github() -> bool:
    return STORAGE_BACKEND == "github"


def backend_label() -> str:
    if using_github():
        return "Private GitHub repository"
    return "Amazon S3" if using_s3() else "Local server"


def _status_response(
    provider: str,
    backend: str,
    configured: bool,
    connected: bool,
    message: str,
) -> dict:
    return {
        "storage": provider if connected else f"{provider} unavailable",
        "storage_backend": backend,
        "storage_provider": provider,
        "configured": configured,
        "reachable": connected,
        "connected": connected,
        "detail": message,
        "message": message,
    }


def _s3_configuration_error() -> str | None:
    missing = [
        name
        for name, value in (("AWS_REGION", AWS_REGION), ("AWS_S3_BUCKET", AWS_S3_BUCKET))
        if not value
    ]
    if missing:
        return (
            f"Missing {', '.join(missing)} in backend/.env. Configure the S3 region and "
            "bucket name before using cloud storage."
        )
    if bool(AWS_ACCESS_KEY_ID) != bool(AWS_SECRET_ACCESS_KEY):
        return (
            "Set both AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY, or remove both and "
            "configure an AWS SDK credential provider such as an AWS profile or IAM role."
        )
    return None


def _s3_status_error(error: Exception) -> str:
    if isinstance(error, StorageConfigurationError):
        return str(error)
    if isinstance(error, (NoCredentialsError, PartialCredentialsError)):
        return (
            "AWS credentials are unavailable or incomplete. Configure both access key "
            "variables in backend/.env, or use an AWS profile or IAM role."
        )
    if isinstance(error, ClientError):
        code = error.response.get("Error", {}).get("Code", "")
        status_code = error.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if code in {
            "InvalidAccessKeyId",
            "SignatureDoesNotMatch",
            "ExpiredToken",
            "InvalidToken",
            "UnrecognizedClientException",
        }:
            return "AWS rejected the configured credentials. Check the IAM user credentials."
        if code in {"NoSuchBucket", "404"}:
            return "The configured S3 bucket does not exist or is not accessible."
        if code in {"InvalidBucketName", "InvalidBucketState"}:
            return "The configured S3 bucket name is invalid."
        if code in {
            "PermanentRedirect",
            "AuthorizationHeaderMalformed",
            "IncorrectEndpoint",
            "IllegalLocationConstraintException",
        }:
            return "The configured AWS_REGION does not match the S3 bucket's region."
        if code in {"AccessDenied", "403"} or status_code == 403:
            return (
                "AWS denied the bucket check. Verify the bucket name and region, and grant "
                "the IAM identity s3:ListBucket access to this bucket."
            )
        return "Amazon S3 returned an error while checking the configured bucket."
    if isinstance(error, InvalidRegionError):
        return "AWS_REGION is not a valid AWS region. Use the region where the S3 bucket was created."
    if isinstance(
        error,
        (
            EndpointConnectionError,
            ConnectTimeoutError,
            ReadTimeoutError,
            URLError,
            TimeoutError,
        ),
    ):
        return "Amazon S3 could not be reached. Check the network connection and AWS region."
    if isinstance(error, BotoCoreError):
        return "The AWS SDK could not complete the S3 bucket check."
    return "Amazon S3 storage is unavailable."


def storage_status() -> dict:
    """Return safe storage diagnostics without exposing credentials."""
    if using_s3():
        configuration_error = _s3_configuration_error()
        if configuration_error:
            return _status_response("Amazon S3", "s3", False, False, configuration_error)
        try:
            _s3_client().head_bucket(Bucket=AWS_S3_BUCKET)
            return _status_response(
                "Amazon S3",
                "s3",
                True,
                True,
                "Files are stored securely in your configured AWS S3 bucket.",
            )
        except (
            BotoCoreError,
            ClientError,
            OSError,
            StorageConfigurationError,
            ImportError,
        ) as error:
            return _status_response("Amazon S3", "s3", True, False, _s3_status_error(error))
    if using_github():
        missing = [
            name
            for name, value in (("GITHUB_REPO", GITHUB_REPO), ("GITHUB_TOKEN", GITHUB_TOKEN))
            if not value
        ]
        if missing:
            return _status_response(
                "Private GitHub repository",
                "github",
                False,
                False,
                f"Missing {', '.join(missing)} in backend/.env.",
            )
        try:
            _github_request("GET", "")
            return _status_response(
                "Private GitHub repository",
                "github",
                True,
                True,
                "The configured private GitHub repository is reachable.",
            )
        except HTTPError as error:
            if error.code == 401:
                message = "GitHub rejected the configured token. Check its validity."
            elif error.code == 403:
                message = "The GitHub token lacks permission to access this repository."
            elif error.code == 404:
                message = "The repository was not found or the token cannot access it."
            else:
                message = "GitHub returned an error while checking the repository."
            return _status_response("Private GitHub repository", "github", True, False, message)
        except (URLError, TimeoutError, OSError):
            return _status_response(
                "Private GitHub repository",
                "github",
                True,
                False,
                "The GitHub API could not be reached. Check the network connection.",
            )
    return _status_response(
        "Local server",
        "local",
        True,
        True,
        "Files are stored on this CloudVault backend because local storage was explicitly selected.",
    )


def _github_request(method: str, path: str, payload: dict | None = None):
    if not using_github() or not GITHUB_TOKEN or not GITHUB_REPO:
        raise StorageConfigurationError("GitHub storage is not configured.")
    repository = _github_repository_slug()
    content_path = f"/{quote(path, safe='/')}" if path else ""
    url = f"https://api.github.com/repos/{repository}/contents{content_path}"
    headers = {"Accept": "application/vnd.github+json", "Authorization": f"Bearer {GITHUB_TOKEN}", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "CloudVault"}
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(url, data=body, headers=headers, method=method)
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _github_repository_slug() -> str:
    value = GITHUB_REPO.strip()
    if "://" in value:
        parsed = urlsplit(value)
        if parsed.scheme != "https" or parsed.hostname != "github.com":
            raise StorageConfigurationError("GITHUB_REPO must identify a GitHub repository.")
        value = parsed.path.strip("/")
    value = value.removesuffix(".git")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value):
        raise StorageConfigurationError("GITHUB_REPO must be OWNER/REPOSITORY.")
    return value


def _github_path(file_id: str) -> str:
    if not file_id or ".." in file_id or "\\" in file_id or not file_id.startswith(f"{GITHUB_DATA_PATH}/"):
        raise ValueError("Invalid file identifier.")
    return file_id


def upload_to_github(file_object, filename: str, content_type: str | None) -> dict:
    del content_type
    safe_name = sanitize_filename(filename)
    key = f"{GITHUB_DATA_PATH}/{uuid.uuid4()}-{safe_name}"
    raw = file_object.read()
    _github_request("PUT", key, {"message": f"CloudVault upload: {safe_name}", "content": base64.b64encode(raw).decode("ascii"), "branch": GITHUB_BRANCH})
    return {"id": key, "name": safe_name, "size": len(raw), "uploaded_at": datetime.now(timezone.utc)}


def list_github_files() -> list[dict]:
    try:
        result = _github_request("GET", GITHUB_DATA_PATH)
    except HTTPError as error:
        if error.code == 404:
            return []
        raise
    entries = []
    for item in result if isinstance(result, list) else []:
        if item.get("type") != "file":
            continue
        key = item.get("path", "")
        _, _, name = key.rpartition("/")
        match = _S3_KEY_PREFIX.fullmatch(name)
        if not match:
            continue
        entries.append(
            {
                "id": key,
                "name": match.group(1),
                "size": item.get("size", 0),
                "uploaded_at": None,
            }
        )
    return entries


def github_file(file_id: str) -> dict:
    return _github_request("GET", _github_path(file_id))


def delete_github_file(file_id: str) -> None:
    item = github_file(file_id)
    _github_request("DELETE", _github_path(file_id), {"message": f"CloudVault delete: {file_id}", "sha": item["sha"], "branch": GITHUB_BRANCH})


def download_github_file(file_id: str) -> tuple[bytes, str]:
    item = github_file(file_id)
    request = Request(item["download_url"], headers={"Authorization": f"Bearer {GITHUB_TOKEN}", "User-Agent": "CloudVault"})
    with urlopen(request, timeout=30) as response:
        return response.read(), item.get("name", "download")


def _s3_client():
    if not using_s3():
        raise StorageConfigurationError("S3 storage is not selected.")
    configuration_error = _s3_configuration_error()
    if configuration_error:
        raise StorageConfigurationError(configuration_error)
    try:
        import boto3
    except ImportError as error:
        raise StorageConfigurationError("S3 mode requires boto3. Install backend requirements first.") from error
    credentials = {}
    if AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY:
        credentials = {
            "aws_access_key_id": AWS_ACCESS_KEY_ID,
            "aws_secret_access_key": AWS_SECRET_ACCESS_KEY,
        }
        if AWS_SESSION_TOKEN:
            credentials["aws_session_token"] = AWS_SESSION_TOKEN
    return boto3.client(
        "s3",
        region_name=AWS_REGION,
        config=Config(
            connect_timeout=3,
            read_timeout=5,
            retries={"max_attempts": 2, "mode": "standard"},
        ),
        **credentials,
    )


def _s3_key(filename: str) -> str:
    return f"{uuid.uuid4()}-{filename}"


def upload_to_s3(file_object, filename: str, content_type: str | None) -> dict:
    safe_name = sanitize_filename(filename)
    key = _s3_key(safe_name)
    start_position = file_object.tell()
    file_object.seek(0, 2)
    size = file_object.tell() - start_position
    file_object.seek(start_position)
    if size == 0:
        raise ValueError("Empty files cannot be uploaded.")
    _s3_client().upload_fileobj(
        file_object,
        AWS_S3_BUCKET,
        key,
        ExtraArgs={
            "ContentType": content_type or "application/octet-stream",
            "Metadata": {
                "original-filename": quote(safe_name, safe=""),
                "cloudvault-size": str(size),
            },
        },
    )
    return {
        "id": key,
        "name": safe_name,
        "size": size,
        "content_type": content_type or "application/octet-stream",
        "uploaded_at": datetime.now(timezone.utc),
    }


def presign_s3_upload(
    filename: str,
    size: int,
    content_type: str,
) -> dict:
    if not using_s3():
        raise StorageConfigurationError("S3 storage is not selected.")
    if size < 1 or size > MAX_FILE_SIZE:
        raise ValueError("File size must be between 1 byte and 100 MiB.")
    if not _CONTENT_TYPE.fullmatch(content_type):
        raise ValueError("A valid file content type is required.")

    safe_name = sanitize_filename(filename)
    key = _s3_key(safe_name)
    headers = {
        "Content-Type": content_type,
        "x-amz-meta-original-filename": quote(safe_name, safe=""),
        "x-amz-meta-cloudvault-size": str(size),
    }
    upload_url = _s3_client().generate_presigned_url(
        "put_object",
        Params={
            "Bucket": AWS_S3_BUCKET,
            "Key": key,
            "ContentType": content_type,
            "Metadata": {
                "original-filename": headers["x-amz-meta-original-filename"],
                "cloudvault-size": str(size),
            },
        },
        ExpiresIn=300,
    )
    return {"id": key, "name": safe_name, "size": size, "upload_url": upload_url, "headers": headers}


def verify_s3_upload(file_id: str, expected_size: int) -> dict:
    key = _validate_s3_key(file_id)
    client = _s3_client()
    result = client.head_object(Bucket=AWS_S3_BUCKET, Key=key)
    actual_size = result.get("ContentLength", 0)
    metadata = result.get("Metadata", {})
    recorded_size = metadata.get("cloudvault-size")
    if (
        actual_size < 1
        or actual_size > MAX_FILE_SIZE
        or actual_size != expected_size
        or recorded_size != str(expected_size)
    ):
        client.delete_object(Bucket=AWS_S3_BUCKET, Key=key)
        raise ValueError("The uploaded file did not match the requested size or exceeded 100 MiB.")
    original_name = unquote(metadata.get("original-filename", ""))
    if not original_name:
        client.delete_object(Bucket=AWS_S3_BUCKET, Key=key)
        raise ValueError("The uploaded file is missing its original filename.")
    return {
        "id": key,
        "name": original_name,
        "size": actual_size,
        "content_type": result.get("ContentType", "application/octet-stream"),
        "uploaded_at": result.get("LastModified", datetime.now(timezone.utc)),
    }


def list_s3_files() -> list[dict]:
    client = _s3_client()
    paginator = client.get_paginator("list_objects_v2")
    entries = []
    for page in paginator.paginate(Bucket=AWS_S3_BUCKET):
        for item in page.get("Contents", []):
            key = item.get("Key")
            if not key:
                continue
            try:
                _validate_s3_key(key)
            except ValueError:
                continue
            metadata = client.head_object(Bucket=AWS_S3_BUCKET, Key=key)
            original_name = metadata.get("Metadata", {}).get("original-filename")
            recorded_size = metadata.get("Metadata", {}).get("cloudvault-size")
            if recorded_size is not None and recorded_size != str(item.get("Size", 0)):
                continue
            match = _S3_KEY_PREFIX.fullmatch(key)
            if not match:
                continue
            entries.append(
                {
                    "id": key,
                    "name": unquote(original_name) if original_name else match.group(1),
                    "size": item.get("Size", 0),
                    "content_type": metadata.get("ContentType", "application/octet-stream"),
                    "uploaded_at": item.get("LastModified"),
                }
            )
    return sorted(entries, key=lambda item: item["uploaded_at"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)


def _validate_s3_key(file_id: str) -> str:
    match = _S3_KEY_PREFIX.fullmatch(file_id)
    if not match:
        raise ValueError("Invalid file identifier.")
    try:
        if str(uuid.UUID(file_id[:36])) != file_id[:36]:
            raise ValueError("Invalid file identifier.")
    except ValueError as error:
        raise ValueError("Invalid file identifier.") from error
    if sanitize_filename(match.group(1)) != match.group(1):
        raise ValueError("Invalid file identifier.")
    return file_id


def delete_s3_file(file_id: str) -> None:
    _s3_client().delete_object(Bucket=AWS_S3_BUCKET, Key=_validate_s3_key(file_id))


def download_s3_file(file_id: str) -> dict:
    return _s3_client().get_object(Bucket=AWS_S3_BUCKET, Key=_validate_s3_key(file_id))


def s3_download_url(file_id: str) -> str:
    file_id = _validate_s3_key(file_id)
    client = _s3_client()
    metadata = client.head_object(Bucket=AWS_S3_BUCKET, Key=file_id)
    original_name = unquote(
        metadata.get("Metadata", {}).get("original-filename", file_id[37:])
    )
    disposition = f"attachment; filename*=UTF-8''{quote(original_name, safe='')}"
    return _s3_client().generate_presigned_url(
        "get_object",
        Params={
            "Bucket": AWS_S3_BUCKET,
            "Key": file_id,
            "ResponseContentDisposition": disposition,
        },
        ExpiresIn=300,
    )


def sanitize_filename(filename: str) -> str:
    name = filename.replace("\\", "/").split("/")[-1]
    name = _CONTROL_CHARS.sub("", name)
    if not name or name in {".", ".."}:
        raise ValueError("A valid filename is required.")
    return name[:255]


def create_temporary_path() -> Path:
    return UPLOAD_DIR / f".{uuid.uuid4()}.part"


def commit_upload(temporary_path: Path, filename: str) -> tuple[str, Path]:
    original_name = sanitize_filename(filename)
    file_id = str(uuid.uuid4())
    destination = UPLOAD_DIR / f"{file_id}.data"
    metadata_path = UPLOAD_DIR / f"{file_id}.json"
    temporary_metadata_path = UPLOAD_DIR / f".{file_id}.json.part"
    temporary_path.replace(destination)
    try:
        with temporary_metadata_path.open("x", encoding="utf-8") as metadata_file:
            json.dump({"name": original_name}, metadata_file)
        temporary_metadata_path.replace(metadata_path)
    except OSError:
        destination.unlink(missing_ok=True)
        temporary_metadata_path.unlink(missing_ok=True)
        raise
    return file_id, destination


def _file_id(path: Path) -> str | None:
    candidate, separator, _ = path.name.partition("__")
    if not separator:
        return None
    try:
        return str(uuid.UUID(candidate))
    except ValueError:
        return None


def list_files() -> list[dict]:
    if using_github():
        return list_github_files()
    if using_s3():
        return list_s3_files()
    entries = []
    for path in UPLOAD_DIR.iterdir():
        if path.suffix == ".json" and not path.name.startswith("."):
            try:
                file_id = str(uuid.UUID(path.stem))
            except ValueError:
                continue
            data_path = UPLOAD_DIR / f"{file_id}.data"
            if not data_path.is_file():
                continue
            try:
                metadata = json.loads(path.read_text(encoding="utf-8"))
                filename = metadata["name"]
                if not isinstance(filename, str):
                    raise ValueError("Stored filename metadata is invalid.")
            except (OSError, json.JSONDecodeError, KeyError) as error:
                raise RuntimeError(f"Could not read metadata for stored file {file_id}.") from error
            stat = data_path.stat()
            entries.append(
                {
                    "id": file_id,
                    "name": filename,
                    "size": stat.st_size,
                    "uploaded_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc),
                }
            )
            continue

        file_id = _file_id(path)
        if file_id is not None and path.is_file():
            stat = path.stat()
            entries.append(
                {
                    "id": file_id,
                    "name": path.name.partition("__")[2],
                    "size": stat.st_size,
                    "uploaded_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc),
                }
            )
    return sorted(entries, key=lambda item: item["uploaded_at"], reverse=True)


def find_file(file_id: str) -> Path | None:
    try:
        canonical_id = str(uuid.UUID(file_id))
    except ValueError:
        return None
    data_path = UPLOAD_DIR / f"{canonical_id}.data"
    if data_path.is_file():
        return data_path
    matches = UPLOAD_DIR.glob(f"{canonical_id}__*")
    return next((path for path in matches if path.is_file()), None)


def get_original_filename(path: Path) -> str:
    if path.suffix == ".data":
        metadata_path = path.with_suffix(".json")
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            filename = metadata["name"]
            if isinstance(filename, str):
                return filename
        except (OSError, json.JSONDecodeError, KeyError):
            pass
        raise RuntimeError(f"Could not read filename metadata for stored file {path.stem}.")
    return path.name.partition("__")[2]


def remove_file(path: Path) -> None:
    path.unlink()
    if path.suffix == ".data":
        path.with_suffix(".json").unlink(missing_ok=True)
