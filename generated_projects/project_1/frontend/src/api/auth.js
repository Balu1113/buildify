import axiosInstance from './axios';

export const authApi = {
  login: (credentials) => axiosInstance.post('/auth/login/', credentials),
  register: (userData) => axiosInstance.post('/auth/register/', userData),
  logout: (refreshToken) => axiosInstance.post('/auth/logout/', { refresh: refreshToken }),
  getMe: () => axiosInstance.get('/auth/user/'),
  refreshToken: (token) => axiosInstance.post('/auth/token/refresh/', { refresh: token }),
};