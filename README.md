<<<<<<< HEAD
# CloudVault

CloudVault is a college mini project demonstrating a cloud-storage-style interface. The React dashboard talks to a FastAPI API. It supports local storage during development and Amazon S3 when configured.

> **Storage note:** Local storage is the default. S3 mode requires an activated AWS account, an existing bucket, and AWS credentials supplied through the AWS SDK credential chain. User accounts and sharing are not implemented.

## Features

- Responsive file dashboard with search, recent files, file counts, and storage usage
- Drag-and-drop and multi-file upload (up to 100 MB per file)
- Per-file upload progress, loading states, and success/error feedback
- File type icons, file sizes, and upload timestamps
- Download and delete actions
- Sharing is not included; the interface has no nonfunctional share controls
- FastAPI validation, generated storage IDs, CORS for local development, and API error messages

## Requirements

- Python 3.10+
- Node.js 18+
- npm

## Run locally

Open two terminals in the project root.

### Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

The API is available at `http://127.0.0.1:8000`; interactive API documentation is at `http://127.0.0.1:8000/docs`.

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

Open the local URL printed by Vite (normally `http://127.0.0.1:5173`). Vite proxies `/api` requests to the backend at `http://127.0.0.1:8000`.

## API

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/` | Check API status |
| `GET` | `/files` | List stored files |
| `POST` | `/upload` | Upload one multipart file |
| `GET` | `/download/{id}` | Download a file |
| `DELETE` | `/files/{id}` | Permanently delete a file |

The previous `/api/health` and `/api/files` routes remain available for compatibility.

Uploaded file content is excluded from Git by `.gitignore`. Upload timestamps are derived from the stored file's modification time because this version intentionally has no database.

## Use a private GitHub repository instead

If AWS is unavailable, set `STORAGE_BACKEND=github`, set `GITHUB_REPO` to a private repository, and provide a fine-grained `GITHUB_TOKEN` with Contents: Read and write permission for only that repository. Keep the token on the backend only. GitHub storage creates commits for uploads and is intended only for small, infrequently changing project files; object storage is better for large or frequently uploaded files.

## Enable Amazon S3 later

After the AWS account is activated and the bucket is created, install the updated backend dependencies and set:

```powershell
$env:STORAGE_BACKEND="s3"
$env:S3_BUCKET_NAME="your-unique-bucket-name"
$env:AWS_REGION="us-east-1"
```

Configure AWS credentials with the AWS CLI or another supported SDK credential source. Do not put access keys in the frontend or commit them to the project. Restart the backend after changing these values. The existing UI will then upload, list, download, and delete objects through S3.
=======
# cloudvault
Cloud-Based File Storage and Sharing System
>>>>>>> 29acd4d4c4f2a731fd52b23663391f75efcbad85
