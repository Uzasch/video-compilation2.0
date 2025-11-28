import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useAuth } from '../hooks/useAuth'
import { Video, ArrowRight, User, Loader2 } from 'lucide-react'

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
    <div className="min-h-screen flex items-center justify-center p-4">
      <Card className="w-full mx-auto max-w-md bg-card border-border shadow-xl animate-in fade-in zoom-in duration-500 slide-in-from-bottom-4">
        <CardHeader className="text-center space-y-4 pb-6">
          {/* Logo */}
          <div className="mx-auto w-16 h-16 bg-primary rounded-2xl flex items-center justify-center shadow-lg">
            <Video className="w-8 h-8 text-primary-foreground" />
          </div>

          <div className="space-y-2">
            <CardTitle className="text-3xl font-bold tracking-tight text-foreground">
              YBH Compilation
            </CardTitle>
            <CardDescription className="text-base text-muted-foreground">
              Video compilation management system
            </CardDescription>
          </div>
        </CardHeader>

        <CardContent className="space-y-6">
          <form onSubmit={handleSubmit} className="space-y-5">
            <div className="space-y-2">
              <Label htmlFor="username" className="text-sm font-medium text-foreground">
                Username
              </Label>
              <div className="relative group">
                <User className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-muted-foreground transition-colors group-focus-within:text-ring" />
                <Input
                  id="username"
                  name="username"
                  type="text"
                  autoComplete="username"
                  required
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="Enter your username"
                  className="pl-10 h-12 bg-background/80 border-input focus:ring-2 focus:ring-ring transition-all text-base"
                  autoFocus
                />
              </div>
            </div>

            <Button
              type="submit"
              disabled={loading}
              className="w-full h-12 text-base font-semibold shadow-lg hover:shadow-xl hover:scale-[1.01] active:scale-[0.99] transition-all duration-200"
            >
              {loading ? (
                <span className="flex items-center gap-2">
                  <Loader2 className="w-5 h-5 animate-spin" />
                  Signing in...
                </span>
              ) : (
                <span className="flex items-center gap-2">
                  Sign in
                  <ArrowRight className="w-5 h-5" />
                </span>
              )}
            </Button>
          </form>

          <div className="relative">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-border/50" />
            </div>
            <div className="relative flex justify-center text-xs uppercase">
              <span className="bg-card px-2 text-muted-foreground">
                Internal Tool
              </span>
            </div>
          </div>

          <p className="text-center text-sm text-muted-foreground">
            Contact admin if you need access credentials
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
