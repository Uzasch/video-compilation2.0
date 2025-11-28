import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import apiClient from '../services/api'
import Layout from '../components/Layout'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from '@/components/ui/command'
import { DateRangePicker } from '@/components/ui/date-range-picker'
import { cn } from '@/lib/utils'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  CheckCircle,
  XCircle,
  Ban,
  Clock,
  Tv,
  ChevronLeft,
  ChevronRight,
  History as HistoryIcon,
  FolderCheck,
  Check,
  ChevronsUpDown
} from 'lucide-react'

const statusConfig = {
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
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  })
}

export default function History() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [page, setPage] = useState(1)
  const [channelFilter, setChannelFilter] = useState('all')
  const [channelOpen, setChannelOpen] = useState(false)
  const [dateRange, setDateRange] = useState(undefined)
  const pageSize = 15

  // Fetch history
  const { data, isLoading } = useQuery({
    queryKey: ['jobHistory', user?.id, page, channelFilter, dateRange?.from?.toISOString(), dateRange?.to?.toISOString()],
    queryFn: async () => {
      const params = { page, page_size: pageSize }
      if (user?.role !== 'admin') {
        params.user_id = user.id
      }
      if (channelFilter && channelFilter !== 'all') {
        params.channel_name = channelFilter
      }
      if (dateRange?.from) {
        params.date_from = dateRange.from.toISOString().split('T')[0]
      }
      if (dateRange?.to) {
        params.date_to = dateRange.to.toISOString().split('T')[0]
      }
      const { data } = await apiClient.get('/jobs/history', { params })
      return data
    },
    enabled: !!user
  })

  // Fetch channels for filter
  const { data: channelsData } = useQuery({
    queryKey: ['channels'],
    queryFn: async () => {
      const { data } = await apiClient.get('/admin/channels')
      return data.channels
    }
  })

  const handleChannelChange = (value) => {
    setChannelFilter(value)
    setPage(1)
  }

  const handleDateChange = (range) => {
    setDateRange(range)
    setPage(1)
  }

  return (
    <Layout>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <h2 className="text-3xl font-bold tracking-tight text-foreground">Compilation History</h2>
            <p className="text-muted-foreground mt-1">
              View past compilations and their status
            </p>
          </div>

          {/* Filters */}
          <div className="flex flex-wrap items-center gap-3">
            {/* Date Range Filter */}
            <DateRangePicker
              date={dateRange}
              onDateChange={handleDateChange}
              className="w-64"
              placeholder="Filter by date"
              align="end"
            />

            {/* Channel Filter */}
            <Popover open={channelOpen} onOpenChange={setChannelOpen}>
              <PopoverTrigger asChild>
                <Button
                  variant="outline"
                  role="combobox"
                  aria-expanded={channelOpen}
                  className="w-48 justify-between bg-background/50"
                >
                  {channelFilter === 'all' ? 'All channels' : channelFilter}
                  <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-48 p-0" align="end">
                <Command>
                  <CommandInput placeholder="Search channels..." className="h-9" />
                  <CommandList>
                    <CommandEmpty>No channel found.</CommandEmpty>
                    <CommandGroup>
                      <CommandItem
                        value="all"
                        onSelect={() => {
                          handleChannelChange('all')
                          setChannelOpen(false)
                        }}
                      >
                        All channels
                        <Check
                          className={cn(
                            "ml-auto h-4 w-4",
                            channelFilter === 'all' ? "opacity-100" : "opacity-0"
                          )}
                        />
                      </CommandItem>
                      {channelsData?.map((ch) => (
                        <CommandItem
                          key={ch}
                          value={ch}
                          onSelect={() => {
                            handleChannelChange(ch)
                            setChannelOpen(false)
                          }}
                        >
                          {ch}
                          <Check
                            className={cn(
                              "ml-auto h-4 w-4",
                              channelFilter === ch ? "opacity-100" : "opacity-0"
                            )}
                          />
                        </CommandItem>
                      ))}
                    </CommandGroup>
                  </CommandList>
                </Command>
              </PopoverContent>
            </Popover>
          </div>
        </div>

        {/* History Table */}
        <Card className="bg-card/60 backdrop-blur-sm border-border/50">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <HistoryIcon className="h-5 w-5" />
              Past Compilations
            </CardTitle>
            <CardDescription>
              {data?.total ? `${data.total} compilation${data.total !== 1 ? 's' : ''} found` : 'No compilations yet'}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="space-y-3">
                {[1, 2, 3, 4, 5].map((i) => (
                  <Skeleton key={i} className="h-12 w-full" />
                ))}
              </div>
            ) : data?.jobs?.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12">
                <HistoryIcon className="h-12 w-12 text-muted-foreground/50 mb-4" />
                <p className="text-muted-foreground mb-4">No compilation history yet</p>
                <Button variant="outline" onClick={() => navigate('/new')}>
                  Create your first compilation
                </Button>
              </div>
            ) : (
              <>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Channel</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Duration</TableHead>
                      <TableHead>Quality</TableHead>
                      <TableHead>Production</TableHead>
                      <TableHead>Completed</TableHead>
                      <TableHead className="text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data?.jobs?.map((job) => {
                      const config = statusConfig[job.status] || statusConfig.cancelled
                      const StatusIcon = config.icon

                      return (
                        <TableRow
                          key={job.job_id}
                          className="cursor-pointer hover:bg-muted/50"
                          onClick={() => navigate(`/compilation/${job.job_id}`)}
                        >
                          <TableCell className="font-medium">{job.channel_name}</TableCell>
                          <TableCell>
                            <Badge variant="outline" className={`flex items-center gap-1 w-fit ${config.className}`}>
                              <StatusIcon className="h-3 w-3" />
                              {config.label}
                            </Badge>
                          </TableCell>
                          <TableCell>
                            <span className="flex items-center gap-1 text-muted-foreground">
                              <Clock className="h-3 w-3" />
                              {formatDuration(job.final_duration)}
                            </span>
                          </TableCell>
                          <TableCell>
                            <span className="flex items-center gap-1">
                              <Tv className="h-3 w-3 text-muted-foreground" />
                              {job.enable_4k ? '4K' : 'HD'}
                            </span>
                          </TableCell>
                          <TableCell>
                            {job.moved_to_production ? (
                              <Badge variant="outline" className="bg-primary/10 text-primary border-primary/30">
                                <FolderCheck className="h-3 w-3 mr-1" />
                                Moved
                              </Badge>
                            ) : job.status === 'completed' ? (
                              <span className="text-muted-foreground text-sm">Pending</span>
                            ) : (
                              <span className="text-muted-foreground text-sm">-</span>
                            )}
                          </TableCell>
                          <TableCell className="text-muted-foreground">
                            {formatDate(job.completed_at)}
                          </TableCell>
                          <TableCell className="text-right">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={(e) => {
                                e.stopPropagation()
                                navigate(`/compilation/${job.job_id}`)
                              }}
                            >
                              View
                            </Button>
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
      </div>
    </Layout>
  )
}
