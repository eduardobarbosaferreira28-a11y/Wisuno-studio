import { useState, useEffect } from 'react'
import { apiFetch } from '@/lib/api'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import { toast } from 'sonner'
import { CheckCircle2, XCircle } from 'lucide-react'

export const SetupPage = () => {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    fetchSetup()
  }, [])

  const fetchSetup = async () => {
    try {
      const res = await apiFetch('/api/setup')
      setData(res)
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const handleSave = async (e) => {
    e.preventDefault()
    setSaving(true)
    
    // Extract env keys from form data
    const formData = new FormData(e.target)
    const envData = {}
    for (let [key, value] of formData.entries()) {
      envData[key] = value
    }

    try {
      await apiFetch('/api/setup', {
        method: 'POST',
        body: JSON.stringify({ env: envData })
      })
      toast.success('Configuration saved successfully')
      fetchSetup() // Refresh validation status
    } catch (err) {
      console.error(err)
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <div className="p-8 text-center text-muted-foreground">Loading...</div>
  if (!data) return <div className="p-8 text-center text-destructive">Failed to load setup data</div>

  return (
    <div className="space-y-6">
      <div>
        <div className="text-xs font-semibold text-primary uppercase tracking-widest mb-1">Configuration</div>
        <h1 className="text-3xl font-bold tracking-tight">Studio Setup</h1>
        <p className="text-muted-foreground mt-1">Manage API keys and check system dependencies.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="md:col-span-2 space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Environment Variables</CardTitle>
              <CardDescription>API keys required for generation tools.</CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleSave} className="space-y-4">
                {Object.entries(data.env).map(([key, val]) => (
                  <div key={key} className="space-y-2">
                    <Label htmlFor={key} className="font-mono text-xs">{key}</Label>
                    <Input 
                      id={key} 
                      name={key} 
                      defaultValue={val} 
                      type={key.includes('KEY') || key.includes('TOKEN') ? 'password' : 'text'}
                      className="font-mono text-sm"
                    />
                  </div>
                ))}
                <Button type="submit" disabled={saving}>
                  {saving ? 'Saving...' : 'Save Configuration'}
                </Button>
              </form>
            </CardContent>
          </Card>
        </div>

        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Dependencies</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {Object.entries(data.checks).map(([key, passed]) => (
                  <div key={key} className="flex items-center justify-between p-3 rounded bg-secondary/50 border border-border">
                    <span className="font-mono text-sm font-medium">{key}</span>
                    {passed ? (
                      <CheckCircle2 className="w-5 h-5 text-green-500" />
                    ) : (
                      <XCircle className="w-5 h-5 text-destructive" />
                    )}
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
