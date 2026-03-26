import React from 'react'
import { useState, useEffect } from 'react'
import { rawMaterial, stockApi } from '../api/client'
import Modal from '../components/Modal'
import PopupDialog from '../components/PopupDialog'
import usePinGate from '../hooks/usePinGate'
import arrow from "./assets/arrow.png"
import cornbag from "./assets/cornbag.png"
import potato from "./assets/potate-1.png"
import searchIcon from "./assets/icons8-search-60.png"
const LAB_PARAMS = ['protein', 'fat', 'fiber', 'ash', 'calcium', 'phosphorus', 'salt', 'moisture']
const MAIZE_EXTRA = ['fungus', 'broke', 'water_damage', 'small', 'dunkey', 'fm', 'maize_count', 'colour', 'smell']


//new 

import * as XLSX from "xlsx";
import { saveAs } from "file-saver";
import {
  formatDateTimeIST,
  parseApiDate,
  toDateInputIST,
  todayDateInputIST,
} from "../utils/datetime";

const IST_TIME_ZONE = "Asia/Kolkata"
const DATE_ONLY_RE = /^\d{4}-\d{2}-\d{2}$/
const DEFAULT_TIME_PARTS = { hour: "12", minute: "00", meridiem: "AM" }

const pad2 = (value) => String(value).padStart(2, "0")

function getTimePartsIST(value) {
  const parsed = parseApiDate(value)
  if (!parsed) return { ...DEFAULT_TIME_PARTS }

  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: IST_TIME_ZONE,
    hour: "2-digit",
    minute: "2-digit",
    hour12: true,
  }).formatToParts(parsed)

  const out = { ...DEFAULT_TIME_PARTS }
  parts.forEach((part) => {
    if (part.type === "hour") out.hour = part.value
    if (part.type === "minute") out.minute = part.value
    if (part.type === "dayPeriod") out.meridiem = part.value.toUpperCase() === "PM" ? "PM" : "AM"
  })
  return out
}

function currentTimePartsIST() {
  return getTimePartsIST(new Date())
}

function toApiDateTimeFrom12HourInput(dateInput, hourInput, minuteInput, meridiemInput) {
  if (!DATE_ONLY_RE.test(String(dateInput || ""))) return null

  const hour12 = Number(hourInput)
  const minute = Number(minuteInput)
  const meridiem = String(meridiemInput || "").toUpperCase()
  if (!Number.isInteger(hour12) || hour12 < 1 || hour12 > 12) return null
  if (!Number.isInteger(minute) || minute < 0 || minute > 59) return null
  if (meridiem !== "AM" && meridiem !== "PM") return null

  let hour24 = hour12 % 12
  if (meridiem === "PM") hour24 += 12

  return `${dateInput}T${pad2(hour24)}:${pad2(minute)}:00+05:30`
}

const emptyEntryForm = () => {
  const time = currentTimePartsIST()
  return {
    date: todayDateInputIST(),
    hour: time.hour,
    minute: time.minute,
    meridiem: time.meridiem,
    rm_type: '',
    supplier: '',
    challan_no: '',
    vehicle_no: '',
    total_weight: '',
    remarks: '',
  }
}

const emptyLabForm = () => ({
  entry_id: null,
  protein: '',
  fat: '',
  fiber: '',
  ash: '',
  calcium: '',
  phosphorus: '',
  salt: '',
  moisture: '',
  fungus: '',
  broke: '',
  water_damage: '',
  small: '',
  dunkey: '',
  fm: '',
  maize_count: '',
  colour: '',
  smell: '',
})

export default function RawMaterial() {

  const [entries, setEntries] = useState([])
  const [rmTypes, setRmTypes] = useState([])
  const [rmStockRows, setRmStockRows] = useState([])
  const [showAdd, setShowAdd] = useState(false)
  const [addError, setAddError] = useState('')
  const [showAddType, setShowAddType] = useState(false)
  const [newRmType, setNewRmType] = useState('')
  const [showLab, setShowLab] = useState(false)
  const [labError, setLabError] = useState('')
  const [showEdit, setShowEdit] = useState(false)
  const [editError, setEditError] = useState('')
  const [selectedEntry, setSelectedEntry] = useState(null)
  const [editingEntry, setEditingEntry] = useState(null)
  const [popupMessage, setPopupMessage] = useState('')
  const { requestPin, pinDialog } = usePinGate()

  //Table
  const [search, setSearch] = useState("");
  const [rmTypeFilter, setRmTypeFilter] = useState("");
const [currentPage, setCurrentPage] = useState(1);

const [fromDate, setFromDate] = useState("")
const [toDate, setToDate] = useState("")
const rowsPerPage = 5;



const downloadPDF = () => {
  stockApi.downloadRMIndividual("pdf").then(({ data }) => {
    const url = URL.createObjectURL(new Blob([data]))
    const a = document.createElement("a")
    a.href = url
    a.download = "rm_individual_stock.pdf"
    a.click()
    URL.revokeObjectURL(url)
  }).catch(() => {
    setPopupMessage("Unable to download individual stock PDF.")
  })
};


const downloadExcel = () => {
  const worksheetData = individualStock.map(item => ({
    "RM Type": item.rm_name,
    "Current Stock": item.closing_stock,
  }));

  const worksheet = XLSX.utils.json_to_sheet(worksheetData);
  const workbook = XLSX.utils.book_new();

  XLSX.utils.book_append_sheet(workbook, worksheet, "Stock");

  const excelBuffer = XLSX.write(workbook, {
    bookType: "xlsx",
    type: "array",
  });

  const file = new Blob([excelBuffer], {
    type:
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;charset=UTF-8",
  });

  saveAs(file, "Individual_Raw_Material_Stock.xlsx");
};

const filteredEntries = entries.filter(e => {
const entryDate = toDateInputIST(e.date, "");
  return (
    (
      e.rm_type.toLowerCase().includes(search.toLowerCase()) ||
      e.supplier.toLowerCase().includes(search.toLowerCase()) ||
      e.vehicle_no.toLowerCase().includes(search.toLowerCase())
    ) &&
    (rmTypeFilter ? e.rm_type === rmTypeFilter : true) &&

  (fromDate ? entryDate >= fromDate : true) &&
(toDate ? entryDate <= toDate : true)
  );
});

const totalPages = Math.ceil(filteredEntries.length / rowsPerPage);

const paginatedEntries = filteredEntries.slice(
  (currentPage - 1) * rowsPerPage,
  currentPage * rowsPerPage
);

  const [form, setForm] = useState(emptyEntryForm())
  const [editForm, setEditForm] = useState(emptyEntryForm())
  const [labForm, setLabForm] = useState(emptyLabForm())

  const load = () => {
    // rawMaterial.list().then(({ data }) => 
      
    //   setEntries(data)
      
    // ).catch(() => setEntries([]))
      rawMaterial.list()
    .then(({ data }) => {
      const sorted = (data || []).sort((a, b) => {
        const bDate = parseApiDate(b.date)?.getTime() ?? Number.NEGATIVE_INFINITY
        const aDate = parseApiDate(a.date)?.getTime() ?? Number.NEGATIVE_INFINITY
        if (bDate !== aDate) return bDate - aDate
        return (Number(b.id) || 0) - (Number(a.id) || 0)
      })
      setEntries(sorted)
    })
    .catch(() => setEntries([]))
    rawMaterial.listTypes().then(({ data }) => setRmTypes(data)).catch(() => setRmTypes([]))
    stockApi.rm().then(({ data }) => setRmStockRows(data || [])).catch(() => setRmStockRows([]))
  }
  useEffect(() => { load() }, [])

  const latestStockByName = rmStockRows.reduce((acc, row) => {
    const current = acc[row.rm_name]
    const rowTime = parseApiDate(row.date)?.getTime() || Number.NEGATIVE_INFINITY
    const currentTime = parseApiDate(current?.date)?.getTime() || Number.NEGATIVE_INFINITY
    if (!current || rowTime > currentTime) {
      acc[row.rm_name] = row
    }
    return acc
  }, {})

  // const individualStock = rmTypes
  //   .map((t) => ({
  //     rm_name: t.name,
  //     closing_stock: latestStockByName[t.name]?.closing_stock ?? 0,
  //   }))
  //   .sort((a, b) => a.rm_name.localeCompare(b.rm_name))


    const individualStock = rmTypes
  .slice()          // copy array
  .reverse()        // newest types first
  .map((t) => ({
    rm_name: t.name,
    closing_stock: latestStockByName[t.name]?.closing_stock ?? 0,
  }))
  const availableRawMaterials = individualStock
    .map((row) => ({
      rm_name: String(row.rm_name || '').trim(),
      closing_stock: Number(row.closing_stock || 0),
    }))
    .filter((row) => row.rm_name && Number.isFinite(row.closing_stock) && row.closing_stock > 0)
    .sort((a, b) => b.closing_stock - a.closing_stock)

  const totalStockWeight = individualStock.reduce((sum, item) => sum + (Number(item.closing_stock) || 0), 0)
  const totalInwardWeight = entries.reduce((sum, item) => sum + (Number(item.total_weight) || 0), 0)

  const handleAdd = async (e) => {
    e.preventDefault()
    setAddError('')
    const entryDateTime = toApiDateTimeFrom12HourInput(form.date, form.hour, form.minute, form.meridiem)
    if (!entryDateTime) {
      setAddError("Please enter a valid entry date and time.")
      return
    }

    try {
      await rawMaterial.create({
        date: entryDateTime,
        rm_type: form.rm_type,
        supplier: form.supplier,
        challan_no: form.challan_no,
        vehicle_no: form.vehicle_no,
        total_weight: parseFloat(form.total_weight),
        remarks: form.remarks,
      })
      setShowAdd(false)
      setForm(emptyEntryForm())
      setAddError('')
      setCurrentPage(1)
      load()
    } catch (err) {
      const detail = err?.response?.data?.detail || 'Unable to create entry.'
      setAddError(detail)
    }
  }

  const openEdit = (entry) => {
    const time = getTimePartsIST(entry.date)
    setEditingEntry(entry)
    setEditForm({
      date: toDateInputIST(entry.date, todayDateInputIST()),
      hour: time.hour,
      minute: time.minute,
      meridiem: time.meridiem,
      rm_type: entry.rm_type || '',
      supplier: entry.supplier || '',
      challan_no: entry.challan_no || '',
      vehicle_no: entry.vehicle_no || '',
      total_weight: String(entry.total_weight ?? ''),
      remarks: entry.remarks || '',
    })
    setShowEdit(true)
  }

  const closeEdit = () => {
    setShowEdit(false)
    setEditingEntry(null)
    setEditForm(emptyEntryForm())
    setEditError('')
  }

  const handleEditSubmit = async (e) => {
    e.preventDefault()
    setEditError('')
    if (!editingEntry) return
    const entryDateTime = toApiDateTimeFrom12HourInput(
      editForm.date,
      editForm.hour,
      editForm.minute,
      editForm.meridiem
    )
    if (!entryDateTime) {
      setEditError("Please enter a valid entry date and time.")
      return
    }

    try {
      await rawMaterial.update(editingEntry.id, {
        date: entryDateTime,
        rm_type: editForm.rm_type,
        supplier: editForm.supplier,
        challan_no: editForm.challan_no,
        vehicle_no: editForm.vehicle_no,
        total_weight: parseFloat(editForm.total_weight),
        remarks: editForm.remarks,
      })
      closeEdit()
      load()
    } catch (err) {
      const detail = err?.response?.data?.detail || 'Unable to update RM entry.'
      setEditError(detail)
    }
  }

  const openLab = async (entry) => {
    setSelectedEntry(entry)
    try {
      const { data } = await rawMaterial.getLabReport(entry.id)
      const report = data?.report || {}
      setLabForm({
        ...emptyLabForm(),
        entry_id: entry.id,
        protein: report.protein ?? '',
        fat: report.fat ?? '',
        fiber: report.fiber ?? '',
        ash: report.ash ?? '',
        calcium: report.calcium ?? '',
        phosphorus: report.phosphorus ?? '',
        salt: report.salt ?? '',
        moisture: report.moisture ?? '',
        fungus: report.fungus ?? '',
        broke: report.broke ?? '',
        water_damage: report.water_damage ?? '',
        small: report.small ?? '',
        dunkey: report.dunkey ?? '',
        fm: report.fm ?? '',
        maize_count: report.maize_count ?? '',
        colour: report.colour ?? '',
        smell: report.smell ?? '',
      })
    } catch {
      setLabForm({
        ...emptyLabForm(),
        entry_id: entry.id,
      })
    }
    setShowLab(true)
  }

  const handleLabSubmit = async (e) => {
    e.preventDefault()
    setLabError('')
    const payload = { ...labForm, entry_id: selectedEntry.id }
    LAB_PARAMS.forEach((k) => { if (payload[k] !== '') payload[k] = parseFloat(payload[k]) || null })
    try {
      await rawMaterial.submitLabReport(payload)
      setShowLab(false)
      setSelectedEntry(null)
      setLabError('')
      load()
    } catch (err) {
      const detail = err?.response?.data?.detail || 'Unable to submit lab report.'
      setLabError(detail)
    }
  }

  const download = (format) => {
    rawMaterial.download(format).then(({ data }) => {
      const ext = format === 'pdf' ? 'pdf' : format === 'xlsx' || format === 'excel' ? 'xlsx' : 'csv'
      const url = URL.createObjectURL(new Blob([data]))
      const a = document.createElement('a')
      a.href = url
      a.download = `raw_material_report.${ext}`
      a.click()
      URL.revokeObjectURL(url)
    })
  }

  const downloadEntryReport = (entryId, format) => {
    rawMaterial.downloadEntry(entryId, format).then(({ data }) => {
      const ext = format === 'pdf' ? 'pdf' : 'xlsx'
      const url = URL.createObjectURL(new Blob([data]))
      const a = document.createElement('a')
      a.href = url
      a.download = `raw_material_entry_${entryId}_report.${ext}`
      a.click()
      URL.revokeObjectURL(url)
    }).catch((err) => {
      const detail = err?.response?.data?.detail || 'Unable to download entry report.'
      setPopupMessage(detail)
    })
  }

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">

  {/* Total Stock */}
<div className="relative rounded-xl overflow-hidden shadow-md h-36 sm:h-40">
  {/* background image */}
  <img
    src={cornbag}
    alt="Raw Material Stock"
    className="absolute inset-0 w-full h-full object-cover"
  />

  {/* overlay */}
  {/* <div className="absolute inset-0 bg-white/40"></div> */}

  {/* content */}
<div className="
  relative z-10 flex flex-col justify-center h-full px-4

  items-center text-center            /* 📱 mobile */

  md:absolute md:inset-0
  md:items-start md:text-left         /* 💻 desktop */

  md:ml-[40%]                         /* ⭐ move into empty space */
  lg:ml-[45%]
">
    <p className="text-base sm:text-xl md:text-2xl text-gray-700 font-medium">
      Total Raw Material (Stock)
    </p>

    <h2 className="text-2xl sm:text-3xl md:text-4xl font-bold text-[#263C2C]">
      {totalStockWeight.toFixed(2)} KG
    </h2>
  </div>
</div>

  {/* Total Usage */}
<div className="relative rounded-xl shadow-md overflow-hidden h-36 sm:h-40">

  {/* background image */}
  <img
    src={potato}
    alt="Raw Material Usage"
    className="absolute inset-0 w-full h-full object-cover"
  />

  {/* overlay for readability */}
  {/* <div className="absolute inset-0 bg-white/30 md:bg-transparent"></div> */}

  {/* content */}
 <div className="
    relative z-10 h-full px-4
    flex flex-col justify-center

    items-center text-center        /* mobile */
    md:items-start md:text-left

    md:ml-[40%]                     /* responsive shift */
    lg:ml-[45%]
">
    <p className="text-base sm:text-xl md:text-2xl text-gray-700 font-medium">
      Total Raw Material (Received) 
    </p>

    <h2 className="text-2xl sm:text-3xl md:text-4xl font-bold text-[#263C2C]">
      {totalInwardWeight.toFixed(2)} KG
    </h2>
  </div>
</div>

</div>  
    <div className="
  flex flex-col gap-4
  sm:flex-row sm:items-center sm:justify-between
">

  <h1 className="text-xl font-semibold text-slate-800 text-center sm:text-left">
    Raw Material
  </h1>

  <div className="
    flex flex-wrap justify-center sm:justify-end
    gap-2
  ">
    <button
      onClick={() => setShowAdd(true)}
      className="px-4 py-2 rounded-lg bg-[#245658] text-primary font-medium w-full sm:w-auto"
    >
      + Add RM Entry
    </button>

    <button
      onClick={() => download('pdf')}
      className="px-4 py-2 rounded-lg border border-gray-600 text-gray-800 hover:bg-primary-light w-full sm:w-auto"
    >
      Download PDF
    </button>

    <button
      onClick={() => download('xlsx')}
      className="px-4 py-2 rounded-lg border border-gray-600 text-gray-800 hover:bg-primary-light w-full sm:w-auto"
    >
      Download Excel
    </button>

    <button
      onClick={() => setShowAddType(true)}
      className="px-4 py-2 rounded-lg border border-gray-600 text-gray-800 hover:bg-primary-light w-full sm:w-auto"
    >
      + Add RM Type
    </button>
  </div>
</div>
      <Modal open={showAddType} onClose={() => { setShowAddType(false); setNewRmType('') }} title="Add RM Type">
        <p className="text-gray-900 text-sm mb-3">New RM name will be added to Raw Material report and RM stock.</p>
        <input type="text" value={newRmType} onChange={(e) => setNewRmType(e.target.value)} placeholder="e.g. MAIZE, SOYA" className="w-full px-3 py-2 rounded-lg bg-primary-light border border-gray-600 text-gray-900 mb-4" />
        <div className="flex gap-2">
          <button onClick={async () => { await rawMaterial.addType(newRmType); setShowAddType(false); setNewRmType(''); load() }} className="px-4 py-2 rounded-lg bg-accent-green text-primary font-medium" disabled={!newRmType.trim()}>Add</button>
          <button onClick={() => { setShowAddType(false); setNewRmType('') }} className="px-4 py-2 rounded-lg border border-gray-600 text-gray-900">Cancel</button>
        </div>
      </Modal>

   <div className="bg-white rounded-xl shadow border overflow-hidden">

{/* 🔍 Search + Filters */}
<div className="bg-white rounded-xl shadow border border-gray-300 overflow-hidden">
  <div className="p-4 border-b border-gray-200 flex flex-wrap items-end gap-4">

    {/* Search */}
    <div className="w-full md:w-64">
      <label className="block text-xs text-gray-500 mb-1">Search</label>
      <div className="relative">
        <img
          src={searchIcon}
          alt="search"
          className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 opacity-60"
        />
        <input
          type="text"
          placeholder="Search..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="border border-gray-400 rounded-lg pl-10 pr-3 py-2 text-sm w-full"
        />
      </div>
    </div>

    {/* RM Type Filter */}
    <div>
      <label className="block text-xs text-gray-500 mb-1">RM Type</label>
      <select
        value={rmTypeFilter}
        onChange={(e) => setRmTypeFilter(e.target.value)}
        className="border border-gray-400 rounded-lg px-3 py-2 text-sm"
      >
        <option value="">All</option>
        {[...new Set(entries.map(e => e.rm_type))].map(type => (
          <option key={type} value={type}>{type}</option>
        ))}
      </select>
    </div>

    {/* Date From */}
    <div>
      <label className="block text-xs text-gray-500 mb-1">Date From</label>
      <input
        type="date"
        value={fromDate}
        onChange={(e) => setFromDate(e.target.value)}
        className="border border-gray-400 rounded-lg px-3 py-2 text-sm"
      />
    </div>

    {/* Date To */}
    <div>
      <label className="block text-xs text-gray-500 mb-1">Date To</label>
      <input
        type="date"
        value={toDate}
        onChange={(e) => setToDate(e.target.value)}
        className="border border-gray-400 rounded-lg px-3 py-2 text-sm"
      />
    </div>

  </div>
</div>
  {/* Table */}
  <div className="overflow-x-auto">
<table className="min-w-full text-sm border border-gray-300">      
     <thead className="bg-[#245658] text-white border-b border-gray-300">
        <tr>
          <th className="px-4 py-3 text-left border border-gray-300">Entry Date & Time</th>
          <th className="px-4 py-3 text-left border border-gray-300">Last Modified</th>
          <th className="px-4 py-3 text-left border border-gray-300">RM Type</th>
          <th className="px-4 py-3 text-left border border-gray-300">Supplier</th>
          <th className="px-4 py-3 text-left border border-gray-300">Challan No</th>
          <th className="px-4 py-3 text-left border border-gray-300">Vehicle No</th>
	          <th className="px-4 py-3 text-left border border-gray-300">Raw Material Weight</th>
	          <th className="px-4 py-3 text-left border border-gray-300">Lab Report</th>
	          <th className="px-4 py-3 text-left border border-gray-300">Action</th>
	          <th className="px-4 py-3 text-left border border-gray-300">Download Report</th>
	          <th className="px-4 py-3 text-left border border-gray-300">Remarks</th>
        </tr>
      </thead>

      <tbody>
        {paginatedEntries.map((e) => (
          <tr key={e.id} className=" hover:bg-gray-50">
            <td className="px-4 py-3 border border-gray-300">{formatDateTimeIST(e.date)}</td>
            <td className="px-4 py-3 border border-gray-300">{formatDateTimeIST(e.last_modified_at || e.created_at)}</td>
            <td className="px-4 py-3 border border-gray-300">{e.rm_type}</td>
            <td className="px-4 py-3 border border-gray-300">{e.supplier}</td>
            <td className="px-4 py-3 border border-gray-300">{e.challan_no}</td>
            <td className="px-4 py-3 border border-gray-300">{e.vehicle_no}</td>
            <td className="px-4 py-3 border border-gray-300">{Number(e.total_weight || 0).toFixed(2)}</td>
            <td className="px-4 py-3 border border-gray-300">
              {e.has_lab_report
                ? <span className="text-green-600 font-medium">Yes</span>
                : <span className="text-gray-900">Not Filled</span>}
            </td>
	            <td className="px-4 py-3 border border-gray-300">
	              <div className="flex items-center gap-3">
	                <button
	                  onClick={() => requestPin(
	                    () => openEdit(e),
	                    { title: 'PIN Required', message: 'Enter PIN to edit (1234) raw material entry.' }
	                  )}
	                  className="text-blue-700 font-medium underline"
	                >
	                  Edit Entry
	                </button>
	                <button
	                  onClick={() => requestPin(
	                    () => openLab(e),
	                    { title: 'PIN Required', message: 'Enter PIN to edit (1234) lab report.' }
	                  )}
	                  className="text-green-700 font-medium underline"
	                >
	                  Edit Lab
	                </button>
	              </div>
	            </td>
	            <td className="px-4 py-3 border border-gray-300">
	              <div className="flex items-center gap-3">
	                <button
	                  onClick={() => downloadEntryReport(e.id, 'pdf')}
	                  className="text-red-700 font-medium underline"
	                >
	                  PDF
	                </button>
	                <button
	                  onClick={() => downloadEntryReport(e.id, 'xlsx')}
	                  className="text-emerald-700 font-medium underline"
	                >
	                  Excel
	                </button>
	              </div>
	            </td>
            <td className="px-4 py-3 border border-gray-300">{e.remarks || '-'}</td>
          </tr>
        ))}
      </tbody>

    </table>
  </div>

  {/* 📄 Pagination Footer */}
  <div className="flex items-center justify-between px-4 py-3 bg-gray-50">

    <span className="text-sm text-gray-600">
      Page {currentPage} of {totalPages}
    </span>

    <div className="flex gap-1">
      <button
        disabled={currentPage === 1}
        onClick={()=>setCurrentPage(p => p - 1)}
        className="px-3 py-1 border rounded disabled:opacity-40"
      >
        ◀
      </button>

      {[...Array(totalPages)].map((_,i)=>(
        <button
          key={i}
          onClick={()=>setCurrentPage(i+1)}
          className={`px-3 py-1 border rounded ${
            currentPage === i+1 ? 'bg-green-700 text-white' : ''
          }`}
        >
          {i+1}
        </button>
      ))}

      <button
        disabled={currentPage === totalPages}
        onClick={()=>setCurrentPage(p => p + 1)}
        className="px-3 py-1 border rounded disabled:opacity-40"
      >
        ▶
      </button>
    </div>
  </div>
</div>

      <div className="bg-white rounded-xl shadow border border-gray-300 overflow-hidden">
     <div className="px-4 py-3 border-b border-gray-200">
  <div className="flex flex-wrap justify-between items-start gap-3">
    
    <div>
      <h2 className="text-sm font-semibold text-slate-800">
        Individual Raw Material Stock
      </h2>
      <p className="text-xs text-gray-500 mt-1">
        Latest closing stock by raw material type
      </p>
    </div>

    <div className="flex flex-wrap gap-2">
      <button
        onClick={downloadPDF}
        className="px-4 py-2 rounded-lg bg-[#245658] border border-gray-600 text-white hover:bg-[#3a8a8d] hover:border-white whitespace-nowrap"
      >
        Download PDF
      </button>

      <button
        onClick={downloadExcel}
        className="px-4 py-2 rounded-lg bg-[#245658] border border-gray-600 text-white hover:bg-[#3a8a8d] hover:border-white whitespace-nowrap"
      >
        Download Excel
      </button>
    </div>

  </div>
</div>
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm border border-gray-300">
            <thead className="bg-[#245658] text-white">
              <tr>
                <th className="px-4 py-3 text-left border border-gray-300">RM Type</th>
                <th className="px-4 py-3 text-left border border-gray-300">Current Stock (kg)</th>
              </tr>
            </thead>
            <tbody>
              {individualStock.length === 0 ? (
                <tr>
                  <td colSpan={2} className="px-4 py-3 text-gray-500 border border-gray-300">
                    No stock data available yet.
                  </td>
                </tr>
              ) : (
                individualStock.map((row) => (
                  <tr key={row.rm_name} className="hover:bg-gray-50">
                    <td className="px-4 py-3 border border-gray-300">{row.rm_name}</td>
                    <td className="px-4 py-3 border border-gray-300 font-medium">{Number(row.closing_stock || 0).toFixed(2)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <Modal open={showAdd} onClose={() => { setShowAdd(false); setAddError(''); }} title="Add RM Inward" >
        <form onSubmit={handleAdd} className="space-y-4">
          <div className="bg-gray-100 border border-gray-300 rounded-lg p-3">
            <p className="text-sm font-semibold text-gray-700 mb-2">Available Raw Materials</p>
            {availableRawMaterials.length === 0 ? (
              <p className="text-sm text-gray-500">No available raw material stock (greater than 0 kg).</p>
            ) : (
              <div className="max-h-[136px] overflow-y-auto overflow-x-auto rounded border border-gray-300">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-gray-200 text-gray-700">
                      <th className="px-3 py-2 text-left border-b border-gray-300">Raw Material</th>
                      <th className="px-3 py-2 text-right border-b border-gray-300">Weight Available (kg)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {availableRawMaterials.map((row) => (
                      <tr key={`available-rm-${row.rm_name}`} className="bg-gray-50 text-gray-700 border-b border-gray-200 last:border-b-0">
                        <td className="px-3 py-2">{row.rm_name}</td>
                        <td className="px-3 py-2 text-right font-medium">{row.closing_stock.toFixed(2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
          {addError && (
            <div className="bg-red-100 text-red-800 px-4 py-3 rounded-lg text-sm border border-red-300">
              {addError}
            </div>
          )}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-sm text-gray-900 mb-1">Date</label>
              <input type="date" value={form.date} onChange={(e) => setForm((f) => ({ ...f, date: e.target.value }))} className="w-full px-3 py-2 rounded-lg bg-primary-light border border-gray-600 text-black" required />
            </div>
            <div>
              <label className="block text-sm text-gray-900 mb-1">Entry Time</label>
              <div className="grid grid-cols-3 gap-2">
                <select
                  value={form.hour}
                  onChange={(e) => setForm((f) => ({ ...f, hour: e.target.value }))}
                  className="w-full px-3 py-2 rounded-lg bg-primary-light border border-gray-600 text-black"
                  required
                >
                  {Array.from({ length: 12 }, (_, index) => {
                    const value = String(index + 1).padStart(2, "0")
                    return <option key={value} value={value}>{value}</option>
                  })}
                </select>
                <select
                  value={form.minute}
                  onChange={(e) => setForm((f) => ({ ...f, minute: e.target.value }))}
                  className="w-full px-3 py-2 rounded-lg bg-primary-light border border-gray-600 text-black"
                  required
                >
                  {Array.from({ length: 60 }, (_, index) => {
                    const value = String(index).padStart(2, "0")
                    return <option key={value} value={value}>{value}</option>
                  })}
                </select>
                <select
                  value={form.meridiem}
                  onChange={(e) => setForm((f) => ({ ...f, meridiem: e.target.value }))}
                  className="w-full px-3 py-2 rounded-lg bg-primary-light border border-gray-600 text-black"
                  required
                >
                  <option value="AM">AM</option>
                  <option value="PM">PM</option>
                </select>
              </div>
            </div>
            <div>
              <label className="block text-sm text-gray-900 mb-1">RM Type (pre-defined)</label>
                <div className="relative">
              <select value={form.rm_type} onChange={(e) => setForm((f) => ({ ...f, rm_type: e.target.value }))} className="w-full px-3  py-2  rounded-lg bg-primary-light border border-gray-600 text-black appearance-none" required>
                <option value="">Select</option>
                {rmTypes.map((t) => (
                  <option key={t.id} value={t.name}>{t.name}</option>
                ))}
              </select>
                <img
      src={arrow}
      alt="arrow"
      className="pointer-events-none text-black absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 "
    />
  </div>
              
            </div>
          </div>
          <div>
            <label className="block text-sm text-gray-900 mb-1">Supplier</label>
            <input type="text" value={form.supplier} onChange={(e) => setForm((f) => ({ ...f, supplier: e.target.value }))} className="w-full px-3 py-2 rounded-lg bg-primary-light border border-gray-600 text-black" required />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-gray-900 mb-1">Challan No</label>
              <input type="text" value={form.challan_no} onChange={(e) => setForm((f) => ({ ...f, challan_no: e.target.value }))} className="w-full px-3 py-2 rounded-lg bg-primary-light border border-gray-600 text-black" required />
            </div>
            <div>
              <label className="block text-sm text-gray-900 mb-1">Vehicle No</label>
              <input type="text" value={form.vehicle_no} onChange={(e) => setForm((f) => ({ ...f, vehicle_no: e.target.value }))} className="w-full px-3 py-2 rounded-lg bg-primary-light border border-gray-600 text-black" required />
            </div>
          </div>
          <div>
            <label className="block text-sm text-gray-900 mb-1">Total Weight</label>
            <input type="number" step="any" value={form.total_weight} onChange={(e) => setForm((f) => ({ ...f, total_weight: e.target.value }))} className="w-full px-3 py-2 rounded-lg bg-primary-light border border-gray-600 text-black" required />
          </div>
          <div>
            <label className="block text-sm text-gray-900 mb-1">Remarks</label>
            <input type="text" value={form.remarks} onChange={(e) => setForm((f) => ({ ...f, remarks: e.target.value }))} className="w-full px-3 py-2 rounded-lg bg-primary-light border border-gray-600 text-black" />
          </div>
          <div className="flex gap-2">
            <button type="submit" className="px-4 py-2 rounded-lg bg-accent-green text-primary font-medium">Submit</button>
            <button type="button" onClick={() => setShowAdd(false)} className="px-4 py-2 rounded-lg border border-gray-600 text-black">Cancel</button>
          </div>
        </form>
      </Modal>

      <Modal open={showEdit} onClose={closeEdit} title="Edit RM Entry">
        <form onSubmit={handleEditSubmit} className="space-y-4">
          <div className="bg-gray-100 border border-gray-300 rounded-lg p-3">
            <p className="text-sm font-semibold text-gray-700 mb-2">Available Raw Materials</p>
            {availableRawMaterials.length === 0 ? (
              <p className="text-sm text-gray-500">No available raw material stock (greater than 0 kg).</p>
            ) : (
              <div className="max-h-[136px] overflow-y-auto overflow-x-auto rounded border border-gray-300">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-gray-200 text-gray-700">
                      <th className="px-3 py-2 text-left border-b border-gray-300">Raw Material</th>
                      <th className="px-3 py-2 text-right border-b border-gray-300">Weight Available (kg)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {availableRawMaterials.map((row) => (
                      <tr key={`available-rm-edit-${row.rm_name}`} className="bg-gray-50 text-gray-700 border-b border-gray-200 last:border-b-0">
                        <td className="px-3 py-2">{row.rm_name}</td>
                        <td className="px-3 py-2 text-right font-medium">{row.closing_stock.toFixed(2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
          {editError && (
            <div className="bg-red-100 text-red-800 px-4 py-3 rounded-lg text-sm border border-red-300">
              {editError}
            </div>
          )}
          {editingEntry && (
            <p className="text-xs text-gray-600">
              Entry Date: {formatDateTimeIST(editingEntry.date)} | Last Modified: {formatDateTimeIST(editingEntry.last_modified_at || editingEntry.created_at)}
            </p>
          )}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-sm text-gray-900 mb-1">Date</label>
              <input type="date" value={editForm.date} onChange={(e) => setEditForm((f) => ({ ...f, date: e.target.value }))} className="w-full px-3 py-2 rounded-lg bg-primary-light border border-gray-600 text-black" required />
            </div>
            <div>
              <label className="block text-sm text-gray-900 mb-1">Entry Time</label>
              <div className="grid grid-cols-3 gap-2">
                <select
                  value={editForm.hour}
                  onChange={(e) => setEditForm((f) => ({ ...f, hour: e.target.value }))}
                  className="w-full px-3 py-2 rounded-lg bg-primary-light border border-gray-600 text-black"
                  required
                >
                  {Array.from({ length: 12 }, (_, index) => {
                    const value = String(index + 1).padStart(2, "0")
                    return <option key={value} value={value}>{value}</option>
                  })}
                </select>
                <select
                  value={editForm.minute}
                  onChange={(e) => setEditForm((f) => ({ ...f, minute: e.target.value }))}
                  className="w-full px-3 py-2 rounded-lg bg-primary-light border border-gray-600 text-black"
                  required
                >
                  {Array.from({ length: 60 }, (_, index) => {
                    const value = String(index).padStart(2, "0")
                    return <option key={value} value={value}>{value}</option>
                  })}
                </select>
                <select
                  value={editForm.meridiem}
                  onChange={(e) => setEditForm((f) => ({ ...f, meridiem: e.target.value }))}
                  className="w-full px-3 py-2 rounded-lg bg-primary-light border border-gray-600 text-black"
                  required
                >
                  <option value="AM">AM</option>
                  <option value="PM">PM</option>
                </select>
              </div>
            </div>
            <div>
              <label className="block text-sm text-gray-900 mb-1">RM Type (pre-defined)</label>
              <div className="relative">
                <select value={editForm.rm_type} onChange={(e) => setEditForm((f) => ({ ...f, rm_type: e.target.value }))} className="w-full px-3 py-2 rounded-lg bg-primary-light border border-gray-600 text-black appearance-none" required>
                  <option value="">Select</option>
                  {rmTypes.map((t) => (
                    <option key={t.id} value={t.name}>{t.name}</option>
                  ))}
                </select>
                <img
                  src={arrow}
                  alt="arrow"
                  className="pointer-events-none text-black absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 "
                />
              </div>
            </div>
          </div>
          <div>
            <label className="block text-sm text-gray-900 mb-1">Supplier</label>
            <input type="text" value={editForm.supplier} onChange={(e) => setEditForm((f) => ({ ...f, supplier: e.target.value }))} className="w-full px-3 py-2 rounded-lg bg-primary-light border border-gray-600 text-black" required />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-gray-900 mb-1">Challan No</label>
              <input type="text" value={editForm.challan_no} onChange={(e) => setEditForm((f) => ({ ...f, challan_no: e.target.value }))} className="w-full px-3 py-2 rounded-lg bg-primary-light border border-gray-600 text-black" required />
            </div>
            <div>
              <label className="block text-sm text-gray-900 mb-1">Vehicle No</label>
              <input type="text" value={editForm.vehicle_no} onChange={(e) => setEditForm((f) => ({ ...f, vehicle_no: e.target.value }))} className="w-full px-3 py-2 rounded-lg bg-primary-light border border-gray-600 text-black" required />
            </div>
          </div>
          <div>
            <label className="block text-sm text-gray-900 mb-1">Raw Material Weight</label>
            <input type="number" step="any" value={editForm.total_weight} onChange={(e) => setEditForm((f) => ({ ...f, total_weight: e.target.value }))} className="w-full px-3 py-2 rounded-lg bg-primary-light border border-gray-600 text-black" required />
          </div>
          <div>
            <label className="block text-sm text-gray-900 mb-1">Remarks</label>
            <input type="text" value={editForm.remarks} onChange={(e) => setEditForm((f) => ({ ...f, remarks: e.target.value }))} className="w-full px-3 py-2 rounded-lg bg-primary-light border border-gray-600 text-black" />
          </div>
          <div className="flex gap-2">
            <button type="submit" className="px-4 py-2 rounded-lg bg-accent-green text-primary font-medium">Update</button>
            <button type="button" onClick={closeEdit} className="px-4 py-2 rounded-lg border border-gray-600 text-black">Cancel</button>
          </div>
          {editingEntry && (
            <div className="text-right text-xs text-gray-600">
              Created At: {formatDateTimeIST(editingEntry.created_at)}
            </div>
          )}
        </form>
      </Modal>

      <Modal open={showLab} onClose={() => { setShowLab(false); setSelectedEntry(null); setLabError(''); }} title="Lab Report" >
        {selectedEntry && (
          <>
            {labError && (
              <div className="bg-red-100 text-red-800 px-4 py-3 rounded-lg text-sm border border-red-300 mb-4">
                {labError}
              </div>
            )}
            <p className="text-black text-sm mb-4">
              Date: {formatDateTimeIST(selectedEntry.date)} | RM Type: {selectedEntry.rm_type} | Supplier: {selectedEntry.supplier} | Challan: {selectedEntry.challan_no} | Vehicle: {selectedEntry.vehicle_no} | Weight: {selectedEntry.total_weight} | Remarks: {selectedEntry.remarks || '—'}
            </p>
            <form onSubmit={handleLabSubmit} className="space-y-4    md:pb-4 overflow-y-auto">
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                {LAB_PARAMS.map((key) => (
                  <div key={key}>
                    <label className="block text-xs text-black capitalize mb-0.5">{key}</label>
                    <input type="number" step="any" value={labForm[key] || ''} onChange={(e) => setLabForm((f) => ({ ...f, [key]: e.target.value }))} className="w-full px-2 py-1.5 rounded bg-primary-light border border-gray-600 text-black text-sm" />
                  </div>
                ))}
              </div>
              {selectedEntry.rm_type?.toLowerCase().includes('maize') && (
                <div className="pt-2 border-t border-gray-700">
                  <p className="text-xs text-black mb-2">For Maize</p>
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                    {MAIZE_EXTRA.map((key) => (
                      <div key={key}>
                        <label className="block text-xs text-black capitalize mb-0.5">{key.replace('_', ' ')}</label>
                        <input type="text" value={labForm[key] || ''} onChange={(e) => setLabForm((f) => ({ ...f, [key]: e.target.value }))} className="w-full px-2 py-1.5 rounded bg-primary-light border border-gray-600 text-black text-sm" />
                      </div>
                    ))}
                  </div>
                </div>
              )}
              <div className="flex gap-2 pt-4 ">
                <button type="submit" className="px-4 py-2 rounded-lg bg-accent-green text-primary font-medium">Submit</button>
                <button type="button" onClick={() => { setShowLab(false); setSelectedEntry(null) }} className="px-4 py-2 rounded-lg border border-gray-600 text-gray-900">Cancel</button>
              </div>
            </form>
          </>
        )}
      </Modal>

      <PopupDialog
        open={Boolean(popupMessage)}
        title="Error"
        message={popupMessage}
        onClose={() => setPopupMessage('')}
      />
      {pinDialog}
    </div>
  )
}
