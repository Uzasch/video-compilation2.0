import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useAuth } from '../hooks/useAuth'
import apiClient from '../services/api'
import Layout from '../components/Layout'
import JobCard from '../components/JobCard'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Plus, Loader2, Users, Clock, Activity } from 'lucide-react'

export default function Dashboard() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [jobs, setJobs] = useState([])

  // Fetch active jobs
  const { data: initialJobs, isLoading } = useQuery({
    queryKey: ['activeJobs', user?.id],
    queryFn: async () => {
      const params = { status: 'active' }
      if (user?.role !== 'admin') {
        params.user_id = user.id
      }
      const { data } = await apiClient.get('/jobs', { params })
      return data
    },
    enabled: !!user
  })

  // Fetch queue statistics
  const { data: queueStats } = useQuery({
    queryKey: ['queueStats'],
    queryFn: async () => {
      const { data } = await apiClient.get('/jobs/queue/stats')
      return data
    },
    refetchInterval: 5000,
    enabled: !!user
  })

  useEffect(() => {
    if (initialJobs) setJobs(initialJobs)
  }, [initialJobs])

  // Poll for job updates
  useEffect(() => {
    if (!user) return
    const interval = setInterval(async () => {
      try {
        const params = { status: 'active' }
        if (user?.role !== 'admin') params.user_id = user.id
        const { data } = await apiClient.get('/jobs', { params })
        setJobs(data || [])
      } catch (error) {
        console.error('Failed to fetch jobs:', error)
      }
    }, 5000)
    return () => clearInterval(interval)
  }, [user])

  return (
    <Layout>
      <div className="space-y-8">
        {/* Header */}
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <h2 className="text-3xl font-bold tracking-tight text-foreground">Dashboard</h2>
            <p className="text-muted-foreground mt-1">
              Monitor active jobs and queue status
            </p>
          </div>
          <Button onClick={() => navigate('/new')} className="shadow-lg hover:shadow-xl transition-all">
            <Plus className="mr-2 h-4 w-4" /> New Compilation
          </Button>
        </div>

        {/* Queue Statistics */}
        {queueStats && (
          <div className="grid gap-4 md:grid-cols-3">
            <Card className="bg-card/60 backdrop-blur-sm border-border/50">
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">Total in Queue</CardTitle>
                <Clock className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold text-foreground">{queueStats.total_in_queue}</div>
                <p className="text-xs text-muted-foreground">jobs waiting or processing</p>
              </CardContent>
            </Card>

            <Card className="bg-card/60 backdrop-blur-sm border-border/50">
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">Active Workers</CardTitle>
                <Users className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold text-foreground">{queueStats.active_workers}</div>
                <p className="text-xs text-muted-foreground">workers processing</p>
              </CardContent>
            </Card>

            <Card className="bg-card/60 backdrop-blur-sm border-border/50">
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">Available Slots</CardTitle>
                <Activity className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold text-foreground">{queueStats.available_slots}</div>
                <p className="text-xs text-muted-foreground">
                  {queueStats.available_slots > 0 ? 'start immediately!' : 'jobs will queue'}
                </p>
              </CardContent>
            </Card>
          </div>
        )}

        {/* User's Queue Position */}
        {queueStats?.user_jobs?.length > 0 && (
          <Card className="bg-muted/50 border-border/50">
            <CardHeader>
              <CardTitle className="text-foreground">Your Jobs in Queue</CardTitle>
              <CardDescription>Track your compilation progress</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {queueStats.user_jobs.map((userJob) => (
                <div
                  key={userJob.job_id}
                  className="flex items-center justify-between p-4 rounded-lg bg-background/80 border border-border/50"
                >
                  <div className="flex items-center gap-4">
                    <div className={`flex items-center justify-center w-10 h-10 rounded-full font-bold ${
                      userJob.is_processing
                        ? 'bg-green-500/10 text-green-600'
                        : 'bg-amber-500/10 text-amber-600'
                    }`}>
                      #{userJob.queue_position}
                    </div>
                    <div>
                      <p className="font-medium text-foreground">{userJob.channel_name}</p>
                      <p className="text-sm text-muted-foreground">
                        {userJob.is_processing ? (
                          <span className="flex items-center gap-1 text-green-600">
                            <Loader2 className="h-3 w-3 animate-spin" /> Processing now
                          </span>
                        ) : (
                          `${userJob.waiting_count} job${userJob.waiting_count !== 1 ? 's' : ''} ahead`
                        )}
                      </p>
                    </div>
                  </div>
                  <Button variant="ghost" size="sm" onClick={() => navigate(`/compilation/${userJob.job_id}`)}>
                    View Details
                  </Button>
                </div>
              ))}
            </CardContent>
          </Card>
        )}

        {/* Active Jobs List */}
        <div>
          <h3 className="text-lg font-semibold text-foreground mb-4">Active Jobs</h3>
          {isLoading ? (
            <div className="space-y-4">
              {[1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-32 w-full rounded-lg" />
              ))}
            </div>
          ) : jobs.length === 0 ? (
            <Card className="bg-card/60 backdrop-blur-sm border-border/50">
              <CardContent className="flex flex-col items-center justify-center py-12">
                <Activity className="h-12 w-12 text-muted-foreground/50 mb-4" />
                <p className="sidebar mb-4">No active jobs</p>
                <Button variant="outline" onClick={() => navigate('/new')}>
                  Create your first compilation
                </Button>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-4">
              {jobs.map((job) => (
                <JobCard key={job.job_id} job={job} />
              ))}
            </div>
          )}
        </div>
      </div>
    </Layout>
  )
}
