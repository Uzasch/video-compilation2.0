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
        placeholder={`Paste video IDs here, one per line...\nabc123\ndef456\nghi789`}
        rows={10}
        className="font-mono text-sm bg-background/50"
      />
      <p className="text-xs text-muted-foreground">
        Enter one video ID per line. Paths and metadata will be fetched automatically.
      </p>
    </div>
  )
}
