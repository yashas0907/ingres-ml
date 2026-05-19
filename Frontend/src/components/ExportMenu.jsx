import { useState, useRef, useEffect } from "react";

export default function ExportMenu({ options, loading = false }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(null);
  const ref = useRef(null);

  useEffect(() => {
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const handleClick = async (opt) => {
    setOpen(false);
    setBusy(opt.id);
    try { await opt.action(); } finally { setBusy(null); }
  };

  return (
    <div className="export-menu-wrapper" ref={ref}>
      <button
        className={`export-trigger-btn ${busy ? "exporting" : ""}`}
        onClick={() => setOpen(o => !o)}
        disabled={!!busy || loading}
        title="Export / Download"
      >
        {busy ? (
          <>
            <span className="export-spinner" />
            <span>Generating…</span>
          </>
        ) : (
          <>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
              <polyline points="7 10 12 15 17 10"/>
              <line x1="12" y1="15" x2="12" y2="3"/>
            </svg>
            <span>Export</span>
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
              <polyline points="6 9 12 15 18 9"/>
            </svg>
          </>
        )}
      </button>

      {open && (
        <div className="export-dropdown">
          <div className="export-dropdown-header">Download as</div>
          {options.map(opt => (
            <button
              key={opt.id}
              className="export-dropdown-item"
              onClick={() => handleClick(opt)}
              disabled={!!busy}
            >
              <span className={`export-type-badge ${opt.type}`}>{opt.type.toUpperCase()}</span>
              <span className="export-item-label">{opt.label}</span>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                <polyline points="7 10 12 15 17 10"/>
                <line x1="12" y1="15" x2="12" y2="3"/>
              </svg>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
