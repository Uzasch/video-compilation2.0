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
import { Switch } from '@/components/ui/switch'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Separator } from '@/components/ui/separator'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from '@/components/ui/command'
import { ArrowLeft, ArrowRight, Loader2, AlertCircle, CheckCircle, Film, Check, ChevronsUpDown } from 'lucide-react'
import { cn } from '@/lib/utils'

export default function NewCompilation() {
  const { user } = useAuth()
  const navigate = useNavigate()

  const [channel, setChannel] = useState('')
  const [channelOpen, setChannelOpen] = useState(false)
  const [videoIds, setVideoIds] = useState('')
  const [sequence, setSequence] = useState(null)
  const [enable4k, setEnable4k] = useState(false)
  const [includeIntro, setIncludeIntro] = useState(true)
  const [includeOutro, setIncludeOutro] = useState(true)
  const [enableLogos, setEnableLogos] = useState(true)
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
    mutationFn: async ({ channel, videoIds, includeIntro, includeOutro, enableLogos, manualPaths = [] }) => {
      const { data } = await apiClient.post('/jobs/verify', {
        channel_name: channel,
        video_ids: videoIds.split('\n').map(id => id.trim()).filter(Boolean),
        include_intro: includeIntro,
        include_outro: includeOutro,
        enable_logos: enableLogos,
        manual_paths: manualPaths
      })
      return data
    },
    onSuccess: (data) => {
      // If logos are enabled, set logo_channel to the selected channel for all video items
      if (enableLogos && channel) {
        data.items = data.items.map(item =>
          item.item_type === 'video'
            ? { ...item, logo_channel: channel }
            : item
        )
      }
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

  // Verify single path mutation
  const verifyPathMutation = useMutation({
    mutationFn: async (path) => {
      const { data } = await apiClient.post('/jobs/verify-path', { path })
      return data
    }
  })

  // Revalidate mutation - only checks paths, preserves user edits
  const revalidateMutation = useMutation({
    mutationFn: async (items) => {
      const { data } = await apiClient.post('/jobs/revalidate', { items })
      return data
    },
    onSuccess: (data) => {
      // Preserve logo_channel from current sequence
      if (sequence && enableLogos && channel) {
        data.items = data.items.map((item, index) => {
          const originalItem = sequence.items[index]
          if (item.item_type === 'video' && originalItem?.logo_channel) {
            return { ...item, logo_channel: originalItem.logo_channel }
          }
          return item.item_type === 'video' ? { ...item, logo_channel: channel } : item
        })
      }
      setSequence(prev => ({ ...prev, ...data }))
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
      toast.error(error.response?.data?.detail || 'Revalidation failed')
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
    verifyMutation.mutate({ channel, videoIds, includeIntro, includeOutro, enableLogos })
  }

  const handleReverify = () => {
    if (!sequence) return
    // Use revalidate to preserve user edits (deleted items, changed paths)
    revalidateMutation.mutate(sequence.items)
  }

  const handleVerifyPath = async (position, path) => {
    if (!path) {
      toast.error('Please enter a path first')
      return
    }
    try {
      const result = await verifyPathMutation.mutateAsync(path)
      // Update the item with verification result
      const updatedItems = sequence.items.map(item =>
        item.position === position
          ? { ...item, path_available: result.available, duration: result.duration || item.duration }
          : item
      )
      setSequence({ ...sequence, items: updatedItems })

      // Check if all paths are now verified
      const allAvailable = updatedItems.every(item => item.path_available)
      setPathsVerified(allAvailable)

      if (result.available) {
        toast.success('Path verified successfully!')
      } else {
        toast.error('Path not found or inaccessible')
      }
    } catch (error) {
      toast.error('Failed to verify path')
    }
  }

  const handleLogoChannelSelect = async (position, selectedChannel) => {
    try {
      const { data } = await apiClient.get(`/admin/channels/${encodeURIComponent(selectedChannel)}/logo`)
      const updatedItems = sequence.items.map(item =>
        item.position === position
          ? { ...item, logo_channel: selectedChannel, logo_path: data.logo_path }
          : item
      )
      setSequence({ ...sequence, items: updatedItems })
      toast.success(`Logo set from ${selectedChannel}`)
    } catch (error) {
      toast.error(`Failed to get logo for ${selectedChannel}`)
    }
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
              {/* Channel Selection - Searchable Combobox */}
              <div className="space-y-2">
                <Label htmlFor="channel">Channel</Label>
                <Popover open={channelOpen} onOpenChange={setChannelOpen}>
                  <PopoverTrigger asChild>
                    <Button
                      variant="outline"
                      role="combobox"
                      aria-expanded={channelOpen}
                      className="w-full justify-between bg-background/50"
                    >
                      {channel || "Select a channel..."}
                      <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                    </Button>
                  </PopoverTrigger>
                  <PopoverContent className="w-[--radix-popover-trigger-width] p-0" align="start">
                    <Command>
                      <CommandInput placeholder="Search channels..." />
                      <CommandList>
                        <CommandEmpty>No channel found.</CommandEmpty>
                        <CommandGroup>
                          {channels?.map((ch) => (
                            <CommandItem
                              key={ch}
                              value={ch}
                              onSelect={() => {
                                setChannel(channel === ch ? '' : ch)
                                setChannelOpen(false)
                              }}
                            >
                              <Check
                                className={cn(
                                  "mr-2 h-4 w-4",
                                  channel === ch ? "opacity-100" : "opacity-0"
                                )}
                              />
                              {ch}
                            </CommandItem>
                          ))}
                        </CommandGroup>
                      </CommandList>
                    </Command>
                  </PopoverContent>
                </Popover>
              </div>

              {/* Video IDs */}
              <VideoIdInput value={videoIds} onChange={setVideoIds} />

              {/* Options Grid */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* 4K Toggle */}
                <div className="flex items-center justify-between p-4 rounded-lg bg-background/50 border border-border/50">
                  <div>
                    <Label htmlFor="4k-switch" className="text-base font-medium">4K Processing</Label>
                    <p className="text-sm text-muted-foreground">Higher quality output</p>
                  </div>
                  <Switch id="4k-switch" checked={enable4k} onCheckedChange={setEnable4k} />
                </div>

                {/* Logo Toggle */}
                <div className="flex items-center justify-between p-4 rounded-lg bg-background/50 border border-border/50">
                  <div>
                    <Label htmlFor="logo-switch" className="text-base font-medium">Enable Logos</Label>
                    <p className="text-sm text-muted-foreground">Overlay channel logo</p>
                  </div>
                  <Switch id="logo-switch" checked={enableLogos} onCheckedChange={setEnableLogos} />
                </div>

                {/* Intro Toggle */}
                <div className="flex items-center justify-between p-4 rounded-lg bg-background/50 border border-border/50">
                  <div>
                    <Label htmlFor="intro-switch" className="text-base font-medium">Include Intro</Label>
                    <p className="text-sm text-muted-foreground">Add channel intro</p>
                  </div>
                  <Switch id="intro-switch" checked={includeIntro} onCheckedChange={setIncludeIntro} />
                </div>

                {/* Outro Toggle */}
                <div className="flex items-center justify-between p-4 rounded-lg bg-background/50 border border-border/50">
                  <div>
                    <Label htmlFor="outro-switch" className="text-base font-medium">Include Outro</Label>
                    <p className="text-sm text-muted-foreground">Add channel outro</p>
                  </div>
                  <Switch id="outro-switch" checked={includeOutro} onCheckedChange={setIncludeOutro} />
                </div>
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
              onVerifyPath={handleVerifyPath}
              isVerifying={verifyPathMutation.isPending}
              channels={channels || []}
              onLogoChannelSelect={handleLogoChannelSelect}
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
                  <Alert className="border-amber-500/50 bg-amber-500/10">
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
                      disabled={revalidateMutation.isPending}
                      className="flex-1"
                    >
                      {revalidateMutation.isPending ? (
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      ) : null}
                      Re-verify All Paths
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
