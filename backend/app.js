import express from "express";
import cors from "cors";
import multer from "multer";
import fs from "node:fs/promises";
import path from "node:path";
import crypto from "node:crypto";
import { fileURLToPath } from "node:url";
import { DeleteObjectCommand, GetObjectCommand, ListObjectsV2Command, PutObjectCommand, S3Client } from "@aws-sdk/client-s3";

const root = path.dirname(fileURLToPath(import.meta.url));
const localDir = path.join(root, "uploads");
const upload = multer({ storage: multer.memoryStorage(), limits: { fileSize: 100 * 1024 * 1024 } });
const useS3 = Boolean(process.env.AWS_S3_BUCKET);
const s3 = useS3 ? new S3Client({ region: process.env.AWS_REGION || "us-east-1" }) : null;
const bucket = process.env.AWS_S3_BUCKET;

function safeName(name) {
  return path.basename(name).replace(/[^a-zA-Z0-9._ -]/g, "_").slice(0, 180) || "unnamed-file";
}

function serializeLocal(fileName, stat) {
  return { id: fileName, name: fileName, size: stat.size, uploaded_at: stat.mtime.toISOString(), type: "" };
}

async function listStoredFiles() {
  if (useS3) {
    const result = await s3.send(new ListObjectsV2Command({ Bucket: bucket }));
    return (result.Contents || []).map((object) => ({
      id: object.Key,
      name: path.basename(object.Key),
      size: object.Size || 0,
      uploaded_at: object.LastModified,
      type: "application/octet-stream",
    })).sort((a, b) => new Date(b.uploaded_at) - new Date(a.uploaded_at));
  }
  await fs.mkdir(localDir, { recursive: true });
  const names = (await fs.readdir(localDir)).filter((name) => !name.startsWith("."));
  return Promise.all(names.map(async (name) => serializeLocal(name, await fs.stat(path.join(localDir, name)))));
}

export function createApp() {
  const app = express();
  app.use(cors({ origin: true }));
  app.get("/", (_req, res) => res.json({ name: "CloudVault API", status: "ok", storage: useS3 ? "s3" : "local" }));
  app.get("/api/health", (_req, res) => res.json({ status: "ok" }));
  app.get(["/files", "/api/files"], async (_req, res) => {
    try { res.json(await listStoredFiles()); } catch (error) { res.status(500).json({ detail: error.message }); }
  });
  app.post(["/upload", "/api/upload"], upload.single("file"), async (req, res) => {
    if (!req.file) return res.status(400).json({ detail: "Please select a file." });
    const name = `${crypto.randomUUID()}-${safeName(req.file.originalname)}`;
    try {
      if (useS3) {
        await s3.send(new PutObjectCommand({ Bucket: bucket, Key: name, Body: req.file.buffer, ContentType: req.file.mimetype, ServerSideEncryption: "AES256" }));
        return res.status(201).json({ id: name, name: req.file.originalname, size: req.file.size, uploaded_at: new Date().toISOString(), type: req.file.mimetype });
      }
      await fs.mkdir(localDir, { recursive: true });
      await fs.writeFile(path.join(localDir, name), req.file.buffer);
      return res.status(201).json({ id: name, name: req.file.originalname, size: req.file.size, uploaded_at: new Date().toISOString(), type: req.file.mimetype });
    } catch (error) { return res.status(500).json({ detail: error.message }); }
  });
  app.get(["/download/:id", "/api/download/:id"], async (req, res) => {
    try {
      if (useS3) {
        const object = await s3.send(new GetObjectCommand({ Bucket: bucket, Key: req.params.id }));
        res.setHeader("Content-Disposition", `attachment; filename="${path.basename(req.params.id).replace(/^[0-9a-f-]+-/, "")}"`);
        if (object.ContentType) res.setHeader("Content-Type", object.ContentType);
        object.Body.pipe(res);
        return;
      }
      const filePath = path.join(localDir, path.basename(req.params.id));
      return res.download(filePath, path.basename(req.params.id).replace(/^[0-9a-f-]+-/, ""));
    } catch { return res.status(404).json({ detail: "File not found." }); }
  });
  app.delete(["/files/:id", "/api/files/:id"], async (req, res) => {
    try {
      if (useS3) await s3.send(new DeleteObjectCommand({ Bucket: bucket, Key: req.params.id }));
      else await fs.unlink(path.join(localDir, path.basename(req.params.id)));
      return res.status(204).end();
    } catch { return res.status(404).json({ detail: "File not found." }); }
  });
  return app;
}

export default createApp();
