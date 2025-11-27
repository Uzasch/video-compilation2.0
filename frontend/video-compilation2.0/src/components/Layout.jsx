import { Link, useLocation, useNavigate } from 'react-router-dom'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Command, CommandGroup, CommandItem, CommandList } from '@/components/ui/command'
import { useAuth } from '../hooks/useAuth'
import { useTheme } from '../hooks/useTheme'
import { LogOut, Home, FileVideo, History, Settings, Video, Sun, Moon, Palette, Check } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useState } from 'react'

export default function Layout({ children }) {
  const { user, logout } = useAuth()
  const { mode, toggleMode, colorTheme, setColorTheme, colorThemes } = useTheme()
  const navigate = useNavigate()
  const location = useLocation()
  const [themeOpen, setThemeOpen] = useState(false)

  const handleLogout = async () => {
    await logout()
    navigate('/login')
  }

  const isActive = (path) => location.pathname === path

  const navLinkClass = (path) =>
    `flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${isActive(path)
      ? 'bg-primary/10 text-primary shadow-sm'
      : 'text-muted-foreground hover:bg-muted hover:text-foreground'
    }`

  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="sticky top-0 z-50 w-full border-b border-border/50 bg-background/70 backdrop-blur-xl shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center gap-8">
              <Link to="/" className="flex items-center gap-2 group">
                <div className="bg-primary/10 p-2 rounded-lg group-hover:bg-primary/20 transition-colors">
                  <Video className="w-5 h-5 text-primary" />
                </div>
                <h1 className="text-xl font-bold text-foreground">
                  YBH Compilation
                </h1>
              </Link>

              {/* Dotted separator */}
              <div className="dotted-separator hidden md:block" />

              {/* Navigation */}
              <nav className="hidden md:flex gap-2">
                <Link to="/" className={navLinkClass('/')}>
                  <Home size={18} />
                  Dashboard
                </Link>
                <Link to="/new" className={navLinkClass('/new')}>
                  <FileVideo size={18} />
                  New Compilation
                </Link>
                <Link to="/history" className={navLinkClass('/history')}>
                  <History size={18} />
                  History
                </Link>
                {user?.role === 'admin' && (
                  <Link to="/admin" className={navLinkClass('/admin')}>
                    <Settings size={18} />
                    Admin
                  </Link>
                )}
              </nav>
            </div>

            {/* User menu */}
            <div className="flex items-center gap-3">
              {/* Theme selector */}
              <Popover open={themeOpen} onOpenChange={setThemeOpen}>
                <PopoverTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="text-muted-foreground hover:text-foreground"
                  >
                    <Palette size={18} />
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="w-48 p-0" align="end">
                  <Command>
                    <CommandList>
                      <CommandGroup heading="Color Theme">
                        {colorThemes.map((theme) => (
                          <CommandItem
                            key={theme.id}
                            value={theme.id}
                            onSelect={() => {
                              setColorTheme(theme.id)
                              setThemeOpen(false)
                            }}
                          >
                            {theme.name}
                            <Check
                              className={cn(
                                "ml-auto h-4 w-4",
                                colorTheme === theme.id ? "opacity-100" : "opacity-0"
                              )}
                            />
                          </CommandItem>
                        ))}
                      </CommandGroup>
                    </CommandList>
                  </Command>
                </PopoverContent>
              </Popover>

              {/* Mode toggle */}
              <Button
                variant="ghost"
                size="icon"
                onClick={toggleMode}
                className="text-muted-foreground hover:text-foreground"
              >
                {mode === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
              </Button>

              <div className="dotted-separator hidden sm:block" />

              <div className="hidden sm:flex flex-col items-end">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-sm">
                    {user?.display_name || user?.username}
                  </span>
                  {user?.role === 'admin' && (
                    <Badge variant="secondary" className="text-xs">
                      Admin
                    </Badge>
                  )}
                </div>
                <span className="text-xs text-muted-foreground">
                  {user?.role === 'admin' ? 'Administrator' : 'Editor'}
                </span>
              </div>

              <div className="dotted-separator hidden sm:block" />

              <Button
                variant="ghost"
                size="sm"
                onClick={handleLogout}
                className="flex items-center gap-2 text-muted-foreground hover:text-destructive hover:bg-destructive/10"
              >
                <LogOut size={18} />
                <span className="hidden sm:inline">Logout</span>
              </Button>
            </div>
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
        {children}
      </main>
    </div>
  )
}
