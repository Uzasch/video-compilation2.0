import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useAuth } from '../hooks/useAuth'
import apiClient from '../services/api'
import Layout from '../components/Layout'
import AddVideoDialog from '../components/AddVideoDialog'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Plus, Loader2, Users, Clock, Activity, Video } from 'lucide-react'

export default function Dashboard() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [addVideoOpen, setAddVideoOpen] = useState(false)

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
          <div className="flex gap-3">
            <Button variant="outline" onClick={() => setAddVideoOpen(true)}>
              <Video className="mr-2 h-4 w-4" /> Add Video
            </Button>
            <Button onClick={() => navigate('/new')} className="shadow-lg hover:shadow-xl transition-all">
              <Plus className="mr-2 h-4 w-4" /> New Compilation
            </Button>
          </div>
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

      </div>

      {/* Add Video Dialog */}
      <AddVideoDialog open={addVideoOpen} onOpenChange={setAddVideoOpen} />
    </Layout>
  )
}
