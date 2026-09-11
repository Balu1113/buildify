import axiosInstance from './axios';

export const todoApi = {
  list: (params) => axiosInstance.get('/todos/', { params }),
  get: (id) => axiosInstance.get(`/todos/${id}/`),
  create: (data) => axiosInstance.post('/todos/', data),
  update: (id, data) => axiosInstance.put(`/todos/${id}/`, data),
  delete: (id) => axiosInstance.delete(`/todos/${id}/`),
  getDashboard: () => axiosInstance.get('/todos/dashboard/'),
};