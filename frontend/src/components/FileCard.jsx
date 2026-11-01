import {
  Archive,
  File,
  FileImage,
  FileText,
  MoreHorizontal,
  Music2,
  Presentation,
  Sheet,
  Video,
} from "lucide-react";
import { useState } from "react";

const typeStyles = {
  image: { icon: FileImage, color: "bg-violet-50 text-violet-600" },
  document: { icon: FileText, color: "bg-blue-50 text-blue-600" },
  spreadsheet: { icon: Sheet, color: "bg-emerald-50 text-emerald-600" },
  presentation: { icon: Presentation, color: "bg-orange-50 text-orange-600" },
  video: { icon: Video, color: "bg-pink-50 text-pink-600" },
  audio: { icon: Music2, color: "bg-amber-50 text-amber-600" },
  archive: { icon: Archive, color: "bg-slate-100 text-slate-600" },
  other: { icon: File, color: "bg-brand-50 text-brand-600" },
};

function getFileStyle(name) {
  const ext = name.split(".").pop()?.toLowerCase() ?? "";
  if (["png", "jpg", "jpeg", "gif", "webp", "svg", "bmp"].includes(ext)) return typeStyles.image;
  if (["pdf", "doc", "docx", "txt", "rtf"].includes(ext)) return typeStyles.document;
  if (["xls", "xlsx", "csv"].includes(ext)) return typeStyles.spreadsheet;
  if (["ppt", "pptx"].includes(ext)) return typeStyles.presentation;
  if (["mp4", "mov", "mkv", "webm"].includes(ext)) return typeStyles.video;
  if (["mp3", "wav", "aac", "flac"].includes(ext)) return typeStyles.audio;
  if (["zip", "rar", "7z", "tar", "gz"].includes(ext)) return typeStyles.archive;
  return typeStyles.other;
}

export function formatFileSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let size = bytes / 1024;
  let unitIndex = 0;
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex += 1;
  }
  return `${size.toFixed(size < 10 ? 1 : 0)} ${units[unitIndex]}`;
}

export function formatUploadDate(value) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export default function FileCard({ file, onDownload, onDelete, downloading }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const { icon: Icon, color } = getFileStyle(file.name);
  return (
    <article className="group min-w-0 rounded-2xl border border-slate-100 bg-white p-4 shadow-card transition hover:-translate-y-0.5 hover:border-blue-100 hover:shadow-lg sm:p-5">
      <div className="flex items-start justify-between gap-3">
        <span className={`grid h-11 w-11 shrink-0 place-items-center rounded-xl ${color}`}>
          <Icon size={21} />
        </span>
        <div className="relative">
          <button
            aria-label={`Actions for ${file.name}`}
            aria-expanded={menuOpen}
            className="rounded-lg p-2 text-slate-400 hover:bg-slate-50 hover:text-ink"
            onClick={() => setMenuOpen((open) => !open)}
            type="button"
          >
            <MoreHorizontal size={19} />
          </button>
          {menuOpen && (
            <div className="absolute right-0 z-10 mt-1 w-36 rounded-xl border border-slate-100 bg-white p-1 shadow-xl">
              <button
                className="w-full rounded-lg px-3 py-2 text-left text-xs font-semibold text-slate-600 hover:bg-slate-50"
                onClick={() => {
                  setMenuOpen(false);
                  onDownload(file);
                }}
                disabled={downloading}
                type="button"
              >
                {downloading ? "Downloading..." : "Download"}
              </button>
              <button
                className="w-full rounded-lg px-3 py-2 text-left text-xs font-semibold text-rose-600 hover:bg-rose-50"
                onClick={() => {
                  setMenuOpen(false);
                  onDelete(file);
                }}
                type="button"
              >
                Delete
              </button>
            </div>
          )}
        </div>
      </div>
      <h3 className="mt-5 truncate text-sm font-bold text-ink" title={file.name}>
        {file.name}
      </h3>
      <div className="mt-2 flex items-center justify-between gap-2 text-[11px] text-slate-400">
        <span>{formatFileSize(file.size)}</span>
        <span className="truncate">{formatUploadDate(file.uploaded_at)}</span>
      </div>
      <button
        className="mt-4 w-full rounded-lg border border-slate-100 py-2 text-xs font-semibold text-slate-600 transition hover:border-brand-100 hover:bg-brand-50 hover:text-brand-700"
        disabled={downloading}
        onClick={() => onDownload(file)}
        type="button"
      >
        {downloading ? "Downloading..." : "Download file"}
      </button>
    </article>
  );
}
