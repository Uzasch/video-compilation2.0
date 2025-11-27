# Task 7: Compilation Workflow Pages

## Objective
Build the main compilation workflow: Dashboard with active jobs and queue stats, New Compilation page with video ID input, sequence editor with per-video customization, and job submission.

## Design Guidelines
- Use **shadcn/ui** components throughout
- Use **semantic theming** variables (bg-background, text-foreground, bg-card, text-muted-foreground, etc.)
- Follow existing patterns from Layout.jsx and Login.jsx
- Use backdrop-blur and subtle shadows for depth
- Consistent animation with `animate-in fade-in` classes

---

## Required shadcn Components

Install additional components if needed:
```bash
npx shadcn@latest add select progress textarea alert collapsible separator scroll-area
```

---

## 1. Dashboard Page

**File: `frontend/video-compilation2.0/src/pages/Dashboard.jsx`**

### Functionality:
- Fetch and display active jobs (queued + processing)
- Show queue statistics with user's position
- Poll for updates every 5 seconds
- Admin sees all jobs, users see only their own

### API Endpoints:
- `GET /api/jobs?status=active` - fetch active jobs
- `GET /api/jobs/queue/stats` - queue statistics

```jsx
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useAuth } from '../hooks/useAuth'
import apiClient from '../services/api'
import Layout from '../components/Layout'
import JobCard from '../components/JobCard'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
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
          <Card className="bg-gradient-to-r from-primary/5 to-primary/10 border-primary/20">
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
                <p className="text-muted-foreground mb-4">No active jobs</p>
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
```

---

## 2. Job Card Component

**File: `frontend/video-compilation2.0/src/components/JobCard.jsx`**

### Functionality:
- Display job status with color-coded badges
- Progress bar for processing jobs
- Show progress_message from backend
- Clickable to view details

```jsx
import { useNavigate } from 'react-router-dom'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { Clock, Loader2, CheckCircle, XCircle, Tv, Calendar } from 'lucide-react'

const statusConfig = {
  queued: { label: 'Queued', variant: 'secondary', icon: Clock },
  processing: { label: 'Processing', variant: 'default', icon: Loader2 },
  completed: { label: 'Completed', variant: 'success', icon: CheckCircle },
  failed: { label: 'Failed', variant: 'destructive', icon: XCircle },
  cancelled: { label: 'Cancelled', variant: 'outline', icon: XCircle }
}

export default function JobCard({ job }) {
  const navigate = useNavigate()
  const config = statusConfig[job.status] || statusConfig.queued
  const StatusIcon = config.icon

  return (
    <Card
      className="bg-card/60 backdrop-blur-sm border-border/50 hover:shadow-lg transition-all cursor-pointer group"
      onClick={() => navigate(`/compilation/${job.job_id}`)}
    >
      <CardContent className="p-6">
        <div className="flex items-start justify-between mb-4">
          <div className="flex-1">
            <div className="flex items-center gap-3 mb-2">
              <h3 className="text-lg font-semibold text-foreground group-hover:text-primary transition-colors">
                {job.channel_name}
              </h3>
              <Badge variant={config.variant} className="flex items-center gap-1">
                <StatusIcon className={`h-3 w-3 ${job.status === 'processing' ? 'animate-spin' : ''}`} />
                {config.label}
              </Badge>
            </div>
            <div className="flex items-center gap-4 text-sm text-muted-foreground">
              <span className="flex items-center gap-1">
                <Tv className="h-4 w-4" />
                {job.enable_4k ? '4K' : 'HD'}
              </span>
              <span className="flex items-center gap-1">
                <Calendar className="h-4 w-4" />
                {new Date(job.created_at).toLocaleDateString()}
              </span>
            </div>
          </div>

          {job.status === 'processing' && (
            <div className="text-right">
              <span className="text-3xl font-bold text-primary">{job.progress}%</span>
            </div>
          )}
        </div>

        {/* Progress bar for processing jobs */}
        {job.status === 'processing' && (
          <div className="space-y-2">
            <Progress value={job.progress} className="h-2" />
            <p className="text-sm text-muted-foreground">
              {job.progress_message || 'Processing...'}
            </p>
          </div>
        )}

        {/* Error message */}
        {job.status === 'failed' && job.error_message && (
          <div className="mt-3 p-3 rounded-lg bg-destructive/10 border border-destructive/20">
            <p className="text-sm text-destructive">{job.error_message}</p>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
```

---

## 3. New Compilation Page

**File: `frontend/video-compilation2.0/src/pages/NewCompilation.jsx`**

### Functionality:
- Step 1: Select channel and enter video IDs
- Verify button calls `/api/jobs/verify` (builds sequence AND verifies paths)
- Step 2: Edit sequence, customize per-video settings
- Submit button calls `/api/jobs/submit`

### API Endpoints:
- `GET /api/admin/channels` - list channels
- `POST /api/jobs/verify` - verify video IDs and build sequence
- `POST /api/jobs/submit` - submit job

```jsx
import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { useAuth } from '../hooks/useAuth'
import apiClient from '../services/api'
import Layout from '../components/Layout'
import VideoIdInput from '../components/VideoIdInput'
import SequenceEditor from '../components/SequenceEditor'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Separator } from '@/components/ui/separator'
import { ArrowLeft, ArrowRight, Loader2, AlertCircle, CheckCircle, Clock, Film } from 'lucide-react'

export default function NewCompilation() {
  const { user } = useAuth()
  const navigate = useNavigate()

  const [channel, setChannel] = useState('')
  const [videoIds, setVideoIds] = useState('')
  const [sequence, setSequence] = useState(null)
  const [enable4k, setEnable4k] = useState(false)
  const [pathsVerified, setPathsVerified] = useState(false)

  // Fetch channels
  const { data: channels, isLoading: channelsLoading } = useQuery({
    queryKey: ['channels'],
    queryFn: async () => {
      const { data } = await apiClient.get('/admin/channels')
      return data.channels
    }
  })

  // Verify mutation
  const verifyMutation = useMutation({
    mutationFn: async ({ channel, videoIds, manualPaths = [] }) => {
      const { data } = await apiClient.post('/jobs/verify', {
        channel_name: channel,
        video_ids: videoIds.split('\n').map(id => id.trim()).filter(Boolean),
        manual_paths: manualPaths
      })
      return data
    },
    onSuccess: (data) => {
      setSequence(data)
      const allAvailable = data.items.every(item => item.path_available)
      setPathsVerified(allAvailable)

      if (!allAvailable) {
        const missingCount = data.items.filter(item => !item.path_available).length
        toast.warning(`${missingCount} item(s) have unavailable paths`)
      } else {
        toast.success('All paths verified successfully!')
      }
    },
    onError: (error) => {
      toast.error(error.response?.data?.detail || 'Verification failed')
    }
  })

  // Submit mutation
  const submitMutation = useMutation({
    mutationFn: async (jobData) => {
      const { data } = await apiClient.post('/jobs/submit', jobData)
      return data
    },
    onSuccess: (data) => {
      toast.success('Job submitted successfully!')
      navigate(`/compilation/${data.job_id}`)
    },
    onError: (error) => {
      toast.error(error.response?.data?.detail || 'Submission failed')
    }
  })

  const handleVerify = () => {
    if (!channel || !videoIds.trim()) {
      toast.error('Please select a channel and enter video IDs')
      return
    }
    verifyMutation.mutate({ channel, videoIds })
  }

  const handleReverify = () => {
    if (!sequence) return
    const manualPaths = sequence.items
      .filter(item => item.item_type === 'transition' || item.item_type === 'image')
      .filter(item => item.path)
      .map(item => item.path)
    verifyMutation.mutate({ channel, videoIds, manualPaths })
  }

  const handleSubmit = () => {
    if (!sequence || !pathsVerified) {
      toast.error('Please verify all paths before submitting')
      return
    }
    submitMutation.mutate({
      user_id: user.id,
      channel_name: channel,
      enable_4k: enable4k,
      items: sequence.items
    })
  }

  return (
    <Layout>
      <div className="max-w-4xl mx-auto space-y-6">
        {/* Header */}
        <div>
          <h2 className="text-3xl font-bold tracking-tight text-foreground">New Compilation</h2>
          <p className="text-muted-foreground mt-1">
            {!sequence ? 'Step 1: Enter video IDs to build your sequence' : 'Step 2: Review and submit'}
          </p>
        </div>

        {/* Step 1: Input */}
        {!sequence && (
          <Card className="bg-card/60 backdrop-blur-sm border-border/50">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Film className="h-5 w-5" />
                Build Compilation
              </CardTitle>
              <CardDescription>
                Select a channel and enter video IDs to fetch from the database
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              {/* Channel Selection */}
              <div className="space-y-2">
                <Label htmlFor="channel">Channel</Label>
                <Select value={channel} onValueChange={setChannel}>
                  <SelectTrigger className="bg-background/50">
                    <SelectValue placeholder="Select a channel..." />
                  </SelectTrigger>
                  <SelectContent>
                    {channels?.map((ch) => (
                      <SelectItem key={ch} value={ch}>{ch}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Video IDs */}
              <VideoIdInput value={videoIds} onChange={setVideoIds} />

              {/* 4K Toggle */}
              <div className="flex items-center justify-between p-4 rounded-lg bg-background/50 border border-border/50">
                <div>
                  <Label htmlFor="4k-switch" className="text-base font-medium">4K Processing</Label>
                  <p className="text-sm text-muted-foreground">Enable higher quality output</p>
                </div>
                <Switch id="4k-switch" checked={enable4k} onCheckedChange={setEnable4k} />
              </div>

              {/* Error Alert */}
              {verifyMutation.isError && (
                <Alert variant="destructive">
                  <AlertCircle className="h-4 w-4" />
                  <AlertDescription>
                    {verifyMutation.error?.response?.data?.detail || 'Verification failed'}
                  </AlertDescription>
                </Alert>
              )}

              {/* Verify Button */}
              <Button
                onClick={handleVerify}
                disabled={verifyMutation.isPending || !channel || !videoIds.trim()}
                className="w-full"
                size="lg"
              >
                {verifyMutation.isPending ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Verifying...
                  </>
                ) : (
                  <>
                    Verify & Build Sequence
                    <ArrowRight className="ml-2 h-4 w-4" />
                  </>
                )}
              </Button>
            </CardContent>
          </Card>
        )}

        {/* Step 2: Sequence Editor */}
        {sequence && (
          <div className="space-y-6">
            {/* Back Button */}
            <Button variant="ghost" onClick={() => setSequence(null)}>
              <ArrowLeft className="mr-2 h-4 w-4" />
              Back to Edit
            </Button>

            {/* Sequence Editor */}
            <SequenceEditor
              sequence={sequence}
              onChange={setSequence}
            />

            {/* Summary Card */}
            <Card className="bg-card/60 backdrop-blur-sm border-border/50">
              <CardHeader>
                <CardTitle>Summary</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <span className="text-muted-foreground">Total items:</span>
                    <span className="ml-2 font-medium text-foreground">{sequence.items.length}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Duration:</span>
                    <span className="ml-2 font-medium text-foreground">
                      {Math.floor(sequence.total_duration / 60)}m {Math.floor(sequence.total_duration % 60)}s
                    </span>
                  </div>
                </div>

                <Separator />

                {/* Status Alert */}
                {!pathsVerified ? (
                  <Alert variant="warning" className="border-amber-500/50 bg-amber-500/10">
                    <AlertCircle className="h-4 w-4 text-amber-600" />
                    <AlertDescription className="text-amber-700">
                      Some paths are unavailable. Fix them and re-verify before submitting.
                    </AlertDescription>
                  </Alert>
                ) : (
                  <Alert className="border-green-500/50 bg-green-500/10">
                    <CheckCircle className="h-4 w-4 text-green-600" />
                    <AlertDescription className="text-green-700">
                      All paths verified and available!
                    </AlertDescription>
                  </Alert>
                )}

                {/* Action Buttons */}
                <div className="flex gap-3">
                  {!pathsVerified && (
                    <Button
                      variant="outline"
                      onClick={handleReverify}
                      disabled={verifyMutation.isPending}
                      className="flex-1"
                    >
                      {verifyMutation.isPending ? (
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      ) : null}
                      Re-verify Paths
                    </Button>
                  )}
                  <Button
                    onClick={handleSubmit}
                    disabled={submitMutation.isPending || !pathsVerified}
                    className="flex-1"
                  >
                    {submitMutation.isPending ? (
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        Submitting...
                      </>
                    ) : (
                      'Submit Compilation'
                    )}
                  </Button>
                </div>
              </CardContent>
            </Card>
          </div>
        )}
      </div>
    </Layout>
  )
}
```

---

## 4. Video ID Input Component

**File: `frontend/video-compilation2.0/src/components/VideoIdInput.jsx`**

```jsx
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'

export default function VideoIdInput({ value, onChange }) {
  const lineCount = value.split('\n').filter(Boolean).length

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <Label htmlFor="video-ids">Video IDs</Label>
        <span className="text-xs text-muted-foreground">
          {lineCount} video{lineCount !== 1 ? 's' : ''}
        </span>
      </div>
      <Textarea
        id="video-ids"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Paste video IDs here, one per line...&#10;abc123&#10;def456&#10;ghi789"
        rows={10}
        className="font-mono text-sm bg-background/50"
      />
      <p className="text-xs text-muted-foreground">
        Enter one video ID per line. Paths and metadata will be fetched automatically.
      </p>
    </div>
  )
}
```

---

## 5. Sequence Editor Component

**File: `frontend/video-compilation2.0/src/components/SequenceEditor.jsx`**

```jsx
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import SequenceItem from './SequenceItem'
import InsertButton from './InsertButton'
import { List } from 'lucide-react'

export default function SequenceEditor({ sequence, onChange }) {
  const updateItem = (position, updates) => {
    const updatedItems = sequence.items.map((item) =>
      item.position === position ? { ...item, ...updates } : item
    )
    onChange({ ...sequence, items: updatedItems })
  }

  const insertItem = (afterPosition, itemType) => {
    const items = [...sequence.items]
    items.forEach(item => {
      if (item.position > afterPosition) item.position++
    })

    const newItem = {
      position: afterPosition + 1,
      item_type: itemType,
      path: null,
      path_available: false,
      logo_path: itemType === 'video' ? sequence.default_logo_path : null,
      text_animation_text: null,
      duration: itemType === 'image' ? 5 : null,
      title: itemType === 'image' ? 'Image Slide' : null
    }

    const insertIndex = items.findIndex(item => item.position === afterPosition)
    items.splice(insertIndex + 1, 0, newItem)
    onChange({ ...sequence, items })
  }

  const deleteItem = (position) => {
    const item = sequence.items.find(i => i.position === position)
    if (item?.item_type === 'intro' || item?.item_type === 'outro') return

    let items = sequence.items.filter(i => i.position !== position)
    items = items.map((item, index) => ({ ...item, position: index + 1 }))
    onChange({ ...sequence, items })
  }

  const handleApplyLogoToAll = (logoPath) => {
    const updatedItems = sequence.items.map((item) =>
      item.item_type === 'video' ? { ...item, logo_path: logoPath } : item
    )
    onChange({ ...sequence, items: updatedItems })
  }

  return (
    <Card className="bg-card/60 backdrop-blur-sm border-border/50">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <List className="h-5 w-5" />
          Video Sequence
        </CardTitle>
        <CardDescription>
          Review items, customize logos and text animations, add transitions
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ScrollArea className="h-[500px] pr-4">
          <div className="space-y-2">
            {sequence.items.map((item) => (
              <div key={item.position}>
                <SequenceItem
                  item={item}
                  onUpdate={updateItem}
                  onDelete={deleteItem}
                  onApplyLogoToAll={handleApplyLogoToAll}
                  defaultLogoPath={sequence.default_logo_path}
                />
                {item.item_type !== 'outro' && (
                  <InsertButton afterPosition={item.position} onInsert={insertItem} />
                )}
              </div>
            ))}
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  )
}
```

---

## 6. Sequence Item Component

**File: `frontend/video-compilation2.0/src/components/SequenceItem.jsx`**

```jsx
import { useState } from 'react'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import ImageUpload from './ImageUpload'
import { Film, Package, Play, Flag, Trash2, Image, Type, ChevronDown, ChevronRight, Check, X, AlertTriangle } from 'lucide-react'

const itemConfig = {
  intro: { icon: Play, color: 'bg-green-500/10 text-green-600 border-green-500/30' },
  video: { icon: Film, color: 'bg-blue-500/10 text-blue-600 border-blue-500/30' },
  transition: { icon: Package, color: 'bg-purple-500/10 text-purple-600 border-purple-500/30' },
  outro: { icon: Flag, color: 'bg-red-500/10 text-red-600 border-red-500/30' },
  image: { icon: Image, color: 'bg-pink-500/10 text-pink-600 border-pink-500/30' }
}

export default function SequenceItem({ item, onUpdate, onDelete, onApplyLogoToAll, defaultLogoPath }) {
  const [isOpen, setIsOpen] = useState(false)
  const config = itemConfig[item.item_type]
  const Icon = config.icon

  const canDelete = !['intro', 'outro'].includes(item.item_type)
  const canHaveLogo = item.item_type === 'video'
  const canHaveTextAnimation = item.item_type === 'video'
  const isImage = item.item_type === 'image'

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <div className={`rounded-lg border ${config.color} transition-all`}>
        <CollapsibleTrigger asChild>
          <div className="flex items-center justify-between p-4 cursor-pointer hover:bg-background/50">
            <div className="flex items-center gap-3">
              <Icon className="h-5 w-5" />
              <div>
                <p className="font-medium text-foreground">
                  {item.title || item.item_type.charAt(0).toUpperCase() + item.item_type.slice(1)}
                </p>
                <p className="text-xs text-muted-foreground">
                  #{item.position}
                  {item.video_id && ` • ${item.video_id}`}
                  {item.duration && ` • ${item.duration.toFixed(1)}s`}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              {/* Path status badge */}
              {item.path_available ? (
                <Badge variant="outline" className="bg-green-500/10 text-green-600 border-green-500/30">
                  <Check className="h-3 w-3 mr-1" /> Available
                </Badge>
              ) : item.path ? (
                <Badge variant="outline" className="bg-red-500/10 text-red-600 border-red-500/30">
                  <X className="h-3 w-3 mr-1" /> Not Found
                </Badge>
              ) : (
                <Badge variant="outline" className="bg-amber-500/10 text-amber-600 border-amber-500/30">
                  <AlertTriangle className="h-3 w-3 mr-1" /> No Path
                </Badge>
              )}

              {canDelete && (
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 text-muted-foreground hover:text-destructive"
                  onClick={(e) => { e.stopPropagation(); onDelete(item.position) }}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              )}

              {isOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
            </div>
          </div>
        </CollapsibleTrigger>

        <CollapsibleContent>
          <div className="px-4 pb-4 pt-2 space-y-4 border-t border-border/50">
            {/* Image upload for image type */}
            {isImage && <ImageUpload item={item} onUpdate={onUpdate} />}

            {/* Manual path input */}
            {!isImage && (
              <div className="space-y-2">
                <Label>Manual Path</Label>
                <Input
                  value={item.path || ''}
                  onChange={(e) => onUpdate(item.position, { path: e.target.value, path_available: false })}
                  placeholder="\\SERVER\path\to\video.mp4"
                  className="font-mono text-sm bg-background/50"
                />
              </div>
            )}

            {/* Logo path for videos */}
            {canHaveLogo && (
              <div className="space-y-2">
                <Label className="flex items-center gap-2">
                  <Image className="h-4 w-4" /> Logo Path
                </Label>
                <div className="flex gap-2">
                  <Input
                    value={item.logo_path || ''}
                    onChange={(e) => onUpdate(item.position, { logo_path: e.target.value })}
                    placeholder="\\SERVER\path\to\logo.png"
                    className="font-mono text-sm bg-background/50"
                  />
                  <Button variant="outline" size="sm" onClick={() => onUpdate(item.position, { logo_path: defaultLogoPath })}>
                    Reset
                  </Button>
                  <Button variant="secondary" size="sm" onClick={() => onApplyLogoToAll(item.logo_path)}>
                    Apply All
                  </Button>
                </div>
              </div>
            )}

            {/* Text animation for videos */}
            {canHaveTextAnimation && (
              <div className="space-y-2">
                <Label className="flex items-center gap-2">
                  <Type className="h-4 w-4" /> Text Animation
                </Label>
                <Input
                  value={item.text_animation_text || ''}
                  onChange={(e) => onUpdate(item.position, { text_animation_text: e.target.value || null })}
                  placeholder="Text to animate letter-by-letter"
                  className="bg-background/50"
                />
                <p className="text-xs text-muted-foreground">Leave empty to disable</p>
              </div>
            )}
          </div>
        </CollapsibleContent>
      </div>
    </Collapsible>
  )
}
```

---

## 7. Insert Button Component

**File: `frontend/video-compilation2.0/src/components/InsertButton.jsx`**

```jsx
import { Button } from '@/components/ui/button'
import { Plus, Film, Package, Image } from 'lucide-react'

export default function InsertButton({ afterPosition, onInsert }) {
  return (
    <div className="flex items-center justify-center py-2 gap-2 opacity-50 hover:opacity-100 transition-opacity">
      <div className="h-[1px] flex-1 bg-border" />
      <div className="flex gap-1">
        <Button
          variant="ghost"
          size="sm"
          className="h-7 px-2 text-xs"
          onClick={() => onInsert(afterPosition, 'video')}
        >
          <Plus className="h-3 w-3 mr-1" />
          <Film className="h-3 w-3" />
        </Button>
        <Button
          variant="ghost"
          size="sm"
          className="h-7 px-2 text-xs"
          onClick={() => onInsert(afterPosition, 'transition')}
        >
          <Plus className="h-3 w-3 mr-1" />
          <Package className="h-3 w-3" />
        </Button>
        <Button
          variant="ghost"
          size="sm"
          className="h-7 px-2 text-xs"
          onClick={() => onInsert(afterPosition, 'image')}
        >
          <Plus className="h-3 w-3 mr-1" />
          <Image className="h-3 w-3" />
        </Button>
      </div>
      <div className="h-[1px] flex-1 bg-border" />
    </div>
  )
}
```

---

## 8. Image Upload Component

**File: `frontend/video-compilation2.0/src/components/ImageUpload.jsx`**

```jsx
import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import apiClient from '../services/api'
import { Upload, X, Loader2 } from 'lucide-react'

export default function ImageUpload({ item, onUpdate }) {
  const [uploading, setUploading] = useState(false)
  const [preview, setPreview] = useState(item.path)

  const handleFileSelect = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return

    if (!file.type.startsWith('image/')) {
      alert('Please select an image file')
      return
    }

    if (file.size > 10 * 1024 * 1024) {
      alert('Image must be smaller than 10MB')
      return
    }

    setUploading(true)
    try {
      const formData = new FormData()
      formData.append('file', file)

      const { data } = await apiClient.post('/uploads/image', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      })

      onUpdate(item.position, {
        path: data.path,
        path_available: true,
        title: item.title || file.name
      })
      setPreview(URL.createObjectURL(file))
    } catch (error) {
      alert('Upload failed: ' + (error.response?.data?.detail || error.message))
    } finally {
      setUploading(false)
    }
  }

  const handleRemove = async () => {
    if (!item.path) return
    try {
      const filename = item.path.split(/[/\\]/).pop()
      await apiClient.delete(`/uploads/image/${filename}`)
      onUpdate(item.position, { path: null, path_available: false })
      setPreview(null)
    } catch (error) {
      console.error('Delete failed:', error)
    }
  }

  return (
    <div className="space-y-4">
      {/* Upload Area */}
      {preview ? (
        <div className="relative">
          <img src={preview} alt="Preview" className="w-full h-32 object-cover rounded-lg border border-border" />
          <Button
            variant="destructive"
            size="icon"
            className="absolute top-2 right-2 h-8 w-8"
            onClick={handleRemove}
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      ) : (
        <label className="flex flex-col items-center justify-center h-32 border-2 border-dashed border-border rounded-lg cursor-pointer hover:border-primary/50 hover:bg-primary/5 transition-all">
          {uploading ? (
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          ) : (
            <>
              <Upload className="h-8 w-8 text-muted-foreground mb-2" />
              <span className="text-sm text-muted-foreground">Click to upload</span>
              <span className="text-xs text-muted-foreground">PNG, JPG, GIF (max 10MB)</span>
            </>
          )}
          <input type="file" className="hidden" accept="image/*" onChange={handleFileSelect} disabled={uploading} />
        </label>
      )}

      {/* Duration & Title */}
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label>Duration (seconds)</Label>
          <Input
            type="number"
            min="0.5"
            max="60"
            step="0.5"
            value={item.duration || 5}
            onChange={(e) => onUpdate(item.position, { duration: parseFloat(e.target.value) })}
            className="bg-background/50"
          />
        </div>
        <div className="space-y-2">
          <Label>Title</Label>
          <Input
            value={item.title || ''}
            onChange={(e) => onUpdate(item.position, { title: e.target.value })}
            placeholder="Image title"
            className="bg-background/50"
          />
        </div>
      </div>
    </div>
  )
}
```

---

## Checklist

- [ ] Install additional shadcn components: `select`, `progress`, `textarea`, `alert`, `collapsible`, `separator`, `scroll-area`, `switch`
- [ ] Dashboard with active jobs and queue statistics
- [ ] Queue stats polling every 5 seconds
- [ ] JobCard with progress bar and status badges
- [ ] NewCompilation with channel select and video ID input
- [ ] Single-step verify via `/api/jobs/verify`
- [ ] SequenceEditor with collapsible items
- [ ] SequenceItem with path status badges
- [ ] Per-video logo_path input with "Apply All"
- [ ] Per-video text_animation_text input
- [ ] InsertButton for adding videos/transitions/images
- [ ] ImageUpload with preview and duration
- [ ] Re-verify button for path fixes
- [ ] Submit only when all paths verified

---

## Next: Task 8
Build History page, Compilation Details page, and Admin panel.
