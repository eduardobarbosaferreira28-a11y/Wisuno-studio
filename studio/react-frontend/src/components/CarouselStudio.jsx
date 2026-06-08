import { useState, useEffect, useRef } from 'react'
import { apiFetch } from '@/lib/api'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import { toast } from 'sonner'
import { Link, ClipboardCopy, Download, Eye, Play, StopCircle, RefreshCcw, Loader2, CheckCircle2, XCircle } from 'lucide-react'
import { Badge } from '@/components/ui/badge'

const LANGUAGES = [
  { code: 'en',    name: 'English',            flag: '🇬🇧', locked: true  },
  { code: 'zh-TW', name: 'Traditional Chinese', flag: '🇹🇼', locked: false },
  { code: 'zh-CN', name: 'Simplified Chinese',  flag: '🇨🇳', locked: false },
  { code: 'th',    name: 'Thai',                flag: '🇹🇭', locked: false },
  { code: 'sw',    name: 'Kiswahili',           flag: '🇰🇪', locked: false },
]

const CONTENT_TYPES = [
  { value: 'market_insight', label: 'Market Insight'  },
  { value: 'market_update',  label: 'Market Update'   },
  { value: 'educational',    label: 'Educational'     },
]

const STEP_LABELS = [
  'Fetch & extract article',
  'Generate script with AI',
  'Generate images',
  'Translate to selected languages',
  'Build carousel files',
]

const STEP_SUBS = [
  'Reading the article from URL or pasted text…',
  'Claude is writing slide content…',
  'Gemini is generating background images…',
  'Translating slides to each language…',
  'Assembling the final HTML carousel files…',
]

export const CarouselStudio = () => {
  const [inputMode, setInputMode] = useState('url')
  const [url, setUrl] = useState('')
  const [text, setText] = useState('')
  const [numSlides, setNumSlides] = useState(6)
  const [contentType, setContentType] = useState('market_insight')
  const [skipImages, setSkipImages] = useState(false)
  const [languages, setLanguages] = useState(new Set(['en']))

  const [jobId, setJobId] = useState(null)
  const [status, setStatus] = useState('idle') // idle, running, done, error
  const [steps, setSteps] = useState([])
  const [results, setResults] = useState(null)
  const [errorDetails, setErrorDetails] = useState(null)

  const pollTimer = useRef(null)

  const toggleLanguage = (code) => {
    if (code === 'en') return
    const newSet = new Set(languages)
    if (newSet.has(code)) newSet.delete(code)
    else newSet.add(code)
    setLanguages(newSet)
  }

  const handleGenerate = async () => {
    if (inputMode === 'url' && !url.trim()) return toast.error('Please enter a URL')
    if (inputMode === 'text' && !text.trim()) return toast.error('Please enter text')

    setStatus('running')
    setSteps([])
    setResults(null)
    setErrorDetails(null)

    try {
      const res = await apiFetch('/api/carousel/run', {
        method: 'POST',
        body: JSON.stringify({
          url: inputMode === 'url' ? url.trim() : null,
          text: inputMode === 'text' ? text.trim() : null,
          num_slides: numSlides,
          content_type: contentType,
          skip_images: skipImages,
          languages: Array.from(languages)
        })
      })

      setJobId(res.job_id)
      toast.info(`Job started (${res.job_id})`)
      startPolling(res.job_id)
    } catch (err) {
      console.error(err)
      setStatus('error')
      setErrorDetails(err.message)
    }
  }

  const startPolling = (id) => {
    if (pollTimer.current) clearInterval(pollTimer.current)
    pollTimer.current = setInterval(() => pollStatus(id), 1500)
  }

  const stopPolling = () => {
    if (pollTimer.current) {
      clearInterval(pollTimer.current)
      pollTimer.current = null
    }
  }

  const pollStatus = async (id) => {
    try {
      const data = await apiFetch(`/api/carousel/status/${id}`)
      setSteps(data.steps || [])

      if (data.status === 'done') {
        stopPolling()
        setStatus('done')
        setResults(data.files)
        toast.success('Carousel generated successfully!')
      } else if (data.status === 'error') {
        stopPolling()
        setStatus('error')
        setErrorDetails(data.error || 'Unknown error occurred')
        toast.error('Generation failed')
      }
    } catch (err) {
      // Keep polling on network errors
    }
  }

  useEffect(() => {
    return () => stopPolling()
  }, [])

  const cancelJob = () => {
    stopPolling()
    setStatus('idle')
    setJobId(null)
    toast.info('Job cancelled')
  }

  const copyCaption = async (url) => {
    try {
      const txt = await fetch(url).then(r => r.text())
      await navigator.clipboard.writeText(txt)
      toast.success('Caption copied to clipboard')
    } catch {
      toast.error('Failed to copy caption')
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <div className="text-xs font-semibold text-primary uppercase tracking-widest mb-1">Production</div>
        <h1 className="text-3xl font-bold tracking-tight">Carousel Studio</h1>
        <p className="text-muted-foreground mt-1">Turn any news article or text into a branded Instagram carousel.</p>
      </div>

      {status === 'idle' && (
        <Card>
          <div className="flex border-b border-border">
            <button 
              className={`flex-1 p-3 text-sm font-medium transition-colors ${inputMode === 'url' ? 'bg-primary/10 text-primary border-b-2 border-primary' : 'text-muted-foreground hover:bg-secondary'}`}
              onClick={() => setInputMode('url')}
            >
              <Link className="inline-block w-4 h-4 mr-2" /> Article URL
            </button>
            <button 
              className={`flex-1 p-3 text-sm font-medium transition-colors ${inputMode === 'text' ? 'bg-primary/10 text-primary border-b-2 border-primary' : 'text-muted-foreground hover:bg-secondary'}`}
              onClick={() => setInputMode('text')}
            >
              <ClipboardCopy className="inline-block w-4 h-4 mr-2" /> Paste Text
            </button>
          </div>
          
          <CardContent className="pt-6 space-y-8">
            {inputMode === 'url' ? (
              <div className="space-y-2">
                <Label>Article URL</Label>
                <Input 
                  placeholder="https://reuters.com/markets/..." 
                  value={url} 
                  onChange={e => setUrl(e.target.value)}
                />
              </div>
            ) : (
              <div className="space-y-2">
                <Label>Article Text</Label>
                <textarea 
                  className="w-full flex min-h-[120px] rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  placeholder="Paste the full article body here..."
                  value={text}
                  onChange={e => setText(e.target.value)}
                />
              </div>
            )}

            <div className="space-y-4">
              <h3 className="text-sm font-semibold">Options</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>Number of slides ({numSlides})</Label>
                  <div className="flex items-center gap-4">
                    <Button variant="outline" size="icon" onClick={() => setNumSlides(Math.max(4, numSlides - 1))} disabled={numSlides <= 4}>-</Button>
                    <span className="font-mono">{numSlides}</span>
                    <Button variant="outline" size="icon" onClick={() => setNumSlides(Math.min(8, numSlides + 1))} disabled={numSlides >= 8}>+</Button>
                  </div>
                </div>
                <div className="space-y-2">
                  <Label>Content Type</Label>
                  <select 
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                    value={contentType}
                    onChange={e => setContentType(e.target.value)}
                  >
                    {CONTENT_TYPES.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
                  </select>
                </div>
              </div>

              <div className="flex items-center justify-between p-4 rounded-lg border border-border bg-secondary/20">
                <div>
                  <div className="font-medium">Skip image generation</div>
                  <div className="text-sm text-muted-foreground">Faster — build text-only slides (no Gemini images)</div>
                </div>
                <input 
                  type="checkbox" 
                  className="w-5 h-5 accent-primary" 
                  checked={skipImages} 
                  onChange={e => setSkipImages(e.target.checked)} 
                />
              </div>
            </div>

            <div className="space-y-4">
              <div className="flex items-baseline justify-between">
                <h3 className="text-sm font-semibold">Languages</h3>
                <span className="text-xs text-muted-foreground">English is always included</span>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                {LANGUAGES.map(l => (
                  <button
                    key={l.code}
                    className={`flex items-center gap-3 p-3 rounded-lg border text-left transition-colors ${languages.has(l.code) ? 'border-primary bg-primary/10' : 'border-border hover:bg-secondary'} ${l.locked ? 'opacity-70 cursor-not-allowed' : ''}`}
                    onClick={() => toggleLanguage(l.code)}
                  >
                    <span className="text-xl">{l.flag}</span>
                    <span className="font-medium text-sm">{l.code}</span>
                  </button>
                ))}
              </div>
            </div>

            <Button className="w-full h-12 text-lg font-bold" onClick={handleGenerate}>
              <Play className="w-5 h-5 mr-2" fill="currentColor" />
              Generate Carousel
            </Button>
          </CardContent>
        </Card>
      )}

      {status === 'running' && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <div>
              <CardTitle>Generating Carousel</CardTitle>
              <CardDescription>Job ID: {jobId}</CardDescription>
            </div>
            <Button variant="outline" onClick={cancelJob}>
              <StopCircle className="w-4 h-4 mr-2" /> Cancel
            </Button>
          </CardHeader>
          <CardContent className="space-y-6">
            {STEP_LABELS.map((label, i) => {
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
                      {step.status === 'running' ? STEP_SUBS[i] :
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

      {status === 'error' && (
        <Card className="border-destructive">
          <CardHeader>
            <CardTitle className="text-destructive flex items-center"><XCircle className="w-5 h-5 mr-2" /> Generation Failed</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="p-4 bg-destructive/10 text-destructive rounded-md font-mono text-sm whitespace-pre-wrap">
              {errorDetails}
            </div>
            <Button onClick={() => setStatus('idle')}><RefreshCcw className="w-4 h-4 mr-2" /> Try Again</Button>
          </CardContent>
        </Card>
      )}

      {status === 'done' && results && (
        <Card className="border-green-500/30">
          <CardHeader className="flex flex-row items-center justify-between border-b border-border pb-4">
            <div>
              <CardTitle className="text-green-500 flex items-center"><CheckCircle2 className="w-5 h-5 mr-2" /> Carousel Ready</CardTitle>
              <CardDescription>Click Download HTML or copy the generated captions.</CardDescription>
            </div>
            <Button variant="outline" onClick={() => setStatus('idle')}><RefreshCcw className="w-4 h-4 mr-2" /> New Carousel</Button>
          </CardHeader>
          <CardContent className="pt-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {Object.entries(results).map(([lang, info]) => (
                <div key={lang} className="p-4 rounded-lg bg-secondary/30 border border-border flex flex-col justify-between">
                  <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-3">
                      <span className="text-3xl">{info.flag}</span>
                      <div>
                        <div className="font-semibold">{info.language_name}</div>
                        <div className="text-xs text-muted-foreground font-mono">{lang}</div>
                      </div>
                    </div>
                    <Badge variant="outline">{info.size_kb} KB</Badge>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <Button variant="default" asChild>
                      <a href={info.carousel_url} target="_blank" rel="noopener noreferrer" download>
                        <Download className="w-4 h-4 mr-2" /> HTML
                      </a>
                    </Button>
                    <Button variant="secondary" onClick={() => copyCaption(info.caption_text_url)}>
                      <ClipboardCopy className="w-4 h-4 mr-2" /> Caption
                    </Button>
                    {/* Note: Preview iframe modal is omitted to keep it simple, they can just download the HTML */}
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
