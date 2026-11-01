import {
  AlertCircle,
  CheckCircle2,
  Cloud,
  Download,
  Files,
  Search,
  Upload,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import FileCard, { formatFileSize } from "../components/FileCard.jsx";
import Sidebar from "../components/Sidebar.jsx";
import UploadDropzone from "../components/UploadDropzone.jsx";
import { deleteFile, downloadFile, listFiles, uploadFile } from "../services/files.js";

const MAX_FILE_SIZE = 100 * 1024 * 1024;

export default function Dashboard() {
  const [files, setFiles] = useState([]);
  const [search, setSearch] = useState("");
  const [activeView, setActiveView] = useState("all");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(null);
  const [downloadingId, setDownloadingId] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const refreshFiles = useCallback(async () => {
    try {
      setFiles(await listFiles());
      setError("");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshFiles();
  }, [refreshFiles]);

  const totalSize = useMemo(() => files.reduce((total, file) => total + file.size, 0), [files]);
  const filteredFiles = useMemo(() => {
    const query = search.trim().toLowerCase();
    return [...files]
      .filter((file) => !query || file.name.toLowerCase().includes(query))
      .filter((file) => activeView !== "recent" || Date.now() - new Date(file.uploaded_at) < 7 * 86400000)
      .sort((a, b) => new Date(b.uploaded_at) - new Date(a.uploaded_at));
  }, [activeView, files, search]);
  const progressPercent = uploadProgress?.totalBytes
    ? Math.min(
        100,
        Math.round(
          ((uploadProgress.completedBytes + uploadProgress.loadedBytes) / uploadProgress.totalBytes) *
            100,
        ),
      )
    : 0;

  async function handleUpload(selectedFiles) {
    setError("");
    setNotice("");
    const invalid = selectedFiles.filter((file) => !file.name.trim() || file.size > MAX_FILE_SIZE);
    const valid = selectedFiles.filter((file) => file.name.trim() && file.size <= MAX_FILE_SIZE);
    const validationError = invalid.length
      ? `${invalid.map((file) => file.name || "Unnamed file").join(", ")} ${
          invalid.length === 1 ? "is" : "are"
        } too large or have no filename. Maximum size is 100 MB per file.`
      : "";
    if (!valid.length) {
      setError(validationError);
      return;
    }

    setBusy(true);
    const totalBytes = valid.reduce((total, file) => total + file.size, 0);
    setUploadProgress({ totalBytes, completedBytes: 0, loadedBytes: 0, currentName: valid[0].name });
    let uploaded = 0;
    const failures = [];
    let completedBytes = 0;
    for (const file of valid) {
      setUploadProgress({ totalBytes, completedBytes, loadedBytes: 0, currentName: file.name });
      try {
        await uploadFile(file, (loaded, total) => {
          setUploadProgress({
            totalBytes,
            completedBytes,
            loadedBytes: total ? Math.min(file.size, (loaded / total) * file.size) : 0,
            currentName: file.name,
          });
        });
        uploaded += 1;
      } catch (uploadError) {
        failures.push(`${file.name}: ${uploadError.message}`);
      }
      completedBytes += file.size;
    }
    await refreshFiles();
    setBusy(false);
    setUploadProgress(null);
    if (failures.length || validationError) {
      setError([validationError, ...failures].filter(Boolean).join(" "));
    } else if (uploaded) {
      setNotice(`${uploaded} ${uploaded === 1 ? "file" : "files"} uploaded successfully.`);
    }
  }

  async function handleDownload(file) {
    setError("");
    setNotice("");
    setDownloadingId(file.id);
    try {
      await downloadFile(file.id, file.name);
      setNotice(`${file.name} downloaded successfully.`);
    } catch (downloadError) {
      setError(downloadError.message);
    } finally {
      setDownloadingId("");
    }
  }

  async function handleDelete(file) {
    if (!window.confirm(`Delete "${file.name}"? This cannot be undone.`)) return;
    setError("");
    setNotice("");
    try {
      await deleteFile(file.id);
      setFiles((currentFiles) => currentFiles.filter((item) => item.id !== file.id));
      setNotice(`${file.name} was deleted.`);
    } catch (deleteError) {
      setError(deleteError.message);
    }
  }

  const title = activeView === "recent" ? "Recent files" : "All files";

  return (
    <div className="min-h-screen md:flex">
      <Sidebar activeView={activeView} onChangeView={setActiveView} />
      <main className="min-w-0 flex-1 px-5 pb-10 pt-6 sm:px-8 md:px-10 md:pt-9 xl:px-14">
        <header className="mb-9 flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-xs font-semibold text-slate-400">Workspace / {title}</p>
            <h1 className="mt-1 font-display text-2xl font-extrabold tracking-tight text-ink sm:text-[30px]">
              Good to see you
            </h1>
          </div>
          <div className="flex items-center gap-2 rounded-full border border-emerald-100 bg-emerald-50 px-3 py-2 text-xs font-bold text-emerald-700">
            <span className="h-2 w-2 rounded-full bg-emerald-500" />
            Local server
          </div>
        </header>

        <section className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-[#2563eb] via-[#357cf4] to-[#55a1fa] p-6 text-white shadow-lg shadow-blue-200/60 sm:p-9">
          <div className="pointer-events-none absolute -right-8 -top-20 h-64 w-64 rounded-full border-[35px] border-white/10" />
          <div className="pointer-events-none absolute -bottom-28 right-40 h-56 w-56 rounded-full border-[30px] border-white/10" />
          <div className="relative z-10 max-w-xl">
            <div className="mb-5 inline-flex items-center gap-2 rounded-full bg-white/15 px-3 py-1.5 text-xs font-semibold backdrop-blur">
              <Cloud size={15} /> Your personal file space
            </div>
            <h2 className="font-display text-2xl font-extrabold leading-tight sm:text-3xl">
              Your files, in one place.
            </h2>
            <p className="mt-2 max-w-md text-sm leading-6 text-blue-50">
              Upload and manage files from this dashboard. Files are stored on the machine running
              the CloudVault backend.
            </p>
            <button
              className="mt-6 inline-flex items-center gap-2 rounded-xl bg-white px-4 py-2.5 text-sm font-bold text-brand-700 shadow-sm transition hover:bg-blue-50 disabled:opacity-70"
              disabled={busy}
              onClick={() => document.getElementById("upload-section")?.scrollIntoView({ behavior: "smooth" })}
              type="button"
            >
              <Upload size={16} /> {busy ? "Uploading..." : "Upload files"}
            </button>
          </div>
          <div className="absolute bottom-8 right-12 hidden rounded-2xl bg-white/15 p-5 backdrop-blur-sm lg:block">
            <Cloud size={62} strokeWidth={1.4} />
          </div>
        </section>

        <section aria-label="Storage summary" className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="flex items-center gap-4 rounded-2xl border border-slate-100 bg-white p-5 shadow-card">
            <span className="grid h-12 w-12 place-items-center rounded-xl bg-blue-50 text-blue-600">
              <Files size={22} />
            </span>
            <div>
              <p className="text-xs font-semibold text-slate-400">Total files</p>
              <p className="mt-0.5 text-xl font-extrabold text-ink">{loading ? "…" : files.length}</p>
            </div>
          </div>
          <div className="flex items-center gap-4 rounded-2xl border border-slate-100 bg-white p-5 shadow-card">
            <span className="grid h-12 w-12 place-items-center rounded-xl bg-indigo-50 text-indigo-600">
              <Download size={21} />
            </span>
            <div>
              <p className="text-xs font-semibold text-slate-400">Storage used</p>
              <p className="mt-0.5 text-xl font-extrabold text-ink">
                {loading ? "…" : formatFileSize(totalSize)}
              </p>
            </div>
          </div>
        </section>

        <section className="mt-8" id="upload-section">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="font-display text-lg font-extrabold text-ink">Add to your vault</h2>
              <p className="mt-1 text-xs text-slate-400">Upload one or more files, up to 100 MB each</p>
            </div>
          </div>
          <UploadDropzone disabled={busy} onFilesSelected={handleUpload} />
          {uploadProgress && (
            <div className="mt-3 rounded-xl border border-blue-100 bg-blue-50 px-4 py-3" role="status">
              <div className="flex items-center justify-between gap-3 text-xs font-semibold text-blue-800">
                <span className="truncate">Uploading {uploadProgress.currentName}</span>
                <span>{progressPercent}%</span>
              </div>
              <div
                aria-label="Upload progress"
                aria-valuemax="100"
                aria-valuemin="0"
                aria-valuenow={progressPercent}
                className="mt-2 h-1.5 overflow-hidden rounded-full bg-blue-100"
                role="progressbar"
              >
                <div
                  className="h-full rounded-full bg-brand-600 transition-[width]"
                  style={{
                    width: `${progressPercent}%`,
                  }}
                />
              </div>
            </div>
          )}
        </section>

        {error && (
          <div className="mt-5 flex items-start justify-between gap-3 rounded-xl border border-rose-100 bg-rose-50 px-4 py-3 text-sm text-rose-700" role="alert">
            <AlertCircle className="mt-0.5 shrink-0" size={17} />
            <span>{error}</span>
          </div>
        )}
        {notice && (
          <div className="mt-5 flex items-center gap-2 rounded-xl border border-emerald-100 bg-emerald-50 px-4 py-3 text-sm text-emerald-700" role="status">
            <CheckCircle2 size={17} />
            <span>{notice}</span>
          </div>
        )}

        <section className="mt-9">
          <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
            <div>
              <h2 className="font-display text-lg font-extrabold text-ink">{title}</h2>
              <p className="mt-1 text-xs text-slate-400">
                {filteredFiles.length} {filteredFiles.length === 1 ? "item" : "items"} in your vault
              </p>
            </div>
            <label className="flex w-full items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-slate-400 sm:w-56">
              <Search size={16} />
              <input
                aria-label="Search files"
                className="min-w-0 flex-1 bg-transparent text-xs text-ink outline-none placeholder:text-slate-400"
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search files..."
                value={search}
              />
            </label>
          </div>

          {loading ? (
            <div className="rounded-2xl border border-slate-100 bg-white px-5 py-12 text-center text-sm text-slate-400">
              Loading your files...
            </div>
          ) : filteredFiles.length ? (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
              {filteredFiles.map((file) => (
                <FileCard
                  file={file}
                  key={file.id}
                  onDelete={handleDelete}
                  onDownload={handleDownload}
                  downloading={downloadingId === file.id}
                />
              ))}
            </div>
          ) : (
            <div className="rounded-2xl border border-slate-100 bg-white px-5 py-12 text-center">
              <div className="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-slate-50 text-slate-400">
                <Files size={22} />
              </div>
              <p className="mt-3 text-sm font-bold text-ink">
                {search ? "No files match your search" : "Your vault is ready"}
              </p>
              <p className="mt-1 text-xs text-slate-400">
                {search ? "Try another name." : "Upload a file above to see it here."}
              </p>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
