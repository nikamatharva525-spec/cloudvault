import { CloudUpload } from "lucide-react";
import { useRef, useState } from "react";

export default function UploadDropzone({ disabled, onFilesSelected }) {
  const inputRef = useRef(null);
  const [isDragging, setIsDragging] = useState(false);

  function chooseFiles(files) {
    if (files?.length) onFilesSelected(Array.from(files));
    if (inputRef.current) inputRef.current.value = "";
  }

  return (
    <div
      className={`rounded-2xl border-2 border-dashed px-5 py-8 text-center transition sm:px-8 ${
        isDragging
          ? "border-brand-500 bg-brand-50"
          : "border-slate-200 bg-white hover:border-brand-300"
      } ${disabled ? "pointer-events-none opacity-60" : ""}`}
      onDragEnter={(event) => {
        event.preventDefault();
        setIsDragging(true);
      }}
      onDragOver={(event) => event.preventDefault()}
      onDragLeave={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) setIsDragging(false);
      }}
      onDrop={(event) => {
        event.preventDefault();
        setIsDragging(false);
        chooseFiles(event.dataTransfer.files);
      }}
    >
      <input
        ref={inputRef}
        className="sr-only"
        disabled={disabled}
        type="file"
        multiple
        onChange={(event) => chooseFiles(event.target.files)}
      />
      <span className="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-brand-50 text-brand-600">
        <CloudUpload size={24} />
      </span>
      <p className="mt-4 text-sm font-semibold text-ink">
        Drop files here or{" "}
        <button
          className="text-brand-600 underline decoration-brand-200 underline-offset-4 hover:text-brand-700"
          disabled={disabled}
          onClick={() => inputRef.current?.click()}
          type="button"
        >
          browse
        </button>
      </p>
      <p className="mt-1 text-xs text-slate-400">Maximum file size: 100 MB each</p>
    </div>
  );
}
