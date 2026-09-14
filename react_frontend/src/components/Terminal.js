import React, { useEffect, useRef } from "react";

const Terminal = ({ terminalInfo }) => {
  const scrollRef = useRef(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [terminalInfo]);

  if (!terminalInfo || !terminalInfo.processes || terminalInfo.processes.length === 0) {
    return null;
  }

  return (
    <div style={{ marginBottom: 16, borderRadius: 12, overflow: "hidden", border: "1px solid var(--border)", background: "var(--bg-tertiary)" }}>
      <div style={{ padding: "12px 16px", background: "var(--bg-secondary)", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, fontWeight: 500, color: "var(--text-primary)" }}>
          <span>💻 Running Commands</span>
          <span style={{ fontSize: 11, color: "var(--text-muted)", marginLeft: 8 }}>
            {terminalInfo.processes.filter(p => p.status === "running").length} running, {terminalInfo.processes.length} total
          </span>
        </div>
      </div>

      <div style={{ padding: 16, display: "grid", gap: 12 }}>
        {terminalInfo.processes.map((process, idx) => (
          <div key={idx} style={{ borderRadius: 8, background: "var(--bg-tertiary)", border: "1px solid var(--border)", overflow: "hidden" }}>
            {/* Command header */}
            <div style={{ padding: "8px 12px", background: "var(--bg-secondary)", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ 
                display: "inline-block", 
                width: 8, 
                height: 8, 
                borderRadius: "50%", 
                background: process.status === "running" ? "#10b981" : "#6b7280",
                animation: process.status === "running" ? "pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite" : "none"
              }} />
              <span style={{ fontSize: 11, fontWeight: 500, color: "var(--text-muted)" }}>{process.script}</span>
              <span style={{ fontSize: 10, color: "var(--text-muted)", marginLeft: "auto" }}>PID: {process.pid}</span>
              <span style={{ fontSize: 10, color: "var(--text-muted)" }}>Port: {process.port}</span>
              <span style={{ fontSize: 10, color: process.status === "running" ? "#10b981" : "#6b7280", fontWeight: 500 }}>
                {process.status === "running" ? "●" : "○"} {process.status}
              </span>
            </div>

            {/* Command info */}
            <div style={{ padding: 12, background: "var(--bg-primary)", borderBottom: "1px solid var(--border)" }}>
              <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 6 }}>
                <strong>CWD:</strong> {process.cwd}
              </div>
              <div style={{ fontSize: 11, fontFamily: "monospace", color: "var(--accent)", wordBreak: "break-all", whiteSpace: "pre-wrap" }}>
                $ {process.command}
              </div>
            </div>

            {/* Output */}
            {process.output && (
              <div
                ref={scrollRef}
                style={{
                  maxHeight: 200,
                  overflowY: "auto",
                  padding: 12,
                  fontFamily: "monospace",
                  fontSize: 10,
                  color: "var(--text-secondary)",
                  lineHeight: 1.4,
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                  background: "#000",
                  borderTop: "1px solid var(--border)"
                }}
              >
                {process.output}
              </div>
            )}
          </div>
        ))}
      </div>

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: .5; }
        }
      `}</style>
    </div>
  );
};

export default Terminal;
