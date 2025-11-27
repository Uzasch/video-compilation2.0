import { createContext, useContext, useEffect, useState } from 'react'

const ThemeContext = createContext()

const COLOR_THEMES = [
  { id: 'default', name: 'Doom 64', class: '' },
  { id: 'trueblack', name: 'True Black', class: 'theme-trueblack' },
  { id: 'darkmatter', name: 'Dark Matter', class: 'theme-darkmatter' },
  { id: 'bubblegum', name: 'Bubblegum', class: 'theme-bubblegum' },
  { id: 'claymorphism', name: 'Claymorphism', class: 'theme-claymorphism' },
  { id: 'supabase', name: 'Supabase', class: 'theme-supabase' },
]

export { COLOR_THEMES }

export function ThemeProvider({ children }) {
  const [mode, setMode] = useState(() => {
    const stored = localStorage.getItem('theme-mode')
    if (stored) return stored
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  })

  const [colorTheme, setColorTheme] = useState(() => {
    return localStorage.getItem('color-theme') || 'default'
  })

  useEffect(() => {
    const root = document.documentElement

    // Remove all theme classes
    root.classList.remove('light', 'dark')
    COLOR_THEMES.forEach(t => {
      if (t.class) root.classList.remove(t.class)
    })

    // Add mode class
    root.classList.add(mode)

    // Add color theme class
    const theme = COLOR_THEMES.find(t => t.id === colorTheme)
    if (theme?.class) {
      root.classList.add(theme.class)
    }

    localStorage.setItem('theme-mode', mode)
    localStorage.setItem('color-theme', colorTheme)
  }, [mode, colorTheme])

  const toggleMode = () => {
    setMode(prev => prev === 'dark' ? 'light' : 'dark')
  }

  return (
    <ThemeContext.Provider value={{
      mode,
      setMode,
      toggleMode,
      colorTheme,
      setColorTheme,
      colorThemes: COLOR_THEMES
    }}>
      {children}
    </ThemeContext.Provider>
  )
}

export function useTheme() {
  const context = useContext(ThemeContext)
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider')
  }
  return context
}
