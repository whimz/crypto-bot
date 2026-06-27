import { useEffect, useRef } from "react";
import { X } from "lucide-react";
import Settings from "./Settings.jsx";

export default function SettingsDrawer({ open, onClose }) {
  const panelRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    const handleClickOutside = (e) => {
      if (panelRef.current && !panelRef.current.contains(e.target)) onClose();
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [open, onClose]);

  return (
    <div
      ref={panelRef}
      className={`fixed top-0 right-0 h-full w-full sm:w-[420px] z-50 bg-bg-card border-l border-border
        shadow-2xl overflow-y-auto transition-transform duration-300 ease-out
        ${open ? "translate-x-0" : "translate-x-full"}`}
    >
      <div className="flex items-center justify-between px-5 pt-5">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-text-dim">Trade settings</h2>
        <button className="icon-button" onClick={onClose} aria-label="Close settings">
          <X size={18} />
        </button>
      </div>
      <div className="p-5 pt-3">
        <Settings />
      </div>
    </div>
  );
}
