"use client";

import { useEffect, useState } from "react";
import { Check, X } from "lucide-react";

type Notice = { id: number; message: string; kind: "success" | "error" };
let nextId = 0;

export function notify(message: string, kind: Notice["kind"] = "success") {
  window.dispatchEvent(new CustomEvent("faultline:notice", { detail: { message, kind } }));
}

export function ToastViewport() {
  const [notices, setNotices] = useState<Notice[]>([]);
  useEffect(() => {
    const listener = (event: Event) => {
      const { message, kind } = (event as CustomEvent<Omit<Notice, "id">>).detail;
      const notice = { id: ++nextId, message, kind };
      setNotices((items) => [...items, notice]);
      window.setTimeout(
        () => setNotices((items) => items.filter((item) => item.id !== notice.id)),
        5000,
      );
    };
    window.addEventListener("faultline:notice", listener);
    return () => window.removeEventListener("faultline:notice", listener);
  }, []);

  return (
    <div className="toast-stack" role="status" aria-live="polite">
      {notices.map((notice) => (
        <div className="toast editorial-card" key={notice.id}>
          {notice.kind === "success" ? <Check size={16} /> : <X size={16} />}
          <span>{notice.message}</span>
          <button
            className="icon-button"
            aria-label="Dismiss notification"
            onClick={() => setNotices((items) => items.filter((item) => item.id !== notice.id))}
          >
            <X size={14} />
          </button>
        </div>
      ))}
    </div>
  );
}
