# Task 6: React Frontend Structure & Authentication

## Objective
Set up React frontend with Vite, configure routing, authentication, and create the basic layout structure.

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
- @supabase/supabase-js
- axios
- tailwindcss
- lucide-react (for icons)

### Install shadcn/ui Components

```bash
cd frontend/video-compilation2.0
npx shadcn@latest add @shadcn/button @shadcn/input @shadcn/form @shadcn/label @shadcn/card @shadcn/badge @shadcn/sonner @shadcn/spinner @shadcn/skeleton
```

**Components installed:**
- `button` - Buttons for forms and actions
- `input` - Text inputs for forms
- `form` - Form wrapper with validation
- `label` - Labels for form fields
- `card` - Card containers for content
- `badge` - Badges for status/roles
- `sonner` - Toast notifications (replaces react-hot-toast)
- `spinner` - Loading spinner
- `skeleton` - Loading skeleton placeholders

---

## 2. Configure Supabase Client

Create Supabase client for authentication and data access.

**File: `frontend/video-compilation2.0/src/services/supabase.js`**

```javascript
import { createClient } from '@supabase/supabase-js'

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY

if (!supabaseUrl || !supabaseAnonKey) {
  throw new Error('Missing Supabase environment variables')
}

export const supabase = createClient(supabaseUrl, supabaseAnonKey, {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
  },
  realtime: {
    params: {
      eventsPerSecond: 10
    }
  }
})

// Helper functions
export const getCurrentUser = async () => {
  const { data: { user }, error } = await supabase.auth.getUser()
  if (error) throw error

  // Fetch profile data
  if (user) {
    const { data: profile } = await supabase
      .from('profiles')
      .select('*')
      .eq('id', user.id)
      .single()

    return { ...user, profile }
  }

  return null
}

export const signIn = async (email, password) => {
  const { data, error } = await supabase.auth.signInWithPassword({
    email,
    password
  })
  if (error) throw error
  return data
}

export const signOut = async () => {
  const { error } = await supabase.auth.signOut()
  if (error) throw error
}

export const resetPassword = async (email) => {
  const { error } = await supabase.auth.resetPasswordForEmail(email, {
    redirectTo: `${window.location.origin}/reset-password`,
  })
  if (error) throw error
}

export const updatePassword = async (newPassword) => {
  const { error } = await supabase.auth.updateUser({
    password: newPassword
  })
  if (error) throw error
}
```

---

## 3. Configure API Client

**File: `frontend/video-compilation2.0/src/services/api.js`**

```javascript
import axios from 'axios'
import { toast } from 'sonner'
import { supabase } from './supabase'

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api'

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// Add auth token to requests
apiClient.interceptors.request.use(async (config) => {
  const { data: { session } } = await supabase.auth.getSession()

  if (session?.access_token) {
    config.headers.Authorization = `Bearer ${session.access_token}`
  }

  return config
})

// Handle errors with toast notifications
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    // Handle different error types
    if (error.response?.status === 401) {
      toast.error('Session expired. Please login again.')
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
      // Display custom error message from backend if available
      const message = error.response?.data?.detail || error.response?.data?.message || 'An error occurred'
      toast.error(message)
    }

    return Promise.reject(error)
  }
)

export default apiClient
```

---

## 4. Authentication Hook

**File: `frontend/video-compilation2.0/src/hooks/useAuth.js`**

```javascript
import { useState, useEffect, createContext, useContext } from 'react'
import { supabase, getCurrentUser, signIn, signOut } from '../services/supabase'

const AuthContext = createContext({})

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null)
  const [profile, setProfile] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // Check active session
    const initAuth = async () => {
      try {
        const currentUser = await getCurrentUser()
        setUser(currentUser)
        setProfile(currentUser?.profile)
      } catch (error) {
        console.error('Auth init error:', error)
      } finally {
        setLoading(false)
      }
    }

    initAuth()

    // Listen for auth changes
    const { data: { subscription } } = supabase.auth.onAuthStateChange(async (event, session) => {
      if (event === 'SIGNED_IN' && session?.user) {
        const currentUser = await getCurrentUser()
        setUser(currentUser)
        setProfile(currentUser?.profile)
      } else if (event === 'SIGNED_OUT') {
        setUser(null)
        setProfile(null)
      }
    })

    return () => subscription.unsubscribe()
  }, [])

  const login = async (email, password) => {
    const data = await signIn(email, password)
    const currentUser = await getCurrentUser()
    setUser(currentUser)
    setProfile(currentUser?.profile)
    return data
  }

  const logout = async () => {
    await signOut()
    setUser(null)
    setProfile(null)
  }

  return (
    <AuthContext.Provider value={{ user, profile, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => useContext(AuthContext)
```

---

## 5. Protected Route Component

**File: `frontend/video-compilation2.0/src/components/ProtectedRoute.jsx`**

```javascript
import { Navigate } from 'react-router-dom'
import { Spinner } from '@/components/ui/spinner'
import { useAuth } from '../hooks/useAuth'

export default function ProtectedRoute({ children, adminOnly = false }) {
  const { user, profile, loading } = useAuth()

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

  if (adminOnly && profile?.role !== 'admin') {
    return <Navigate to="/" replace />
  }

  return children
}
```

---

## 6. App Router Setup

**File: `frontend/video-compilation2.0/src/App.jsx`**

```javascript
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from '@/components/ui/sonner'
import { AuthProvider } from './hooks/useAuth'
import ProtectedRoute from './components/ProtectedRoute'

// Pages
import Login from './pages/Login'
import ForgotPassword from './pages/ForgotPassword'
import ResetPassword from './pages/ResetPassword'
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
          <Toaster position="top-right" />
          <Routes>
            {/* Public routes */}
            <Route path="/login" element={<Login />} />
            <Route path="/forgot-password" element={<ForgotPassword />} />
            <Route path="/reset-password" element={<ResetPassword />} />

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

## 7. Layout Component

**File: `frontend/video-compilation2.0/src/components/Layout.jsx`**

```javascript
import { Link, useNavigate } from 'react-router-dom'
import { Badge } from '@/components/ui/badge'
import { useAuth } from '../hooks/useAuth'
import { LogOut, Home, FileVideo, History, Settings } from 'lucide-react'

export default function Layout({ children }) {
  const { profile, logout } = useAuth()
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
                {profile?.role === 'admin' && (
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
                  {profile?.display_name || profile?.username}
                </span>
                {profile?.role === 'admin' && (
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

## 8. Login Page

**File: `frontend/video-compilation2.0/src/pages/Login.jsx`**

```javascript
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useAuth } from '../hooks/useAuth'

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)

  const { login } = useAuth()
  const navigate = useNavigate()

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)

    try {
      await login(email, password)
      toast.success('Welcome back!')
      navigate('/')
    } catch (err) {
      toast.error(err.message || 'Login failed. Please check your credentials.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-md w-full space-y-8">
        <div>
          <h2 className="mt-6 text-center text-3xl font-extrabold text-gray-900">
            YBH Compilation Tool
          </h2>
          <p className="mt-2 text-center text-sm text-gray-600">
            Sign in to your account
          </p>
        </div>

        <form className="mt-8 space-y-6" onSubmit={handleSubmit}>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                name="email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                name="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter your password"
              />
            </div>
          </div>

          <div className="space-y-4">
            <Button type="submit" disabled={loading} className="w-full">
              {loading ? 'Signing in...' : 'Sign in'}
            </Button>
          </div>

          <div className="text-center">
            <Link
              to="/forgot-password"
              className="text-sm text-blue-600 hover:text-blue-500"
            >
              Forgot your password?
            </Link>
          </div>
        </form>
      </div>
    </div>
  )
}
```

---

## 9. Forgot Password Page

**File: `frontend/video-compilation2.0/src/pages/ForgotPassword.jsx`**

```javascript
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { resetPassword } from '../services/supabase'

export default function ForgotPassword() {
  const [email, setEmail] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)

    try {
      await resetPassword(email)
      toast.success('Password reset email sent! Check your inbox.')
      setTimeout(() => navigate('/login'), 2000)
    } catch (err) {
      toast.error(err.message || 'Failed to send reset email.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-md w-full space-y-8">
        <div>
          <h2 className="mt-6 text-center text-3xl font-extrabold text-gray-900">
            Reset your password
          </h2>
          <p className="mt-2 text-center text-sm text-gray-600">
            Enter your email address and we'll send you a link to reset your password
          </p>
        </div>

        <form className="mt-8 space-y-6" onSubmit={handleSubmit}>
          <div className="space-y-2">
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              name="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
            />
          </div>

          <div className="space-y-4">
            <Button type="submit" disabled={loading} className="w-full">
              {loading ? 'Sending...' : 'Send reset link'}
            </Button>
          </div>

          <div className="text-center">
            <Link
              to="/login"
              className="text-sm text-blue-600 hover:text-blue-500"
            >
              Back to login
            </Link>
          </div>
        </form>
      </div>
    </div>
  )
}
```

---

## 10. Reset Password Page

**File: `frontend/video-compilation2.0/src/pages/ResetPassword.jsx`**

```javascript
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { updatePassword } from '../services/supabase'

export default function ResetPassword() {
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  const handleSubmit = async (e) => {
    e.preventDefault()

    if (password !== confirmPassword) {
      toast.error('Passwords do not match')
      return
    }

    if (password.length < 6) {
      toast.error('Password must be at least 6 characters')
      return
    }

    setLoading(true)

    try {
      await updatePassword(password)
      toast.success('Password updated successfully!')
      setTimeout(() => navigate('/login'), 2000)
    } catch (err) {
      toast.error(err.message || 'Failed to update password.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-md w-full space-y-8">
        <div>
          <h2 className="mt-6 text-center text-3xl font-extrabold text-gray-900">
            Set new password
          </h2>
          <p className="mt-2 text-center text-sm text-gray-600">
            Enter your new password below
          </p>
        </div>

        <form className="mt-8 space-y-6" onSubmit={handleSubmit}>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="password">New Password</Label>
              <Input
                id="password"
                name="password"
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter new password"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="confirmPassword">Confirm Password</Label>
              <Input
                id="confirmPassword"
                name="confirmPassword"
                type="password"
                required
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="Confirm new password"
              />
            </div>
          </div>

          <div>
            <Button type="submit" disabled={loading} className="w-full">
              {loading ? 'Updating...' : 'Update password'}
            </Button>
          </div>
        </form>
      </div>
    </div>
  )
}
```

---

## 11. Update Environment Variables

**File: `frontend/video-compilation2.0/.env`**

```env
VITE_SUPABASE_URL=https://xxxxx.supabase.co
VITE_SUPABASE_ANON_KEY=your-anon-key
VITE_API_URL=http://192.168.1.x:8000/api
```

---

## 12. Update Tailwind Config

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
- [ ] Supabase client configured with password reset functions
- [ ] API client with auth interceptors and toast notifications
- [ ] AuthProvider and useAuth hook created
- [ ] ProtectedRoute component with loading spinner
- [ ] Router setup with all routes (including forgot/reset password)
- [ ] Layout component with navigation and badge
- [ ] Login page implemented with shadcn components
- [ ] Forgot Password page implemented
- [ ] Reset Password page implemented
- [ ] Sonner toast notifications configured
- [ ] Environment variables set
- [ ] Tailwind CSS configured
- [ ] Test login flow with Supabase user
- [ ] Test password reset flow

---

## Next: Task 7
Build the main compilation workflow pages: Dashboard, New Compilation form, and sequence editor.
