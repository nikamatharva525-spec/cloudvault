import express from "express";
import cors from "cors";
import multer from "multer";
import fs from "node:fs/promises";
import path from "node:path";
import crypto from "node:crypto";
import { fileURLToPath } from "node:url";
import { del, list, put } from "@vercel/blob";

const root = path.dirname(fileURLToPath(import.meta.url));
const localDir = path.join(root, "uploads");
const upload = multer({ storage: multer.memoryStorage(), limits: { fileSize: 100 * 1024 * 1024 } });
const useBlob = Boolean(process.env.BLOB_READ_WRITE_TOKEN);

function safeName(name) {
  return path.basename(name).replace(/[^a-zA-Z0-9._ -]/g, "_").slice(0, 180) || "unnamed-file";
}

function serializeLocal(fileName, stat) {
  return { id: fileName, name: fileName, size: stat.size, uploaded_at: stat.mtime.toISOString(), type: "" };
}

async function listStoredFiles() {
  if (useBlob) {
    const result = await list({ token: process.env.BLOB_READ_WRITE_TOKEN });
    return result.blobs.map((blob) => ({
      id: blob.pathname,
      name: path.basename(blob.pathname),
      size: blob.size,
      uploaded_at: blob.uploadedAt,
      type: blob.contentType || "application/octet-stream",
      url: blob.url,
    })).sort((a, b) => new Date(b.uploaded_at) - new Date(a.uploaded_at));
  }
  await fs.mkdir(localDir, { recursive: true });
  const names = (await fs.readdir(localDir)).filter((name) => !name.startsWith("."));
  return Promise.all(names.map(async (name) => serializeLocal(name, await fs.stat(path.join(localDir, name)))));
}

export function createApp() {
  const app = express();
  app.use(cors({ origin: true }));
  app.get("/", (_req, res) => res.json({ name: "CloudVault API", status: "ok", storage: useBlob ? "vercel-blob" : "local" }));
  app.get("/api/health", (_req, res) => res.json({ status: "ok" }));
  app.get(["/files", "/api/files"], async (_req, res) => {
    try { res.json(await listStoredFiles()); } catch (error) { res.status(500).json({ detail: error.message }); }
  });
  app.post(["/upload", "/api/upload"], upload.single("file"), async (req, res) => {
    if (!req.file) return res.status(400).json({ detail: "Please select a file." });
    const name = `${crypto.randomUUID()}-${safeName(req.file.originalname)}`;
    try {
      if (useBlob) {
        const blob = await put(name, req.file.buffer, { access: "public", contentType: req.file.mimetype, token: process.env.BLOB_READ_WRITE_TOKEN, addRandomSuffix: false });
        return res.status(201).json({ id: name, name: req.file.originalname, size: req.file.size, uploaded_at: new Date().toISOString(), type: req.file.mimetype, url: blob.url });
      }
      await fs.mkdir(localDir, { recursive: true });
      await fs.writeFile(path.join(localDir, name), req.file.buffer);
      return res.status(201).json({ id: name, name: req.file.originalname, size: req.file.size, uploaded_at: new Date().toISOString(), type: req.file.mimetype });
    } catch (error) { return res.status(500).json({ detail: error.message }); }
  });
  app.get(["/download/:id", "/api/download/:id"], async (req, res) => {
    try {
      if (useBlob) {
        const blobs = await list({ prefix: req.params.id, token: process.env.BLOB_READ_WRITE_TOKEN });
        if (!blobs.blobs[0]) return res.status(404).json({ detail: "File not found." });
        return res.redirect(blobs.blobs[0].downloadUrl || blobs.blobs[0].url);
      }
      const filePath = path.join(localDir, path.basename(req.params.id));
      return res.download(filePath, path.basename(req.params.id).replace(/^[0-9a-f-]+-/, ""));
    } catch { return res.status(404).json({ detail: "File not found." }); }
  });
  app.delete(["/files/:id", "/api/files/:id"], async (req, res) => {
    try {
      if (useBlob) await del(req.params.id, { token: process.env.BLOB_READ_WRITE_TOKEN });
      else await fs.unlink(path.join(localDir, path.basename(req.params.id)));
      return res.status(204).end();
    } catch { return res.status(404).json({ detail: "File not found." }); }
  });
  return app;
}

export default createApp();
