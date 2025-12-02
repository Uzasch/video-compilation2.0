import axios from 'axios'
import { toast } from 'sonner'

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api'

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// Add user_id to requests if logged in (except admin endpoints which show all users)
apiClient.interceptors.request.use((config) => {
  const user = JSON.parse(localStorage.getItem('user') || 'null')

  if (user?.id) {
    // Skip adding user_id for admin endpoints (they should show all users' data)
    const isAdminEndpoint = config.url?.startsWith('/admin')

    if (!isAdminEndpoint) {
      // Add user_id as query param (backend expects this)
      config.params = {
        ...config.params,
        user_id: user.id
      }
    }
  }

  return config
})

// Handle errors with toast notifications
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      toast.error('Session expired. Please login again.')
      localStorage.removeItem('user')
      window.location.href = '/login'
    } else if (error.response?.status === 403) {
      toast.error('You do not have permission to perform this action.')
    } else if (error.response?.status === 404) {
      toast.error('Resource not found.')
    } else if (error.response?.status >= 500) {
      toast.error('Server error. Please try again later.')
    } else if (error.code === 'ECONNABORTED') {
      toast.error('Request timeout. Please check your connection.')
    } else if (!error.response) {
      toast.error('Network error. Please check your connection.')
    } else {
      const message = error.response?.data?.detail || error.response?.data?.message || 'An error occurred'
      toast.error(message)
    }

    return Promise.reject(error)
  }
)

// Auth API
export const authApi = {
  login: (username) => apiClient.post('/auth/login', { username }),
  logout: () => apiClient.post('/auth/logout'),
  getCurrentUser: (userId) => apiClient.get('/auth/me', { params: { user_id: userId } })
}

// Jobs API (for later use)
export const jobsApi = {
  getAll: () => apiClient.get('/jobs'),
  getById: (jobId) => apiClient.get(`/jobs/${jobId}`),
  create: (data) => apiClient.post('/jobs', data),
  cancel: (jobId) => apiClient.post(`/jobs/${jobId}/cancel`)
}

export default apiClient
