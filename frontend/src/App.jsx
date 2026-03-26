import React from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider } from './context/AuthContext'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import RawMaterial from './pages/RawMaterial'
import Dispatch from './pages/Dispatch'
import Production from './pages/Production'
import Stock from './pages/Stock'
import Settings from './pages/Settings'
import ClientLogin from './pages/ClientLogin'
import { backendStatus } from './api/client'

function ServerMaintenanceOverlay() {
  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
      <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-6 shadow-2xl text-center">
        <div className="mx-auto mb-4 h-10 w-10 rounded-full border-4 border-slate-200 border-t-[#245658] animate-spin" />
        <h2 className="text-xl font-semibold text-slate-800">Server Under Maintenance</h2>
        <p className="mt-2 text-sm text-slate-600">
          Backend service is currently unavailable. This screen will close automatically once the server is back online.
        </p>
      </div>
    </div>
  )
}

export default function App() {
  const [isBackendReachable, setIsBackendReachable] = React.useState(backendStatus.get())

  React.useEffect(() => {
    const unsubscribe = backendStatus.subscribe(setIsBackendReachable)
    const probeBackend = () => {
      backendStatus.ping().catch(() => {})
    }

    probeBackend()
    const timer = setInterval(probeBackend, 5000)

    return () => {
      clearInterval(timer)
      unsubscribe()
    }
  }, [])

  React.useEffect(() => {
    const originalOverflow = document.body.style.overflow
    if (!isBackendReachable) {
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = originalOverflow || ''
    }

    return () => {
      document.body.style.overflow = originalOverflow
    }
  }, [isBackendReachable])

  return (
    <AuthProvider>
      <>
        <Routes>
            <Route path="/" element={<ClientLogin />} />
          <Route path="/layout" element={<Layout />}>
            <Route index element={<Dashboard />} />
            <Route path="raw-material" element={<RawMaterial />} />
            <Route path="dispatch" element={<Dispatch />} />
            <Route path="production" element={<Production />} />
            <Route path="stock" element={<Stock />} />
            <Route path="settings" element={<Settings />} />
              

          </Route>
             {/* <Route path="login" element={<ClientLogin />} /> */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        {!isBackendReachable && <ServerMaintenanceOverlay />}
      </>
    </AuthProvider>
  )
}
