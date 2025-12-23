import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { useForm, useFieldArray } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { toast } from 'sonner'
import apiClient from '../services/api'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Form,
  FormField,
  FormItem,
  FormControl,
  FormMessage,
} from '@/components/ui/form'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Plus,
  Trash2,
  Loader2,
  CheckCircle,
  XCircle,
  AlertCircle,
  Video
} from 'lucide-react'

// Zod schema for validation
const videoSchema = z.object({
  video_id: z.string().min(1, 'Video ID is required'),
  path: z.string().min(1, 'Path is required'),
  video_title: z.string().min(1, 'Title is required'),
})

const formSchema = z.object({
  videos: z.array(videoSchema).min(1, 'At least one video is required'),
})

export default function AddVideoDialog({ open, onOpenChange }) {
  const [results, setResults] = useState(null)

  const form = useForm({
    resolver: zodResolver(formSchema),
    defaultValues: {
      videos: [{ video_id: '', path: '', video_title: '' }],
    },
  })

  const { fields, append, remove } = useFieldArray({
    control: form.control,
    name: 'videos',
  })

  const addVideoMutation = useMutation({
    mutationFn: async (data) => {
      const response = await apiClient.post('/jobs/videos', data)
      return response.data
    },
    onSuccess: (data) => {
      setResults(data.results)
      if (data.inserted_count > 0 && data.updated_count > 0) {
        toast.success(`Added ${data.inserted_count} new, updated ${data.updated_count} video(s)`)
      } else if (data.inserted_count > 0) {
        toast.success(`Successfully added ${data.inserted_count} video(s)`)
      } else if (data.updated_count > 0) {
        toast.success(`Successfully updated ${data.updated_count} video(s)`)
      }
      if (data.failed_count > 0) {
        toast.warning(`${data.failed_count} video(s) failed validation`)
      }
    },
    onError: (error) => {
      toast.error(error.response?.data?.detail || 'Failed to add videos')
    },
  })

  const onSubmit = (data) => {
    setResults(null)
    addVideoMutation.mutate(data)
  }

  const handleClose = () => {
    form.reset()
    setResults(null)
    onOpenChange(false)
  }

  const addRow = () => {
    append({ video_id: '', path: '', video_title: '' })
  }

  const handleAddMore = () => {
    // Clear the form for more entries but keep results
    form.reset({
      videos: [{ video_id: '', path: '', video_title: '' }],
    })
    setResults(null)
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[900px] max-h-[90vh]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Video className="h-5 w-5" />
            Add Videos
          </DialogTitle>
          <DialogDescription>
            Add new videos to the system. The path will be verified before saving.
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)}>
            <ScrollArea className="h-[350px] pr-4">
              <div className="space-y-3">
                {/* Column Headers */}
                <div className="grid grid-cols-[1fr_2fr_1.5fr_40px] gap-2 px-1 text-sm font-medium text-muted-foreground sticky top-0 bg-background py-2">
                  <div>Video ID *</div>
                  <div>Path *</div>
                  <div>Title *</div>
                  <div></div>
                </div>

                {/* Video Rows */}
                {fields.map((field, index) => (
                  <div key={field.id} className="space-y-1">
                    <div className="grid grid-cols-[1fr_2fr_1.5fr_40px] gap-2 items-start">
                      <FormField
                        control={form.control}
                        name={`videos.${index}.video_id`}
                        render={({ field }) => (
                          <FormItem>
                            <FormControl>
                              <Input
                                {...field}
                                placeholder="abc123xyz"
                                className="h-9"
                              />
                            </FormControl>
                            <FormMessage className="text-xs" />
                          </FormItem>
                        )}
                      />

                      <FormField
                        control={form.control}
                        name={`videos.${index}.path`}
                        render={({ field }) => (
                          <FormItem>
                            <FormControl>
                              <Input
                                {...field}
                                placeholder="V:\folder\video.mp4 or \\192.168.1.6\Share..."
                                className="h-9 font-mono text-xs"
                              />
                            </FormControl>
                            <FormMessage className="text-xs" />
                          </FormItem>
                        )}
                      />

                      <FormField
                        control={form.control}
                        name={`videos.${index}.video_title`}
                        render={({ field }) => (
                          <FormItem>
                            <FormControl>
                              <Input
                                {...field}
                                placeholder="Video Title"
                                className="h-9"
                              />
                            </FormControl>
                            <FormMessage className="text-xs" />
                          </FormItem>
                        )}
                      />

                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        className="h-9 w-9"
                        onClick={() => remove(index)}
                        disabled={fields.length === 1}
                      >
                        <Trash2 className="h-4 w-4 text-muted-foreground hover:text-destructive" />
                      </Button>
                    </div>

                    {/* Show result status if available */}
                    {results?.[index] && (
                      <div className="flex items-center gap-2 text-sm ml-1 px-2 py-1 rounded bg-muted/50">
                        {results[index].saved ? (
                          <CheckCircle className="h-4 w-4 text-green-500 flex-shrink-0" />
                        ) : (
                          <XCircle className="h-4 w-4 text-destructive flex-shrink-0" />
                        )}
                        <span className={`text-xs ${results[index].saved ? 'text-green-600' : 'text-destructive'}`}>
                          {results[index].saved
                            ? (results[index].updated ? 'Updated successfully' : 'Saved successfully')
                            : results[index].error === 'Path not found on SMB share'
                              ? 'File not found - check the path'
                              : results[index].error}
                        </span>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </ScrollArea>

            {/* Add Row Button */}
            {!results && (
              <div className="mt-4">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={addRow}
                  className="w-full"
                >
                  <Plus className="h-4 w-4 mr-2" />
                  Add Another Video
                </Button>
              </div>
            )}

             {/* Changed items-start to items-center */}
            <div className="mt-4 flex items-center gap-3 rounded-lg border bg-muted/50 px-4 py-3">
              <AlertCircle className="h-4 w-4 text-muted-foreground flex-shrink-0" /> 
              <p className="text-xs text-muted-foreground">
                Enter the full path to the video file from Windows Explorer or Mac Finder.
              </p>
            </div>

            <DialogFooter className="mt-6">
              <Button type="button" variant="outline" onClick={handleClose}>
                {results ? 'Close' : 'Cancel'}
              </Button>
              {results ? (
                <Button type="button" onClick={handleAddMore}>
                  <Plus className="h-4 w-4 mr-2" />
                  Add More Videos
                </Button>
              ) : (
                <Button type="submit" disabled={addVideoMutation.isPending}>
                  {addVideoMutation.isPending ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Validating & Saving...
                    </>
                  ) : (
                    'Add Videos'
                  )}
                </Button>
              )}
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}
