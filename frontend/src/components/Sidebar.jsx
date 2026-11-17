import { Cloud, FolderClosed, HardDrive } from "lucide-react";

export default function Sidebar({ activeView, onChangeView, storageStatus }) {
  const items = [
    { id: "all", label: "All files", icon: FolderClosed },
    { id: "recent", label: "Recent", icon: HardDrive },
  ];

  return (
    <aside className="flex w-full shrink-0 flex-col border-b border-slate-200 bg-white px-5 py-5 md:min-h-screen md:w-[250px] md:border-b-0 md:border-r md:px-6 md:py-8">
      <a className="flex items-center gap-3" href="/" aria-label="CloudVault home">
        <span className="grid h-10 w-10 place-items-center rounded-xl bg-brand-600 text-white shadow-lg shadow-blue-200">
          <Cloud size={22} strokeWidth={2.5} />
        </span>
        <span className="font-display text-xl font-extrabold tracking-tight text-ink">
          Cloud<span className="text-brand-600">Vault</span>
        </span>
      </a>

      <div className="mt-8 flex gap-2 overflow-x-auto md:mt-12 md:flex-col md:gap-1">
        <p className="hidden px-3 pb-3 text-[11px] font-bold uppercase tracking-[0.16em] text-slate-400 md:block">
          Workspace
        </p>
        {items.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            className={`flex shrink-0 items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold transition ${
              activeView === id
                ? "bg-brand-50 text-brand-700"
                : "text-slate-500 hover:bg-slate-50 hover:text-ink"
            }`}
            onClick={() => onChangeView(id)}
            type="button"
          >
            <Icon size={18} />
            {label}
          </button>
        ))}
      </div>

      <div className="mt-auto hidden rounded-2xl bg-slate-50 p-4 md:mt-10 md:block">
        <p className="text-xs font-semibold text-slate-600">Storage location</p>
        <p className="mt-1 text-sm font-bold text-ink">{storageStatus.storage}</p>
        <p className="mt-2 text-[11px] leading-5 text-slate-400">{storageStatus.detail}</p>
      </div>
    </aside>
  );
}
