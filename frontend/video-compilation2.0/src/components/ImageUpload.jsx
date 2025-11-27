import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import apiClient from '../services/api'
import { Upload, X, Loader2 } from 'lucide-react'
import { toast } from 'sonner'

export default function ImageUpload({ item, onUpdate }) {
  const [uploading, setUploading] = useState(false)
  const [preview, setPreview] = useState(item.path)

  const handleFileSelect = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return

    if (!file.type.startsWith('image/')) {
      toast.error('Please select an image file')
      return
    }

    if (file.size > 10 * 1024 * 1024) {
      toast.error('Image must be smaller than 10MB')
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
      toast.success('Image uploaded successfully')
    } catch (error) {
      toast.error('Upload failed: ' + (error.response?.data?.detail || error.message))
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
      toast.success('Image removed')
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
