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
