import axios from 'axios'

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// Request interceptor to add auth token
api.interceptors.request.use(
  config => {
    const token = localStorage.getItem('auth_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  error => Promise.reject(error)
)

export interface User {
  id: string
  username: string
  email: string
  full_name?: string
  role: 'admin' | 'researcher' | 'viewer'
  is_active: boolean
}

export interface LoginRequest {
  username: string
  password: string
}

export interface RegisterRequest {
  username: string
  email: string
  password: string
  full_name?: string
}

export interface AuthResponse {
  access_token: string
  token_type: string
  user: User
}

export const authApi = {
  login: (data: LoginRequest) => {
    const formData = new URLSearchParams()
    formData.append('username', data.username)
    formData.append('password', data.password)
    return api.post<AuthResponse>('/auth/login', formData.toString(), {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
    })
  },

  register: (data: RegisterRequest) =>
    api.post<AuthResponse>('/auth/register', data),

  getMe: () =>
    api.get<User>('/auth/me'),

  changePassword: (oldPassword: string, newPassword: string) =>
    api.post('/auth/change-password', { old_password: oldPassword, new_password: newPassword }),

  listUsers: () =>
    api.get<User[]>('/auth/users'),

  updateUserRole: (userId: string, role: string) =>
    api.put(`/auth/users/${userId}/role`, null, { params: { role } }),

  deleteUser: (userId: string) =>
    api.delete(`/auth/users/${userId}`)
}

export default api
