# Task 6: React Frontend Structure & Authentication

## Objective
Set up React frontend with Vite, configure routing, authentication, and create the basic layout structure.

---

## 1. Frontend Project Setup

The frontend project has already been initialized with Vite. Verify the structure:

```bash
cd frontend
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

---

## 2. Configure Supabase Client

Create Supabase client for authentication and data access.

**File: `frontend/src/services/supabase.js`**

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
```

---

## 3. Configure API Client

**File: `frontend/src/services/api.js`**

```javascript
import axios from 'axios'
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

// Handle errors
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Redirect to login
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

export default apiClient
```

---

## 4. Authentication Hook

**File: `frontend/src/hooks/useAuth.js`**

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

**File: `frontend/src/components/ProtectedRoute.jsx`**

```javascript
import { Navigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'

export default function ProtectedRoute({ children, adminOnly = false }) {
  const { user, profile, loading } = useAuth()

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-lg">Loading...</div>
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

**File: `frontend/src/App.jsx`**

```javascript
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
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

## 7. Layout Component

**File: `frontend/src/components/Layout.jsx`**

```javascript
import { Link, useNavigate } from 'react-router-dom'
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
                  <span className="ml-2 px-2 py-1 text-xs font-medium text-blue-700 bg-blue-100 rounded">
                    Admin
                  </span>
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

**File: `frontend/src/pages/Login.jsx`**

```javascript
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const { login } = useAuth()
  const navigate = useNavigate()

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      await login(email, password)
      navigate('/')
    } catch (err) {
      setError(err.message || 'Login failed. Please check your credentials.')
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
          {error && (
            <div className="rounded-md bg-red-50 p-4">
              <div className="text-sm text-red-700">{error}</div>
            </div>
          )}

          <div className="rounded-md shadow-sm -space-y-px">
            <div>
              <label htmlFor="email" className="sr-only">Email</label>
              <input
                id="email"
                name="email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="appearance-none rounded-none relative block w-full px-3 py-2 border border-gray-300 placeholder-gray-500 text-gray-900 rounded-t-md focus:outline-none focus:ring-blue-500 focus:border-blue-500 focus:z-10 sm:text-sm"
                placeholder="Email address"
              />
            </div>
            <div>
              <label htmlFor="password" className="sr-only">Password</label>
              <input
                id="password"
                name="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="appearance-none rounded-none relative block w-full px-3 py-2 border border-gray-300 placeholder-gray-500 text-gray-900 rounded-b-md focus:outline-none focus:ring-blue-500 focus:border-blue-500 focus:z-10 sm:text-sm"
                placeholder="Password"
              />
            </div>
          </div>

          <div>
            <button
              type="submit"
              disabled={loading}
              className="group relative w-full flex justify-center py-2 px-4 border border-transparent text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50"
            >
              {loading ? 'Signing in...' : 'Sign in'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
```

---

## 9. Update Environment Variables

**File: `frontend/.env`**

```env
VITE_SUPABASE_URL=https://xxxxx.supabase.co
VITE_SUPABASE_ANON_KEY=your-anon-key
VITE_API_URL=http://192.168.1.x:8000/api
```

---

## 10. Update Tailwind Config

**File: `frontend/tailwind.config.js`**

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

**File: `frontend/src/index.css`**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

---

## Checklist

- [ ] Supabase client configured
- [ ] API client with auth interceptors
- [ ] AuthProvider and useAuth hook created
- [ ] ProtectedRoute component
- [ ] Router setup with all routes
- [ ] Layout component with navigation
- [ ] Login page implemented
- [ ] Environment variables set
- [ ] Tailwind CSS configured
- [ ] Test login flow with Supabase user

---

## Next: Task 7
Build the main compilation workflow pages: Dashboard, New Compilation form, and sequence editor.
