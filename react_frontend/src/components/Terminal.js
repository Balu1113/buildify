import React, { useEffect, useRef } from "react";

const Terminal = ({ terminalInfo, preparationStatus }) => {
  const scrollRef = useRef(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [terminalInfo, preparationStatus]);

  const hasProcesses = terminalInfo && terminalInfo.processes && terminalInfo.processes.length > 0;
  const isPrepping = preparationStatus && preparationStatus.status === "preparing";

  if (!hasProcesses && !isPrepping) {
    return null;
  }

  return (
    <div style={{ marginBottom: 16, borderRadius: 12, overflow: "hidden", border: "1px solid var(--border)", background: "var(--bg-tertiary)" }}>
      <div style={{ padding: "12px 16px", background: "var(--bg-secondary)", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, fontWeight: 500, color: "var(--text-primary)" }}>
          <span>💻 Running Commands</span>
          {hasProcesses && (
            <span style={{ fontSize: 11, color: "var(--text-muted)", marginLeft: 8 }}>
              {terminalInfo.processes.filter(p => p.status === "running").length} running, {terminalInfo.processes.length} total
            </span>
          )}
        </div>
      </div>

      <div style={{ padding: 16, display: "grid", gap: 12 }}>
        {/* Preparation Status */}
        {isPrepping && (
          <div style={{ borderRadius: 8, background: "var(--bg-tertiary)", border: "1px solid var(--border)", overflow: "hidden" }}>
            {/* Prep header */}
            <div style={{ padding: "8px 12px", background: "var(--bg-secondary)", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ 
                display: "inline-block", 
                width: 8, 
                height: 8, 
                borderRadius: "50%", 
                background: "#f59e0b",
                animation: "pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite"
              }} />
              <span style={{ fontSize: 11, fontWeight: 500, color: "var(--text-muted)" }}>
                {preparationStatus.stage === "npm_install" ? "📦 NPM Install" : "⚙️ Preparation"}
              </span>
              <span style={{ fontSize: 10, color: "#f59e0b", fontWeight: 500, marginLeft: "auto" }}>
                ● preparing
              </span>
            </div>

            {/* Prep info */}
            <div style={{ padding: 12, background: "var(--bg-primary)", borderBottom: "1px solid var(--border)" }}>
              <div style={{ fontSize: 11, color: "var(--text-secondary)", marginBottom: 8 }}>
                {preparationStatus.message}
              </div>
              {preparationStatus.stage === "npm_install" && (
                <>
                  {preparationStatus.package_dir && (
                    <div style={{ fontSize: 10, color: "var(--text-muted)", marginBottom: 6 }}>
                      <strong>CWD:</strong> {preparationStatus.package_dir}
                    </div>
                  )}
                  <div style={{ fontSize: 11, fontFamily: "monospace", color: "var(--accent)", wordBreak: "break-all", whiteSpace: "pre-wrap", marginBottom: 6 }}>
                    $ {preparationStatus.command || "npm install --no-audit --no-fund"}
                  </div>
                  <div style={{ fontSize: 10, color: "var(--text-muted)" }}>
                    Stage: <code style={{ color: "var(--accent)" }}>{preparationStatus.stage}</code>
                  </div>
                </>
              )}
              {preparationStatus.stage && preparationStatus.stage !== "npm_install" && (
                <div style={{ fontSize: 10, color: "var(--text-muted)" }}>
                  Stage: <code style={{ color: "var(--accent)" }}>{preparationStatus.stage}</code>
                </div>
              )}
            </div>

            {/* Prep output */}
            <div
              ref={scrollRef}
              style={{
                minHeight: 60,
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
              {preparationStatus.output?.length ? (
                preparationStatus.output.join("")
              ) : (
                <div style={{ animation: "pulse 1s ease-in-out infinite" }}>⏳ Waiting for command output...</div>
              )}
            </div>
          </div>
        )}

        {/* Process Output */}
        {hasProcesses && terminalInfo.processes.map((process, idx) => (
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
