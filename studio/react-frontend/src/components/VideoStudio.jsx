import { useState, useRef, useEffect } from 'react'
import { apiFetch } from '@/lib/api'
import { supabase } from '@/lib/supabase'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import { toast } from 'sonner'
import { UploadCloud, Video, Play, StopCircle, RefreshCcw, Loader2, CheckCircle2, XCircle, Trash2, Download } from 'lucide-react'

const VIDEO_STEP_LABELS = [
  'Probe video',
  'Transcribe audio',
  'Pack transcript',
  'AI cut analysis',
  'Waiting for your approval',
  'Render final video',
]

const VIDEO_STEP_SUBS = [
  'Reading resolution, duration and frame rate...',
  'Uploading audio to ElevenLabs Scribe...',
  'Grouping transcript into phrase-level timeline...',
  'Claude is reading the transcript and selecting the best cuts...',
  'Review and approve the proposed cuts below...',
  'FFmpeg is extracting, grading and concatenating segments...',
]

const GRADE_PRESETS = [
  { value: 'neutral_punch',  label: 'Neutral Punch — light contrast, clean'   },
  { value: 'warm_cinematic', label: 'Warm Cinematic — retro, teal/orange'      },
  { value: 'subtle',         label: 'Subtle — barely perceptible cleanup'      },
  { value: 'none',           label: 'No Grade — straight copy'                 },
  { value: 'auto',           label: 'Auto — per-segment data-driven correction' },
]

const BEAT_COLORS = {
  HOOK:       'text-orange-500',
  POINT:      'text-blue-500',
  EXAMPLE:    'text-green-500',
  INSIGHT:    'text-purple-500',
  TRANSITION: 'text-slate-500',
  CTA:        'text-yellow-500',
  CLOSING:    'text-pink-500',
}

export const VideoStudio = () => {
  const [file, setFile] = useState(null)
  const [grade, setGrade] = useState('neutral_punch')
  const [speakerName, setSpeakerName] = useState('')
  const [speakerTitle, setSpeakerTitle] = useState('')
  const [slideDur, setSlideDur] = useState('4')
  const [graphics, setGraphics] = useState(true)
  const [music, setMusic] = useState(true)

  const [status, setStatus] = useState('idle') // idle, uploading, processing, review, rendering, done, error
  const [uploadProgress, setUploadProgress] = useState(0)
  const [jobId, setJobId] = useState(null)
  const [steps, setSteps] = useState([])
  const [errorDetails, setErrorDetails] = useState(null)
  const [failedStep, setFailedStep] = useState(null)

  const [probe, setProbe] = useState(null)
  const [cuts, setCuts] = useState([])
  const [downloadUrl, setDownloadUrl] = useState(null)

  const fileInputRef = useRef(null)
  const pollTimer = useRef(null)

  const handleFileChange = (e) => {
    const f = e.target.files?.[0]
    if (f) setFile(f)
  }

  const handleDrop = (e) => {
    e.preventDefault()
    const f = e.dataTransfer?.files?.[0]
    if (f) setFile(f)
  }

  const handleUpload = async () => {
    if (!file) return toast.error('Please select a video file first')

    setStatus('uploading')
    setUploadProgress(0)

    try {
      const { data: { session } } = await supabase.auth.getSession()
      const authHeader = session ? { 'Authorization': `Bearer ${session.access_token}` } : {}

      const chunkSize = 20 * 1024 * 1024
      const totalChunks = Math.ceil(file.size / chunkSize)
      const uploadId = crypto.randomUUID()

      for (let i = 0; i < totalChunks; i++) {
        const start = i * chunkSize
        const end = Math.min(start + chunkSize, file.size)
        const chunk = file.slice(start, end)

        const formData = new FormData()
        formData.append('upload_id', uploadId)
        formData.append('chunk_index', i)
        formData.append('file', chunk, file.name)

        const r = await fetch('/api/video/upload_chunk', {
          method: 'POST',
          headers: authHeader,
          body: formData
        })

        if (!r.ok) throw new Error(`Upload failed at chunk ${i + 1}`)
        setUploadProgress(Math.round(((i + 1) / totalChunks) * 100))
      }

      setStatus('processing')
      
      const completeData = new FormData()
      completeData.append('upload_id', uploadId)
      completeData.append('filename', file.name)
      completeData.append('total_chunks', totalChunks)

      const cr = await fetch('/api/video/upload_complete', {
        method: 'POST',
        headers: authHeader,
        body: completeData
      })

      if (!cr.ok) {
        const err = await cr.json().catch(() => ({}))
        throw new Error(err.detail || 'Upload completion failed')
      }

      const res = await cr.json()
      setJobId(res.job_id)
      startPolling(res.job_id)

    } catch (err) {
      toast.error(err.message || 'Upload failed')
      setStatus('idle')
    }
  }

  const startPolling = (id) => {
    if (pollTimer.current) clearInterval(pollTimer.current)
    pollTimer.current = setInterval(() => pollStatus(id), 2000)
  }

  const stopPolling = () => {
    if (pollTimer.current) {
      clearInterval(pollTimer.current)
      pollTimer.current = null
    }
  }

  const pollStatus = async (id) => {
    try {
      const data = await apiFetch(`/api/video/status/${id}`)
      setSteps(data.steps || [])

      if (data.status === 'awaiting_approval') {
        stopPolling()
        setProbe(data.probe)
        setCuts(data.proposed_cuts || [])
        setStatus('review')
      } else if (data.status === 'rendering') {
        setStatus('rendering')
      } else if (data.status === 'done') {
        stopPolling()
        setDownloadUrl(data.download_url)
        setStatus('done')
        toast.success('Video rendered successfully!')
      } else if (data.status === 'error') {
        stopPolling()
        const failedIndex = (data.steps || []).findIndex(s => s.status === 'error')
        setFailedStep(failedIndex >= 0 ? failedIndex : null)
        setErrorDetails(data.error || 'Unknown error')
        setStatus('error')
        toast.error('Pipeline failed')
      }
    } catch {
      // Keep polling
    }
  }

  useEffect(() => {
    return () => stopPolling()
  }, [])

  const handleApprove = async () => {
    if (cuts.length === 0) return toast.error('Add at least one cut')
    setStatus('rendering')
    try {
      await apiFetch(`/api/video/approve/${jobId}`, {
        method: 'POST',
        body: JSON.stringify({
          cuts,
          grade,
          include_graphics: graphics,
          include_music: music,
        })
      })
      startPolling(jobId)
    } catch (err) {
      toast.error('Failed to start render')
      setStatus('review')
    }
  }

  const handleRetry = async () => {
    if (failedStep === null || !jobId) return
    setStatus('processing')
    try {
      await apiFetch(`/api/video/retry/${jobId}`, {
        method: 'POST',
        body: JSON.stringify({
          step_index: failedStep,
          grade,
          include_graphics: graphics,
          include_music: music
        })
      })
      startPolling(jobId)
    } catch (err) {
      toast.error('Failed to retry')
      setStatus('error')
    }
  }

  const reset = () => {
    stopPolling()
    setFile(null)
    setJobId(null)
    setCuts([])
    setStatus('idle')
  }

  return (
    <div className="space-y-6">
      <div>
        <div className="text-xs font-semibold text-primary uppercase tracking-widest mb-1">Production</div>
        <h1 className="text-3xl font-bold tracking-tight">Video Studio</h1>
        <p className="text-muted-foreground mt-1">Upload a raw talking-head MP4 → AI proposes cuts → render.</p>
      </div>

      {status === 'idle' && (
        <Card>
          <CardContent className="pt-6 space-y-6">
            {!file ? (
              <div 
                className="border-2 border-dashed border-border rounded-xl p-12 text-center hover:bg-secondary/50 transition-colors cursor-pointer"
                onClick={() => fileInputRef.current?.click()}
                onDragOver={e => e.preventDefault()}
                onDrop={handleDrop}
              >
                <div className="text-4xl mb-4">🎬</div>
                <div className="font-medium text-lg">Drop your MP4 here</div>
                <div className="text-sm text-muted-foreground mt-1">or click to browse · MP4, MOV, M4V, MKV</div>
                <input 
                  type="file" 
                  accept=".mp4,.mov,.m4v,.avi,.mkv" 
                  className="hidden" 
                  ref={fileInputRef}
                  onChange={handleFileChange}
                />
              </div>
            ) : (
              <div className="flex items-center justify-between p-4 rounded-xl border border-border bg-secondary/20">
                <div className="flex items-center gap-4">
                  <div className="text-3xl">🎞️</div>
                  <div>
                    <div className="font-medium">{file.name}</div>
                    <div className="text-sm text-muted-foreground">{(file.size / (1024*1024)).toFixed(1)} MB</div>
                  </div>
                </div>
                <Button variant="ghost" onClick={() => setFile(null)}>Clear</Button>
              </div>
            )}

            <div className="space-y-4">
              <h3 className="font-semibold">Render Options</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>Color Grade</Label>
                  <select className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm" value={grade} onChange={e => setGrade(e.target.value)}>
                    {GRADE_PRESETS.map(g => <option key={g.value} value={g.value}>{g.label}</option>)}
                  </select>
                </div>
                <div className="space-y-2">
                  <Label>Slide Duration</Label>
                  <select className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm" value={slideDur} onChange={e => setSlideDur(e.target.value)}>
                    <option value="3">3 seconds</option>
                    <option value="4">4 seconds</option>
                    <option value="5">5 seconds</option>
                    <option value="6">6 seconds</option>
                  </select>
                </div>
                <div className="space-y-2">
                  <Label>Speaker Name (optional)</Label>
                  <Input placeholder="e.g. Eduardo Leite" value={speakerName} onChange={e => setSpeakerName(e.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label>Speaker Title (optional)</Label>
                  <Input placeholder="e.g. CEO, Wisuno" value={speakerTitle} onChange={e => setSpeakerTitle(e.target.value)} />
                </div>
              </div>

              <div className="space-y-3">
                <div className="flex justify-between items-center p-3 rounded-lg border border-border bg-secondary/10">
                  <div>
                    <div className="font-medium">AI graphic slides</div>
                    <div className="text-sm text-muted-foreground">Claude extracts 3 data points → HyperFrames animated cards</div>
                  </div>
                  <input type="checkbox" className="w-5 h-5 accent-primary" checked={graphics} onChange={e => setGraphics(e.target.checked)} />
                </div>
                <div className="flex justify-between items-center p-3 rounded-lg border border-border bg-secondary/10">
                  <div>
                    <div className="font-medium">Background music</div>
                    <div className="text-sm text-muted-foreground">ElevenLabs AI-generated instrumental</div>
                  </div>
                  <input type="checkbox" className="w-5 h-5 accent-primary" checked={music} onChange={e => setMusic(e.target.checked)} />
                </div>
              </div>
            </div>

            <Button className="w-full h-12 text-lg font-bold" onClick={handleUpload} disabled={!file}>
              <UploadCloud className="w-5 h-5 mr-2" /> Upload & Analyse
            </Button>
          </CardContent>
        </Card>
      )}

      {(status === 'uploading' || status === 'processing' || status === 'rendering') && (
        <Card>
          <CardHeader>
            <CardTitle>{status === 'uploading' ? `Uploading... ${uploadProgress}%` : status === 'rendering' ? 'Rendering Video...' : 'Analysing Video...'}</CardTitle>
            <CardDescription>{jobId ? `Job ID: ${jobId}` : 'Please wait'}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            {VIDEO_STEP_LABELS.map((label, i) => {
              const step = steps[i] || { status: 'pending' }
              return (
                <div key={i} className={`flex items-start gap-4 ${step.status === 'pending' ? 'opacity-50' : ''}`}>
                  <div className="mt-1">
                    {step.status === 'done' ? <CheckCircle2 className="w-5 h-5 text-green-500" /> :
                     step.status === 'error' ? <XCircle className="w-5 h-5 text-destructive" /> :
                     step.status === 'running' ? <Loader2 className="w-5 h-5 text-primary animate-spin" /> :
                     <div className="w-5 h-5 rounded-full border-2 border-muted-foreground" />}
                  </div>
                  <div>
                    <div className="font-medium">{label}</div>
                    <div className="text-sm text-muted-foreground">
                      {step.status === 'running' ? VIDEO_STEP_SUBS[i] :
                       step.status === 'done' ? (step.note || 'Done') :
                       step.status === 'error' ? step.error : 'Waiting...'}
                    </div>
                  </div>
                </div>
              )
            })}
          </CardContent>
        </Card>
      )}

      {status === 'review' && (
        <Card>
          <CardHeader className="border-b border-border pb-4">
            <div className="flex justify-between items-start">
              <div>
                <CardTitle className="flex items-center"><Video className="w-5 h-5 mr-2" /> Review Proposed Cuts</CardTitle>
                <CardDescription className="mt-1">Claude analysed your transcript. Remove any cuts you don't want, edit the captions, and click Approve.</CardDescription>
              </div>
              <div className="text-right">
                <div className="text-2xl font-black font-mono text-primary">
                  {cuts.reduce((s, c) => s + (c.end - c.start), 0).toFixed(1)}s
                </div>
                <div className="text-xs text-muted-foreground uppercase tracking-widest">total duration</div>
              </div>
            </div>
            
            {probe && (
              <div className="flex flex-wrap gap-3 mt-4 text-xs font-mono text-muted-foreground">
                <Badge variant="secondary">📐 {probe.width}x{probe.height}</Badge>
                <Badge variant="secondary">⏱ {probe.duration?.toFixed(1)}s</Badge>
                <Badge variant="secondary">🎞 {probe.fps} fps</Badge>
                <Badge variant="secondary">💾 {probe.size_mb} MB</Badge>
              </div>
            )}
          </CardHeader>
          <CardContent className="pt-6 space-y-4">
            {cuts.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground border border-dashed rounded-lg">No cuts remaining.</div>
            ) : (
              cuts.map((cut, idx) => (
                <div key={idx} className="p-4 rounded-lg border border-border bg-secondary/20 relative group">
                  <button 
                    className="absolute top-2 right-2 p-2 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded opacity-0 group-hover:opacity-100 transition-opacity"
                    onClick={() => {
                      const newCuts = [...cuts]
                      newCuts.splice(idx, 1)
                      setCuts(newCuts)
                    }}
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                  <div className="flex items-center gap-4 mb-3">
                    <span className={`text-xs font-bold tracking-widest uppercase ${BEAT_COLORS[cut.beat] || 'text-muted-foreground'}`}>{cut.beat || '—'}</span>
                    <div className="flex items-center gap-2 text-sm font-mono bg-background px-3 py-1 rounded border">
                      <input type="number" step="0.1" className="w-16 bg-transparent text-right outline-none" value={cut.start.toFixed(2)} onChange={e => {
                        const newCuts = [...cuts]
                        newCuts[idx].start = Number(e.target.value)
                        setCuts(newCuts)
                      }} />
                      <span className="text-muted-foreground">→</span>
                      <input type="number" step="0.1" className="w-16 bg-transparent outline-none" value={cut.end.toFixed(2)} onChange={e => {
                        const newCuts = [...cuts]
                        newCuts[idx].end = Number(e.target.value)
                        setCuts(newCuts)
                      }} />
                      <span className="text-primary ml-2 bg-primary/10 px-1.5 py-0.5 rounded">
                        {(cut.end - cut.start).toFixed(1)}s
                      </span>
                    </div>
                  </div>
                  <textarea 
                    className="w-full flex min-h-[60px] rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background"
                    value={cut.quote || ''}
                    onChange={e => {
                      const newCuts = [...cuts]
                      newCuts[idx].quote = e.target.value
                      setCuts(newCuts)
                    }}
                  />
                  {cut.reason && <div className="text-xs text-muted-foreground mt-2 italic">{cut.reason}</div>}
                </div>
              ))
            )}

            <div className="flex gap-4 pt-4">
              <Button className="flex-1 h-12 text-lg font-bold" onClick={handleApprove}>
                <CheckCircle2 className="w-5 h-5 mr-2" /> Approve & Render
              </Button>
              <Button variant="outline" className="h-12" onClick={reset}>
                <RefreshCcw className="w-5 h-5 mr-2" /> Start Over
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {status === 'error' && (
        <Card className="border-destructive">
          <CardHeader>
            <CardTitle className="text-destructive flex items-center"><XCircle className="w-5 h-5 mr-2" /> Pipeline Failed</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="p-4 bg-destructive/10 text-destructive rounded-md font-mono text-sm whitespace-pre-wrap">
              {errorDetails}
            </div>
            <div className="flex gap-4 flex-wrap">
              <Button variant="default" onClick={handleRetry} disabled={failedStep === null}><RefreshCcw className="w-4 h-4 mr-2" /> Retry Failed Step</Button>
              <Button variant="secondary" onClick={() => setStatus('review')} disabled={cuts.length === 0}>Edit Cuts & Re-render</Button>
              <Button variant="outline" onClick={reset}>Start Over</Button>
            </div>
          </CardContent>
        </Card>
      )}

      {status === 'done' && (
        <Card className="border-green-500/30">
          <CardHeader>
            <CardTitle className="text-green-500 flex items-center"><CheckCircle2 className="w-5 h-5 mr-2" /> Video Ready</CardTitle>
            <CardDescription>Your polished video is ready. The file includes graded cuts, burned-in subtitles, and loudness-normalized audio (−14 LUFS).</CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="aspect-video bg-black rounded-lg overflow-hidden border border-border">
              <video src={`/api/video/stream/${jobId}`} controls className="w-full h-full" playsInline />
            </div>
            <div className="flex gap-4">
              <Button className="flex-1 h-12" asChild>
                <a href={downloadUrl} download><Download className="w-5 h-5 mr-2" /> Download MP4</a>
              </Button>
              <Button variant="secondary" className="h-12" onClick={reset}>
                <RefreshCcw className="w-5 h-5 mr-2" /> New Video
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
