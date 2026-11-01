from datetime import datetime, timezone

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, RedirectResponse, Response

from app.services import storage

router = APIRouter(tags=["files"])
MAX_FILE_SIZE = 100 * 1024 * 1024
CHUNK_SIZE = 1024 * 1024


@router.get("/files")
@router.get("/api/files", include_in_schema=False)
def get_files():
    return storage.list_files()


@router.post("/upload", status_code=status.HTTP_201_CREATED)
@router.post("/api/files", status_code=status.HTTP_201_CREATED, include_in_schema=False)
async def upload_file(file: UploadFile = File(...)):
    if not file.filename or not file.filename.strip():
        raise HTTPException(status_code=400, detail="A filename is required.")
    try:
        safe_name = storage.sanitize_filename(file.filename)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    temporary_path = storage.create_temporary_path()
    size = 0
    try:
        if storage.using_github():
            return storage.upload_to_github(file.file, safe_name, file.content_type)
        if storage.using_s3():
            result = storage.upload_to_s3(file.file, safe_name, file.content_type)
            return result
        with temporary_path.open("xb") as destination:
            while chunk := await file.read(CHUNK_SIZE):
                size += len(chunk)
                if size > MAX_FILE_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail="File is too large. Maximum upload size is 100 MB.",
                    )
                destination.write(chunk)
        if size == 0:
            raise HTTPException(status_code=400, detail="Empty files cannot be uploaded.")
        file_id, final_path = storage.commit_upload(temporary_path, safe_name)
    except HTTPException:
        temporary_path.unlink(missing_ok=True)
        raise
    except OSError as error:
        temporary_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="Could not save the uploaded file.") from error
    finally:
        await file.close()

    stat = final_path.stat()
    return {
        "id": file_id,
        "name": safe_name,
        "size": stat.st_size,
        "uploaded_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc),
    }


@router.get("/download/{file_id}")
@router.get("/api/files/{file_id}/download", include_in_schema=False)
def download_file(file_id: str):
    if storage.using_github():
        try:
            content, filename = storage.download_github_file(file_id)
            return Response(content, media_type="application/octet-stream", headers={"Content-Disposition": f'attachment; filename="{filename}"'})
        except Exception as error:
            raise HTTPException(status_code=404, detail="File not found.") from error
    if storage.using_s3():
        try:
            return RedirectResponse(storage.s3_download_url(file_id), status_code=307)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except Exception as error:
            raise HTTPException(status_code=404, detail="File not found.") from error
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
        return None
    if storage.using_s3():
        try:
            storage.delete_s3_file(file_id)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return None
    path = storage.find_file(file_id)
    if path is None:
        raise HTTPException(status_code=404, detail="File not found.")
    try:
        storage.remove_file(path)
    except OSError as error:
        raise HTTPException(status_code=500, detail="Could not delete the file.") from error
    return None
