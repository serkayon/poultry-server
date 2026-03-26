import React from 'react'
import { Outlet, NavLink } from 'react-router-dom'
import { useEffect, useRef, useState } from 'react'
import {
  LayoutDashboard,
  ClipboardList,
  Truck,
  Factory,
  Boxes,
  Settings,
  Menu,
  X,
  BellRing,
  AlertTriangle,
} from 'lucide-react'
import { productionApi } from '../api/client'

const nav = [
  { to: '/layout', label: 'Dashboard', icon: LayoutDashboard },
  { to: 'raw-material', label: 'RM Reports', icon: ClipboardList },
  { to: 'dispatch', label: 'Dispatch Reports', icon: Truck },
  { to: 'production', label: 'Production Reports', icon: Factory },
  { to: 'stock', label: 'Stock Reports', icon: Boxes },
  { to: 'settings', label: 'Settings', icon: Settings },
]

export default function Layout() {
  const [open, setOpen] = useState(false)
  const [batchNotifications, setBatchNotifications] = useState([])
  const knownBatchIdsRef = useRef(new Set())
  const completedReminderIdsRef = useRef(new Set())
  const initializedRef = useRef(false)

  const dismissBatchNotification = (id) => {
    setBatchNotifications((prev) => prev.filter((item) => item.id !== id))
  }

  useEffect(() => {
    let alive = true

    const pushNotification = (message, type = 'info') => {
      const id = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
      setBatchNotifications((prev) => [{ id, message, type }, ...prev].slice(0, 5))
    }

    const checkBatchUpdates = async () => {
      try {
        const { data } = await productionApi.listBatches()
        if (!alive || !Array.isArray(data)) return

        const currentIds = new Set(data.map((b) => b.id))
        if (!initializedRef.current) {
          knownBatchIdsRef.current = currentIds
          completedReminderIdsRef.current = new Set(
            data
              .filter((b) => (b.run_status || '').toLowerCase() === 'completed')
              .map((b) => b.id)
          )
          initializedRef.current = true
          return
        }

        data.forEach((batch) => {
          const batchId = batch?.id
          if (batchId == null) return
          const batchNo = batch?.batch_no || batchId
          const productName = String(batch?.product_name || '').trim()
          const runStatus = String(batch?.run_status || '').toLowerCase()
          const needsDetails = !productName || !batch?.has_report

          if (!knownBatchIdsRef.current.has(batchId)) {
            if (!productName) {
              pushNotification(
                `New batch ${batchNo} added from HMI. Please add batch details in Production.`
              )
            }
            knownBatchIdsRef.current.add(batchId)
          }

          if (
            runStatus === 'completed' &&
            needsDetails &&
            !completedReminderIdsRef.current.has(batchId)
          ) {
            pushNotification(
              `Batch ${batchNo} completed. Please update missing batch details/report.`,
              'warning'
            )
            completedReminderIdsRef.current.add(batchId)
          }
        })
      } catch {
        // Ignore polling errors for non-blocking UI notifications.
      }
    }

    checkBatchUpdates()
    const interval = setInterval(checkBatchUpdates, 10000)
    return () => {
      alive = false
      clearInterval(interval)
    }
  }, [])

  return (
<div className="h-screen flex flex-col bg-slate-50 overflow-hidden overflow-x-hidden">
      
      {/* 🔷 FULL WIDTH BANNER */}
   <div className="relative w-full h-[200px] md:h-[170px] sm:h-[120px] bg-slate-100 overflow-hidden">

  {/* Banner Image */}
  <img
    src="/poultry-banner.png"
    alt="banner"
    className="w-full h-full object-fill"
  />

  {/* Overlay Content */}
  <div className="absolute inset-0 flex flex-col items-center justify-start">
    <h1 className="text-xl mt-20 sm:text-xl md:text-3xl font-semibold text-gray-800 sm:mt-8">
      
      PRODUCTION TRACKING SYSTEM
    </h1>
  </div>

  {/* Profile */}
  <div className="absolute right-6 top-4 flex items-center gap-3">
    <div className="text-right text-xs sm:text-sm">
      <p className="text-sm font-medium">FEED MILL INTELLIGENCE</p>
      <p className="text-xs text-gray-500">+91 98765 43210</p>
    </div>
    <img
      src="/profile.png"
      className="w-12 h-12 rounded-full border border-slate-700 border-3"
      alt="profile"
    />
  </div>

</div>

      {/* 🔷 SIDEBAR + CONTENT */}
      <div className="flex flex-1 overflow-hidden w-full">

        {/* MOBILE MENU BUTTON */}
        <button
          onClick={() => setOpen(true)}
          className="lg:hidden fixed top-3 left-3 z-50 bg-white p-2 rounded-lg shadow"
        >
          <Menu size={22} />
        </button>

        {/* SIDEBAR */}
        <aside
          className={`fixed lg:static z-40 w-56 h-full flex flex-col bg-[#DCE4EE] border-r shadow transition-transform duration-300
          ${open ? 'translate-x-0' : '-translate-x-full'} lg:translate-x-0`}
        >
          <div className="lg:hidden flex justify-end p-3">
            <X onClick={() => setOpen(false)} className="cursor-pointer" />
          </div>

<nav className="px-2 pt-2 flex-1">         
     {nav.map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                end={to === '/layout'}
                onClick={() => setOpen(false)}
               className={({ isActive }) =>
  `flex items-center gap-2 px-3 py-2 rounded-md mb-1 text-md font-medium transition
                  ${
                    isActive
                      ? 'bg-[#245658] text-gray-100 border-l-4 border-green-950'
                      : 'text-slate-600 hover:bg-slate-100'
                  }`
                }
              >
                <Icon size={18} />
                {label}
              </NavLink>
            ))}
          </nav>

<div className="mt-auto relative">
  <img
    src="/farm-bg.png"
    alt="farm"
    className="w-full object-cover"
  />

  <div className="absolute inset-0 flex flex-col items-center justify-end pb-3 bg-gradient-to-t from-black/30 via-black/20 to-transparent">
    <span className="text-[10px] text-slate-200 tracking-wide">
      Powered by
    </span>

      <span
      className="text-sm font-semibold tracking-[0.25em]
                 text-transparent bg-clip-text
                 bg-gradient-to-r from-gray-300 via-white to-gray-400
                 bg-[length:200px_auto]
                 animate-shine">
      SERKAYON
    </span>
  </div>
</div>
        </aside>

        {/* MAIN AREA */}
        <div className="flex-1 flex flex-col min-w-0">

          {/* ONLY SCROLLABLE AREA */}
          <main className="flex-1 pb-24 p-4 md:p-6 overflow-y-auto min-w-0 ">
            <Outlet />
          </main>

        </div>
      </div>

      {/* MOBILE BOTTOM NAV */}
<div className="fixed bottom-0 left-0 right-0 bg-white border-t shadow-md 
                flex justify-around items-center 
                py-2 pb-safe z-50 lg:hidden">

  <NavLink to="" end className="flex flex-col items-center">
    {({ isActive }) => (
      <>
        <div
          className={`flex items-center justify-center rounded-full transition
          ${isActive ? "bg-[#D7E6E6] w-11 h-11" : "w-11 h-11"}`}
        >
          <LayoutDashboard
            size={22}
            color={isActive ? "black" : "#475569"}
          />
        </div>

        <span
          className="text-[10px] sm:text-xs md:text-sm mt-1  font-extrabold"
          style={{ color: isActive ? "#245658" : "#475569" }}
        >
          Dashboard
        </span>
      </>
    )}
  </NavLink>

  <NavLink to="production" className="flex flex-col items-center">
    {({ isActive }) => (
      <>
        <div className={`flex items-center justify-center rounded-full transition
          ${isActive ? "bg-[#D7E6E6] w-11 h-11" : "w-11 h-11"}`}>
          <Factory size={22} color={isActive ? "black" : "#475569"} />
        </div>

        <span className="text-[10px] mt-1  font-extrabold"
          style={{ color: isActive ? "#245658" : "#475569" }}>
          Production
        </span>
      </>
    )}
  </NavLink>

  <NavLink to="stock" className="flex flex-col items-center">
    {({ isActive }) => (
      <>
        <div className={`flex items-center justify-center rounded-full transition
          ${isActive ? "bg-[#D7E6E6] w-11 h-11" : "w-11 h-11"}`}>
          <Boxes size={22} color={isActive ? "black" : "#475569"} />
        </div>

        <span className="text-[10px] mt-1  font-extrabold"
          style={{ color: isActive ? "#245658" : "#475569" }}>
          Stock
        </span>
      </>
    )}
  </NavLink>

  <NavLink to="dispatch" className="flex flex-col items-center">
    {({ isActive }) => (
      <>
        <div className={`flex items-center justify-center rounded-full transition
          ${isActive ? "bg-[#D7E6E6] w-11 h-11" : "w-11 h-11"}`}>
          <Truck size={22} color={isActive ? "black" : "#475569"} />
        </div>

        <span className="text-[10px] mt-1  font-extrabold"
          style={{ color: isActive ? "#245658" : "#475569" }}>
          Dispatch
        </span>
      </>
    )}
  </NavLink>

  <NavLink to="raw-material" className="flex flex-col items-center">
    {({ isActive }) => (
      <>
        <div className={`flex items-center justify-center rounded-full transition
          ${isActive ? "bg-[#D7E6E6] w-11 h-11" : "w-11 h-11"}`}>
          <ClipboardList size={22} color={isActive ? "black" : "#475569"} />
        </div>

        <span className="text-[10px] mt-1 font-extrabold" 
          style={{ color: isActive ? "#245658" : "#475569" }}>
          RM
        </span>
      </>
    )}
  </NavLink>


	  <NavLink to="settings" className="flex flex-col items-center">
    {({ isActive }) => (
      <>
        <div className={`flex items-center justify-center rounded-full transition
          ${isActive ? "bg-[#D7E6E6] w-11 h-11" : "w-11 h-11"}`}>
          <Settings size={22} color={isActive ? "black" : "#475569"} />
        </div>

        <span className="text-[10px] mt-1 font-extrabold" 
          style={{ color: isActive ? "#245658" : "#475569" }}>
          Settings
        </span>
      </>
    )}
	  </NavLink>
	</div>

      {batchNotifications.length > 0 && (
        <div className="fixed right-4 bottom-20 md:bottom-4 z-[80] w-[360px] max-w-[calc(100vw-1.5rem)] space-y-3">
          {batchNotifications.map((item) => (
            <div
              key={item.id}
              className={`relative overflow-hidden rounded-xl border-2 shadow-[0_14px_30px_rgba(15,23,42,0.28)] ${
                item.type === 'warning'
                  ? 'bg-gradient-to-br from-amber-50 via-orange-50 to-amber-100 border-amber-300 text-amber-950'
                  : 'bg-gradient-to-br from-cyan-50 via-white to-blue-50 border-cyan-300 text-slate-900'
              }`}
            >
              <div
                className={`absolute left-0 top-0 h-full w-1.5 ${
                  item.type === 'warning' ? 'bg-amber-500' : 'bg-cyan-500'
                }`}
              />
              <div className="absolute right-10 top-2 rounded-full bg-white/80 px-2 py-0.5 text-[10px] font-extrabold tracking-wider text-slate-700">
                NEW
              </div>
              <div className="px-3 py-3 pl-4">
                <div className="flex items-start gap-3">
                  <div
                    className={`mt-0.5 rounded-full p-2 ${
                      item.type === 'warning'
                        ? 'bg-amber-200 text-amber-900 animate-pulse'
                        : 'bg-cyan-100 text-cyan-800'
                    }`}
                  >
                    {item.type === 'warning' ? <AlertTriangle size={16} /> : <BellRing size={16} />}
                  </div>
                  <div className="flex-1">
                    <p className="text-[11px] font-extrabold uppercase tracking-[0.16em] text-slate-700">
                      {item.type === 'warning' ? 'Action Needed' : 'Batch Alert'}
                    </p>
                    <p className="mt-0.5 text-sm font-semibold leading-5">{item.message}</p>
                    <p className="mt-1 text-[11px] text-slate-600">
                      Go to Production and complete batch details.
                    </p>
                  </div>
                <button
                  type="button"
                  onClick={() => dismissBatchNotification(item.id)}
                  className="rounded-md border border-black/10 bg-white/80 p-1 text-slate-600 hover:bg-white"
                  aria-label="Close notification"
                >
                  <X size={13} />
                </button>
              </div>
            </div>
            </div>
          ))}
        </div>
      )}
	    </div>
	  )
}
