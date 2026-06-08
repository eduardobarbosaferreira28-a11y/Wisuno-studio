import { useState, useEffect } from 'react'
import { apiFetch } from '@/lib/api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { RefreshCw, Download, Play, Images, AlertCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'

export const DashboardPage = () => {
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(true)

  const fetchHistory = async () => {
    setLoading(true)
    try {
      const data = await apiFetch(`/api/history?t=${Date.now()}`)
      setHistory(data.history || [])
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchHistory()
  }, [])

  // Group by date
  const groups = history.reduce((acc, entry) => {
    const dateStr = new Date(entry.timestamp).toLocaleDateString(undefined, { 
      month: 'long', day: 'numeric', year: 'numeric' 
    })
    if (!acc[dateStr]) acc[dateStr] = []
    acc[dateStr].push(entry)
    return acc
  }, {})

  return (
    <div className="space-y-6">
      <div>
        <div className="text-xs font-semibold text-primary uppercase tracking-widest mb-1">Home</div>
        <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground mt-1">Recent carousel and video production runs.</p>
      </div>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-4 border-b border-border">
          <CardTitle className="text-lg font-medium">Job History</CardTitle>
          <Button variant="ghost" size="sm" onClick={fetchHistory} disabled={loading}>
            <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
        </CardHeader>
        <CardContent className="pt-6">
          {loading && history.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">Loading history...</div>
          ) : history.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">No recent runs found.</div>
          ) : (
            <div className="space-y-8">
              {Object.entries(groups).map(([dateStr, items]) => (
                <div key={dateStr} className="space-y-3">
                  <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-widest">{dateStr}</h3>
                  <div className="space-y-3">
                    {items.map(entry => (
                      <JobCard key={entry.job_id || Math.random()} entry={entry} />
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

const JobCard = ({ entry }) => {
  const details = entry.details || {}
  const topic = details.topic || 'Unknown Topic'
  const isError = entry.status === 'error'

  return (
    <div className="flex flex-col sm:flex-row gap-4 p-4 rounded-lg bg-secondary/50 border border-border items-start sm:items-center">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          {entry.job_type === 'carousel' ? (
            <Badge variant="outline" className="bg-primary/10 text-primary border-primary/20"><Images className="w-3 h-3 mr-1" /> Carousel</Badge>
          ) : (
            <Badge variant="outline" className="bg-blue-500/10 text-blue-500 border-blue-500/20"><Play className="w-3 h-3 mr-1" /> Video</Badge>
          )}
          {isError && (
            <Badge variant="destructive"><AlertCircle className="w-3 h-3 mr-1"/> Failed</Badge>
          )}
          <span className="text-xs text-muted-foreground font-mono">{entry.job_id}</span>
        </div>
        <h4 className="font-medium text-foreground truncate">{topic}</h4>
        
        {isError && details.error && (
          <div className="text-sm text-destructive mt-1 bg-destructive/10 p-2 rounded">{details.error}</div>
        )}
      </div>

      <div className="flex gap-2 w-full sm:w-auto">
        {details.files && details.files.map((file, i) => (
          <Button key={i} variant="secondary" size="sm" asChild>
            <a href={file.url} download target="_blank" rel="noopener noreferrer">
              <Download className="w-4 h-4 mr-2" />
              {file.lang.toUpperCase()}
            </a>
          </Button>
        ))}
      </div>
    </div>
  )
}
