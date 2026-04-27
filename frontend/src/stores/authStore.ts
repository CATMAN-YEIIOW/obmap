import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { authApi, User, LoginRequest, RegisterRequest } from '../services/auth'

interface AuthState {
  user: User | null
  token: string | null
  isAuthenticated: boolean
  isLoading: boolean
  error: string | null

  login: (data: LoginRequest) => Promise<void>
  register: (data: RegisterRequest) => Promise<void>
  logout: () => void
  checkAuth: () => Promise<void>
  clearError: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      token: null,
      isAuthenticated: false,
      isLoading: false,
      error: null,

      login: async (data: LoginRequest) => {
        set({ isLoading: true, error: null })
        try {
          const response = await authApi.login(data)
          const { access_token, user } = response.data
          set({
            user,
            token: access_token,
            isAuthenticated: true,
            isLoading: false
          })
          // Set auth header for future requests
          localStorage.setItem('auth_token', access_token)
        } catch (error: any) {
          set({
            error: error.response?.data?.detail || '登录失败',
            isLoading: false
          })
          throw error
        }
      },

      register: async (data: RegisterRequest) => {
        set({ isLoading: true, error: null })
        try {
          const response = await authApi.register(data)
          const { access_token, user } = response.data
          set({
            user,
            token: access_token,
            isAuthenticated: true,
            isLoading: false
          })
          localStorage.setItem('auth_token', access_token)
        } catch (error: any) {
          set({
            error: error.response?.data?.detail || '注册失败',
            isLoading: false
          })
          throw error
        }
      },

      logout: () => {
        set({
          user: null,
          token: null,
          isAuthenticated: false,
          error: null
        })
        localStorage.removeItem('auth_token')
      },

      checkAuth: async () => {
        const token = localStorage.getItem('auth_token')
        if (!token) {
          set({ isAuthenticated: false })
          return
        }

        try {
          const response = await authApi.getMe()
          set({
            user: response.data,
            token,
            isAuthenticated: true
          })
        } catch {
          localStorage.removeItem('auth_token')
          set({
            user: null,
            token: null,
            isAuthenticated: false
          })
        }
      },

      clearError: () => {
        set({ error: null })
      }
    }),
    {
      name: 'auth-storage',
      partialize: (state) => ({
        user: state.user,
        token: state.token,
        isAuthenticated: state.isAuthenticated
      })
    }
  )
)
