import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import apiClient from '../services/api'
import { convertPathForClient } from '../utils/pathUtils'
import Layout from '../components/Layout'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { Skeleton } from '@/components/ui/skeleton'
import { Separator } from '@/components/ui/separator'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  ArrowLeft,
  Clock,
  Loader2,
  CheckCircle,
  XCircle,
  Ban,
  Tv,
  Calendar,
  Film,
  Play,
  Flag,
  Package,
  Image,
  FolderCheck,
  Download,
  Trash2,
  RefreshCw,
  AlertCircle,
  User,
  FileVideo,
  Copy,
  Check
} from 'lucide-react'

const statusConfig = {
  queued: {
    label: 'Queued',
    icon: Clock,
    className: 'bg-amber-500/10 text-amber-600 border-amber-500/30'
  },
  processing: {
    label: 'Processing',
    icon: Loader2,
    className: 'bg-blue-500/10 text-blue-600 border-blue-500/30'
  },
  completed: {
    label: 'Completed',
    icon: CheckCircle,
    className: 'bg-green-500/10 text-green-600 border-green-500/30'
  },
  failed: {
    label: 'Failed',
    icon: XCircle,
    className: 'bg-destructive/10 text-destructive border-destructive/30'
  },
  cancelled: {
    label: 'Cancelled',
    icon: Ban,
    className: 'bg-muted text-muted-foreground border-border'
  }
}

const itemTypeConfig = {
  intro: { icon: Play, color: 'text-green-600' },
  video: { icon: Film, color: 'text-blue-600' },
  transition: { icon: Package, color: 'text-purple-600' },
  outro: { icon: Flag, color: 'text-red-600' },
  image: { icon: Image, color: 'text-pink-600' }
}

function formatDuration(seconds) {
  if (!seconds) return '-'
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins}m ${secs}s`
}

function formatDate(dateString) {
  if (!dateString) return '-'
  return new Date(dateString).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  })
}

export default function CompilationDetails() {
  const { jobId } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [moveDialogOpen, setMoveDialogOpen] = useState(false)
  const [customFilename, setCustomFilename] = useState('')
  const [copied, setCopied] = useState(false)

  // Fetch job details
  const { data: job, isLoading: jobLoading, error: jobError } = useQuery({
    queryKey: ['job', jobId],
    queryFn: async () => {
      const { data } = await apiClient.get(`/jobs/${jobId}`)
      return data
    },
    refetchInterval: (data) => {
      // Poll every 3 seconds for active jobs
      if (data?.status === 'queued' || data?.status === 'processing') {
        return 3000
      }
      return false
    }
  })

  // Fetch job items
  const { data: items, isLoading: itemsLoading } = useQuery({
    queryKey: ['jobItems', jobId],
    queryFn: async () => {
      const { data } = await apiClient.get(`/jobs/${jobId}/items`)
      return data
    },
    enabled: !!job
  })

  // Cancel mutation
  const cancelMutation = useMutation({
    mutationFn: async () => {
      const { data } = await apiClient.post(`/jobs/${jobId}/cancel`)
      return data
    },
    onSuccess: () => {
      toast.success('Job cancelled successfully')
      queryClient.invalidateQueries(['job', jobId])
    },
    onError: (error) => {
      toast.error(error.response?.data?.detail || 'Failed to cancel job')
    }
  })

  // Move to production mutation
  const moveMutation = useMutation({
    mutationFn: async (filename) => {
      const { data } = await apiClient.post(`/jobs/${jobId}/move-to-production`, {
        custom_filename: filename || null
      })
      return data
    },
    onSuccess: (data) => {
      toast.success(`Moved to production: ${data.filename}`)
      setMoveDialogOpen(false)
      queryClient.invalidateQueries(['job', jobId])
    },
    onError: (error) => {
      toast.error(error.response?.data?.detail || 'Failed to move to production')
    }
  })

  const handleCancel = () => {
    if (confirm('Are you sure you want to cancel this job?')) {
      cancelMutation.mutate()
    }
  }

  const handleMoveToProduction = () => {
    moveMutation.mutate(customFilename)
  }

  const handleCopySequence = () => {
    if (!items || items.length === 0) return

    const lines = []
    for (const item of items) {
      // Skip intro and outro
      if (item.item_type === 'intro' || item.item_type === 'outro') continue
      // Skip images
      if (item.item_type === 'image') continue

      // For videos, add video_id
      if (item.item_type === 'video' && item.video_id) {
        lines.push(item.video_id)
      }
      // For transitions with manual path, add the path
      else if (item.item_type === 'transition' && item.path) {
        lines.push(item.path)
      }
    }

    const text = lines.join('\n')

    // Fallback for HTTP (navigator.clipboard requires HTTPS)
    const textArea = document.createElement('textarea')
    textArea.value = text
    textArea.style.position = 'fixed'
    textArea.style.left = '-9999px'
    document.body.appendChild(textArea)
    textArea.select()
    try {
      document.execCommand('copy')
      setCopied(true)
      toast.success(`Copied ${lines.length} items to clipboard`)
      setTimeout(() => setCopied(false), 2000)
    } catch (err) {
      toast.error('Failed to copy to clipboard')
    }
    document.body.removeChild(textArea)
  }

  if (jobLoading) {
    return (
      <Layout>
        <div className="space-y-6">
          <Skeleton className="h-8 w-64" />
          <Skeleton className="h-48 w-full" />
          <Skeleton className="h-96 w-full" />
        </div>
      </Layout>
    )
  }

  if (jobError || !job) {
    return (
      <Layout>
        <div className="space-y-6">
          <Button variant="ghost" onClick={() => navigate(-1)}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back
          </Button>
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>
              {jobError?.response?.data?.detail || 'Job not found'}
            </AlertDescription>
          </Alert>
        </div>
      </Layout>
    )
  }

  const config = statusConfig[job.status] || statusConfig.queued
  const StatusIcon = config.icon

  return (
    <Layout>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex flex-col sm:flex-row justify-between items-start gap-4">
          <div className="flex items-center gap-4">
            <Button variant="ghost" size="icon" onClick={() => navigate(-1)}>
              <ArrowLeft className="h-5 w-5" />
            </Button>
            <div>
              <div className="flex items-center gap-3">
                <h2 className="text-3xl font-bold tracking-tight text-foreground">
                  {job.channel_name}
                </h2>
                <Badge variant="outline" className={`flex items-center gap-1 ${config.className}`}>
                  <StatusIcon className={`h-3 w-3 ${job.status === 'processing' ? 'animate-spin' : ''}`} />
                  {config.label}
                </Badge>
              </div>
              <p className="text-muted-foreground mt-1">
                Job ID: {job.job_id}
              </p>
            </div>
          </div>

          {/* Actions */}
          <div className="flex gap-2">
            {job.status === 'queued' && (
              <Button
                variant="destructive"
                onClick={handleCancel}
                disabled={cancelMutation.isPending}
              >
                {cancelMutation.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Trash2 className="mr-2 h-4 w-4" />
                )}
                Cancel Job
              </Button>
            )}
            {job.status === 'completed' && !job.moved_to_production && (
              <Button onClick={() => setMoveDialogOpen(true)}>
                <FolderCheck className="mr-2 h-4 w-4" />
                Move to Production
              </Button>
            )}
            {job.status === 'completed' && job.moved_to_production && (
              <Badge variant="outline" className="bg-primary/10 text-primary border-primary/30 px-4 py-2">
                <FolderCheck className="mr-2 h-4 w-4" />
                Moved to Production
              </Badge>
            )}
          </div>
        </div>

        {/* Progress for processing jobs */}
        {job.status === 'processing' && (
          <Card className="bg-card/60 backdrop-blur-sm border-border/50">
            <CardContent className="pt-6">
              <div className="space-y-4">
                <div className="flex justify-between items-center">
                  <span className="text-sm font-medium text-foreground">Progress</span>
                  <span className="text-2xl font-bold text-primary">{job.progress || 0}%</span>
                </div>
                <Progress value={job.progress || 0} className="h-3" />
                <p className="text-sm text-muted-foreground">
                  {job.progress_message || 'Processing...'}
                </p>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Error for failed jobs */}
        {job.status === 'failed' && job.error_message && (
          <Alert variant="destructive">
            <XCircle className="h-4 w-4" />
            <AlertDescription className="ml-2">
              <span className="font-medium">Error:</span> {job.error_message}
            </AlertDescription>
          </Alert>
        )}

        {/* Job Details */}
        <div className="grid gap-6 md:grid-cols-2">
          {/* Info Card */}
          <Card className="bg-card/60 backdrop-blur-sm border-border/50">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <FileVideo className="h-5 w-5" />
                Job Information
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-sm text-muted-foreground">Quality</p>
                  <p className="font-medium text-foreground flex items-center gap-2">
                    <Tv className="h-4 w-4" />
                    {job.enable_4k ? '4K Ultra HD' : 'Full HD 1080p'}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Duration</p>
                  <p className="font-medium text-foreground flex items-center gap-2">
                    <Clock className="h-4 w-4" />
                    {formatDuration(job.final_duration)}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Created</p>
                  <p className="font-medium text-foreground flex items-center gap-2">
                    <Calendar className="h-4 w-4" />
                    {formatDate(job.created_at)}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Completed</p>
                  <p className="font-medium text-foreground">
                    {job.completed_at ? formatDate(job.completed_at) : '-'}
                  </p>
                </div>
              </div>

              <Separator />

              {/* Output paths */}
              {job.output_path && (
                <div>
                  <p className="text-sm text-muted-foreground mb-1">Output Path</p>
                  <p className="text-sm font-mono bg-muted/50 p-2 rounded break-all">
                    {convertPathForClient(job.output_path)}
                  </p>
                </div>
              )}

              {job.production_path && (
                <div>
                  <p className="text-sm text-muted-foreground mb-1">Production Path</p>
                  <p className="text-sm font-mono bg-primary/10 p-2 rounded break-all text-primary">
                    {convertPathForClient(job.production_path)}
                  </p>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Items Card */}
          <Card className="bg-card/60 backdrop-blur-sm border-border/50">
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="flex items-center gap-2">
                  <Film className="h-5 w-5" />
                  Sequence Items
                </CardTitle>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleCopySequence}
                  disabled={!items || items.length === 0}
                  className={copied ? 'bg-green-600 hover:bg-green-600 text-white border-green-600' : ''}
                >
                  {copied ? (
                    <>
                      <Check className="mr-2 h-4 w-4" />
                      Copied
                    </>
                  ) : (
                    <>
                      <Copy className="mr-2 h-4 w-4" />
                      Copy IDs
                    </>
                  )}
                </Button>
              </div>
              <CardDescription>
                {items?.length || 0} items in this compilation
              </CardDescription>
            </CardHeader>
            <CardContent>
              {itemsLoading ? (
                <div className="space-y-2">
                  {[1, 2, 3, 4, 5].map((i) => (
                    <Skeleton key={i} className="h-10 w-full" />
                  ))}
                </div>
              ) : items?.length === 0 ? (
                <p className="text-muted-foreground text-center py-8">
                  No items found
                </p>
              ) : (
                <ScrollArea className="h-[300px] pr-4">
                  <div className="space-y-2">
                    {items?.map((item) => {
                      const typeConfig = itemTypeConfig[item.item_type] || itemTypeConfig.video
                      const TypeIcon = typeConfig.icon

                      return (
                        <div
                          key={item.id || item.position}
                          className="flex items-center gap-3 p-3 rounded-lg bg-muted/30 border border-border/50"
                        >
                          <div className={`p-2 rounded-md bg-background ${typeConfig.color}`}>
                            <TypeIcon className="h-4 w-4" />
                          </div>
                          <div className="flex-1 min-w-0">
                            <p className="font-medium text-foreground truncate">
                              {item.title || `${item.item_type.charAt(0).toUpperCase()}${item.item_type.slice(1)}`}
                            </p>
                            <p className="text-xs text-muted-foreground">
                              #{item.position}
                              {item.duration && ` • ${item.duration.toFixed(1)}s`}
                              {item.resolution && ` • ${item.resolution}`}
                            </p>
                          </div>
                          {item.is_4k && (
                            <Badge variant="outline" className="text-xs">4K</Badge>
                          )}
                        </div>
                      )
                    })}
                  </div>
                </ScrollArea>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Move to Production Dialog */}
        <Dialog open={moveDialogOpen} onOpenChange={setMoveDialogOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Move to Production</DialogTitle>
              <DialogDescription>
                Copy the completed compilation to the production folder.
                Optionally specify a custom filename.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-4">
              <div className="space-y-2">
                <Label htmlFor="filename">Custom Filename (optional)</Label>
                <Input
                  id="filename"
                  value={customFilename}
                  onChange={(e) => setCustomFilename(e.target.value)}
                  placeholder={`${job.channel_name}_${new Date().toISOString().split('T')[0]}`}
                  className="bg-background/50"
                />
                <p className="text-xs text-muted-foreground">
                  Leave empty to auto-generate: channelname_yyyy-mm-dd_hhmmss.mp4
                </p>
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setMoveDialogOpen(false)}>
                Cancel
              </Button>
              <Button onClick={handleMoveToProduction} disabled={moveMutation.isPending}>
                {moveMutation.isPending ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Moving...
                  </>
                ) : (
                  <>
                    <FolderCheck className="mr-2 h-4 w-4" />
                    Move to Production
                  </>
                )}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </Layout>
  )
}
