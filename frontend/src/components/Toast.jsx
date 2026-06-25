import { useCallback, useEffect, useState } from "react";
import { subscribeToasts } from "../toastBus.js";

const AUTO_DISMISS_MS = 8_000;

function ToastItem({ toast, onDismiss }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(toast.requestId);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // clipboard API unavailable - nothing useful to do, the id is still visible to copy by hand
    }
  };

  return (
    <div className="toast">
      <div className="toast-header">
        <span className="toast-title">⚠ {toast.title}</span>
        <button className="toast-close" onClick={() => onDismiss(toast.id)} aria-label="Dismiss">
          ✕
        </button>
      </div>
      {toast.description && <div className="toast-description">{toast.description}</div>}
      <div className="toast-footer">
        {toast.requestId && (
          <button className="toast-request-id" onClick={handleCopy} title="Copy request ID">
            {copied ? "Copied!" : `ID: ${toast.requestId}`}
          </button>
        )}
        <div className="toast-actions">
          {toast.retry && (
            <button
              className="toast-retry"
              onClick={() => {
                toast.retry();
                onDismiss(toast.id);
              }}
            >
              Retry
            </button>
          )}
          <button className="toast-dismiss" onClick={() => onDismiss(toast.id)}>
            Dismiss
          </button>
        </div>
      </div>
    </div>
  );
}

export default function Toast() {
  const [toasts, setToasts] = useState([]);

  const dismiss = useCallback((id) => {
    setToasts((current) => current.filter((t) => t.id !== id));
  }, []);

  useEffect(() => {
    return subscribeToasts((toast) => {
      setToasts((current) => [...current, toast]);
      setTimeout(() => dismiss(toast.id), AUTO_DISMISS_MS);
    });
  }, [dismiss]);

  if (toasts.length === 0) return null;

  return (
    <div className="toast-container">
      {toasts.map((toast) => (
        <ToastItem key={toast.id} toast={toast} onDismiss={dismiss} />
      ))}
    </div>
  );
}
