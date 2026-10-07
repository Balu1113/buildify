import React, { useEffect, useRef } from "react";

const Terminal = ({ terminalInfo, preparationStatus }) => {
  const scrollRef = useRef(null);
  const repairScrollRef = useRef(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [terminalInfo, preparationStatus]);

  useEffect(() => {
    if (repairScrollRef.current) {
      repairScrollRef.current.scrollTop = repairScrollRef.current.scrollHeight;
    }
  }, [preparationStatus?.output]);

  const hasProcesses = terminalInfo && terminalInfo.processes && terminalInfo.processes.length > 0;
  const isPrepping = preparationStatus && preparationStatus.status === "preparing";
  const isRepairing = preparationStatus && preparationStatus.status === "repairing";
  const repairReady = preparationStatus && preparationStatus.status === "ready" && preparationStatus.stage === "auto_repair";
  const repairFailed = preparationStatus && preparationStatus.status === "failed" && preparationStatus.stage === "auto_repair";

  if (!hasProcesses && !isPrepping && !isRepairing && !repairReady && !repairFailed) {
    return null;
  }

  return (
    <div style={{ width: "100%", minWidth: 0, boxSizing: "border-box", marginBottom: 16, borderRadius: 12, overflow: "hidden", border: `1px solid ${isRepairing ? "#f59e0b" : repairFailed ? "var(--danger)" : repairReady ? "var(--success)" : "var(--border)"}`, background: "var(--bg-tertiary)" }}>
      <div style={{ padding: "12px 16px", background: isRepairing ? "rgba(245,158,11,0.08)" : repairFailed ? "rgba(239,68,68,0.08)" : repairReady ? "rgba(16,185,129,0.08)" : "var(--bg-secondary)", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, fontWeight: 600, color: isRepairing ? "#f59e0b" : repairFailed ? "var(--danger)" : repairReady ? "var(--success)" : "var(--text-primary)" }}>
          {isRepairing ? (
            <><span style={{ display: "inline-block", width: 8, height: 8, borderRadius: "50%", background: "#f59e0b", animation: "pulse 1s ease-in-out infinite" }} />
            🔍 Auto Bug Detection &amp; Fix — Analyzing runtime error...</>
          ) : repairFailed ? (
            <><span>❌ Auto-Repair Failed</span></>
          ) : repairReady ? (
            <><span style={{ display: "inline-block", width: 8, height: 8, borderRadius: "50%", background: "var(--success)" }} />
            ✅ Auto-Repair Applied — Restarting application...</>
          ) : (
            <><span>💻 Running Commands</span>
            {hasProcesses && (
              <span style={{ fontSize: 11, color: "var(--text-muted)", marginLeft: 8 }}>
                {terminalInfo.processes.filter(p => p.status === "running").length} running, {terminalInfo.processes.length} total
              </span>
            )}</>
          )}
        </div>
        {isRepairing && (
          <div className="spinner" style={{ width: 16, height: 16, borderColor: "#f59e0b", borderTopColor: "transparent" }} />
        )}
      </div>

      <div style={{ padding: 16, display: "grid", gap: 12 }}>

        {/* ── Auto Bug Detection & Fix Panel ── */}
        {(isRepairing || repairReady || repairFailed) && (
          <div style={{ borderRadius: 8, border: `1px solid ${isRepairing ? "#f59e0b44" : repairFailed ? "var(--danger)" : "var(--success)"}`, overflow: "hidden" }}>
            {/* Status bar */}
            <div style={{ padding: "8px 14px", background: isRepairing ? "rgba(245,158,11,0.12)" : repairFailed ? "rgba(239,68,68,0.12)" : "rgba(16,185,129,0.12)", borderBottom: `1px solid ${isRepairing ? "#f59e0b44" : repairFailed ? "var(--danger)" : "var(--success)"}`, display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{ fontSize: 12, fontWeight: 600, color: isRepairing ? "#f59e0b" : repairFailed ? "var(--danger)" : "var(--success)" }}>
                {isRepairing ? "🤖 AI Agent is analyzing the crash and generating a fix..." : repairFailed ? "🚫 Could not automatically fix the runtime error" : "✅ Fix applied successfully"}
              </span>
            </div>

            {/* Message */}
            <div style={{ padding: "10px 14px", background: "var(--bg-primary)", borderBottom: "1px solid var(--border)" }}>
              <div style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: (preparationStatus?.summary || (repairReady && preparationStatus?.changed_files?.length)) ? 6 : 0 }}>
                {preparationStatus?.message}
              </div>
              {preparationStatus?.summary && (
                <div style={{ fontSize: 11, color: "var(--accent, #6366f1)", marginBottom: 6, fontWeight: 500 }}>
                  💡 {preparationStatus.summary}
                </div>
              )}
              {repairReady && preparationStatus?.changed_files?.length > 0 && (
                <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                  <strong style={{ color: "var(--success)" }}>Files patched:</strong>{" "}
                  {preparationStatus.changed_files.map((f, i) => (
                    <code key={i} style={{ background: "var(--bg-tertiary)", padding: "1px 5px", borderRadius: 4, fontSize: 10, marginRight: 4 }}>{f}</code>
                  ))}
                </div>
              )}
              {repairFailed && preparationStatus?.error && (
                <div style={{ fontSize: 11, color: "var(--danger)", marginTop: 4, fontFamily: "monospace" }}>
                  {preparationStatus.error}
                </div>
              )}
            </div>

            {/* Error output that was analyzed */}
            {preparationStatus?.output && (
              <div
                ref={repairScrollRef}
                style={{ maxHeight: 180, overflowY: "auto", padding: 12, fontFamily: "monospace", fontSize: 10, color: "#fca5a5", lineHeight: 1.4, whiteSpace: "pre-wrap", wordBreak: "break-word", background: "#0d0d0d", borderTop: "1px solid var(--border)" }}
              >
                <div style={{ color: "#6b7280", marginBottom: 6 }}>── crash output being analyzed ──</div>
                {preparationStatus.output}
              </div>
            )}
          </div>
        )}

        {/* ── NPM Install / Generic Preparation Status ── */}
        {isPrepping && (
          <div style={{ borderRadius: 8, background: "var(--bg-tertiary)", border: "1px solid var(--border)", overflow: "hidden" }}>
            {/* Prep header */}
            <div style={{ minWidth: 0, padding: "8px 12px", background: "var(--bg-secondary)", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
              <span style={{ display: "inline-block", width: 8, height: 8, borderRadius: "50%", background: "#f59e0b", animation: "pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite" }} />
              <span style={{ fontSize: 11, fontWeight: 500, color: "var(--text-muted)" }}>
                {preparationStatus.stage === "npm_install" ? "📦 NPM Install" : "⚙️ Preparation"}
              </span>
              <span style={{ fontSize: 10, color: "#f59e0b", fontWeight: 500, marginLeft: "auto" }}>● preparing</span>
            </div>

            {/* Prep info */}
            <div style={{ padding: 12, background: "var(--bg-primary)", borderBottom: "1px solid var(--border)" }}>
              <div style={{ fontSize: 11, color: "var(--text-secondary)", marginBottom: 8 }}>{preparationStatus.message}</div>
              {preparationStatus.stage === "npm_install" && (
                <>
                  {preparationStatus.package_dir && (
                    <div style={{ fontSize: 10, color: "var(--text-muted)", marginBottom: 6 }}><strong>CWD:</strong> {preparationStatus.package_dir}</div>
                  )}
                  <div style={{ fontSize: 11, fontFamily: "monospace", color: "var(--accent)", wordBreak: "break-all", whiteSpace: "pre-wrap", marginBottom: 6 }}>
                    $ {preparationStatus.command || "npm install --no-audit --no-fund"}
                  </div>
                  <div style={{ fontSize: 10, color: "var(--text-muted)" }}>Stage: <code style={{ color: "var(--accent)" }}>{preparationStatus.stage}</code></div>
                </>
              )}
              {preparationStatus.stage && preparationStatus.stage !== "npm_install" && (
                <div style={{ fontSize: 10, color: "var(--text-muted)" }}>Stage: <code style={{ color: "var(--accent)" }}>{preparationStatus.stage}</code></div>
              )}
            </div>

            {/* Prep output */}
            <div ref={scrollRef} style={{ minHeight: 60, maxHeight: 200, overflowY: "auto", padding: 12, fontFamily: "monospace", fontSize: 10, color: "var(--text-secondary)", lineHeight: 1.4, whiteSpace: "pre-wrap", wordBreak: "break-word", background: "#000", borderTop: "1px solid var(--border)" }}>
              {preparationStatus.output?.length ? preparationStatus.output.join("") : (
                <div style={{ animation: "pulse 1s ease-in-out infinite" }}>⏳ Waiting for command output...</div>
              )}
            </div>
          </div>
        )}

        {/* Process Output */}
        {hasProcesses && terminalInfo.processes.map((process, idx) => (
          <div key={idx} style={{ minWidth: 0, borderRadius: 8, background: "var(--bg-tertiary)", border: "1px solid var(--border)", overflow: "hidden" }}>
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
              <span style={{ minWidth: 0, overflowWrap: "anywhere", fontSize: 11, fontWeight: 500, color: "var(--text-muted)" }}>{process.script}</span>
              <span style={{ flexShrink: 0, fontSize: 10, color: "var(--text-muted)", marginLeft: "auto" }}>PID: {process.pid}</span>
              <span style={{ flexShrink: 0, fontSize: 10, color: "var(--text-muted)" }}>Port: {process.port}</span>
              <span style={{ fontSize: 10, color: process.status === "running" ? "#10b981" : "#6b7280", fontWeight: 500 }}>
                {process.status === "running" ? "●" : "○"} {process.status}
              </span>
            </div>

            {/* Command info */}
              <div style={{ minWidth: 0, padding: 12, background: "var(--bg-primary)", borderBottom: "1px solid var(--border)" }}>
              <div style={{ overflowWrap: "anywhere", fontSize: 11, color: "var(--text-muted)", marginBottom: 6 }}>
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
                  minWidth: 0,
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
