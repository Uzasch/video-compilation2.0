import { useNavigate } from 'react-router-dom'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { Clock, Loader2, CheckCircle, XCircle, Tv, Calendar } from 'lucide-react'

const statusConfig = {
  queued: { label: 'Queued', variant: 'secondary', icon: Clock },
  processing: { label: 'Processing', variant: 'default', icon: Loader2 },
  completed: { label: 'Completed', variant: 'outline', icon: CheckCircle, className: 'bg-green-500/10 text-green-600 border-green-500/30' },
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
              <Badge variant={config.variant} className={`flex items-center gap-1 ${config.className || ''}`}>
                <StatusIcon className={`h-3 w-3 ${job.status === 'processing' ? 'animate-spin' : ''}`} />
                {config.label}
              </Badge>
            </div>
            <div className="flex items-center gap-4 text-sm text-muted-foreground">
              <span className="flex items-center gap-1">
                <Tv className="h-4 w-4" />
                {job.enable_4k ? '4K' : 'Full HD'}
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
