# Task 7: Compilation Workflow Pages

## Objective
Build the main compilation workflow: Dashboard with active jobs, New Compilation page with video ID input, sequence editor with per-video logos, and job submission.

---

## 1. Dashboard Page

**File: `frontend/src/pages/Dashboard.jsx`**

```javascript
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useAuth } from '../hooks/useAuth'
import apiClient from '../services/api'
import Layout from '../components/Layout'
import JobCard from '../components/JobCard'
import { Plus, Loader } from 'lucide-react'

export default function Dashboard() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [jobs, setJobs] = useState([])

  // Fetch active jobs
  const { data: initialJobs, isLoading } = useQuery({
    queryKey: ['activeJobs', user?.id],
    queryFn: async () => {
      // Use API client instead of direct Supabase query
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
    refetchInterval: 5000,  // Update every 5 seconds
    enabled: !!user
  })

  useEffect(() => {
    if (initialJobs) {
      setJobs(initialJobs)
    }
  }, [initialJobs])

  // Polling for job updates (alternative to real-time subscriptions)
  // For real-time updates, you can integrate Supabase Realtime separately
  useEffect(() => {
    if (!user) return

    // Poll for updates every 5 seconds
    const interval = setInterval(async () => {
      try {
        const params = { status: 'active' }
        if (user?.role !== 'admin') {
          params.user_id = user.id
        }
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
      <div className="space-y-6">
        {/* Header */}
        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
            <p className="text-sm text-gray-600 mt-1">
              Active compilation jobs
            </p>
          </div>
          <button
            onClick={() => navigate('/new')}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 font-medium"
          >
            <Plus size={20} />
            New Compilation
          </button>
        </div>

        {/* Queue Statistics Card */}
        {queueStats && queueStats.user_jobs.length > 0 && (
          <div className="bg-gradient-to-r from-blue-50 to-indigo-50 rounded-lg shadow p-6 border border-blue-200">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-gray-900">Queue Status</h2>
              <div className="flex items-center gap-2 text-sm text-gray-600">
                <div className="flex items-center gap-1">
                  <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
                  <span>{queueStats.active_workers} workers active</span>
                </div>
                <span className="text-gray-400">•</span>
                <span>{queueStats.total_in_queue} total in queue</span>
              </div>
            </div>

            <div className="space-y-3">
              {queueStats.user_jobs.map((userJob) => (
                <div
                  key={userJob.job_id}
                  className="flex items-center justify-between bg-white rounded-lg p-4 border border-gray-200"
                >
                  <div className="flex items-center gap-3">
                    <div className={`flex items-center justify-center w-10 h-10 rounded-full ${
                      userJob.is_processing ? 'bg-green-100 text-green-700' : 'bg-amber-100 text-amber-700'
                    }`}>
                      <span className="font-bold text-lg">#{userJob.queue_position}</span>
                    </div>
                    <div>
                      <h3 className="font-medium text-gray-900">{userJob.channel_name}</h3>
                      <p className="text-sm text-gray-600">
                        {userJob.is_processing ? (
                          <span className="flex items-center gap-1 text-green-600">
                            <Loader size={14} className="animate-spin" />
                            Processing now
                          </span>
                        ) : (
                          <span className="text-amber-600">
                            {userJob.waiting_count === 0 ? (
                              'Next in queue'
                            ) : (
                              `${userJob.waiting_count} job${userJob.waiting_count > 1 ? 's' : ''} ahead`
                            )}
                          </span>
                        )}
                      </p>
                    </div>
                  </div>
                  <button
                    onClick={() => navigate(`/compilation/${userJob.job_id}`)}
                    className="text-sm text-blue-600 hover:text-blue-700 font-medium"
                  >
                    View Details →
                  </button>
                </div>
              ))}
            </div>

            {queueStats.available_slots > 0 && (
              <div className="mt-4 p-3 bg-green-50 rounded-lg border border-green-200">
                <p className="text-sm text-green-700">
                  ✓ {queueStats.available_slots} worker{queueStats.available_slots > 1 ? 's' : ''} available -
                  your next job will start immediately!
                </p>
              </div>
            )}
          </div>
        )}

        {/* Active Jobs */}
        {isLoading ? (
          <div className="text-center py-12 text-gray-500">Loading jobs...</div>
        ) : jobs.length === 0 ? (
          <div className="text-center py-12">
            <p className="text-gray-500 mb-4">No active jobs</p>
            <button
              onClick={() => navigate('/new')}
              className="text-blue-600 hover:text-blue-700 font-medium"
            >
              Create your first compilation
            </button>
          </div>
        ) : (
          <div className="grid gap-4">
            {jobs.map((job) => (
              <JobCard key={job.job_id} job={job} />
            ))}
          </div>
        )}
      </div>
    </Layout>
  )
}
```

---

## 2. Job Card Component

**File: `frontend/src/components/JobCard.jsx`**

```javascript
import { useNavigate } from 'react-router-dom'
import { Clock, User, Tv, CheckCircle, XCircle, Loader } from 'lucide-react'

export default function JobCard({ job }) {
  const navigate = useNavigate()

  const statusColors = {
    queued: 'bg-yellow-100 text-yellow-800',
    processing: 'bg-blue-100 text-blue-800',
    completed: 'bg-green-100 text-green-800',
    failed: 'bg-red-100 text-red-800',
    cancelled: 'bg-gray-100 text-gray-800'
  }

  const StatusIcon = {
    queued: Clock,
    processing: Loader,
    completed: CheckCircle,
    failed: XCircle,
    cancelled: XCircle
  }[job.status]

  return (
    <div
      onClick={() => navigate(`/compilation/${job.job_id}`)}
      className="bg-white rounded-lg shadow p-6 hover:shadow-md transition-shadow cursor-pointer"
    >
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <div className="flex items-center gap-3 mb-2">
            <h3 className="text-lg font-semibold text-gray-900">
              {job.channel_name}
            </h3>
            <span className={`px-2.5 py-0.5 rounded-full text-xs font-medium ${statusColors[job.status]}`}>
              <span className="flex items-center gap-1">
                <StatusIcon size={14} className={job.status === 'processing' ? 'animate-spin' : ''} />
                {job.status}
              </span>
            </span>
          </div>

          <div className="flex items-center gap-4 text-sm text-gray-600">
            <span className="flex items-center gap-1">
              <User size={16} />
              {job.user_id}
            </span>
            <span className="flex items-center gap-1">
              <Tv size={16} />
              {job.enable_4k ? '4K' : 'HD'}
            </span>
            <span className="flex items-center gap-1">
              <Clock size={16} />
              {new Date(job.created_at).toLocaleString()}
            </span>
          </div>
        </div>

        <div className="text-right">
          {job.status === 'processing' && (
            <div className="text-2xl font-bold text-blue-600">
              {job.progress}%
            </div>
          )}
        </div>
      </div>

      {/* Progress bar for processing jobs */}
      {job.status === 'processing' && (
        <div className="mt-4 space-y-2">
          <div className="w-full bg-gray-200 rounded-full h-2">
            <div
              className="bg-blue-600 h-2 rounded-full transition-all duration-500"
              style={{ width: `${job.progress}%` }}
            />
          </div>

          {/* Progress message and percentage */}
          <div className="flex items-center justify-between text-sm">
            <span className="text-gray-600">
              {job.progress_message || 'Processing...'}
            </span>
            <span className="font-semibold text-blue-600">
              {job.progress}%
            </span>
          </div>
        </div>
      )}

      {/* Error message */}
      {job.status === 'failed' && job.error_message && (
        <div className="mt-3 text-sm text-red-600">
          Error: {job.error_message}
        </div>
      )}
    </div>
  )
}
```

---

## 3. New Compilation Page (Main Form)

**File: `frontend/src/pages/NewCompilation.jsx`**

```javascript
import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import apiClient from '../services/api'
import Layout from '../components/Layout'
import VideoIdInput from '../components/VideoIdInput'
import SequenceEditor from '../components/SequenceEditor'
import { AlertCircle } from 'lucide-react'

export default function NewCompilation() {
  const { user } = useAuth()
  const navigate = useNavigate()

  const [channel, setChannel] = useState('')
  const [videoIds, setVideoIds] = useState('')
  const [sequence, setSequence] = useState(null)
  const [enable4k, setEnable4k] = useState(false)
  const [pathsVerified, setPathsVerified] = useState(false)

  // Fetch channels from BigQuery
  const { data: channels } = useQuery({
    queryKey: ['channels'],
    queryFn: async () => {
      const { data } = await apiClient.get('/admin/channels')
      return data.channels  // Extract channels array from response
    }
  })

  // Verify and build sequence from video IDs (single step - backend does path verification)
  const verifyMutation = useMutation({
    mutationFn: async ({ channel, videoIds, manualPaths = [] }) => {
      const { data } = await apiClient.post('/jobs/verify', {
        channel_name: channel,
        video_ids: videoIds.split('\n').map(id => id.trim()).filter(Boolean),
        manual_paths: manualPaths  // For manually added paths
      })
      return data
    },
    onSuccess: (data) => {
      setSequence(data)
      // Check if all paths are available
      const allAvailable = data.items.every(item => item.path_available)
      setPathsVerified(allAvailable)

      if (!allAvailable) {
        const missingCount = data.items.filter(item => !item.path_available).length
        alert(`${missingCount} item(s) have unavailable paths. Please fix or delete them.`)
      }
    }
  })

  // Step 3: Submit job
  const submitMutation = useMutation({
    mutationFn: async (jobData) => {
      const { data } = await apiClient.post('/jobs/submit', jobData)
      return data
    },
    onSuccess: (data) => {
      navigate(`/compilation/${data.job_id}`)
    }
  })

  const handleVerify = () => {
    if (!channel || !videoIds.trim()) {
      alert('Please select a channel and enter video IDs')
      return
    }
    verifyMutation.mutate({ channel, videoIds })
  }

  // Re-verify after manual edits (e.g., fixing paths)
  const handleReverify = () => {
    if (!sequence) return
    // Collect any manually edited paths
    const manualPaths = sequence.items
      .filter(item => item.item_type === 'transition' || item.item_type === 'image')
      .filter(item => item.path)
      .map(item => item.path)

    verifyMutation.mutate({
      channel,
      videoIds,  // Re-verify with original video IDs
      manualPaths
    })
  }

  const handleSubmit = () => {
    if (!sequence || !pathsVerified) {
      alert('Please verify all paths are available before submitting')
      return
    }

    const jobData = {
      user_id: user.id,
      channel_name: channel,
      enable_4k: enable4k,
      items: sequence.items
    }

    submitMutation.mutate(jobData)
  }

  return (
    <Layout>
      <div className="max-w-5xl mx-auto space-y-6">
        <h1 className="text-2xl font-bold text-gray-900">New Compilation</h1>

        {/* Step 1: Channel & Video IDs */}
        {!sequence && (
          <div className="bg-white rounded-lg shadow p-6 space-y-6">
            <div>
              <h2 className="text-lg font-semibold text-gray-900 mb-4">
                Step 1: Select Channel & Enter Video IDs
              </h2>

              {/* Channel selection */}
              <div className="mb-4">
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Channel
                </label>
                <select
                  value={channel}
                  onChange={(e) => setChannel(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="">Select a channel...</option>
                  {channels?.map((ch) => (
                    <option key={ch.name} value={ch.name}>
                      {ch.name}
                    </option>
                  ))}
                </select>
              </div>

              {/* Video IDs input */}
              <VideoIdInput
                value={videoIds}
                onChange={setVideoIds}
              />

              {/* 4K Option */}
              <div className="mt-4">
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={enable4k}
                    onChange={(e) => setEnable4k(e.target.checked)}
                    className="w-4 h-4 text-blue-600 rounded focus:ring-blue-500"
                  />
                  <span className="text-sm font-medium text-gray-700">
                    Enable 4K Processing
                  </span>
                </label>
              </div>
            </div>

            {/* Error */}
            {verifyMutation.isError && (
              <div className="flex items-start gap-2 p-4 bg-red-50 rounded-md">
                <AlertCircle className="text-red-600 mt-0.5" size={20} />
                <div className="text-sm text-red-700">
                  {verifyMutation.error.response?.data?.detail || 'Verification failed'}
                </div>
              </div>
            )}

            {/* Verify button */}
            <button
              onClick={handleVerify}
              disabled={verifyMutation.isPending}
              className="w-full py-2 px-4 bg-blue-600 text-white rounded-md hover:bg-blue-700 font-medium disabled:opacity-50"
            >
              {verifyMutation.isPending ? 'Verifying...' : 'Verify & Build Sequence'}
            </button>
          </div>
        )}

        {/* Step 2: Edit Sequence */}
        {sequence && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold text-gray-900">
                Step 2: Review & Edit Sequence
              </h2>
              <button
                onClick={() => setSequence(null)}
                className="text-sm text-gray-600 hover:text-gray-900"
              >
                ← Back to Edit
              </button>
            </div>

            <SequenceEditor
              sequence={sequence}
              onChange={setSequence}
            />

            {/* Summary & Submit */}
            <div className="bg-white rounded-lg shadow p-6">
              <div className="space-y-4">
                {/* Summary */}
                <div>
                  <p className="text-sm text-gray-600">
                    Total items: <span className="font-medium">{sequence.items.length}</span>
                  </p>
                  {sequence.total_duration && (
                    <p className="text-sm text-gray-600">
                      Estimated duration: <span className="font-medium">
                        {Math.floor(sequence.total_duration / 60)}m {Math.floor(sequence.total_duration % 60)}s
                      </span>
                    </p>
                  )}
                  {!pathsVerified && (
                    <p className="text-sm text-amber-600 mt-2">
                      ⚠ Some paths are unavailable. Fix them and click "Re-verify" before submitting.
                    </p>
                  )}
                  {pathsVerified && (
                    <p className="text-sm text-green-600 mt-2">
                      ✓ All paths verified and available!
                    </p>
                  )}
                </div>

                {/* Action buttons */}
                <div className="flex gap-3">
                  {!pathsVerified && (
                    <button
                      onClick={handleReverify}
                      disabled={verifyMutation.isPending}
                      className="flex-1 py-2 px-6 bg-blue-600 text-white rounded-md hover:bg-blue-700 font-medium disabled:opacity-50"
                    >
                      {verifyMutation.isPending ? 'Re-verifying...' : 'Re-verify Paths'}
                    </button>
                  )}

                  <button
                    onClick={handleSubmit}
                    disabled={submitMutation.isPending || !pathsVerified}
                    className="flex-1 py-2 px-6 bg-green-600 text-white rounded-md hover:bg-green-700 font-medium disabled:opacity-50"
                  >
                    {submitMutation.isPending ? 'Submitting...' : 'Submit Compilation'}
                  </button>
                </div>

                {/* Help text */}
                <p className="text-xs text-gray-500">
                  {pathsVerified
                    ? 'All files verified. Click "Submit Compilation" to queue the job.'
                    : 'Fix unavailable paths by editing items, then click "Re-verify Paths".'}
                </p>
              </div>
            </div>
          </div>
        )}
      </div>
    </Layout>
  )
}
```

---

## 4. Video ID Input Component

**File: `frontend/src/components/VideoIdInput.jsx`**

```javascript
export default function VideoIdInput({ value, onChange }) {
  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-2">
        Video IDs (one per line)
      </label>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Paste video IDs here, one per line...&#10;abc123&#10;def456&#10;ghi789"
        rows={10}
        className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono text-sm"
      />
      <p className="text-xs text-gray-500 mt-1">
        Enter one video ID per line. Titles and paths will be fetched automatically.
      </p>
    </div>
  )
}
```

---

## 5. Sequence Editor Component

**File: `frontend/src/components/SequenceEditor.jsx`**

```javascript
import { useState } from 'react'
import SequenceItem from './SequenceItem'
import InsertButton from './InsertButton'

export default function SequenceEditor({ sequence, onChange }) {
  const [applyLogoToAll, setApplyLogoToAll] = useState(false)

  const updateItem = (position, updates) => {
    const updatedItems = sequence.items.map((item) =>
      item.position === position ? { ...item, ...updates } : item
    )
    onChange({ ...sequence, items: updatedItems })
  }

  const insertItem = (afterPosition, itemType) => {
    const items = [...sequence.items]
    const insertIndex = items.findIndex(item => item.position === afterPosition)

    // Shift positions of all items after insert point
    items.forEach(item => {
      if (item.position > afterPosition) {
        item.position++
      }
    })

    // Insert new item
    const newItem = {
      position: afterPosition + 1,
      item_type: itemType,
      path: null,
      path_available: false,  // Will be set to true after upload or path verification
      logo_path: itemType === 'video' ? sequence.default_logo_path : null,
      text_animation_text: null,  // Text string for letter-by-letter animation
      duration: itemType === 'image' ? 5 : null,  // Default 5 seconds for images
      title: itemType === 'image' ? 'Image Slide' : null
    }

    items.splice(insertIndex + 1, 0, newItem)

    onChange({ ...sequence, items })
  }

  const deleteItem = (position) => {
    // Can't delete intro or outro
    const item = sequence.items.find(i => i.position === position)
    if (item?.item_type === 'intro' || item?.item_type === 'outro') {
      alert("Can't delete intro or outro")
      return
    }

    let items = sequence.items.filter(i => i.position !== position)

    // Reorder positions
    items = items.map((item, index) => ({
      ...item,
      position: index + 1
    }))

    onChange({ ...sequence, items })
  }

  const handleApplyLogoToAll = (logoPath) => {
    const updatedItems = sequence.items.map((item) => {
      // Only apply to videos, not intro/outro/transitions
      if (item.item_type === 'video') {
        return { ...item, logo_path: logoPath }
      }
      return item
    })
    onChange({ ...sequence, items: updatedItems })
  }

  return (
    <div className="bg-white rounded-lg shadow">
      <div className="p-6 border-b border-gray-200">
        <h3 className="text-lg font-semibold text-gray-900">Video Sequence</h3>
        <p className="text-sm text-gray-600 mt-1">
          Drag to reorder videos, add transitions, and customize per-video settings
        </p>
      </div>

      <div className="p-6 space-y-2">
        {sequence.items.map((item, index) => (
          <div key={item.position}>
            <SequenceItem
              item={item}
              onUpdate={updateItem}
              onDelete={deleteItem}
              onApplyLogoToAll={handleApplyLogoToAll}
              defaultLogoPath={sequence.default_logo_path}
            />

            {/* Insert button (not after outro) */}
            {item.item_type !== 'outro' && (
              <InsertButton
                afterPosition={item.position}
                onInsert={insertItem}
              />
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
```

---

## 6. Sequence Item Component

**File: `frontend/src/components/SequenceItem.jsx`**

```javascript
import { useState } from 'react'
import { Film, Package, Play, Flag, Trash2, Image as ImageIcon, Type } from 'lucide-react'
import ImageUpload from './ImageUpload'

const itemIcons = {
  intro: Play,
  video: Film,
  transition: Package,
  outro: Flag,
  image: ImageIcon
}

const itemColors = {
  intro: 'bg-green-100 text-green-800 border-green-300',
  video: 'bg-blue-100 text-blue-800 border-blue-300',
  transition: 'bg-purple-100 text-purple-800 border-purple-300',
  outro: 'bg-red-100 text-red-800 border-red-300',
  image: 'bg-pink-100 text-pink-800 border-pink-300'
}

export default function SequenceItem({ item, onUpdate, onDelete, onApplyLogoToAll, defaultLogoPath }) {
  const [expanded, setExpanded] = useState(false)
  const Icon = itemIcons[item.item_type]

  const canDelete = item.item_type !== 'intro' && item.item_type !== 'outro'
  const canHaveLogo = item.item_type === 'video'
  const canHaveTextAnimation = item.item_type === 'video'
  const isImage = item.item_type === 'image'

  return (
    <div className={`border-2 rounded-lg ${itemColors[item.item_type]}`}>
      {/* Main row */}
      <div
        className="p-4 cursor-pointer hover:bg-opacity-50"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3 flex-1">
            <Icon size={20} />
            <div className="flex-1">
              <div className="font-medium">
                {item.title || item.item_type.toUpperCase()}
              </div>
              <div className="text-xs opacity-75">
                Position: {item.position}
                {isImage && item.duration && ` • ${item.duration}s`}
                {item.video_id && ` • ${item.video_id}`}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* Path status indicators */}
            {item.path_available && (
              <span className="text-xs bg-green-100 text-green-800 px-2 py-1 rounded flex items-center gap-1">
                ✓ Available
              </span>
            )}
            {!item.path_available && item.path && (
              <span className="text-xs bg-red-100 text-red-800 px-2 py-1 rounded flex items-center gap-1">
                ✗ Not Found
              </span>
            )}
            {!item.path_available && !item.path && (
              <span className="text-xs bg-amber-100 text-amber-800 px-2 py-1 rounded flex items-center gap-1">
                ⚠ Not Verified
              </span>
            )}

            {canDelete && (
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  onDelete(item.position)
                }}
                className="p-1 hover:bg-red-200 rounded"
              >
                <Trash2 size={16} />
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Expanded details */}
      {expanded && (
        <div className="border-t border-current border-opacity-20 p-4 space-y-4 bg-white bg-opacity-50">

          {/* Image upload (only for image type) */}
          {isImage && (
            <ImageUpload item={item} onUpdate={onUpdate} />
          )}

          {/* Path input (for non-image items) */}
          {!isImage && (
            <div>
              <label className="block text-xs font-medium mb-1">Manual Path</label>
              <input
                type="text"
                value={item.path || ''}
                onChange={(e) => onUpdate(item.position, { path: e.target.value, path_available: false })}
                placeholder="\\SERVER\path\to\video.mp4"
                className="w-full px-2 py-1 text-sm border border-gray-300 rounded"
              />
              <p className="text-xs text-gray-500 mt-1">Path will be verified when you click "Verify & Process"</p>
            </div>
          )}

          {/* Logo path (only for videos) */}
          {canHaveLogo && (
            <div>
              <label className="block text-xs font-medium mb-1 flex items-center gap-1">
                <ImageIcon size={14} />
                Logo Path
              </label>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={item.logo_path || ''}
                  onChange={(e) => onUpdate(item.position, { logo_path: e.target.value })}
                  placeholder="\\SERVER\path\to\logo.png"
                  className="flex-1 px-2 py-1 text-sm border border-gray-300 rounded"
                />
                <button
                  onClick={() => onUpdate(item.position, { logo_path: defaultLogoPath })}
                  className="px-3 py-1 text-xs bg-gray-200 hover:bg-gray-300 rounded"
                >
                  Reset
                </button>
                <button
                  onClick={() => onApplyLogoToAll(item.logo_path)}
                  className="px-3 py-1 text-xs bg-blue-600 text-white hover:bg-blue-700 rounded"
                >
                  Apply to All Videos
                </button>
              </div>
            </div>
          )}

          {/* Text animation (only for videos) */}
          {canHaveTextAnimation && (
            <div>
              <label className="block text-xs font-medium mb-1 flex items-center gap-1">
                <Type size={14} />
                Text Animation
              </label>
              <input
                type="text"
                value={item.text_animation_text || ''}
                onChange={(e) => onUpdate(item.position, { text_animation_text: e.target.value || null })}
                placeholder="Text to animate letter-by-letter"
                className="w-full px-2 py-1 text-sm border border-gray-300 rounded"
              />
              <p className="text-xs text-gray-600 mt-1">
                Leave empty to disable text animation for this video
              </p>
            </div>
          )}

          {/* Duration display */}
          {item.duration && (
            <div className="text-xs text-gray-600">
              Duration: {item.duration.toFixed(1)}s
            </div>
          )}
        </div>
      )}
    </div>
  )
}
```

---

## 7. Insert Button Component

**File: `frontend/src/components/InsertButton.jsx`**

```javascript
import { Plus } from 'lucide-react'

export default function InsertButton({ afterPosition, onInsert }) {
  return (
    <div className="flex items-center justify-center py-2">
      <div className="flex gap-2">
        <button
          onClick={() => onInsert(afterPosition, 'video')}
          className="px-3 py-1 text-xs bg-blue-100 text-blue-700 hover:bg-blue-200 rounded-md flex items-center gap-1"
        >
          <Plus size={14} />
          Video
        </button>
        <button
          onClick={() => onInsert(afterPosition, 'transition')}
          className="px-3 py-1 text-xs bg-purple-100 text-purple-700 hover:bg-purple-200 rounded-md flex items-center gap-1"
        >
          <Plus size={14} />
          Transition
        </button>
        <button
          onClick={() => onInsert(afterPosition, 'image')}
          className="px-3 py-1 text-xs bg-pink-100 text-pink-700 hover:bg-pink-200 rounded-md flex items-center gap-1"
        >
          <Plus size={14} />
          Image
        </button>
      </div>
    </div>
  )
}
```

---

## 8. Image Upload Component

**File: `frontend/src/components/ImageUpload.jsx`**

```javascript
import { useState } from 'react'
import { Upload, X, Loader } from 'lucide-react'
import apiClient from '../services/api'

export default function ImageUpload({ item, onUpdate }) {
  const [uploading, setUploading] = useState(false)
  const [preview, setPreview] = useState(item.path)

  const handleFileSelect = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return

    // Validate file type
    if (!file.type.startsWith('image/')) {
      alert('Please select an image file')
      return
    }

    // Validate file size (10MB)
    if (file.size > 10 * 1024 * 1024) {
      alert('Image must be smaller than 10MB')
      return
    }

    setUploading(true)

    try {
      // Create FormData
      const formData = new FormData()
      formData.append('file', file)

      // Upload to backend
      const { data } = await apiClient.post('/uploads/image', formData, {
        headers: {
          'Content-Type': 'multipart/form-data'
        }
      })

      // Update item with uploaded path
      onUpdate(item.position, {
        path: data.path,
        path_available: true,  // File just uploaded, so it's available
        title: item.title || file.name
      })

      // Set preview
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
      // Extract filename from path
      const filename = item.path.split(/[/\\]/).pop()
      await apiClient.delete(`/uploads/image/${filename}`)

      // Clear from item
      onUpdate(item.position, {
        path: null,
        path_available: false
      })

      setPreview(null)
    } catch (error) {
      console.error('Delete failed:', error)
    }
  }

  return (
    <div className="space-y-2">
      <label className="block text-xs font-medium mb-1">
        Upload Image
      </label>

      {preview ? (
        <div className="relative">
          <img
            src={preview}
            alt="Preview"
            className="w-full h-32 object-cover rounded border border-gray-300"
          />
          <button
            onClick={handleRemove}
            className="absolute top-1 right-1 p-1 bg-red-500 text-white rounded-full hover:bg-red-600"
          >
            <X size={16} />
          </button>
        </div>
      ) : (
        <label className="flex flex-col items-center justify-center w-full h-32 border-2 border-gray-300 border-dashed rounded cursor-pointer hover:bg-gray-50">
          <div className="flex flex-col items-center justify-center pt-5 pb-6">
            {uploading ? (
              <Loader className="w-8 h-8 mb-2 text-gray-400 animate-spin" />
            ) : (
              <Upload className="w-8 h-8 mb-2 text-gray-400" />
            )}
            <p className="text-xs text-gray-500">
              {uploading ? 'Uploading...' : 'Click to upload image'}
            </p>
            <p className="text-xs text-gray-400">PNG, JPG, GIF (max 10MB)</p>
          </div>
          <input
            type="file"
            className="hidden"
            accept="image/*"
            onChange={handleFileSelect}
            disabled={uploading}
          />
        </label>
      )}

      {/* Duration input */}
      <div>
        <label className="block text-xs font-medium mb-1">
          Display Duration (seconds)
        </label>
        <input
          type="number"
          min="0.5"
          max="60"
          step="0.5"
          value={item.duration || 5}
          onChange={(e) => onUpdate(item.position, { duration: parseFloat(e.target.value) })}
          className="w-full px-2 py-1 text-sm border border-gray-300 rounded"
        />
      </div>

      {/* Title input */}
      <div>
        <label className="block text-xs font-medium mb-1">
          Title (optional)
        </label>
        <input
          type="text"
          value={item.title || ''}
          onChange={(e) => onUpdate(item.position, { title: e.target.value })}
          placeholder="Image slide title"
          className="w-full px-2 py-1 text-sm border border-gray-300 rounded"
        />
      </div>
    </div>
  )
}
```

---

## Checklist

- [ ] Dashboard page with active jobs list
- [ ] Queue statistics card showing user's position in queue
- [ ] Queue stats update every 5 seconds (polling)
- [ ] Display processing vs waiting status for each job
- [ ] JobCard component with progress bar
- [ ] JobCard displays progress_message alongside percentage
- [ ] Jobs polling for updates (every 5 seconds)
- [ ] New Compilation page with channel selection
- [ ] Channel list from `/api/admin/channels`
- [ ] Video ID input component
- [ ] Verify button calls `/api/jobs/verify` (single step - builds sequence AND verifies paths)
- [ ] Sequence editor with all items in order
- [ ] SequenceItem component with expandable details
- [ ] SequenceItem shows path_available badges (✓ Available, ✗ Not Found)
- [ ] Per-video logo input with "Apply to All" button
- [ ] Per-video text_animation_text input (string, not array)
- [ ] Insert buttons for adding videos/transitions/images
- [ ] ImageUpload component with preview (uses `/api/uploads/image`)
- [ ] Image duration and title inputs
- [ ] Delete functionality (except intro/outro)
- [ ] Manual path input for transitions/images
- [ ] "Re-verify" button to re-check paths after manual edits
- [ ] Show warning if any paths unavailable
- [ ] Disable submit button until all paths verified
- [ ] Submit button calls `/api/jobs/submit` (only if all path_available=true)
- [ ] Test full workflow: video IDs → verify → edit sequence → submit
- [ ] Test image upload and insertion in sequence
- [ ] Test fixing unavailable paths with re-verify

---

## Next: Task 8
Build History page, Compilation Details page, and Admin panel.
