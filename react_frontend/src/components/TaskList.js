import React, { useState, useEffect } from "react";
import { taskAPI } from "../services/api";

const TaskList = () => {
  const [tasks, setTasks] = useState([]);
  const [formData, setFormData] = useState({ title: "", description: "", priority: "medium", status: "todo" });
  const [filters, setFilters] = useState({ status: "", priority: "" });
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState(null);

  useEffect(() => { fetchTasks(); }, [filters]);

  const fetchTasks = async () => { try { const p = {}; if (filters.status) p.status = filters.status; if (filters.priority) p.priority = filters.priority; const r = await taskAPI.list(p); setTasks(r.data); } catch {} };
  const showToast = (msg, type = "info") => { setToast({ msg, type }); setTimeout(() => setToast(null), 4000); };

  const handleSubmit = async (e) => {
    e.preventDefault(); setLoading(true);
    try { const r = await taskAPI.create(formData); showToast(`Task created! AI priority: ${r.data.priority}`, "success"); setFormData({ title: "", description: "", priority: "medium", status: "todo" }); fetchTasks(); }
    catch { showToast("Error.", "error"); } setLoading(false);
  };

  const handleStatusChange = async (id, s) => { try { const t = tasks.find(t => t.id === id); await taskAPI.update(id, { ...t, status: s }); fetchTasks(); } catch {} };
  const handleDelete = async (id) => { try { await taskAPI.delete(id); fetchTasks(); } catch {} };

  const counts = { total: tasks.length, todo: tasks.filter(t => t.status === "todo").length, active: tasks.filter(t => t.status === "in_progress").length, done: tasks.filter(t => t.status === "done").length };

  return (
    <div className="animate-in">
      <div className="page-header"><h1 className="page-title">Tasks</h1><p className="page-subtitle">AI-powered priority suggestions for every task</p></div>
      {toast && <div className={`toast toast-${toast.type}`}>{toast.type === "success" ? "✨" : "⚠"} {toast.msg}</div>}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 24 }}>
        {[{ l: "Total", v: counts.total, c: "var(--text-primary)" }, { l: "To Do", v: counts.todo, c: "var(--info)" }, { l: "Active", v: counts.active, c: "var(--warning)" }, { l: "Done", v: counts.done, c: "var(--success)" }].map(s => (
          <div key={s.l} className="stat-card"><div className="stat-value" style={{ color: s.c }}>{s.v}</div><div className="stat-label">{s.l}</div></div>
        ))}
      </div>

      <div className="card" style={{ marginBottom: 20 }}>
        <div className="card-header"><div><div className="card-title">New Task</div><div className="card-subtitle">Priority auto-suggested by AI</div></div></div>
        <form onSubmit={handleSubmit}>
          <div className="grid-2">
            <div className="form-group"><label className="form-label">Title</label><input className="input" name="title" placeholder="Fix auth bug" value={formData.title} onChange={(e) => setFormData({ ...formData, title: e.target.value })} required /></div>
            <div className="form-group"><label className="form-label">Description</label><textarea className="textarea" name="description" placeholder="Details..." value={formData.description} onChange={(e) => setFormData({ ...formData, description: e.target.value })} rows={1} /></div>
          </div>
          <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
            <select className="select" name="priority" value={formData.priority} onChange={(e) => setFormData({ ...formData, priority: e.target.value })} style={{ width: 130 }}>
              <option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option>
            </select>
            <select className="select" name="status" value={formData.status} onChange={(e) => setFormData({ ...formData, status: e.target.value })} style={{ width: 150 }}>
              <option value="todo">To Do</option><option value="in_progress">In Progress</option><option value="done">Done</option>
            </select>
            <button type="submit" disabled={loading} className="btn btn-primary">{loading ? <><div className="spinner" /> Creating...</> : "+ Create"}</button>
          </div>
        </form>
      </div>

      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        <select className="select" value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value })} style={{ width: 150 }}>
          <option value="">All Statuses</option><option value="todo">To Do</option><option value="in_progress">Active</option><option value="done">Done</option>
        </select>
        <select className="select" value={filters.priority} onChange={(e) => setFilters({ ...filters, priority: e.target.value })} style={{ width: 150 }}>
          <option value="">All Priorities</option><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option>
        </select>
      </div>

      <div className="card">
        {tasks.length === 0 ? <div className="empty-state"><div className="empty-state-icon">✅</div><div className="empty-state-text">No tasks yet</div></div> : (
          <div style={{ display: "grid", gap: 4 }}>
            {tasks.map(t => (
              <div key={t.id} style={{ padding: "10px 14px", borderRadius: 10, background: "var(--bg-tertiary)", display: "flex", alignItems: "center", gap: 12, opacity: t.status === "done" ? 0.5 : 1 }}>
                <div className={`status-dot ${t.priority}`} />
                <div style={{ flex: 1 }}><div style={{ fontSize: 13, fontWeight: 500 }}>{t.title}</div>{t.description && <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>{t.description.substring(0, 80)}</div>}</div>
                <select value={t.status} onChange={(e) => handleStatusChange(t.id, e.target.value)} className="select" style={{ width: 110, padding: "5px 10px", fontSize: 11 }}>
                  <option value="todo">To Do</option><option value="in_progress">Active</option><option value="done">Done</option>
                </select>
                <span className={`badge badge-${t.priority}`}>{t.priority}</span>
                <button onClick={() => handleDelete(t.id)} className="btn btn-danger btn-sm">✕</button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default TaskList;
