import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { DragDropContext, Droppable, Draggable } from '@hello-pangea/dnd'
import { toast } from 'sonner'
import apiClient from '../services/api'
import Layout from '../components/Layout'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { Skeleton } from '@/components/ui/skeleton'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from '@/components/ui/command'
import { DateRangePicker } from '@/components/ui/date-range-picker'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { cn } from '@/lib/utils'
import {
  Activity,
  BarChart3,
  CheckCircle,
  ChevronLeft,
  ChevronRight,
  ChevronsUpDown,
  Check,
  Clock,
  GripVertical,
  Loader2,
  Server,
  Tv,
  Users,
  XCircle,
  Ban,
  Trash2,
  RefreshCw,
  Zap,
  TrendingUp,
  Calendar,
  Timer
} from 'lucide-react'

const statusConfig = {
  queued: { label: 'Queued', icon: Clock, className: 'bg-amber-500/10 text-amber-600 border-amber-500/30' },
  processing: { label: 'Processing', icon: Loader2, className: 'bg-blue-500/10 text-blue-600 border-blue-500/30' },
  completed: { label: 'Completed', icon: CheckCircle, className: 'bg-green-500/10 text-green-600 border-green-500/30' },
  failed: { label: 'Failed', icon: XCircle, className: 'bg-destructive/10 text-destructive border-destructive/30' },
  cancelled: { label: 'Cancelled', icon: Ban, className: 'bg-muted text-muted-foreground border-border' }
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
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  })
}

function formatUptime(seconds) {
  if (!seconds) return '-'
  const hours = Math.floor(seconds / 3600)
  const mins = Math.floor((seconds % 3600) / 60)
  return `${hours}h ${mins}m`
}

// ==================== STATS CARDS ====================
function StatsCards({ stats, workersData }) {
  const cards = [
    {
      title: 'Total Jobs',
      value: stats?.total_jobs || 0,
      icon: BarChart3,
      description: `${stats?.completed_today || 0} completed today`
    },
    {
      title: 'Processing',
      value: stats?.by_status?.processing || 0,
      icon: Loader2,
      description: `${stats?.by_status?.queued || 0} queued`,
      iconClass: 'animate-spin'
    },
    {
      title: 'Success Rate',
      value: `${stats?.success_rate || 0}%`,
      icon: TrendingUp,
      description: `${stats?.by_status?.failed || 0} failed`
    },
    {
      title: 'Active Workers',
      value: workersData?.total_workers || 0,
      icon: Server,
      description: `${workersData?.busy_workers || 0} busy, ${workersData?.idle_workers || 0} idle`
    },
    {
      title: 'Avg Processing',
      value: `${stats?.avg_processing_time_minutes || 0}m`,
      icon: Timer,
      description: `${stats?.total_video_duration_hours || 0}h total video`
    }
  ]

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-5">
      {cards.map((card) => (
        <Card key={card.title} className="bg-card/60 backdrop-blur-sm border-border/50">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              {card.title}
            </CardTitle>
            <card.icon className={cn("h-4 w-4 text-muted-foreground", card.iconClass)} />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-foreground">{card.value}</div>
            <p className="text-xs text-muted-foreground mt-1">{card.description}</p>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}

// ==================== QUEUE MANAGER ====================
function QueueManager({ queueData, onReorder, onCancel, isReordering }) {
  const jobs = queueData?.jobs || []

  const handleDragEnd = (result) => {
    if (!result.destination) return

    const sourceIndex = result.source.index
    const destIndex = result.destination.index

    if (sourceIndex === destIndex) return

    // Get only queued jobs for reordering
    const queuedJobs = jobs.filter(j => j.status === 'queued')
    const processingJobs = jobs.filter(j => j.status === 'processing')

    // Reorder queued jobs
    const reordered = [...queuedJobs]
    const [moved] = reordered.splice(sourceIndex - processingJobs.length, 1)
    reordered.splice(destIndex - processingJobs.length, 0, moved)

    // Create position updates
    const positions = reordered.map((job, index) => ({
      job_id: job.job_id,
      position: index + 1
    }))

    onReorder(positions)
  }

  if (!jobs.length) {
    return (
      <Card className="bg-card/60 backdrop-blur-sm border-border/50">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Activity className="h-5 w-5" />
            Queue Management
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
            <CheckCircle className="h-12 w-12 mb-4 opacity-50" />
            <p>Queue is empty</p>
          </div>
        </CardContent>
      </Card>
    )
  }

  const processingJobs = jobs.filter(j => j.status === 'processing')
  const queuedJobs = jobs.filter(j => j.status === 'queued')

  return (
    <Card className="bg-card/60 backdrop-blur-sm border-border/50">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Activity className="h-5 w-5" />
          Queue Management
        </CardTitle>
        <CardDescription>
          {queueData?.processing || 0} processing, {queueData?.queued || 0} queued
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ScrollArea className="h-[400px] pr-4">
          {/* Processing jobs (not draggable) */}
          {processingJobs.map((job) => (
            <div
              key={job.job_id}
              className="flex items-center gap-3 p-3 mb-2 rounded-lg bg-blue-500/10 border border-blue-500/30"
            >
              <div className="w-6 flex justify-center">
                <Loader2 className="h-4 w-4 animate-spin text-blue-600" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-foreground">{job.channel_name}</span>
                  {job.enable_4k && <Badge variant="outline" className="text-xs">4K</Badge>}
                </div>
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <span>{job.display_name}</span>
                  <span>•</span>
                  <span>{job.progress || 0}%</span>
                </div>
              </div>
              <Progress value={job.progress || 0} className="w-20 h-2" />
            </div>
          ))}

          {/* Queued jobs (draggable) */}
          <DragDropContext onDragEnd={handleDragEnd}>
            <Droppable droppableId="queue">
              {(provided) => (
                <div {...provided.droppableProps} ref={provided.innerRef}>
                  {queuedJobs.map((job, index) => (
                    <Draggable
                      key={job.job_id}
                      draggableId={job.job_id}
                      index={index + processingJobs.length}
                    >
                      {(provided, snapshot) => (
                        <div
                          ref={provided.innerRef}
                          {...provided.draggableProps}
                          className={cn(
                            "flex items-center gap-3 p-3 mb-2 rounded-lg bg-muted/30 border border-border/50",
                            snapshot.isDragging && "shadow-lg opacity-90"
                          )}
                        >
                          <div
                            {...provided.dragHandleProps}
                            className="cursor-grab active:cursor-grabbing"
                          >
                            <GripVertical className="h-4 w-4 text-muted-foreground" />
                          </div>
                          <div className="w-6 text-center text-sm font-medium text-muted-foreground">
                            #{index + 1}
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="font-medium text-foreground">{job.channel_name}</span>
                              {job.enable_4k && <Badge variant="outline" className="text-xs">4K</Badge>}
                            </div>
                            <div className="text-xs text-muted-foreground">
                              {job.display_name} • {formatDate(job.created_at)}
                            </div>
                          </div>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8 text-muted-foreground hover:text-destructive"
                            onClick={() => onCancel(job.job_id)}
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      )}
                    </Draggable>
                  ))}
                  {provided.placeholder}
                </div>
              )}
            </Droppable>
          </DragDropContext>
        </ScrollArea>
      </CardContent>
    </Card>
  )
}

// ==================== WORKER STATUS ====================
function WorkerStatus({ workersData, isLoading }) {
  const workers = workersData?.workers || []

  if (isLoading) {
    return (
      <Card className="bg-card/60 backdrop-blur-sm border-border/50">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Server className="h-5 w-5" />
            Worker Status
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {[1, 2].map((i) => (
              <Skeleton key={i} className="h-20 w-full" />
            ))}
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card className="bg-card/60 backdrop-blur-sm border-border/50">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Server className="h-5 w-5" />
          Worker Status
        </CardTitle>
        <CardDescription>
          {workersData?.total_workers || 0} workers connected
        </CardDescription>
      </CardHeader>
      <CardContent>
        {workers.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
            <Server className="h-12 w-12 mb-4 opacity-50" />
            <p>No workers connected</p>
            {workersData?.error && (
              <p className="text-xs mt-2">{workersData.error}</p>
            )}
          </div>
        ) : (
          <ScrollArea className="h-[340px] pr-4">
            <div className="space-y-3">
              {workers.map((worker) => (
                <div
                  key={worker.name}
                  className={cn(
                    "p-4 rounded-lg border",
                    worker.status === 'busy'
                      ? "bg-blue-500/10 border-blue-500/30"
                      : "bg-muted/30 border-border/50"
                  )}
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-medium text-foreground truncate max-w-[180px]">
                      {worker.name}
                    </span>
                    <Badge
                      variant="outline"
                      className={cn(
                        worker.status === 'busy'
                          ? "bg-blue-500/10 text-blue-600 border-blue-500/30"
                          : "bg-green-500/10 text-green-600 border-green-500/30"
                      )}
                    >
                      {worker.status === 'busy' ? (
                        <>
                          <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                          Busy
                        </>
                      ) : (
                        <>
                          <Zap className="h-3 w-3 mr-1" />
                          Idle
                        </>
                      )}
                    </Badge>
                  </div>

                  {worker.current_task && (
                    <div className="text-sm text-muted-foreground mb-2">
                      <span className="text-foreground">{worker.current_task.name}</span>
                      {worker.current_task.args?.[0] && (
                        <span className="text-xs ml-2 font-mono">
                          {worker.current_task.args[0].substring(0, 8)}...
                        </span>
                      )}
                    </div>
                  )}

                  <div className="flex items-center gap-4 text-xs text-muted-foreground">
                    <span>Uptime: {formatUptime(worker.uptime)}</span>
                    <span>Reserved: {worker.reserved_count}</span>
                  </div>
                </div>
              ))}
            </div>
          </ScrollArea>
        )}
      </CardContent>
    </Card>
  )
}

// ==================== JOB HISTORY TABLE ====================
function JobHistoryTable({ channelsData }) {
  const [page, setPage] = useState(1)
  const [statusFilter, setStatusFilter] = useState('all')
  const [channelFilter, setChannelFilter] = useState('all')
  const [dateRange, setDateRange] = useState(undefined)
  const [statusOpen, setStatusOpen] = useState(false)
  const [channelOpen, setChannelOpen] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ['adminJobs', page, statusFilter, channelFilter, dateRange?.from?.toISOString(), dateRange?.to?.toISOString()],
    queryFn: async () => {
      const params = { page, page_size: 15 }
      if (statusFilter !== 'all') params.status = statusFilter
      if (channelFilter !== 'all') params.channel_name = channelFilter
      if (dateRange?.from) params.date_from = dateRange.from.toISOString().split('T')[0]
      if (dateRange?.to) params.date_to = dateRange.to.toISOString().split('T')[0]
      const { data } = await apiClient.get('/admin/jobs', { params })
      return data
    }
  })

  const handleDateChange = (range) => {
    setDateRange(range)
    setPage(1)
  }

  const jobs = data?.jobs || []
  const statuses = ['all', 'queued', 'processing', 'completed', 'failed', 'cancelled']
  const channels = channelsData || []

  return (
    <Card className="bg-card/60 backdrop-blur-sm border-border/50">
      <CardHeader>
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <CardTitle className="flex items-center gap-2">
              <BarChart3 className="h-5 w-5" />
              Job History
            </CardTitle>
            <CardDescription>
              {data?.total || 0} total jobs
            </CardDescription>
          </div>

          {/* Filters */}
          <div className="flex flex-wrap gap-2">
            {/* Date range filter */}
            <DateRangePicker
              date={dateRange}
              onDateChange={handleDateChange}
              className="w-56"
              placeholder="Filter by date"
              align="end"
            />

            {/* Status filter */}
            <Popover open={statusOpen} onOpenChange={setStatusOpen}>
              <PopoverTrigger asChild>
                <Button variant="outline" className="w-32 justify-between bg-background/50">
                  {statusFilter === 'all' ? 'All Status' : statusConfig[statusFilter]?.label || statusFilter}
                  <ChevronsUpDown className="ml-2 h-4 w-4 opacity-50" />
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-32 p-0">
                <Command>
                  <CommandList>
                    <CommandGroup>
                      {statuses.map((status) => (
                        <CommandItem
                          key={status}
                          value={status}
                          onSelect={() => {
                            setStatusFilter(status)
                            setPage(1)
                            setStatusOpen(false)
                          }}
                        >
                          {status === 'all' ? 'All Status' : statusConfig[status]?.label || status}
                          <Check className={cn("ml-auto h-4 w-4", statusFilter === status ? "opacity-100" : "opacity-0")} />
                        </CommandItem>
                      ))}
                    </CommandGroup>
                  </CommandList>
                </Command>
              </PopoverContent>
            </Popover>

            {/* Channel filter */}
            <Popover open={channelOpen} onOpenChange={setChannelOpen}>
              <PopoverTrigger asChild>
                <Button variant="outline" className="w-40 justify-between bg-background/50">
                  {channelFilter === 'all' ? 'All Channels' : channelFilter}
                  <ChevronsUpDown className="ml-2 h-4 w-4 opacity-50" />
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-40 p-0">
                <Command>
                  <CommandInput placeholder="Search..." className="h-9" />
                  <CommandList>
                    <CommandEmpty>No channel found.</CommandEmpty>
                    <CommandGroup>
                      <CommandItem
                        value="all"
                        onSelect={() => {
                          setChannelFilter('all')
                          setPage(1)
                          setChannelOpen(false)
                        }}
                      >
                        All Channels
                        <Check className={cn("ml-auto h-4 w-4", channelFilter === 'all' ? "opacity-100" : "opacity-0")} />
                      </CommandItem>
                      {channels.map((ch) => (
                        <CommandItem
                          key={ch}
                          value={ch}
                          onSelect={() => {
                            setChannelFilter(ch)
                            setPage(1)
                            setChannelOpen(false)
                          }}
                        >
                          {ch}
                          <Check className={cn("ml-auto h-4 w-4", channelFilter === ch ? "opacity-100" : "opacity-0")} />
                        </CommandItem>
                      ))}
                    </CommandGroup>
                  </CommandList>
                </Command>
              </PopoverContent>
            </Popover>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-3">
            {[1, 2, 3, 4, 5].map((i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Channel</TableHead>
                  <TableHead>User</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Worker</TableHead>
                  <TableHead>Duration</TableHead>
                  <TableHead>Created</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {jobs.map((job) => {
                  const config = statusConfig[job.status] || statusConfig.queued
                  const StatusIcon = config.icon

                  return (
                    <TableRow key={job.job_id}>
                      <TableCell className="font-medium">
                        <div className="flex items-center gap-2">
                          {job.channel_name}
                          {job.enable_4k && (
                            <Badge variant="outline" className="text-xs">
                              <Tv className="h-3 w-3 mr-1" />
                              4K
                            </Badge>
                          )}
                        </div>
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {job.display_name || job.username}
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className={`flex items-center gap-1 w-fit ${config.className}`}>
                          <StatusIcon className={cn("h-3 w-3", job.status === 'processing' && "animate-spin")} />
                          {config.label}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-muted-foreground font-mono text-xs">
                        {job.worker_id ? (
                          <span title={job.worker_id}>
                            {job.worker_id.split('@')[0] || job.worker_id.substring(0, 12)}
                          </span>
                        ) : '-'}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {formatDuration(job.final_duration)}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {formatDate(job.created_at)}
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>

            {/* Pagination */}
            {data && data.total_pages > 1 && (
              <div className="flex items-center justify-between mt-4 pt-4 border-t border-border/50">
                <p className="text-sm text-muted-foreground">
                  Page {data.page} of {data.total_pages}
                </p>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage(p => Math.max(1, p - 1))}
                    disabled={page === 1}
                  >
                    <ChevronLeft className="h-4 w-4 mr-1" />
                    Previous
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage(p => Math.min(data.total_pages, p + 1))}
                    disabled={page >= data.total_pages}
                  >
                    Next
                    <ChevronRight className="h-4 w-4 ml-1" />
                  </Button>
                </div>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  )
}

// ==================== MAIN ADMIN PAGE ====================
export default function Admin() {
  const queryClient = useQueryClient()

  // Fetch stats
  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ['adminStats'],
    queryFn: async () => {
      const { data } = await apiClient.get('/admin/stats')
      return data
    },
    refetchInterval: 30000 // Refresh every 30 seconds
  })

  // Fetch queue
  const { data: queueData, isLoading: queueLoading } = useQuery({
    queryKey: ['adminQueue'],
    queryFn: async () => {
      const { data } = await apiClient.get('/admin/queue')
      return data
    },
    refetchInterval: 5000 // Refresh every 5 seconds
  })

  // Fetch workers
  const { data: workersData, isLoading: workersLoading } = useQuery({
    queryKey: ['adminWorkers'],
    queryFn: async () => {
      const { data } = await apiClient.get('/admin/workers')
      return data
    },
    refetchInterval: 5000 // Refresh every 5 seconds
  })

  // Fetch channels for filter
  const { data: channelsData } = useQuery({
    queryKey: ['channels'],
    queryFn: async () => {
      const { data } = await apiClient.get('/admin/channels')
      return data.channels
    }
  })

  // Reorder mutation
  const reorderMutation = useMutation({
    mutationFn: async (positions) => {
      const { data } = await apiClient.post('/admin/queue/reorder', { positions })
      return data
    },
    onSuccess: (data) => {
      if (data.errors?.length) {
        toast.warning(`Updated ${data.updated} jobs. Errors: ${data.errors.join(', ')}`)
      } else {
        toast.success(`Queue reordered (${data.updated} jobs updated)`)
      }
      queryClient.invalidateQueries(['adminQueue'])
    },
    onError: (error) => {
      toast.error(error.response?.data?.detail || 'Failed to reorder queue')
    }
  })

  // Cancel mutation
  const cancelMutation = useMutation({
    mutationFn: async (jobId) => {
      const { data } = await apiClient.post(`/admin/jobs/${jobId}/cancel`)
      return data
    },
    onSuccess: (data) => {
      toast.success(`Job cancelled: ${data.channel_name}`)
      queryClient.invalidateQueries(['adminQueue'])
      queryClient.invalidateQueries(['adminStats'])
    },
    onError: (error) => {
      toast.error(error.response?.data?.detail || 'Failed to cancel job')
    }
  })

  const handleCancel = (jobId) => {
    if (confirm('Are you sure you want to cancel this job?')) {
      cancelMutation.mutate(jobId)
    }
  }

  return (
    <Layout>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex justify-between items-center">
          <div>
            <h2 className="text-3xl font-bold tracking-tight text-foreground">Admin Dashboard</h2>
            <p className="text-muted-foreground mt-1">
              Manage queue, monitor workers, and view system statistics
            </p>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              queryClient.invalidateQueries(['adminStats'])
              queryClient.invalidateQueries(['adminQueue'])
              queryClient.invalidateQueries(['adminWorkers'])
            }}
          >
            <RefreshCw className="h-4 w-4 mr-2" />
            Refresh
          </Button>
        </div>

        {/* Stats Cards */}
        {statsLoading ? (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-5">
            {[1, 2, 3, 4, 5].map((i) => (
              <Skeleton key={i} className="h-24" />
            ))}
          </div>
        ) : (
          <StatsCards stats={stats} workersData={workersData} />
        )}

        {/* Queue and Workers */}
        <div className="grid gap-6 lg:grid-cols-2">
          <QueueManager
            queueData={queueData}
            onReorder={(positions) => reorderMutation.mutate(positions)}
            onCancel={handleCancel}
            isReordering={reorderMutation.isPending}
          />
          <WorkerStatus workersData={workersData} isLoading={workersLoading} />
        </div>

        {/* Job History */}
        <JobHistoryTable channelsData={channelsData} />
      </div>
    </Layout>
  )
}
