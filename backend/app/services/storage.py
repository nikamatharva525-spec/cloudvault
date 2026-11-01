import json
import os
import re
import uuid
import base64
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "local").lower()
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "").strip()
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
GITHUB_REPO = os.getenv("GITHUB_REPO", "").strip()
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main").strip() or "main"
GITHUB_DATA_PATH = os.getenv("GITHUB_DATA_PATH", "cloudvault-data").strip().strip("/")

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def using_s3() -> bool:
    return STORAGE_BACKEND == "s3" and bool(S3_BUCKET_NAME)


def using_github() -> bool:
    return STORAGE_BACKEND == "github" and bool(GITHUB_TOKEN and GITHUB_REPO)


def backend_label() -> str:
    if using_github():
        return "Private GitHub repository"
    return "Amazon S3" if using_s3() else "Local server"


def _github_request(method: str, path: str, payload: dict | None = None):
    if not using_github():
        raise RuntimeError("GitHub storage is not configured.")
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{quote(path, safe='/')}"
    headers = {"Accept": "application/vnd.github+json", "Authorization": f"Bearer {GITHUB_TOKEN}", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "CloudVault"}
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(url, data=body, headers=headers, method=method)
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


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
        entries.append({"id": key, "name": name.split("-", 1)[-1], "size": item.get("size", 0), "uploaded_at": None})
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
        raise RuntimeError("S3 storage is not configured.")
    try:
        import boto3
    except ImportError as error:
        raise RuntimeError("S3 mode requires boto3. Install backend requirements first.") from error
    return boto3.client("s3", region_name=AWS_REGION)


def _s3_key(filename: str) -> str:
    return f"{uuid.uuid4()}-{filename}"


def upload_to_s3(file_object, filename: str, content_type: str | None) -> dict:
    safe_name = sanitize_filename(filename)
    key = _s3_key(safe_name)
    _s3_client().upload_fileobj(
        file_object,
        S3_BUCKET_NAME,
        key,
        ExtraArgs={"ContentType": content_type or "application/octet-stream"},
    )
    return {"id": key, "name": safe_name, "size": None, "uploaded_at": datetime.now(timezone.utc)}


def list_s3_files() -> list[dict]:
    result = _s3_client().list_objects_v2(Bucket=S3_BUCKET_NAME, MaxKeys=1000)
    entries = []
    for item in result.get("Contents", []):
        key = item.get("Key")
        if not key:
            continue
        _, _, name = key.partition("-")
        entries.append(
            {
                "id": key,
                "name": name or key,
                "size": item.get("Size", 0),
                "uploaded_at": item.get("LastModified"),
            }
        )
    return sorted(entries, key=lambda item: item["uploaded_at"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)


def delete_s3_file(file_id: str) -> None:
    if not file_id or "/" in file_id or "\\" in file_id or ".." in file_id:
        raise ValueError("Invalid file identifier.")
    _s3_client().delete_object(Bucket=S3_BUCKET_NAME, Key=file_id)


def s3_download_url(file_id: str) -> str:
    if not file_id or "/" in file_id or "\\" in file_id or ".." in file_id:
        raise ValueError("Invalid file identifier.")
    return _s3_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": S3_BUCKET_NAME, "Key": file_id},
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
