import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import { Toaster } from '@/components/ui/sonner'
import { AuthProvider, useAuth } from '@/components/AuthProvider'
import { Layout } from '@/components/Layout'
import { LoginPage } from '@/components/LoginPage'
import { DashboardPage } from '@/components/DashboardPage'
import { SetupPage } from '@/components/SetupPage'
import { CarouselStudio } from '@/components/CarouselStudio'
import { VideoStudio } from '@/components/VideoStudio'

const ProtectedRoute = ({ children }) => {
  const { session, loading } = useAuth()
  
  if (loading) return null
  if (!session) return <Navigate to="/login" replace />
  
  return children
}

function App() {
  return (
    <AuthProvider>
      <Router>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          
          <Route path="/" element={
            <ProtectedRoute>
              <Layout />
            </ProtectedRoute>
          }>
            <Route index element={<DashboardPage />} />
            <Route path="setup" element={<SetupPage />} />
            <Route path="carousel" element={<CarouselStudio />} />
            <Route path="video" element={<VideoStudio />} />
          </Route>
        </Routes>
      </Router>
      <Toaster theme="dark" position="top-center" />
    </AuthProvider>
  )
}

export default App
