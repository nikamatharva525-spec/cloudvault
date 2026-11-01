# CloudVault

CloudVault is a React + Node.js cloud storage dashboard with a bold neobrutalist interface.

## Stack

- React, Vite and `lucide-react` frontend
- Node.js, Express and Multer API
- Vercel Blob for persistent production storage
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

Create a Vercel Blob store, then add `BLOB_READ_WRITE_TOKEN` to the Vercel project environment variables. Import the repository with the repository root as the project root; `vercel.json` builds the frontend and routes `/api/*` to the Node serverless function.

Never put GitHub, Vercel, Blob, or other private tokens in frontend code or commit them to the repository. Use the included `.env.example` as the configuration template.
