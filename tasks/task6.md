# Task 6: React Frontend Structure & Authentication

## Objective
Set up React frontend with Vite, configure routing, simple username-based authentication (no password), and create the basic layout structure.

---

## 1. Frontend Project Setup

The frontend project has already been initialized with Vite. Verify the structure:

```bash
cd frontend/video-compilation2.0
npm list  # Check installed dependencies
```

**Expected dependencies (from task1.md):**
- react, react-dom
- react-router-dom
- @tanstack/react-query
- axios
- tailwindcss
- lucide-react (for icons)

### Install shadcn/ui Components

```bash
cd frontend/video-compilation2.0
npx shadcn@latest add button input form label card badge sonner spinner skeleton
```

**Components installed:**
- `button` - Buttons for forms and actions
- `input` - Text inputs for forms
- `form` - Form wrapper with validation
- `label` - Labels for form fields
- `card` - Card containers for content
- `badge` - Badges for status/roles
- `sonner` - Toast notifications
- `spinner` - Loading spinner
- `skeleton` - Loading skeleton placeholders

---

## 2. Configure API Client

**File: `frontend/video-compilation2.0/src/services/api.js`**

```javascript
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

// Add user_id to requests if logged in
apiClient.interceptors.request.use((config) => {
  const user = JSON.parse(localStorage.getItem('user') || 'null')

  if (user?.id) {
    // Add user_id as query param (backend expects this)
    config.params = {
      ...config.params,
      user_id: user.id
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

// Jobs API
export const jobsApi = {
  getAll: () => apiClient.get('/jobs'),
  getById: (jobId) => apiClient.get(`/jobs/${jobId}`),
  create: (data) => apiClient.post('/jobs', data),
  cancel: (jobId) => apiClient.post(`/jobs/${jobId}/cancel`)
}

export default apiClient
```

---

## 3. Authentication Hook

**File: `frontend/video-compilation2.0/src/hooks/useAuth.jsx`**

```javascript
import { useState, useEffect, createContext, useContext } from 'react'
import { authApi } from '../services/api'

const AuthContext = createContext({})

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // Check for stored user on mount
    const initAuth = async () => {
      try {
        const storedUser = localStorage.getItem('user')
        if (storedUser) {
          const parsed = JSON.parse(storedUser)
          // Verify user still exists in backend
          const response = await authApi.getCurrentUser(parsed.id)
          setUser(response.data)
          localStorage.setItem('user', JSON.stringify(response.data))
        }
      } catch (error) {
        console.error('Auth init error:', error)
        localStorage.removeItem('user')
      } finally {
        setLoading(false)
      }
    }

    initAuth()
  }, [])

  const login = async (username) => {
    const response = await authApi.login(username)
    const userData = response.data.user
    setUser(userData)
    localStorage.setItem('user', JSON.stringify(userData))
    return userData
  }

  const logout = async () => {
    try {
      await authApi.logout()
    } catch (error) {
      // Ignore logout errors
    }
    setUser(null)
    localStorage.removeItem('user')
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => useContext(AuthContext)
```

**Note:** The `user` object contains all profile data including `role`, `username`, and `display_name` directly (no separate `profile` object).

---

## 4. Protected Route Component

**File: `frontend/video-compilation2.0/src/components/ProtectedRoute.jsx`**

```javascript
import { Navigate } from 'react-router-dom'
import { Spinner } from '@/components/ui/spinner'
import { useAuth } from '../hooks/useAuth'

export default function ProtectedRoute({ children, adminOnly = false }) {
  const { user, loading } = useAuth()

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Spinner size="lg" />
      </div>
    )
  }

  if (!user) {
    return <Navigate to="/login" replace />
  }

  if (adminOnly && user?.role !== 'admin') {
    return <Navigate to="/" replace />
  }

  return children
}
```

---

## 5. App Router Setup

**File: `frontend/video-compilation2.0/src/App.jsx`**

```javascript
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from '@/components/ui/sonner'
import { AuthProvider } from './hooks/useAuth'
import ProtectedRoute from './components/ProtectedRoute'

// Pages
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import NewCompilation from './pages/NewCompilation'
import History from './pages/History'
import CompilationDetails from './pages/CompilationDetails'
import Admin from './pages/Admin'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
      staleTime: 5 * 60 * 1000 // 5 minutes
    }
  }
})

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Toaster position="top-right" richColors />
          <Routes>
            {/* Public routes */}
            <Route path="/login" element={<Login />} />

            {/* Protected routes */}
            <Route
              path="/"
              element={
                <ProtectedRoute>
                  <Dashboard />
                </ProtectedRoute>
              }
            />
            <Route
              path="/new"
              element={
                <ProtectedRoute>
                  <NewCompilation />
                </ProtectedRoute>
              }
            />
            <Route
              path="/history"
              element={
                <ProtectedRoute>
                  <History />
                </ProtectedRoute>
              }
            />
            <Route
              path="/compilation/:jobId"
              element={
                <ProtectedRoute>
                  <CompilationDetails />
                </ProtectedRoute>
              }
            />

            {/* Admin only routes */}
            <Route
              path="/admin"
              element={
                <ProtectedRoute adminOnly>
                  <Admin />
                </ProtectedRoute>
              }
            />

            {/* Catch all */}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  )
}

export default App
```

---

## 6. Layout Component

**File: `frontend/video-compilation2.0/src/components/Layout.jsx`**

```javascript
import { Link, useNavigate } from 'react-router-dom'
import { Badge } from '@/components/ui/badge'
import { useAuth } from '../hooks/useAuth'
import { LogOut, Home, FileVideo, History, Settings } from 'lucide-react'

export default function Layout({ children }) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const handleLogout = async () => {
    await logout()
    navigate('/login')
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white shadow">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center gap-8">
              <h1 className="text-xl font-bold text-gray-900">
                YBH Compilation Tool
              </h1>

              {/* Navigation */}
              <nav className="flex gap-4">
                <Link
                  to="/"
                  className="flex items-center gap-2 px-3 py-2 rounded-md text-sm font-medium text-gray-700 hover:bg-gray-100"
                >
                  <Home size={18} />
                  Dashboard
                </Link>
                <Link
                  to="/new"
                  className="flex items-center gap-2 px-3 py-2 rounded-md text-sm font-medium text-gray-700 hover:bg-gray-100"
                >
                  <FileVideo size={18} />
                  New Compilation
                </Link>
                <Link
                  to="/history"
                  className="flex items-center gap-2 px-3 py-2 rounded-md text-sm font-medium text-gray-700 hover:bg-gray-100"
                >
                  <History size={18} />
                  History
                </Link>
                {user?.role === 'admin' && (
                  <Link
                    to="/admin"
                    className="flex items-center gap-2 px-3 py-2 rounded-md text-sm font-medium text-gray-700 hover:bg-gray-100"
                  >
                    <Settings size={18} />
                    Admin
                  </Link>
                )}
              </nav>
            </div>

            {/* User menu */}
            <div className="flex items-center gap-4">
              <div className="text-sm">
                <span className="text-gray-500">Logged in as </span>
                <span className="font-medium text-gray-900">
                  {user?.display_name || user?.username}
                </span>
                {user?.role === 'admin' && (
                  <Badge variant="secondary" className="ml-2">
                    Admin
                  </Badge>
                )}
              </div>
              <button
                onClick={handleLogout}
                className="flex items-center gap-2 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100 rounded-md"
              >
                <LogOut size={18} />
                Logout
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {children}
      </main>
    </div>
  )
}
```

---

## 7. Login Page

**File: `frontend/video-compilation2.0/src/pages/Login.jsx`**

```javascript
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useAuth } from '../hooks/useAuth'
import { Video, ArrowRight, User } from 'lucide-react'

export default function Login() {
  const [username, setUsername] = useState('')
  const [loading, setLoading] = useState(false)

  const { login } = useAuth()
  const navigate = useNavigate()

  const handleSubmit = async (e) => {
    e.preventDefault()

    if (!username.trim()) {
      toast.error('Please enter your username')
      return
    }

    setLoading(true)

    try {
      await login(username.trim())
      toast.success('Welcome back!')
      navigate('/')
    } catch (err) {
      const message = err.response?.data?.detail || 'Login failed. User not found.'
      toast.error(message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4 relative overflow-hidden bg-background">
      {/* Background Elements */}
      <div className="absolute inset-0 z-0">
        <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] rounded-full bg-primary/10 blur-[100px]" />
        <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] rounded-full bg-secondary/20 blur-[100px]" />
      </div>

      <Card className="w-full mx-auto max-w-md bg-card/40 backdrop-blur-xl border-border/50 shadow-2xl relative z-10 animate-in fade-in zoom-in duration-500 slide-in-from-bottom-4">
        <CardHeader className="text-center space-y-2 pb-6">
          <div className="mx-auto w-12 h-12 bg-primary/10 rounded-xl flex items-center justify-center mb-2 ring-1 ring-primary/20">
            <Video className="w-6 h-6 text-primary" />
          </div>
          <CardTitle className="text-3xl font-bold tracking-tight text-foreground">
            YBH Compilation
          </CardTitle>
          <CardDescription className="text-base text-muted-foreground">
            Enter your username to access the dashboard
          </CardDescription>
        </CardHeader>

        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-6">
            <div className="space-y-2">
              <Label htmlFor="username" className="text-sm font-medium text-foreground">Username</Label>
              <div className="relative">
                <User className="absolute left-3 top-2.5 h-5 w-5 text-muted-foreground" />
                <Input
                  id="username"
                  name="username"
                  type="text"
                  autoComplete="username"
                  required
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="Enter your username"
                  className="pl-10 h-11 bg-background/50 border-input focus:ring-2 focus:ring-ring transition-all"
                  autoFocus
                />
              </div>
            </div>

            <Button
              type="submit"
              disabled={loading}
              className="w-full h-11 text-base font-medium shadow-lg hover:shadow-xl transition-all duration-300"
            >
              {loading ? (
                'Signing in...'
              ) : (
                <span className="flex items-center gap-2">
                  Sign in <ArrowRight className="w-4 h-4" />
                </span>
              )}
            </Button>
          </form>

          <p className="mt-6 text-center text-sm text-muted-foreground">
            Contact admin if you need access
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
```

---

## 8. Update Environment Variables

**File: `frontend/video-compilation2.0/.env`**

```env
VITE_API_URL=http://192.168.1.x:8000/api
```

---

## 9. Update Tailwind Config

**File: `frontend/video-compilation2.0/tailwind.config.js`**

```javascript
/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {},
  },
  plugins: [],
}
```

**File: `frontend/video-compilation2.0/src/index.css`**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

---

## Checklist

- [ ] shadcn/ui components installed (button, input, form, label, card, badge, sonner, spinner, skeleton)
- [ ] API client with user_id interceptor and toast notifications
- [ ] AuthProvider and useAuth hook created (username-only login, no password)
- [ ] ProtectedRoute component with loading spinner
- [ ] Router setup with all routes
- [ ] Layout component with navigation and badge (uses `user.role`)
- [ ] Login page with username-only input
- [ ] Sonner toast notifications configured
- [ ] Environment variables set (VITE_API_URL)
- [ ] Tailwind CSS configured
- [ ] Test login flow with username

---

## Next: Task 7
Build the main compilation workflow pages: Dashboard, New Compilation form, and sequence editor.
