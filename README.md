# CloudVault

CloudVault is a React/Vite file dashboard backed by a FastAPI API. Amazon S3 is the recommended production store. Local disk and private GitHub storage are explicit development alternatives; local disk is not durable on Vercel.

## Features

- Responsive file dashboard with search, recent files, storage status, and upload progress
- Single-user password gate with signed, HttpOnly sessions
- Multi-file upload with a 100 MiB limit per file
- Authenticated file listing, download, and deletion
- S3 uploads and downloads use short-lived presigned URLs; AWS credentials stay on the backend

The password gate protects one shared vault. It does not provide user accounts, per-file ownership, or sharing.

## Requirements

- Python 3.10+
- Node.js 18+
- npm

## Run locally

Copy `backend/.env.example` to `backend/.env`, choose `STORAGE_BACKEND=local` for an offline test or `STORAGE_BACKEND=s3` for AWS, then set:

- `CLOUDVAULT_ACCESS_PASSWORD` to a password of at least 12 characters
- `CLOUDVAULT_SESSION_SECRET` to a randomly generated value of at least 32 bytes
- For S3, `AWS_REGION`, `AWS_S3_BUCKET`, and credentials from the AWS SDK credential chain

Keep `backend/.env` private; it is ignored by Git and excluded from Vercel uploads.

In the project root, generate a signing secret with `python -c "import secrets; print(secrets.token_urlsafe(32))"` and copy it into the local environment file. Do not use the generated example value as an application password.

### Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

The API is available at `http://127.0.0.1:8000`. Health is public at `/api/health`; file and storage endpoints require signing in.

### Frontend

```powershell
cd frontend
npm ci
npm run dev
```

Open the Vite URL (normally `http://127.0.0.1:5173`). Vite proxies `/api` requests to the backend. The API allows credentialed CORS only for the local Vite origins by default. When frontend and backend are on different production origins, set `CORS_ALLOWED_ORIGINS` to a comma-separated list of exact approved origins; do not use `*`.

## API

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Public liveness check |
| `GET` | `/api/auth/status` | Check whether the session is signed in |
| `POST` | `/api/auth/login` | Exchange the password for an HttpOnly session cookie |
| `POST` | `/api/auth/logout` | Clear the session cookie |
| `GET` | `/api/storage/status` | Authenticated storage diagnostics |
| `GET` | `/api/files` | List stored files (authenticated) |
| `POST` | `/api/files` | Upload through the API in local/GitHub mode (authenticated) |
| `POST` | `/api/uploads/presign` | Create a short-lived S3 upload URL (authenticated) |
| `POST` | `/api/uploads/{id}/complete` | Verify an S3 upload's actual size (authenticated) |
| `GET` | `/api/files/{id}/download-url` | Create a short-lived S3 download URL (authenticated) |
| `GET` | `/api/files/{id}/download` | Download in local/GitHub mode (authenticated) |
| `DELETE` | `/api/files/{id}` | Permanently delete a file (authenticated) |

The API validates names and sizes. S3 upload completion checks the stored object's actual size and removes a mismatched or oversized object. The dashboard prevents empty files and files over 100 MiB before transfer.

## S3 setup

Use an existing private bucket and keep S3 Block Public Access enabled. CloudVault does not create buckets or change AWS resources. The backend needs:

- `s3:ListBucket` on the bucket
- `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject`, and `s3:AbortMultipartUpload` on its objects

S3-backed browser uploads need a bucket CORS rule for the exact frontend origin. Add this rule alongside any existing rules using the AWS console or your approved infrastructure workflow; replace the placeholder with the deployed HTTPS origin:

```json
[
  {
    "AllowedOrigins": ["https://your-approved-cloudvault-domain"],
    "AllowedMethods": ["PUT"],
    "AllowedHeaders": [
      "content-type",
      "x-amz-meta-original-filename",
      "x-amz-meta-cloudvault-size"
    ],
    "ExposeHeaders": ["ETag"],
    "MaxAgeSeconds": 300
  }
]
```

The API only signs uploads up to 100 MiB, and verifies the actual S3 object size before listing it. Downloads use a short-lived signed URL with attachment disposition. No AWS secret is sent to the browser.

For intentional local-disk development set `STORAGE_BACKEND=local`. GitHub mode is intended only for small, infrequently changed files: set `STORAGE_BACKEND=github`, `GITHUB_REPO` (`OWNER/REPOSITORY` or an HTTPS GitHub repository URL), and a backend-only fine-grained `GITHUB_TOKEN` with Contents read/write access to that private repository.

## Vercel deployment

The root `vercel.json` builds the Vite frontend and routes `/api/*` to a Python FastAPI function (`api/index.py`). The function is stateless; Vercel's request/response body limit is much smaller than 100 MiB, so file bytes go directly between the browser and S3. Do not proxy large upload/download bodies through the function. For a future workload needing persistent local files, long-running jobs, WebSockets, or continuous connections, host FastAPI on a persistent service such as Render, Fly.io, or AWS, and point the frontend to that API.

Before deploying, add these environment variables to the linked Vercel project through its dashboard or an approved secret-management workflow. Never copy `backend/.env` into the deployment archive or commit real values:

| Variable | Required | Notes |
| --- | --- | --- |
| `STORAGE_BACKEND` | Yes | Must be `s3` on Vercel |
| `AWS_S3_BUCKET` | Yes | Existing private bucket name |
| `AWS_REGION` | Yes | Region containing the bucket |
| `AWS_ACCESS_KEY_ID` | Yes, unless runtime credentials are available | Backend-only, least-privilege credential |
| `AWS_SECRET_ACCESS_KEY` | Yes, unless runtime credentials are available | Backend-only secret |
| `AWS_SESSION_TOKEN` | Optional | Required with temporary AWS credentials |
| `CLOUDVAULT_ACCESS_PASSWORD` | Yes | At least 12 characters; keep private |
| `CLOUDVAULT_ACCESS_EMAIL` | Yes | Email used with the access password; keep private |
| `CLOUDVAULT_SESSION_SECRET` | Yes | At least 32 random bytes; rotate to invalidate sessions |
| `CORS_ALLOWED_ORIGINS` | Only for a separate API origin | Exact frontend origins, comma-separated; never `*` |
| `VITE_API_BASE_URL` | No | Leave unset for the same-origin Vercel deployment |

Configure the S3 CORS rule above for the final Vercel domain before testing uploads. Then deploy from the repository root with the Vercel CLI (`vercel --prod`). Verify login, list, upload of a file at the 100 MiB boundary, download, and delete with a disposable test file before treating the deployment as production-ready. The Vercel Python function is suitable for the short API control requests; durable content remains in S3.

Registration is available for local development only. The deployed Vercel app uses the access email and password configured in Vercel environment variables because serverless functions do not provide durable local state.

## Tests

Run backend unit tests and the frontend production build:

```powershell
cd backend
python -m unittest discover -s tests -v
cd ..\frontend
npm run build
```

The frontend currently has no separate lint, type-check, or test scripts configured.
