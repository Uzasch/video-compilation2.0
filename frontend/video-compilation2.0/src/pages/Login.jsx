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
      {/* Background gradient orbs using theme colors */}
      <div className="absolute inset-0 z-0">
        <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] rounded-full bg-primary/20 blur-[100px]" />
        <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] rounded-full bg-chart-2/20 blur-[100px]" />
      </div>

      <Card className="w-full mx-auto max-w-md bg-card/80 backdrop-blur-lg border-border/50 shadow-xl relative z-10 animate-in fade-in zoom-in duration-500 slide-in-from-bottom-4">
        <CardHeader className="text-center space-y-2 pb-6">
          <div className="mx-auto w-14 h-14 bg-primary/10 rounded-xl flex items-center justify-center mb-2">
            <Video className="w-7 h-7 text-primary" />
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
              <Label htmlFor="username" className="text-sm font-medium text-foreground">
                Username
              </Label>
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
                  className="pl-10 h-11 bg-input/50 border-border focus:ring-2 focus:ring-ring/20 transition-all"
                  autoFocus
                />
              </div>
            </div>

            <Button
              type="submit"
              disabled={loading}
              className="w-full h-11 text-base font-medium shadow-lg hover:shadow-xl transition-all duration-300 bg-primary hover:bg-primary/90 text-primary-foreground"
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
