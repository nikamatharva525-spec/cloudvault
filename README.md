# CloudVault

CloudVault is a React + Node.js cloud storage dashboard with a bold neobrutalist interface.

## Stack

- React, Vite and `lucide-react` frontend
- Node.js, Express and Multer API
- Amazon S3 for persistent production storage
- Local disk fallback for development

## Local development

```powershell
npm install
npm install --prefix frontend
Copy-Item .env.example .env
npm run dev
```

Run the frontend in a second terminal:

```powershell
npm run dev --prefix frontend
```

The API runs on `http://localhost:8000` and the Vite app on `http://localhost:5173`.

## Vercel deployment

Create an S3 bucket in `us-east-1`, then add `AWS_REGION`, `AWS_S3_BUCKET`, `AWS_ACCESS_KEY_ID`, and `AWS_SECRET_ACCESS_KEY` to the deployment environment. Import the repository with the repository root as the project root; `vercel.json` builds the frontend and routes `/api/*` to the Node serverless function.

Never put GitHub, Vercel, Blob, or other private tokens in frontend code or commit them to the repository. Use the included `.env.example` as the configuration template.
