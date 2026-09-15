import React, { useState, useEffect, useRef } from "react";
import { projectAPI, taskAPI, pipelineAPI, generatedAPI } from "../services/api";
import CodeMirror from "@uiw/react-codemirror";
import { python } from "@codemirror/lang-python";
import { javascript } from "@codemirror/lang-javascript";
import { html } from "@codemirror/lang-html";
import { css } from "@codemirror/lang-css";
import { oneDark } from "@codemirror/theme-one-dark";
import Terminal from "./Terminal";

const STAGES = ["planning", "developing", "testing", "debugging", "reviewing", "completed"];
const STAGE_ICONS = { planning: "📋", developing: "🔨", testing: "🧪", debugging: "🐛", reviewing: "👁️", completed: "✨", failed: "❌" };
const FILE_ICONS = { py: "🐍", js: "📜", jsx: "⚛️", ts: "📘", html: "🌐", css: "🎨", json: "📋", txt: "📄", md: "📝", tsx: "⚛️" };
const AI_MODELS = [
  {
    provider: "Google",
    models: [
      { value: "gemini-2.5-flash", label: "Gemini 2.5 Flash" },
      { value: "gemini-2.5-flash-lite", label: "Gemini 2.5 Flash Lite" },
      { value: "gemini-2.5-pro", label: "Gemini 2.5 Pro" },
      { value: "gemini-2.0-flash", label: "Gemini 2.0 Flash" },
      { value: "gemini-3-flash", label: "Gemini 3 Flash" },
      { value: "gemini-3.1-flash-lite", label: "Gemini 3.1 Flash Lite" },
      { value: "gemini-3.5-flash", label: "Gemini 3.5 Flash" },
      { value: "gemini-3.6-flash", label: "Gemini 3.6 Flash" },
      { value: "gemini-3.7-flash", label: "Gemini 3.7 Flash" },
      { value: "gemini-3.8-flash", label: "Gemini 3.8 Flash" },
      { value: "gemma-4-26b", label: "Gemma 4 26B" },
      { value: "gemma-4-31b", label: "Gemma 4 31B" },
    ],
  },
  {
    provider: "Groq",
    models: [
      { value: "openai/gpt-oss-120b", label: "GPT OSS 120B" },
      { value: "openai/gpt-oss-20b", label: "GPT OSS 20B (Fast)" },
    ],
  },
  {
    provider: "OpenRouter",
    models: [
      { value: "deepseek/deepseek-chat-v3.1", label: "DeepSeek Chat V3.1" },
      { value: "nex-agi/nex-n2.5-pro:free", label: "Nex AGI N2.5 Pro (Free)" },
      { value: "google/gemini-2.5-flash", label: "Google Gemini 2.5 Flash" },
      { value: "openai/gpt-4.1-mini", label: "OpenAI GPT-4.1 Mini" },
      { value: "meta-llama/llama-3.3-70b-instruct", label: "Meta Llama 3.3 70B Instruct" },
      { value: "mistralai/mistral-small-3.1-24b-instruct", label: "Mistral Small 3.1 24B Instruct" },
      { value: "poolside/poolside-laguna-s-2.1", label: "Poolside Laguna S 2.1" },
      { value: "poolside/poolside-laguna-xs-2.1", label: "Poolside Laguna XS 2.1" },
      { value: "cohere/north-mini-code", label: "Cohere North Mini Code" },
      { value: "dots3/dots3-note", label: "Dots3-Note" },
      { value: "thinking-machines/inkling", label: "Thinking Machines Inkling" },
    ],
  },
];

const ModelProviderSelector = ({ value, onChange, disabled = false }) => {
  const selectedGroup = AI_MODELS.find((group) => group.models.some((model) => model.value === value)) || AI_MODELS[0];
  const [selectedProvider, setSelectedProvider] = useState(selectedGroup.provider);

  useEffect(() => {
    const matchedGroup = AI_MODELS.find((group) => group.models.some((model) => model.value === value)) || AI_MODELS[0];
    setSelectedProvider(matchedGroup.provider);
  }, [value]);

  const activeGroup = AI_MODELS.find((group) => group.provider === selectedProvider) || AI_MODELS[0];
  const activeOptions = activeGroup.models;
  const selectedModel = activeOptions.some((model) => model.value === value) ? value : activeOptions[0]?.value;

  useEffect(() => {
    if (!disabled && selectedModel !== value) {
      onChange(selectedModel);
    }
  }, [selectedModel, value, disabled, onChange]);

  const handleProviderChange = (nextProvider) => {
    const nextGroup = AI_MODELS.find((group) => group.provider === nextProvider) || AI_MODELS[0];
    const nextModel = nextGroup.models[0]?.value;
    setSelectedProvider(nextProvider);
    if (nextModel) onChange(nextModel);
  };

  return (
    <div style={{ display: "grid", gap: 8 }}>
      <select
        className="input"
        value={selectedProvider}
        onChange={(e) => handleProviderChange(e.target.value)}
        disabled={disabled}
        aria-label="AI provider"
      >
        {AI_MODELS.map((group) => (
          <option key={group.provider} value={group.provider}>{group.provider}</option>
        ))}
      </select>

      <select
        className="input"
        value={selectedModel}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        aria-label="AI model"
      >
        {activeOptions.map((model) => (
          <option key={model.value} value={model.value}>{model.label}</option>
        ))}
      </select>
    </div>
  );
};

const getLang = (path) => {
  const ext = path.split(".").pop();
  if (ext === "py") return [python()];
  if (ext === "js" || ext === "jsx" || ext === "ts" || ext === "tsx") return [javascript()];
  if (ext === "html" || ext === "htm") return [html()];
  if (ext === "css") return [css()];
  return [];
};

const buildFileTree = (files) => {
  const tree = {};
  files.forEach((f) => {
    const parts = f.path.split(/[/\\]/);
    let current = tree;
    parts.forEach((part, i) => {
      if (i === parts.length - 1) {
        current[part] = { _file: true, size: f.size, path: f.path };
      } else {
        if (!current[part]) current[part] = {};
        current = current[part];
      }
    });
  });
  return tree;
};

const FileTree = ({ tree, selectedFile, onSelect, depth = 0 }) => {
  const [openFolders, setOpenFolders] = useState(() => {
    const initial = {};
    const walk = (node, prefix) => {
      Object.keys(node).sort((a, b) => {
        const aIsFile = node[a]._file;
        const bIsFile = node[b]._file;
        if (aIsFile !== bIsFile) return aIsFile ? 1 : -1;
        return a.localeCompare(b);
      }).forEach((key) => {
        if (!node[key]._file) {
          initial[prefix + key] = depth < 2;
          walk(node[key], prefix + key + "/");
        }
      });
    };
    walk(tree, "");
    return initial;
  });

  const toggleFolder = (path) => setOpenFolders((prev) => ({ ...prev, [path]: !prev[path] }));

  const entries = Object.keys(tree).sort((a, b) => {
    const aIsFile = tree[a]._file;
    const bIsFile = tree[b]._file;
    if (aIsFile !== bIsFile) return aIsFile ? 1 : -1;
    return a.localeCompare(b);
  });

  return (
    <>
      {entries.map((name) => {
        const item = tree[name];
        if (item._file) {
          const ext = name.split(".").pop();
          return (
            <div key={item.path} onClick={() => onSelect(item.path)} className={`file-item ${selectedFile === item.path ? "active" : ""}`} style={{ paddingLeft: 8 + depth * 16 }}>
              <span className="file-icon">{FILE_ICONS[ext] || "📄"}</span>
              <span style={{ flex: 1, fontSize: 12 }}>{name}</span>
              <span className="file-size">{item.size > 1024 ? `${(item.size / 1024).toFixed(1)}k` : `${item.size}B`}</span>
            </div>
          );
        }
        const folderPath = name;
        const isOpen = openFolders[folderPath];
        return (
          <div key={folderPath}>
            <div onClick={() => toggleFolder(folderPath)} className="file-item" style={{ paddingLeft: 8 + depth * 16, cursor: "pointer", userSelect: "none" }}>
              <span style={{ fontSize: 10, width: 12, display: "inline-block", textAlign: "center", transition: "transform 0.2s", transform: isOpen ? "rotate(90deg)" : "rotate(0deg)" }}>▶</span>
              <span className="file-icon">{isOpen ? "📂" : "📁"}</span>
              <span style={{ flex: 1, fontSize: 12, fontWeight: 500 }}>{name}</span>
            </div>
            {isOpen && (
              <div className="file-tree-folder" style={{ borderLeft: "1px solid var(--border)", marginLeft: 8 + depth * 16 + 6 }}>
                <FileTree tree={item} selectedFile={selectedFile} onSelect={onSelect} depth={depth + 1} />
              </div>
            )}
          </div>
        );
      })}
    </>
  );
};

const ProjectList = () => {
  const [projects, setProjects] = useState([]);
  const [formData, setFormData] = useState({ name: "", description: "", ai_model: "deepseek/deepseek-chat-v3.1" });
  const [selectedAiModel, setSelectedAiModel] = useState("deepseek/deepseek-chat-v3.1");
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState(null);
  const [selectedProject, setSelectedProject] = useState(null);
  const [pipeline, setPipeline] = useState(null);
  const [tasks, setTasks] = useState([]);
  const [files, setFiles] = useState([]);
  const [selectedFile, setSelectedFile] = useState(null);
  const [fileContent, setFileContent] = useState("");
  const [runInfo, setRunInfo] = useState(null);
  const [terminalInfo, setTerminalInfo] = useState(null);
  const [preparationStatus, setPreparationStatus] = useState(null);
  const [runState, setRunState] = useState({ status: "idle", port: null });
  const [editorContent, setEditorContent] = useState("");
  const [fileTab, setFileTab] = useState("view");
  const [modifyPrompt, setModifyPrompt] = useState("");
  const [modifyLoading, setModifyLoading] = useState(false);
  const [modifyHistory, setModifyHistory] = useState([]);
  const [applyChatChanges, setApplyChatChanges] = useState(false);
  const logRef = useRef(null);
  const pollRef = useRef(null);
  const runPollRef = useRef(null);
  const modifyEndRef = useRef(null);
  const autoRunProjectRef = useRef(null);
  const previewSignatureRef = useRef(null);

  useEffect(() => { fetchProjects(); return () => { if (pollRef.current) clearInterval(pollRef.current); if (runPollRef.current) clearInterval(runPollRef.current); }; }, []);

  const showToast = (msg, type = "info") => { setToast({ msg, type }); setTimeout(() => setToast(null), 5000); };
  const fetchProjects = async () => { try { const r = await projectAPI.list(); setProjects(r.data); } catch {} };
  const fetchTasks = async (pid) => { try { const r = await taskAPI.list({ project_id: pid }); setTasks(r.data); } catch {} };
  const fetchPipeline = async (pid) => { try { const r = await pipelineAPI.getByProject(pid); if (r.data?.length) { setPipeline(r.data[0]); return r.data[0]; } } catch {} return null; };
  const fetchFiles = async (pid) => { try { const r = await generatedAPI.files(`project_${pid}`); const nextFiles = r.data.files || []; setFiles(nextFiles); return nextFiles; } catch { setFiles([]); return []; } };

  const startPolling = (pid) => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      const p = await fetchPipeline(pid); await fetchTasks(pid); const currentFiles = await fetchFiles(pid);
      if (p && (p.stage === "completed" || p.stage === "failed")) {
        clearInterval(pollRef.current); pollRef.current = null; setLoading(false);
        if (p.stage === "completed") {
          showToast("Build complete. Starting project preview...", "success");
          const completedKey = `${pid}:completed`;
          if (autoRunProjectRef.current !== completedKey) {
            previewSignatureRef.current = null;
            const started = await handleRunForProject(pid, true);
            if (started) {
              autoRunProjectRef.current = completedKey;
              previewSignatureRef.current = currentFiles.map((file) => `${file.path}:${file.updated_at || file.size}`).join("|");
            }
          }
        }
        else showToast("Build stopped. Review the unfinished tasks and retry.", "error");
      } else if (p && currentFiles.length) {
        const activeKey = `${pid}:active`;
        const signature = currentFiles.map((file) => `${file.path}:${file.updated_at || file.size}`).join("|");
        if (autoRunProjectRef.current !== activeKey || previewSignatureRef.current !== signature) {
          const restarted = await handleRunForProject(pid, true);
          if (restarted) {
            autoRunProjectRef.current = activeKey;
            previewSignatureRef.current = signature;
            showToast("Live preview updated from the latest generated files.", "info");
          }
        }
      }
    }, 3000);
  };

  const handleSubmit = async (e) => {
    e.preventDefault(); setLoading(true); setToast(null); setFiles([]); setSelectedFile(null); setRunInfo(null);
    autoRunProjectRef.current = null;
    previewSignatureRef.current = null;
    try {
      const r = await projectAPI.create(formData); setSelectedProject(r.data.id); setSelectedAiModel(formData.ai_model); setFormData({ name: "", description: "", ai_model: formData.ai_model });
      showToast("Project created. AI agents are building...", "info"); fetchProjects(); await fetchTasks(r.data.id);
      setTimeout(async () => { await fetchPipeline(r.data.id); startPolling(r.data.id); }, 2000);
    } catch { showToast("Error creating project.", "error"); setLoading(false); }
  };

  const handleRetry = async () => {
    if (!pipeline) return;
    setLoading(true);
    try {
      await pipelineAPI.start(pipeline.id);
      showToast("Retrying unfinished tasks...", "info");
      await fetchPipeline(selectedProject);
      startPolling(selectedProject);
    } catch (err) {
      setLoading(false);
      showToast(err.response?.data?.error || "Unable to retry the pipeline.", "error");
    }
  };

  const handleStopPipeline = async () => {
    if (!pipeline || pipeline.stage === "completed" || pipeline.stage === "failed") return;
    try {
      await pipelineAPI.stop(pipeline.id);
      showToast("Stop requested. The current agent step will finish first.", "info");
      await fetchPipeline(selectedProject);
    } catch (err) {
      showToast(err.response?.data?.error || "Unable to stop the pipeline.", "error");
    }
  };

  const handleSelect = async (p) => {
    setSelectedProject(p.id); setSelectedAiModel(p.ai_model || "deepseek/deepseek-chat-v3.1"); setSelectedFile(null); setFileContent(""); setRunInfo(null); setFileTab("view"); setModifyHistory([]); setTerminalInfo(null); setPreparationStatus(null);
    autoRunProjectRef.current = null;
    previewSignatureRef.current = null;
    setRunState({ status: "idle", port: null });
    if (runPollRef.current) { clearInterval(runPollRef.current); runPollRef.current = null; }
    await fetchTasks(p.id); const pi = await fetchPipeline(p.id); setPipeline(pi);
    if (pi) await fetchFiles(p.id);
    if (pi && pi.stage !== "completed" && pi.stage !== "failed") { startPolling(p.id); setLoading(true); }
  };
  const handleModelChange = async (value) => {
    const ai_model = value;
    setSelectedAiModel(ai_model);
    if (!selectedProject) return;
    try {
      await projectAPI.patch(selectedProject, { ai_model });
      showToast("AI model updated. It applies to the next pipeline run.", "info");
    } catch {
      showToast("Unable to update the AI model.", "error");
    }
  };

  const handleViewFile = async (path) => {
    try {
      const r = await generatedAPI.readFile(`project_${selectedProject}`, path);
      setSelectedFile(path); setFileContent(r.data.content); setEditorContent(r.data.content); setFileTab("view");
    } catch {}
  };

  const handleCloseFile = () => {
    setSelectedFile(null);
    setFileContent("");
    setEditorContent("");
    setFileTab("view");
    setModifyHistory([]);
    setModifyPrompt("");
  };

  const handleSaveFile = async () => {
    if (!selectedFile) return;
    try {
      const r = await generatedAPI.saveFile(`project_${selectedProject}`, selectedFile, editorContent);
      setFileContent(editorContent); setFiles(r.data.files); showToast("File saved", "success");
    } catch { showToast("Failed to save file", "error"); }
  };

  const handleModify = async () => {
    if (!modifyPrompt.trim()) return;
    const prompt = modifyPrompt.trim();
    setModifyPrompt(""); setModifyLoading(true);
    setModifyHistory((h) => [...h, { role: "user", text: prompt }]);
    try {
      const r = await generatedAPI.chat(`project_${selectedProject}`, prompt, modifyHistory, applyChatChanges, selectedAiModel);
      const data = r.data;
      const recommendations = (data.recommendations || []).map((item) => `${item.priority.toUpperCase()}: ${item.title} (${item.effort})`).join("\n");
      const changed = (data.changed_files || []).join(", ");
      const summary = [data.answer, data.project_assessment, recommendations ? `Recommendations:\n${recommendations}` : "", changed ? `Applied: ${changed}` : ""].filter(Boolean).join("\n\n");
      setModifyHistory((h) => [...h, { role: "ai", text: summary, files: changed }]);
      setFiles(r.data.files);
      if (selectedFile) {
        try {
          const fr = await generatedAPI.readFile(`project_${selectedProject}`, selectedFile);
          setFileContent(fr.data.content); setEditorContent(fr.data.content);
        } catch {}
      }
      showToast(changed ? `Applied: ${changed}` : "Advice received", "success");
    } catch (err) {
      const data = err.response?.data;
      const message = data?.detail || data?.error || "Modification failed. Try again.";
      setModifyHistory((h) => [...h, { role: "ai", text: message }]);
      showToast(message, "error");
    }
    setModifyLoading(false);
  };

  const handleRunForProject = async (projectId, automatic = false) => {
    try {
      setRunState({ status: "starting", port: null });
      setPreparationStatus(null);
      const r = await generatedAPI.run(`project_${projectId}`);
      setTerminalInfo(r.data.terminal || null);
      if (r.data.status === "running") {
        setRunState({ status: "running", port: r.data.port });
        setPreparationStatus(null);
        if (!automatic) showToast(`App running on port ${r.data.port}`, "success");
        startRunPolling();
        return true;
      }
      if (r.data.status === "preparing") {
        setRunState({ status: "starting", port: null });
        setPreparationStatus(r.data);
        if (!automatic) showToast(r.data.message || "Preparing frontend dependencies...", "info");
        startRunPolling();
        return false;
      }
      if (r.data.status === "environment-unavailable") {
        setRunState({ status: "idle", port: null });
        setPreparationStatus(null);
        showToast("Preview unavailable: Node.js/npm is not installed on the server.", "info");
      }
      if (r.data.status === "not-ready") {
        setRunState({ status: "idle", port: null });
        setPreparationStatus(null);
        showToast(r.data.message || "Frontend not yet built. Complete pipeline finalization.", "info");
      }
    } catch (err) {
      setRunState({ status: "idle", port: null });
      setPreparationStatus(null);
      const data = err.response?.data;
      setTerminalInfo(data?.terminal || null);
      if (!automatic) showToast(data?.output || data?.error || "Failed to start app", "error");
    }
    return false;
  };

  const handleRun = async () => {
    await handleRunForProject(selectedProject);
  };

  const handleStop = async () => {
    try {
      await generatedAPI.stop(`project_${selectedProject}`);
      setRunState({ status: "idle", port: null });
      setTerminalInfo(null);
      setPreparationStatus(null);
      if (runPollRef.current) { clearInterval(runPollRef.current); runPollRef.current = null; }
      showToast("App stopped", "info");
    } catch {}
  };

  const startRunPolling = () => {
  if (runPollRef.current) clearInterval(runPollRef.current);

  runPollRef.current = setInterval(async () => {
    try {
      const r = await generatedAPI.status(`project_${selectedProject}`);

      if (r.data.terminal) {
        setTerminalInfo(r.data.terminal);
      }

      // Frontend dependencies are still being installed
      if (r.data.status === "preparing") {
        setPreparationStatus(r.data);
        setRunState({
          status: "starting",
          port: null,
        });
        return;
      }

      // Dependencies finished.
      // Automatically start the project — no refresh/run click required.
      if (r.data.status === "ready") {
        setPreparationStatus({
          ...r.data,
          status: "preparing",
          stage: "starting",
          message: "Dependencies ready. Starting the application...",
        });

        setRunState({
          status: "starting",
          port: null,
        });

        // Stop this polling interval before starting the app.
        clearInterval(runPollRef.current);
        runPollRef.current = null;

        try {
          const runResponse = await generatedAPI.run(
            `project_${selectedProject}`
          );

          if (runResponse.data.terminal) {
            setTerminalInfo(runResponse.data.terminal);
          }

          if (runResponse.data.status === "running") {
            setPreparationStatus(null);

            setRunState({
              status: "running",
              port: runResponse.data.port,
            });

            startRunPolling();

            showToast(
              `App running on port ${runResponse.data.port}`,
              "success"
            );

            return;
          }

          if (runResponse.data.status === "preparing") {
            setPreparationStatus(runResponse.data);
            setRunState({
              status: "starting",
              port: null,
            });

            startRunPolling();
            return;
          }

          throw new Error(
            runResponse.data.error ||
              runResponse.data.message ||
              "Failed to start the application."
          );
        } catch (runError) {
          const data = runError.response?.data;

          setRunState({
            status: "idle",
            port: null,
          });

          setPreparationStatus(null);

          setTerminalInfo(data?.terminal || null);

          showToast(
            data?.output ||
              data?.error ||
              "Failed to start the application.",
            "error"
          );
        }

        return;
      }

      // Application is running
      if (r.data.status === "running") {
        setPreparationStatus(null);

        setRunState({
          status: "running",
          port: r.data.port,
        });

        return;
      }

      // Application stopped
      if (
        r.data.status === "stopped" ||
        r.data.status === "not_running"
      ) {
        setRunState({
          status: "idle",
          port: null,
        });

        setTerminalInfo(null);
        setPreparationStatus(null);

        clearInterval(runPollRef.current);
        runPollRef.current = null;
      }

      // Preparation/start failure
      if (
        r.data.status === "failed" ||
        r.data.status === "environment-unavailable" ||
        r.data.status === "not-ready"
      ) {
        setRunState({
          status: "idle",
          port: null,
        });

        setPreparationStatus(null);

        clearInterval(runPollRef.current);
        runPollRef.current = null;

        showToast(
          r.data.message ||
            r.data.error ||
            "Unable to start the application.",
          "error"
        );
      }
    } catch (error) {
      console.error("Preview status polling failed:", error);

      // Don't immediately kill the UI state because of one
      // temporary network failure.
    }
  }, 2000);
};
  const handleDelete = async (id) => { try { await projectAPI.delete(id); if (selectedProject === id) { setSelectedProject(null); setTasks([]); setPipeline(null); setFiles([]); } fetchProjects(); } catch {} };

  useEffect(() => { if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight; }, [pipeline?.log]);
  useEffect(() => { if (modifyEndRef.current) modifyEndRef.current.scrollIntoView({ behavior: "smooth" }); }, [modifyHistory]);

  const isComplete = pipeline?.stage === "completed";
  const visibleStages = pipeline?.stage === "failed" ? [...STAGES.slice(0, -1), "failed"] : STAGES;
  const pipelineStageIdx = visibleStages.indexOf(pipeline?.stage);
  const unfinishedTaskCount = tasks.filter((task) => task.status !== "done").length;

  return (
    <div className="animate-in">
      <div className="page-header">
        <h1 className="page-title">Projects</h1>
        <p className="page-subtitle">Describe an idea. AI plans, codes, tests, and delivers a working project.</p>
      </div>

      {toast && <div className={`toast toast-${toast.type}`}>{toast.type === "success" ? "✨" : toast.type === "error" ? "⚠" : "💡"} {toast.msg}</div>}

      <div className="card" style={{ marginBottom: 24 }}>
        <div className="card-header">
          <div><div className="card-title">New Project</div><div className="card-subtitle">AI handles everything from here</div></div>
          {loading && <div className="spinner" />}
        </div>
        <form onSubmit={handleSubmit}>
          <div className="grid-2">
            <div className="form-group"><label className="form-label">Name</label><input className="input" name="name" placeholder="My Awesome App" value={formData.name} onChange={(e) => setFormData({ ...formData, name: e.target.value })} required /></div>
            <div className="form-group"><label className="form-label">Description</label><textarea className="textarea" name="description" placeholder="Build a todo app with auth, categories, and a dashboard..." value={formData.description} onChange={(e) => setFormData({ ...formData, description: e.target.value })} rows={2} required /></div>
            <div className="form-group"><label className="form-label">AI model</label><ModelProviderSelector value={formData.ai_model} onChange={(value) => setFormData({ ...formData, ai_model: value })} /></div>
          </div>
          <button type="submit" disabled={loading} className="btn btn-primary btn-lg" style={{ marginTop: 4 }}>
            {loading ? <><div className="spinner" /> Building...</> : "✨ Create & Build with AI"}
          </button>
        </form>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: selectedProject ? "260px 1fr" : "1fr", gap: 20 }}>
        <div className="card">
          <div className="card-header"><div className="card-title">Projects</div><span className="badge" style={{ background: "var(--bg-hover)", color: "var(--text-muted)" }}>{projects.length}</span></div>
          {projects.length === 0 ? (
            <div className="empty-state"><div className="empty-state-icon">📂</div><div className="empty-state-text">No projects yet</div></div>
          ) : (
            <div style={{ display: "grid", gap: 4 }}>
              {projects.map((p) => (
                <div key={p.id} onClick={() => handleSelect(p)} style={{ padding: "12px 14px", borderRadius: 12, cursor: "pointer", background: selectedProject === p.id ? "var(--accent-glow)" : "transparent", border: selectedProject === p.id ? "1px solid var(--accent)" : "1px solid transparent", transition: "all 0.2s ease" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "start" }}>
                    <div><div style={{ fontWeight: 600, fontSize: 13 }}>{p.name}</div><div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 3 }}>{p.description?.substring(0, 40)}...</div></div>
                    <button onClick={(e) => { e.stopPropagation(); handleDelete(p.id); }} className="btn btn-danger btn-sm" style={{ padding: "3px 7px", fontSize: 9 }}>✕</button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {selectedProject && (
          <div className="animate-in">
            {pipeline && (
              <div className="card" style={{ marginBottom: 16 }}>
                <div className="card-header">
                  <div className="card-title">Build Pipeline</div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <div style={{ width: 240 }}>
                      <ModelProviderSelector value={selectedAiModel} onChange={handleModelChange} disabled={pipeline.stage !== "completed" && pipeline.stage !== "failed"} />
                    </div>
                    <span className={`badge badge-${pipeline.stage}`}>{STAGE_ICONS[pipeline.stage]} {pipeline.stage}</span>
                    {pipeline.stage !== "completed" && pipeline.stage !== "failed" ? (
                      <button onClick={handleStopPipeline} disabled={!loading} className="btn btn-danger btn-sm">
                        ⏹ Stop pipeline
                      </button>
                    ) : (pipeline.stage === "failed" || unfinishedTaskCount > 0) && (
                      <button onClick={handleRetry} disabled={loading} className="btn btn-primary btn-sm">
                        {loading ? "Retrying..." : "Continue unfinished"}
                      </button>
                    )}
                  </div>
                </div>
                <div className="pipeline-stages" style={{ marginBottom: 14 }}>
                  {visibleStages.map((s, i) => (
                    <div key={s} data-stage={s} className={`pipeline-stage ${pipeline.stage === s ? "active" : ""} ${i < pipelineStageIdx ? "done" : ""}`}>
                      {STAGE_ICONS[s]} {s.charAt(0).toUpperCase() + s.slice(1)}
                    </div>
                  ))}
                </div>
                {pipeline.current_task && <div style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 6 }}>Working on: <strong>{pipeline.current_task}</strong></div>}
                <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 10 }}>Progress: {pipeline.completed_tasks}/{pipeline.total_tasks} tasks</div>
                {pipeline.stage === "failed" && unfinishedTaskCount > 0 && (
                  <div style={{ fontSize: 12, color: "var(--danger)", marginBottom: 10 }}>
                    {unfinishedTaskCount} task{unfinishedTaskCount === 1 ? "" : "s"} still need{unfinishedTaskCount === 1 ? "s" : ""} work.
                  </div>
                )}
                <div ref={logRef} className="terminal" style={{ height: 200 }}>{pipeline.log || "Initializing..."}</div>
              </div>
            )}

            <div className="card" style={{ marginBottom: 16 }}>
              <div className="card-header"><div className="card-title">Tasks</div><span className="badge" style={{ background: "var(--bg-hover)", color: "var(--text-muted)" }}>{tasks.filter(t => t.status === "done").length}/{tasks.length}</span></div>
              <div style={{ display: "grid", gap: 4 }}>
                {tasks.map((t) => (
                  <div key={t.id} style={{ padding: "9px 14px", borderRadius: 10, background: "var(--bg-tertiary)", display: "flex", alignItems: "center", gap: 10, opacity: t.status === "done" ? 0.5 : 1 }}>
                    <div className={`status-dot ${t.priority}`} />
                    <span style={{ flex: 1, fontSize: 12, fontWeight: 500 }}>{t.title}</span>
                    <span className={`badge badge-${t.priority}`}>{t.priority}</span>
                    <span className={`badge badge-${t.status}`}>{t.status === "in_progress" ? "active" : t.status}</span>
                  </div>
                ))}
              </div>
            </div>

            {pipeline && (isComplete || files.length > 0 || loading) && (
              <div className="card" style={{ minWidth: 0, borderColor: "var(--success)" }}>
                <div className="card-header">
                  <div><div className="card-title" style={{ color: "var(--success)" }}>✨ Generated Project</div><div className="card-subtitle">{files.length ? `${files.length} files written live` : "Agents are creating files..."}</div></div>
                  <div style={{ display: "flex", gap: 8 }}>
                    {isComplete && runState.status === "running" ? (
                      <button onClick={handleStop} className="btn btn-danger">⏹ Stop</button>
                    ) : isComplete && runState.status === "starting" ? (
                      <button disabled className="btn btn-success"><div className="spinner" style={{ width: 14, height: 14, display: "inline-block", marginRight: 6 }} /> Starting...</button>
                    ) : isComplete ? (
                      <button onClick={handleRun} className="btn btn-success">▶ Run Project</button>
                    ) : null}
                  </div>
                </div>
                {(runState.status === "running" || runState.status === "starting") && (
                  <>
                    <Terminal terminalInfo={terminalInfo} preparationStatus={preparationStatus} />
                  </>
                )}
                {runState.status === "running" && runState.port && (
  <div
    style={{
      marginBottom: 16,
      borderRadius: 12,
      overflow: "hidden",
      border: "1px solid var(--border)",
    }}
  >
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "6px 12px",
        background: "var(--bg-tertiary)",
        borderBottom: "1px solid var(--border)",
      }}
    >
      <span
        style={{
          fontSize: 11,
          color: "var(--text-muted)",
        }}
      >
        🌐 Preview
      </span>

      <a
        href={generatedAPI.previewUrl(selectedProject)}
        target="_blank"
        rel="noreferrer"
        style={{
          fontSize: 11,
          color: "var(--accent)",
          textDecoration: "none",
        }}
      >
        ↗ Open in new tab
      </a>
    </div>

    <iframe
      src={generatedAPI.previewUrl(selectedProject)}
      title="Project Preview"
      style={{
        width: "100%",
        height: 400,
        border: "none",
        background: "#fff",
      }}
    />
  </div>
)}
                {files.length > 0 ? (
                  <div style={{ minWidth: 0, display: "grid", gridTemplateColumns: "minmax(0, 260px) minmax(0, 1fr)", gap: 12 }}>
                    <div style={{ maxHeight: 400, overflowY: "auto", background: "var(--bg-tertiary)", borderRadius: 12, padding: 6 }}>
                      <FileTree tree={buildFileTree(files)} selectedFile={selectedFile} onSelect={handleViewFile} />
                    </div>
                    <div>
                      {selectedFile ? (
                        <div className="code-viewer" style={{ display: "flex", flexDirection: "column" }}>
                          <div style={{ display: "flex", borderBottom: "1px solid var(--border)", background: "var(--bg-tertiary)", borderRadius: "12px 12px 0 0", padding: "0 4px" }}>
                            {["view", "edit", "modify"].map((tab) => (
                              <button key={tab} onClick={() => setFileTab(tab)} style={{ padding: "8px 16px", fontSize: 12, fontWeight: 500, border: "none", cursor: "pointer", background: "transparent", color: fileTab === tab ? "var(--accent)" : "var(--text-muted)", borderBottom: fileTab === tab ? "2px solid var(--accent)" : "2px solid transparent", transition: "all 0.2s" }}>
                                {tab === "view" ? "📄 View" : tab === "edit" ? "✏️ Edit" : "🤖 Modify"}
                              </button>
                            ))}
                            <div style={{ flex: 1 }} />
                            {fileTab === "edit" && (
                              <button onClick={handleSaveFile} className="btn btn-primary btn-sm" style={{ margin: "4px 8px 4px 0", padding: "4px 12px", fontSize: 11 }}>💾 Save</button>
                            )}
                          </div>
                          <div className="code-header" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
                            <span>📄 {selectedFile}</span>
                            <button onClick={handleCloseFile} className="btn btn-sm" aria-label={`Close ${selectedFile}`} title="Close file" style={{ padding: "2px 8px", fontSize: 16, lineHeight: 1 }}>×</button>
                          </div>
                          {fileTab === "view" && <pre className="code-content">{fileContent}</pre>}
                          {fileTab === "edit" && (
                            <div style={{ maxHeight: 500, overflow: "auto" }}>
                              <CodeMirror value={editorContent} height="500px" theme={oneDark} extensions={getLang(selectedFile)} onChange={(val) => setEditorContent(val)} />
                            </div>
                          )}
                          {fileTab === "modify" && (
                            <div style={{ display: "flex", flexDirection: "column", height: 500 }}>
                              <div style={{ flex: 1, overflowY: "auto", padding: 12, display: "grid", gap: 8 }}>
                                {modifyHistory.length === 0 && (
                                  <div style={{ textAlign: "center", color: "var(--text-muted)", padding: 40, fontSize: 13 }}>
                                    Ask AI to modify this project. Try: "add error handling", "create a README", "refactor the main function"
                                  </div>
                                )}
                                {modifyHistory.map((m, i) => (
                                  <div key={i} style={{ padding: "8px 12px", borderRadius: 10, background: m.role === "user" ? "var(--accent-glow)" : "var(--bg-tertiary)", border: m.role === "user" ? "1px solid var(--accent)" : "1px solid var(--border)", fontSize: 12 }}>
                                    <div style={{ fontWeight: 600, marginBottom: 4, color: m.role === "user" ? "var(--accent)" : "var(--success)" }}>{m.role === "user" ? "You" : "AI"}</div>
                                    <div style={{ color: "var(--text-primary)", whiteSpace: "pre-wrap" }}>{m.text}</div>
                                    {m.files && <div style={{ marginTop: 6, fontSize: 11, color: "var(--text-muted)" }}>Changed: <code>{m.files}</code></div>}
                                  </div>
                                ))}
                                {modifyLoading && <div style={{ padding: "8px 12px", borderRadius: 10, background: "var(--bg-tertiary)", border: "1px solid var(--border)", fontSize: 12, color: "var(--text-muted)" }}><div className="spinner" style={{ width: 14, height: 14, display: "inline-block", marginRight: 8 }} /> AI is working...</div>}
                                <div ref={modifyEndRef} />
                              </div>
                              <div style={{ display: "flex", gap: 8, padding: 12, borderTop: "1px solid var(--border)" }}>
                                <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: "var(--text-muted)" }}><input type="checkbox" checked={applyChatChanges} onChange={(e) => setApplyChatChanges(e.target.checked)} /> Apply changes</label>
                                <input className="input" style={{ flex: 1 }} placeholder="Ask for features, fixes, or competitor-inspired improvements..." value={modifyPrompt} onChange={(e) => setModifyPrompt(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleModify(); } }} disabled={modifyLoading} />
                                <button onClick={handleModify} className="btn btn-primary btn-sm" disabled={modifyLoading || !modifyPrompt.trim()} style={{ padding: "6px 16px" }}>{modifyLoading ? <div className="spinner" style={{ width: 14, height: 14 }} /> : "Send"}</button>
                              </div>
                            </div>
                          )}
                        </div>
                      ) : (
                        <div style={{ padding: 48, textAlign: "center", color: "var(--text-muted)" }}><div style={{ fontSize: 36, marginBottom: 10, animation: "float 3s ease-in-out infinite" }}>👈</div>Select a file</div>
                      )}
                    </div>
                  </div>
                ) : <div className="empty-state"><div className="empty-state-text">No files generated</div></div>}
              </div>
            )}

            {isComplete && (
              <div className="card" style={{ marginTop: 16, borderColor: "var(--info)" }}>
                <div className="card-header">
                  <div><div className="card-title" style={{ color: "var(--info)" }}>🔧 Modify Project</div><div className="card-subtitle">Ask AI to add features, fix bugs, or restructure your project</div></div>
                </div>
                {modifyHistory.length > 0 && (
                  <div style={{ maxHeight: 300, overflowY: "auto", marginBottom: 12, display: "grid", gap: 8 }}>
                    {modifyHistory.map((m, i) => (
                      <div key={i} style={{ padding: "10px 14px", borderRadius: 10, background: m.role === "user" ? "var(--accent-glow)" : "var(--bg-tertiary)", border: m.role === "user" ? "1px solid var(--accent)" : "1px solid var(--border)", fontSize: 12 }}>
                        <div style={{ fontWeight: 600, marginBottom: 4, color: m.role === "user" ? "var(--accent)" : "var(--success)" }}>{m.role === "user" ? "You" : "AI"}</div>
                        <div style={{ color: "var(--text-primary)", whiteSpace: "pre-wrap" }}>{m.text}</div>
                        {m.files && <div style={{ marginTop: 6, fontSize: 11, color: "var(--text-muted)" }}>Changed: <code>{m.files}</code></div>}
                      </div>
                    ))}
                    {modifyLoading && (
                      <div style={{ padding: "10px 14px", borderRadius: 10, background: "var(--bg-tertiary)", border: "1px solid var(--border)", fontSize: 12, color: "var(--text-muted)" }}>
                        <div className="spinner" style={{ width: 14, height: 14, display: "inline-block", marginRight: 8 }} /> AI is working...
                      </div>
                    )}
                    <div ref={modifyEndRef} />
                  </div>
                )}
                {modifyHistory.length === 0 && (
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 12 }}>
                    {[
                      "Add a README.md file",
                      "Add error handling",
                      "Add input validation",
                      "Improve the UI styling",
                      "Add unit tests",
                      "Add API documentation",
                      "Refactor for better structure",
                      "Add logging",
                    ].map((s) => (
                      <button key={s} onClick={() => setModifyPrompt(s)} className="btn btn-ghost btn-sm" style={{ fontSize: 11, padding: "4px 10px" }}>{s}</button>
                    ))}
                  </div>
                )}
                <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 12 }}>
                  <div style={{ flex: 0 }}><label className="form-label" style={{ marginBottom: 0 }}>AI Model</label><ModelProviderSelector value={selectedAiModel} onChange={handleModelChange} disabled={pipeline.stage !== "completed" && pipeline.stage !== "failed"} /></div>
                  <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: "var(--text-muted)", marginLeft: "auto" }}><input type="checkbox" checked={applyChatChanges} onChange={(e) => setApplyChatChanges(e.target.checked)} /> Apply changes</label>
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                  <input className="input" style={{ flex: 1 }} placeholder="Ask for features, fixes, or competitor-inspired improvements..." value={modifyPrompt} onChange={(e) => setModifyPrompt(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleModify(); } }} disabled={modifyLoading} />
                  <button onClick={handleModify} className="btn btn-primary" disabled={modifyLoading || !modifyPrompt.trim()} style={{ padding: "8px 20px" }}>{modifyLoading ? <div className="spinner" style={{ width: 14, height: 14 }} /> : "🚀 Send"}</button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default ProjectList;
