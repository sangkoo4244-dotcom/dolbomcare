import axios from 'axios';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// 요청 인터셉터 - 토큰 추가
apiClient.interceptors.request.use((config) => {
  const token = typeof window !== 'undefined'
    ? localStorage.getItem('access_token')
    : null;

  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }

  return config;
});

// 로그인 API
export const authAPI = {
  login: (email: string, password: string) =>
    apiClient.post('/auth/login', { email, password }),

  register: (email: string, password: string, fullName: string, role: string) =>
    apiClient.post('/auth/register', {
      email,
      password,
      full_name: fullName,
      role,
    }),
};

export default apiClient;
