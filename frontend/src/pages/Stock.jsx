import React from 'react'
import { useState, useEffect } from 'react'
import { rawMaterial, stockApi } from '../api/client'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { formatDateIST } from "../utils/datetime";

const STOCK_RANGE_OPTIONS = [
  { value: 'today', label: 'Today' },
  { value: 'last_7_days', label: 'Last 7 Days' },
  { value: 'last_15_days', label: 'Last 15 Days' },
  { value: 'last_30_days', label: 'Last 30 Days' },
]

export default function Stock() {
  const [rmStock, setRmStock] = useState([])
  const [feedStock, setFeedStock] = useState([])
  const [rmTypes, setRmTypes] = useState([])
  const [rmRange, setRmRange] = useState('today')
  const [feedRange, setFeedRange] = useState('today')

  useEffect(() => {
    stockApi.rm().then(({ data }) => setRmStock(data || [])).catch(() => setRmStock([]))
    stockApi.feed().then(({ data }) => setFeedStock(data || [])).catch(() => setFeedStock([]))
    rawMaterial.listTypes().then(({ data }) => setRmTypes(data || [])).catch(() => setRmTypes([]))
  }, [])

  const formatQty = (value) => {
    const num = Number(value)
    if (Number.isNaN(num)) return '0'
    if (Number.isInteger(num)) return String(num)
    return num.toFixed(2)
  }

  const buildBagMix = (bagStockByWeight) => {
    const entries = Object.entries(bagStockByWeight || {})
      .sort((a, b) => Number(a[0]) - Number(b[0]))
      .map(([bagWeight, stockKg]) => {
        const weight = Number(bagWeight)
        const stock = Number(stockKg)
        if (!Number.isFinite(weight) || weight <= 0) return null
        const bags = Number.isFinite(stock) ? stock / weight : 0
        return {
          key: `${bagWeight}-${stockKg}`,
          weightLabel: `${formatQty(weight)} kg`,
          bagsLabel: `${formatQty(bags)} bags`,
          stockLabel: `${formatQty(stock)} kg`,
        }
      })
      .filter(Boolean)

    return entries
  }

  const renderBagMix = (items) => {
    if (!Array.isArray(items) || items.length === 0) {
      return <span className="text-gray-500">N/A</span>
    }
    return (
      <div className="flex flex-wrap gap-1.5">
        {items.map((item) => (
          <span
            key={item.key}
            title={`Stock: ${item.stockLabel}`}
            className="inline-flex items-center rounded-full border border-slate-300 bg-slate-100 px-2 py-0.5 text-xs text-slate-700"
          >
            <span className="font-medium">{item.weightLabel}</span>
            <span className="mx-1 text-slate-400">•</span>
            <span>{item.bagsLabel}</span>
          </span>
        ))}
      </div>
    )
  }

  const latestByType = (rows, keySelector) =>
    rows.reduce((acc, row) => {
      const key = keySelector(row)
      if (!key) return acc

      const rowTime = row.date ? new Date(row.date).getTime() : Number.NEGATIVE_INFINITY
      const current = acc[key]
      if (!current || rowTime > current.time) {
        acc[key] = {
          time: rowTime,
          row,
        }
      }
      return acc
    }, {})

  const normalizeFeedType = (value) => String(value || '').trim()
  const normalizeBagWeight = (value) => {
    const num = Number(value)
    return Number.isFinite(num) && num > 0 ? num : null
  }

  const latestFeedByType = latestByType(feedStock, (row) => {
    const feedType = normalizeFeedType(row?.feed_type)
    if (!feedType) return ''
    const bagWeight = normalizeBagWeight(row?.bag_weight_kg)
    return `${feedType}__${bagWeight == null ? 'na' : bagWeight}`
  })
  const latestRmByType = latestByType(rmStock, (row) => String(row?.rm_name || '').trim())

  const feedAvailableStock = Object.values(latestFeedByType)
    .reduce((acc, item) => {
      const feedType = normalizeFeedType(item?.row?.feed_type)
      if (!feedType) return acc
      if (!acc[feedType]) {
        acc[feedType] = {
          name: feedType,
          closing: 0,
          bagStockByWeight: {},
        }
      }
      const closingKg = Number(item?.row?.closing_stock) || 0
      acc[feedType].closing += closingKg
      const bagWeight = normalizeBagWeight(item?.row?.bag_weight_kg)
      if (bagWeight != null) {
        const weightKey = formatQty(bagWeight)
        acc[feedType].bagStockByWeight[weightKey] = (acc[feedType].bagStockByWeight[weightKey] || 0) + closingKg
      }
      return acc
    }, {})
  const feedAvailableStockRows = Object.values(feedAvailableStock)
    .map((row) => ({
      name: row.name,
      closing: row.closing,
      bagMix: buildBagMix(row.bagStockByWeight),
    }))
    .sort((a, b) => a.name.localeCompare(b.name))

  const rmAvailableStock = (rmTypes.length ? rmTypes.map((item) => item.name) : Object.keys(latestRmByType))
    .map((name) => ({
      name,
      closing: Number(latestRmByType[name]?.row?.closing_stock) || 0,
    }))
    .sort((a, b) => a.name.localeCompare(b.name))

  const feedChartData = feedAvailableStockRows.map(({ name, closing }) => ({ name, closing }))
  const rmChartData = rmAvailableStock.map(({ name, closing }) => ({ name, closing }))

  const buildDownloadRangeParams = (rangeKey) => {
    const { start, end } = resolveDateRange(rangeKey)
    return {
      from_date: start.toISOString(),
      to_date: end.toISOString(),
    }
  }

  const downloadRm = (format, rangeKey = rmRange) => {
    stockApi.downloadRM(format, buildDownloadRangeParams(rangeKey)).then(({ data }) => {
      const ext = format === 'pdf' ? 'pdf' : 'xlsx'
      const url = URL.createObjectURL(new Blob([data]))
      const a = document.createElement('a')
      a.href = url
      a.download = `rm_stock.${ext}`
      a.click()
      URL.revokeObjectURL(url)
    })
  }

  const downloadFeed = (format, rangeKey = feedRange) => {
    stockApi.downloadFeed(format, buildDownloadRangeParams(rangeKey)).then(({ data }) => {
      const ext = format === 'pdf' ? 'pdf' : 'xlsx'
      const url = URL.createObjectURL(new Blob([data]))
      const a = document.createElement('a')
      a.href = url
      a.download = `feed_stock.${ext}`
      a.click()
      URL.revokeObjectURL(url)
    })
  }

  const downloadOverall = (format) => {
    stockApi.downloadOverall(format).then(({ data }) => {
      const ext = format === 'pdf' ? 'pdf' : 'xlsx'
      const url = URL.createObjectURL(new Blob([data]))
      const a = document.createElement('a')
      a.href = url
      a.download = `overall_stock_report.${ext}`
      a.click()
      URL.revokeObjectURL(url)
    })
  }

  const resolveDateRange = (rangeKey) => {
    const end = new Date()
    end.setHours(23, 59, 59, 999)
    const start = new Date(end)
    start.setHours(0, 0, 0, 0)

    if (rangeKey === 'last_7_days') {
      start.setDate(start.getDate() - 6)
    } else if (rangeKey === 'last_15_days') {
      start.setDate(start.getDate() - 14)
    } else if (rangeKey === 'last_30_days') {
      start.setDate(start.getDate() - 29)
    }

    return { start, end }
  }

  const inSelectedRange = (dateValue, rangeKey) => {
    const date = new Date(dateValue)
    if (Number.isNaN(date.getTime())) return false
    const { start, end } = resolveDateRange(rangeKey)
    return date >= start && date <= end
  }

  const filteredRmStock = rmStock.filter((row) => inSelectedRange(row?.date, rmRange))
  const filteredFeedStock = feedStock.filter((row) => inSelectedRange(row?.date, feedRange))
  const filteredFeedStockGrouped = Object.values(
    filteredFeedStock.reduce((acc, row) => {
      const feedType = normalizeFeedType(row?.feed_type)
      if (!feedType || !row?.date) return acc
      const key = `${row.date}__${feedType}`
      if (!acc[key]) {
        acc[key] = {
          date: row.date,
          feed_type: feedType,
          opening_stock: 0,
          produced: 0,
          dispatched: 0,
          closing_stock: 0,
          bagStockByWeight: {},
        }
      }
      acc[key].opening_stock += Number(row?.opening_stock) || 0
      acc[key].produced += Number(row?.produced) || 0
      acc[key].dispatched += Number(row?.dispatched) || 0
      const closingKg = Number(row?.closing_stock) || 0
      acc[key].closing_stock += closingKg
      const bagWeight = normalizeBagWeight(row?.bag_weight_kg)
      if (bagWeight != null) {
        const weightKey = formatQty(bagWeight)
        acc[key].bagStockByWeight[weightKey] = (acc[key].bagStockByWeight[weightKey] || 0) + closingKg
      }
      return acc
    }, {})
  )
    .map((row) => ({
      ...row,
      bagMix: buildBagMix(row.bagStockByWeight),
    }))
    .sort((a, b) => new Date(b.date) - new Date(a.date) || a.feed_type.localeCompare(b.feed_type))

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-slate-800">Stock Report</h1>
      {/* <p className="text-gray-400 text-sm">Opening + Received - Consumption = Closing (RM). Opening + Produced - Dispatched = Closing (Feed).</p> */}

      <div className="bg-primary-card border border-gray-700 rounded-xl p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-medium text-slate-800">Overall Stock Downloads</h2>
            <p className="text-xs text-gray-500 mt-1">Download both Raw Material and Feed reports together.</p>
          </div>
          <div className="flex gap-2">
            <button onClick={() => downloadOverall('pdf')} className="px-3 py-1.5 rounded-lg border border-gray-600 text-gray-800 text-sm hover:bg-primary-light">Download RM + Feed PDF</button>
            <button onClick={() => downloadOverall('xlsx')} className="px-3 py-1.5 rounded-lg border border-gray-600 text-gray-800 text-sm hover:bg-primary-light">Download RM + Feed Export</button>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-primary-card border border-gray-700 rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-700 flex items-start justify-between gap-3 lg:flex-row flex-col">
            <div>
              <h2 className="text-sm font-medium text-slate-800">Individual Raw Material Available Stock</h2>
              <p className="text-xs text-gray-500 mt-1">Latest closing stock by RM type</p>
            </div>
            <div className="flex gap-2 shrink-0">
              <button onClick={() => downloadRm('pdf')} className="px-3 py-1.5 rounded-lg border border-gray-600 text-gray-800 text-sm hover:bg-primary-light">Download PDF</button>
              <button onClick={() => downloadRm('xlsx')} className="px-3 py-1.5 rounded-lg border border-gray-600 text-gray-800 text-sm hover:bg-primary-light">Download Export</button>
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-[#245658] text-white border-b border-gray-300">
                <tr>
                  <th className="px-4 py-3 text-left border border-gray-300">RM Type</th>
                  <th className="px-4 py-3 text-left border border-gray-300">Available Stock</th>
                </tr>
              </thead>
              <tbody>
                {rmAvailableStock.length === 0 ? (
                  <tr>
                    <td colSpan={2} className="px-4 py-3 text-gray-500 border border-gray-300">
                      No RM stock data available.
                    </td>
                  </tr>
                ) : (
                  rmAvailableStock.map((row) => (
                    <tr key={row.name} className="border-b border-gray-700/50 hover:bg-primary-light/30">
                      <td className="px-4 py-3 text-slate-800">{row.name}</td>
                      <td className="px-4 py-3 text-accent-green font-medium">{formatQty(row.closing)}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className="bg-primary-card border border-gray-700 rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-700 flex items-start justify-between gap-3  lg:flex-row flex-col">
            <div>
              <h2 className="text-sm font-medium text-slate-800">Individual Feed Available Stock</h2>
              <p className="text-xs text-gray-500 mt-1">Latest closing stock by feed type (all bag sizes combined)</p>
            </div>
            <div className="flex gap-2 shrink-0">
              <button onClick={() => downloadFeed('pdf')} className="px-3 py-1.5 rounded-lg border border-gray-600 text-gray-800 text-sm hover:bg-primary-light">Download PDF</button>
              <button onClick={() => downloadFeed('xlsx')} className="px-3 py-1.5 rounded-lg border border-gray-600 text-gray-800 text-sm hover:bg-primary-light">Download Export</button>
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-[#245658] text-white border-b border-gray-300">
                <tr>
                  <th className="px-4 py-3 text-left border border-gray-300">Feed Type</th>
                  <th className="px-4 py-3 text-left border border-gray-300">Bag Size Mix</th>
                  <th className="px-4 py-3 text-left border border-gray-300">Available Stock</th>
                </tr>
              </thead>
              <tbody>
                {feedAvailableStockRows.length === 0 ? (
                  <tr>
                    <td colSpan={3} className="px-4 py-3 text-gray-500 border border-gray-300">
                      No feed stock data available.
                    </td>
                  </tr>
                ) : (
                  feedAvailableStockRows.map((row) => (
                    <tr key={row.name} className="border-b border-gray-700/50 hover:bg-primary-light/30">
                      <td className="px-4 py-3 text-slate-800">{row.name}</td>
                      <td className="px-4 py-3 text-slate-800">{renderBagMix(row.bagMix)}</td>
                      <td className="px-4 py-3 text-accent-green font-medium">{formatQty(row.closing)}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

    
      <div className="bg-primary-card border border-gray-700 rounded-xl overflow-hidden">
        <div className="flex items-center justify-between p-4 border-b border-gray-700">
          <h2 className="font-medium text-slate-800">Raw Material Stock</h2>
          <div className="flex flex-wrap items-center gap-2">
            <select
              value={rmRange}
              onChange={(e) => setRmRange(e.target.value)}
              className="px-3 py-1.5 rounded-lg border border-gray-600 text-gray-800 text-sm bg-white"
            >
              {STOCK_RANGE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <button onClick={() => downloadRm('pdf')} className="px-3 py-1.5 rounded-lg border border-gray-600 text-gray-800 text-sm hover:bg-primary-light">PDF</button>
            <button onClick={() => downloadRm('xlsx')} className="px-3 py-1.5 rounded-lg border border-gray-600 text-gray-800 text-sm hover:bg-primary-light">Excel</button>
          </div>
        </div>
        <div className="max-h-[340px] overflow-y-auto overflow-x-auto">
          <table className="w-full text-left">
            <thead className="bg-[#245658] text-white border-b border-gray-300">
              <tr>
                <th className="px-4 py-3 text-left border border-gray-300">Date</th>
                <th className="px-4 py-3 text-left border border-gray-300">RM Name</th>
                <th className="px-4 py-3 text-left border border-gray-300">Opening</th>
                <th className="px-4 py-3 text-left border border-gray-300">Received</th>
                <th className="px-4 py-3 text-left border border-gray-300">Consumption</th>
                <th className="px-4 py-3 text-left border border-gray-300">Closing</th>
              </tr>
            </thead>
            <tbody>
              {filteredRmStock.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-3 text-gray-500 border border-gray-300">
                    No raw material stock rows for selected range.
                  </td>
                </tr>
              ) : (
                filteredRmStock.map((r, i) => (
                  <tr key={i} className="border-b border-gray-700/50 hover:bg-primary-light/30">
                    <td className="px-4 py-3 text-gray-800">{formatDateIST(r.date)}</td>
                    <td className="px-4 py-3 text-slate-800">{r.rm_name}</td>
                    <td className="px-4 py-3 text-gray-800">{r.opening_stock}</td>
                    <td className="px-4 py-3 text-gray-800">{r.received}</td>
                    <td className="px-4 py-3 text-gray-800">{r.consumption}</td>
                    <td className="px-4 py-3 text-accent-green font-medium">{r.closing_stock}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="bg-primary-card border border-gray-700 rounded-xl overflow-hidden">
        <div className="flex items-center justify-between p-4 border-b border-gray-700">
          <h2 className="font-medium text-slate-800">Feed Stock</h2>
          <div className="flex flex-wrap items-center gap-2">
            <select
              value={feedRange}
              onChange={(e) => setFeedRange(e.target.value)}
              className="px-3 py-1.5 rounded-lg border border-gray-600 text-gray-800 text-sm bg-white"
            >
              {STOCK_RANGE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <button onClick={() => downloadFeed('pdf')} className="px-3 py-1.5 rounded-lg border border-gray-600 text-gray-800 text-sm hover:bg-primary-light">PDF</button>
            <button onClick={() => downloadFeed('xlsx')} className="px-3 py-1.5 rounded-lg border border-gray-600 text-gray-800 text-sm hover:bg-primary-light">Excel</button>
          </div>
        </div>
        <div className="max-h-[340px] overflow-y-auto overflow-x-auto">
          <table className="w-full text-left">
            <thead className="bg-[#245658] text-white border-b border-gray-300">
              <tr>
                <th className="px-4 py-3 text-left border border-gray-300">Date</th>
                <th className="px-4 py-3 text-left border border-gray-300">Feed Type</th>
                <th className="px-4 py-3 text-left border border-gray-300">Bag Size Mix</th>
                <th className="px-4 py-3 text-left border border-gray-300">Opening</th>
                <th className="px-4 py-3 text-left border border-gray-300">Produced</th>
                <th className="px-4 py-3 text-left border border-gray-300">Dispatched</th>
                <th className="px-4 py-3 text-left border border-gray-300">Closing</th>
              </tr>
            </thead>
            <tbody>
              {filteredFeedStockGrouped.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-3 text-gray-500 border border-gray-300">
                    No feed stock rows for selected range.
                  </td>
                </tr>
              ) : (
                filteredFeedStockGrouped.map((r, i) => (
                  <tr key={i} className="border-b border-gray-700/50 hover:bg-primary-light/30">
                    <td className="px-4 py-3 text-gray-800">{formatDateIST(r.date)}</td>
                    <td className="px-4 py-3 text-slate-800">{r.feed_type}</td>
                    <td className="px-4 py-3 text-slate-800">{renderBagMix(r.bagMix)}</td>
                    <td className="px-4 py-3 text-gray-800">{r.opening_stock}</td>
                    <td className="px-4 py-3 text-gray-800">{r.produced}</td>
                    <td className="px-4 py-3 text-gray-800">{r.dispatched}</td>
                    <td className="px-4 py-3 text-accent-green font-medium">{r.closing_stock}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        
      </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-primary-card border border-gray-700 rounded-xl p-4">
          <h2 className="text-sm font-medium text-gray-900 mb-3">Feed stock summary (latest closing by feed type)</h2>
          {feedChartData.length > 0 ? (
            <div className="h-48">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={feedChartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                  <XAxis dataKey="name" stroke="#9ca3af" fontSize={10} />
                  <YAxis stroke="#9ca3af" fontSize={10} />
                  <Tooltip contentStyle={{ backgroundColor: '#1a222d', border: '1px solid #374151' }} />
                  <Bar dataKey="closing" fill="#00c853" name="Closing" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="text-gray-900 text-sm">No feed stock data.</p>
          )}
        </div>
        <div className="bg-primary-card border border-gray-700 rounded-xl p-4">
          <h2 className="text-sm font-medium text-gray-900 mb-3">RM stock summary (latest closing by type)</h2>
          {rmChartData.length > 0 ? (
            <div className="h-48">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={rmChartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                  <XAxis dataKey="name" stroke="#9ca3af" fontSize={10} />
                  <YAxis stroke="#9ca3af" fontSize={10} />
                  <Tooltip contentStyle={{ backgroundColor: '#1a222d', border: '1px solid #374151' }} />
                  <Bar dataKey="closing" fill="#ffab00" name="Closing" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="text-gray-500 text-sm">No RM stock data.</p>
          )}
        </div>
      </div>

    </div>
  )
}
