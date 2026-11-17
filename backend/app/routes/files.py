from datetime import datetime, timezone
from urllib.parse import quote, unquote
from urllib.error import HTTPError, URLError

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
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from fastapi.responses import FileResponse, Response, StreamingResponse

from app.services import storage
from app.security import require_authenticated

router = APIRouter(tags=["files"], dependencies=[Depends(require_authenticated)])
CHUNK_SIZE = 1024 * 1024


class PresignUploadRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=1024)
    size: int = Field(gt=0, le=storage.MAX_FILE_SIZE)
    content_type: str = Field(default="application/octet-stream", max_length=255)


class CompleteUploadRequest(BaseModel):
    size: int = Field(gt=0, le=storage.MAX_FILE_SIZE)


def _storage_http_error(error: Exception) -> HTTPException:
    if isinstance(error, storage.StorageConfigurationError):
        return HTTPException(status_code=503, detail=str(error))
    if isinstance(error, (NoCredentialsError, PartialCredentialsError)):
        return HTTPException(
            status_code=503,
            detail="AWS credentials are unavailable. Configure credentials in backend/.env or use an AWS profile or IAM role.",
        )
    if isinstance(error, (EndpointConnectionError, ConnectTimeoutError, ReadTimeoutError)):
        return HTTPException(status_code=503, detail="Amazon S3 could not be reached. Check the network and AWS region.")
    if isinstance(error, InvalidRegionError):
        return HTTPException(
            status_code=502,
            detail="AWS_REGION is not valid. Use the region where the S3 bucket was created.",
        )
    if isinstance(error, ClientError):
        code = error.response.get("Error", {}).get("Code", "")
        if code in {"NoSuchKey", "NotFound", "404"}:
            return HTTPException(status_code=404, detail="File not found.")
        if code in {"InvalidAccessKeyId", "SignatureDoesNotMatch", "ExpiredToken", "InvalidToken"}:
            return HTTPException(status_code=503, detail="AWS rejected the configured credentials.")
        if code in {"AccessDenied", "403"}:
            return HTTPException(
                status_code=403,
                detail="AWS denied this operation. Verify the IAM permissions for the configured S3 bucket.",
            )
        if code in {"NoSuchBucket"}:
            return HTTPException(status_code=502, detail="The configured S3 bucket does not exist.")
        if code in {"InvalidBucketName", "InvalidBucketState"}:
            return HTTPException(status_code=400, detail="The configured S3 bucket name is invalid.")
        if code in {"PermanentRedirect", "AuthorizationHeaderMalformed", "IncorrectEndpoint"}:
            return HTTPException(status_code=502, detail="AWS_REGION does not match the configured S3 bucket.")
        return HTTPException(
            status_code=502,
            detail="Amazon S3 returned an error while processing the request.",
        )
    if isinstance(error, BotoCoreError):
        return HTTPException(status_code=502, detail="Amazon S3 request failed.")
    return HTTPException(status_code=500, detail="Storage operation failed.")


def _github_http_error(error: Exception) -> HTTPException:
    if isinstance(error, HTTPError):
        if error.code == 401:
            return HTTPException(status_code=503, detail="GitHub rejected the configured token.")
        if error.code == 403:
            return HTTPException(status_code=403, detail="GitHub denied this storage operation.")
        if error.code == 404:
            return HTTPException(status_code=404, detail="File not found.")
        return HTTPException(status_code=502, detail="GitHub returned a storage error.")
    if isinstance(error, (URLError, TimeoutError, OSError)):
        return HTTPException(status_code=503, detail="GitHub storage could not be reached.")
    return HTTPException(status_code=500, detail="Storage operation failed.")


@router.get("/files")
@router.get("/api/files", include_in_schema=False)
def get_files():
    try:
        return storage.list_files()
    except (HTTPError, URLError, TimeoutError) as error:
        raise _github_http_error(error) from error
    except (BotoCoreError, OSError, storage.StorageConfigurationError) as error:
        raise _storage_http_error(error) from error


@router.post("/api/uploads/presign")
def presign_upload(payload: PresignUploadRequest):
    if not storage.using_s3():
        raise HTTPException(status_code=400, detail="Direct uploads are available only with S3 storage.")
    try:
        safe_name = storage.sanitize_filename(payload.filename)
        return storage.presign_s3_upload(
            safe_name,
            payload.size,
            payload.content_type,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except (BotoCoreError, OSError, storage.StorageConfigurationError) as error:
        raise _storage_http_error(error) from error


@router.post("/api/uploads/{file_id}/complete")
def complete_upload(file_id: str, payload: CompleteUploadRequest):
    if not storage.using_s3():
        raise HTTPException(status_code=400, detail="Direct uploads are available only with S3 storage.")
    try:
        return storage.verify_s3_upload(file_id, payload.size)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except (BotoCoreError, OSError, storage.StorageConfigurationError) as error:
        raise _storage_http_error(error) from error


@router.post("/upload", status_code=status.HTTP_201_CREATED)
@router.post("/api/files", status_code=status.HTTP_201_CREATED, include_in_schema=False)
async def upload_file(file: UploadFile = File(...)):
    if not file.filename or not file.filename.strip():
        raise HTTPException(status_code=400, detail="A filename is required.")
    try:
        safe_name = storage.sanitize_filename(file.filename)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    try:
        file.file.seek(0, 2)
        size = file.file.tell()
        file.file.seek(0)
    except (OSError, ValueError) as error:
        await file.close()
        raise HTTPException(status_code=400, detail="Could not read the uploaded file.") from error
    if size == 0:
        await file.close()
        raise HTTPException(status_code=400, detail="Empty files cannot be uploaded.")
    if size > storage.MAX_FILE_SIZE:
        await file.close()
        raise HTTPException(
            status_code=413,
            detail="File is too large. Maximum upload size is 100 MiB.",
        )

    temporary_path = None
    size = 0
    try:
        if storage.using_s3():
            result = storage.upload_to_s3(file.file, safe_name, file.content_type)
            return result
        if storage.using_github():
            return storage.upload_to_github(file.file, safe_name, file.content_type)
        temporary_path = storage.create_temporary_path()
        with temporary_path.open("xb") as destination:
            while chunk := await file.read(CHUNK_SIZE):
                size += len(chunk)
                if size > storage.MAX_FILE_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail="File is too large. Maximum upload size is 100 MiB.",
                    )
                destination.write(chunk)
        if size == 0:
            raise HTTPException(status_code=400, detail="Empty files cannot be uploaded.")
        file_id, final_path = storage.commit_upload(temporary_path, safe_name)
    except HTTPException:
        if temporary_path:
            temporary_path.unlink(missing_ok=True)
        raise
    except ValueError as error:
        if temporary_path:
            temporary_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(error)) from error
    except (BotoCoreError, OSError, storage.StorageConfigurationError) as error:
        if temporary_path:
            temporary_path.unlink(missing_ok=True)
        raise _storage_http_error(error) from error
    finally:
        await file.close()

    stat = final_path.stat()
    return {
        "id": file_id,
        "name": safe_name,
        "size": stat.st_size,
        "uploaded_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc),
    }


@router.get("/api/files/{file_id}/download-url")
def download_url(file_id: str):
    if not storage.using_s3():
        raise HTTPException(status_code=400, detail="Direct downloads are available only with S3 storage.")
    try:
        return {"url": storage.s3_download_url(file_id)}
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except (BotoCoreError, OSError, storage.StorageConfigurationError) as error:
        raise _storage_http_error(error) from error


@router.get("/download/{file_id}")
@router.get("/api/files/{file_id}/download", include_in_schema=False)
def download_file(file_id: str):
    if storage.using_github():
        try:
            content, filename = storage.download_github_file(file_id)
            return Response(
                content,
                media_type="application/octet-stream",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            raise _github_http_error(error) from error
    if storage.using_s3():
        try:
            result = storage.download_s3_file(file_id)
            body = result["Body"]
            metadata = result.get("Metadata", {})
            filename = unquote(metadata.get("original-filename", file_id[37:]))

            def stream_s3_body():
                try:
                    yield from body.iter_chunks(chunk_size=CHUNK_SIZE)
                finally:
                    body.close()

            return StreamingResponse(
                stream_s3_body(),
                media_type=result.get("ContentType", "application/octet-stream"),
                headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except storage.StorageConfigurationError as error:
            raise _storage_http_error(error) from error
        except (BotoCoreError, OSError) as error:
            raise _storage_http_error(error) from error
    path = storage.find_file(file_id)
    if path is None:
        raise HTTPException(status_code=404, detail="File not found.")
    return FileResponse(path, filename=storage.get_original_filename(path))


@router.delete("/files/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
@router.delete("/api/files/{file_id}", status_code=status.HTTP_204_NO_CONTENT, include_in_schema=False)
def delete_file(file_id: str):
    if storage.using_github():
        try:
            storage.delete_github_file(file_id)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            raise _github_http_error(error) from error
        return None
    if storage.using_s3():
        try:
            storage.delete_s3_file(file_id)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except (BotoCoreError, storage.StorageConfigurationError, OSError) as error:
            raise _storage_http_error(error) from error
        return None
    path = storage.find_file(file_id)
    if path is None:
        raise HTTPException(status_code=404, detail="File not found.")
    try:
        storage.remove_file(path)
    except OSError as error:
        raise HTTPException(status_code=500, detail="Could not delete the file.") from error
    return None
