import axios from "axios";

const API_BASE_URL =
  process.env.REACT_APP_API_BASE_URL || "http://localhost:8000/api";

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: { "Content-Type": "application/json" },
});

api.interceptors.request.use(
  (config) => {
    const access = localStorage.getItem("access_token");
    if (access) {
      config.headers.Authorization = `Bearer ${access}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;
      const refresh = localStorage.getItem("refresh_token");
      if (refresh) {
        try {
          const response = await axios.post(`${API_BASE_URL}/auth/token/refresh/`, { refresh });
          const { access } = response.data;
          localStorage.setItem("access_token", access);
          originalRequest.headers.Authorization = `Bearer ${access}`;
          return api(originalRequest);
        } catch {
          localStorage.removeItem("access_token");
          localStorage.removeItem("refresh_token");
          window.location.href = "/login";
        }
      } else {
        window.location.href = "/login";
      }
    }
    return Promise.reject(error);
  }
);

export const projectAPI = {
  list: () => api.get("/projects/"),
  get: (id) => api.get(`/projects/${id}/`),
  create: (data) => api.post("/projects/", data),
  update: (id, data) => api.put(`/projects/${id}/`, data),
  patch: (id, data) => api.patch(`/projects/${id}/`, data),
  delete: (id) => api.delete(`/projects/${id}/`),
};

export const taskAPI = {
  list: (params = {}) => api.get("/tasks/", { params }),
  get: (id) => api.get(`/tasks/${id}/`),
  create: (data) => api.post("/tasks/", data),
  update: (id, data) => api.put(`/tasks/${id}/`, data),
  delete: (id) => api.delete(`/tasks/${id}/`),
  suggestPriority: (data) => api.post("/tasks/suggest-priority/", data),
};

export const expenseAPI = {
  list: () => api.get("/expenses/"),
  get: (id) => api.get(`/expenses/${id}/`),
  create: (data) => api.post("/expenses/", data),
  update: (id, data) => api.put(`/expenses/${id}/`, data),
  delete: (id) => api.delete(`/expenses/${id}/`),
  parseText: (text) => api.post("/expenses/parse-text/", { text }),
  uploadReceipt: (file) => {
    const formData = new FormData();
    formData.append("file", file);
    return api.post("/expenses/upload/", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },
  getSummary: () => api.get("/expenses/summary/"),
};

export const aiAPI = {
  parseExpense: (text) => api.post("/ai/parse-expense/", { text }),
  planProject: (description) =>
    api.post("/ai/plan-project/", { description }),
  reviewCode: (sourceFiles, testResults = "") =>
    api.post("/ai/review-code/", { source_files: sourceFiles, test_results: testResults }),
};

export const pipelineAPI = {
  list: (params = {}) => api.get("/pipeline/", { params }),
  get: (id) => api.get(`/pipeline/${id}/`),
  getByProject: (projectId) => api.get("/pipeline/", { params: { project_id: projectId } }),
  start: (id) => api.post(`/pipeline/${id}/start/`),
  stop: (id) => api.post(`/pipeline/${id}/stop/`),
};

const normalizeGeneratedProjectId = (projectId) => {
  const value = String(projectId);
  return value.startsWith("project_") ? value : `project_${value}`;
};

export const generatedAPI = {
  list: () => api.get("/ai/generated/"),
  files: (projectId) => api.get(`/ai/generated/${normalizeGeneratedProjectId(projectId)}/files/`),
  readFile: (projectId, filePath) =>
    api.get(`/ai/generated/${normalizeGeneratedProjectId(projectId)}/file/`, {
      params: { file_path: filePath },
    }),
  modify: (projectId, modification, model) =>
    api.post(`/ai/generated/${normalizeGeneratedProjectId(projectId)}/modify/`, {
      modification,
      model,
    }),
  chat: (projectId, message, conversation = [], applyChanges = false, model) =>
    api.post(`/ai/generated/${normalizeGeneratedProjectId(projectId)}/chat/`, {
      message,
      conversation,
      apply_changes: applyChanges,
      model,
    }),
  saveFile: (projectId, filePath, content) =>
    api.put(`/ai/generated/${normalizeGeneratedProjectId(projectId)}/save/`, {
      file_path: filePath,
      content,
    }),
  run: (projectId) =>
    api.post(`/ai/generated/${normalizeGeneratedProjectId(projectId)}/run/`),
  stop: (projectId) =>
    api.post(`/ai/generated/${normalizeGeneratedProjectId(projectId)}/stop/`),
  status: (projectId) =>
    api.get(`/ai/generated/${normalizeGeneratedProjectId(projectId)}/status/`),

  previewUrl: (projectId) =>
    `${API_BASE_URL}/ai/generated/${normalizeGeneratedProjectId(projectId)}/preview/`,
};

export const authAPI = {
  register: (data) => api.post("/auth/register/", data),
  login: (data) => api.post("/auth/login/", data),
  logout: (data) => api.post("/auth/logout/", data),
  profile: () => api.get("/auth/profile/"),
  updateProfile: (data) => api.put("/auth/profile/", data),
  changePassword: (data) => api.post("/auth/change-password/", data),
};

export default api;
