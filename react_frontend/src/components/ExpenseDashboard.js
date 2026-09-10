import React, { useState, useEffect } from "react";
import { Chart as ChartJS, ArcElement, Tooltip, Legend } from "chart.js";
import { Pie } from "react-chartjs-2";
import { expenseAPI } from "../services/api";

ChartJS.register(ArcElement, Tooltip, Legend);
const COLORS = ["#a78bfa", "#4ade80", "#fbbf24", "#f87171", "#60a5fa", "#c084fc", "#f472b6", "#2dd4bf"];

const ExpenseDashboard = () => {
  const [expenses, setExpenses] = useState([]);
  const [chartData, setChartData] = useState(null);
  const [aiText, setAiText] = useState("");
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState(null);

  useEffect(() => { fetchExpenses(); fetchSummary(); }, []);
  const fetchExpenses = async () => { try { const r = await expenseAPI.list(); setExpenses(r.data); } catch {} };
  const fetchSummary = async () => { try { const r = await expenseAPI.getSummary(); const d = r.data; if (d.length) setChartData({ labels: d.map(i => `Cat ${i.category_id}`), datasets: [{ data: d.map(i => i.total), backgroundColor: COLORS, borderWidth: 0, hoverOffset: 8 }] }); } catch {} };
  const showToast = (msg, type = "info") => { setToast({ msg, type }); setTimeout(() => setToast(null), 4000); };

  const handleAiParse = async () => {
    if (!aiText.trim()) return; setLoading(true);
    try { await expenseAPI.parseText(aiText); showToast("Expense saved!", "success"); setAiText(""); fetchExpenses(); fetchSummary(); }
    catch { showToast("Error.", "error"); } setLoading(false);
  };

  const handleUpload = async (e) => {
    const file = e.target.files[0]; if (!file) return; setLoading(true);
    try { await expenseAPI.uploadReceipt(file); showToast("Receipt parsed!", "success"); fetchExpenses(); fetchSummary(); }
    catch { showToast("Error.", "error"); } setLoading(false);
  };

  const handleDelete = async (id) => { try { await expenseAPI.delete(id); fetchExpenses(); fetchSummary(); } catch {} };
  const total = expenses.reduce((s, e) => s + e.amount, 0);

  return (
    <div className="animate-in">
      <div className="page-header"><h1 className="page-title">Expenses</h1><p className="page-subtitle">AI-powered expense tracking from text or receipts</p></div>
      {toast && <div className={`toast toast-${toast.type}`}>{toast.type === "success" ? "✨" : "⚠"} {toast.msg}</div>}

      <div className="card" style={{ marginBottom: 20 }}>
        <div className="card-header"><div><div className="card-title">Add Expense</div><div className="card-subtitle">Type naturally or upload a receipt</div></div></div>
        <div style={{ display: "flex", gap: 10 }}>
          <input className="input" placeholder='e.g. "Spent $45 at Whole Foods on groceries"' value={aiText} onChange={(e) => setAiText(e.target.value)} onKeyDown={(e) => e.key === "Enter" && handleAiParse()} style={{ flex: 1 }} />
          <button onClick={handleAiParse} disabled={loading || !aiText.trim()} className="btn btn-primary">{loading ? <div className="spinner" /> : "🤖"} Add</button>
          <label className="btn btn-ghost" style={{ cursor: "pointer" }}>📷 Receipt<input type="file" accept="image/*" onChange={handleUpload} disabled={loading} style={{ display: "none" }} /></label>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12, marginBottom: 20 }}>
        <div className="stat-card"><div className="stat-value">${total.toFixed(2)}</div><div className="stat-label">Total</div></div>
        <div className="stat-card"><div className="stat-value">{expenses.length}</div><div className="stat-label">Transactions</div></div>
        <div className="stat-card"><div className="stat-value">{chartData?.labels?.length || 0}</div><div className="stat-label">Categories</div></div>
      </div>

      <div className="grid-2">
        <div className="card">
          <div className="card-header"><div className="card-title">Spending</div></div>
          {chartData ? <div style={{ display: "flex", justifyContent: "center", padding: "10px 0" }}><Pie data={chartData} options={{ plugins: { legend: { position: "bottom", labels: { color: "var(--text-muted)", font: { family: "'Space Grotesk'", size: 11 }, padding: 14 } } }, cutout: "55%", animation: { animateScale: true } }} /></div> : <div className="empty-state"><div className="empty-state-icon">📊</div><div className="empty-state-text">No data yet</div></div>}
        </div>
        <div className="card">
          <div className="card-header"><div className="card-title">Recent</div><span className="badge" style={{ background: "var(--bg-hover)", color: "var(--text-muted)" }}>{expenses.length}</span></div>
          {expenses.length === 0 ? <div className="empty-state"><div className="empty-state-icon">💰</div><div className="empty-state-text">No expenses</div></div> : (
            <div style={{ maxHeight: 350, overflowY: "auto" }}>
              {expenses.map(e => (
                <div key={e.id} style={{ padding: "11px 0", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 12 }}>
                  <div style={{ width: 38, height: 38, borderRadius: 10, background: "var(--accent-glow)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 15, flexShrink: 0 }}>{e.ai_label ? "🤖" : "💳"}</div>
                  <div style={{ flex: 1 }}><div style={{ fontSize: 13, fontWeight: 500 }}>{e.description}</div><div style={{ fontSize: 11, color: "var(--text-muted)", display: "flex", gap: 6, alignItems: "center", marginTop: 2 }}>{e.ai_label && <span className="badge badge-medium" style={{ fontSize: 9 }}>{e.ai_label}</span>}{new Date(e.date).toLocaleDateString()}</div></div>
                  <div style={{ fontWeight: 700, fontSize: 15 }}>${e.amount.toFixed(2)}</div>
                  <button onClick={() => handleDelete(e.id)} className="btn btn-danger btn-sm">✕</button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default ExpenseDashboard;
