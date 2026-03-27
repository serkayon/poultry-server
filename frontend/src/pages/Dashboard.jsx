import React from "react";
import { useState, useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import { dispatchApi, plc, productionApi, stockApi } from "../api/client";
import {
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
  Area,
  AreaChart,
  ReferenceLine,
} from "recharts";
import { Truck, Factory, Boxes } from "lucide-react";
import live from "./assets/live.png";
import raw from "./assets/raw.png";
import truck from "./assets/truck.png";
import corn from "./assets/corn.png";
import largegoods from "./assets/bags.png";

import {
  Thermometer,
  Droplets,
  Gauge,
  Wind,
  Activity,
} from "lucide-react";
import {
  formatDateIST,
  formatTimeIST,
  parseApiDate,
  toDateInputIST,
  todayDateInputIST,
} from "../utils/datetime";

const chartColors = {
  temp: "#FF0000",
  humidity: "#06b6d4",
  condTemp: "#059669",
  baggingTemp: "#ea580c",
  feederSpeed: "#7c3aed",
  pressureBefore: "#0d9488",
  pressureAfter: "#ca8a04",
  feederLoad: "#0f766e",
};

export default function Dashboard() {
  const [plcData, setPlcData] = useState(null);
  const [plcHistory, setPlcHistory] = useState([]);
  const [machineStatus, setMachineStatus] = useState(null);
  const [dateTime, setDateTime] = useState(new Date());
  const displayedBatchIdRef = useRef(null);
  const hasGraphHistoryRef = useRef(false);
  const [todayMetrics, setTodayMetrics] = useState({
    rawMaterialStockKg: 0,
    currentDayDispatchKg: 0,
    currentDayProductionKg: 0,
    finishedGoodsStockKg: 0,
  });

  const formatMt = (valueKg) => {
    const safeKg = Math.max(0, Number(valueKg) || 0);
    const safeMt = safeKg / 1000;
    return safeMt.toFixed(3);
  };

  const toApiDateTimeFromDateInputIST = (dateInput, endOfDay = false) =>
    `${dateInput}T${endOfDay ? "23:59:59" : "00:00:00"}+05:30`;

  const formatTime24IST = (value, fallback = "") => {
    const parsed = parseApiDate(value);
    if (!parsed) return fallback;
    return new Intl.DateTimeFormat("en-IN", {
      timeZone: "Asia/Kolkata",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    }).format(parsed);
  };

  const fixedTicks = (maxValue) =>
    Array.from({ length: 11 }, (_, idx) => (maxValue / 10) * idx);

  const feedStockKey = (row) => {
    const feedVariant = String(row?.feed_variant || "").trim();
    if (feedVariant) return feedVariant;
    const feedType = String(row?.feed_type || "").trim();
    if (!feedType) return "";
    const bagWeight = row?.bag_weight_kg == null ? "" : ` (${Number(row.bag_weight_kg)}kg/bag)`;
    return `${feedType}${bagWeight}`;
  };

  const sumLatestClosingByType = (rows, keySelector) => {
    const latestByKey = new Map();
    (rows || []).forEach((row) => {
      const key = String(keySelector(row) || "").trim();
      if (!key) return;
      const ts = new Date(row?.date || 0).getTime();
      const prev = latestByKey.get(key);
      if (!prev || ts > prev.ts) {
        latestByKey.set(key, {
          ts,
          closing: Number(row?.closing_stock) || 0,
        });
      }
    });
    let total = 0;
    latestByKey.forEach((item) => {
      total += item.closing;
    });
    return total;
  };

  const sumLatestClosingByTypeForDay = (rows, keySelector, dayKey) => {
    const dayRows = (rows || []).filter(
      (row) => toDateInputIST(row?.date, "") === dayKey
    );
    return sumLatestClosingByType(dayRows, keySelector);
  };

  //For Date and Time
  useEffect(() => {
    const t = setInterval(() => setDateTime(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    const loadDashboardMetrics = async () => {
      const today = todayDateInputIST();
      const fromDate = toApiDateTimeFromDateInputIST(today, false);
      const toDate = toApiDateTimeFromDateInputIST(today, true);

      try {
        const [
          rmAllRes,
          feedTodayRes,
          dispatchTodayRes,
          productionTodayRes,
        ] = await Promise.all([
          stockApi.rm(),
          stockApi.feed({ date: today }),
          dispatchApi.list({ from_date: fromDate, to_date: toDate }),
          productionApi.listBatches({ date: today }),
        ]);

        const rmAllRows = Array.isArray(rmAllRes?.data) ? rmAllRes.data : [];
        const feedTodayRows = Array.isArray(feedTodayRes?.data) ? feedTodayRes.data : [];
        const dispatchTodayRows = Array.isArray(dispatchTodayRes?.data)
          ? dispatchTodayRes.data
          : [];
        const productionTodayRows = Array.isArray(productionTodayRes?.data)
          ? productionTodayRes.data
          : [];

        const rawMaterialStockKg = sumLatestClosingByType(
          rmAllRows,
          (row) => row?.rm_name
        );

        const finishedGoodsStockKg = sumLatestClosingByTypeForDay(
          feedTodayRows,
          feedStockKey,
          today
        );

        const currentDayDispatchKg = dispatchTodayRows
          .filter((row) => toDateInputIST(row?.date, "") === today)
          .reduce((sum, row) => {
            const directTotal = Number(row?.total_weight);
            if (Number.isFinite(directTotal)) return sum + directTotal;
            const products = Array.isArray(row?.products) ? row.products : [];
            const productTotal = products.reduce(
              (acc, p) => acc + (Number(p?.total_weight) || 0),
              0
            );
            return sum + productTotal;
          }, 0);

        const currentDayProductionKg = productionTodayRows
          .filter((row) => toDateInputIST(row?.date, "") === today)
          .reduce((sum, row) => sum + (Number(row?.output) || 0), 0);

        setTodayMetrics({
          rawMaterialStockKg,
          currentDayDispatchKg,
          currentDayProductionKg,
          finishedGoodsStockKg,
        });
      } catch {
        setTodayMetrics({
          rawMaterialStockKg: 0,
          currentDayDispatchKg: 0,
          currentDayProductionKg: 0,
          finishedGoodsStockKg: 0,
        });
      }
    };

    loadDashboardMetrics();
    const t = setInterval(loadDashboardMetrics, 30000);
    return () => clearInterval(t);
  }, []);

  //Update the PLC data and history every 5 seconds
  useEffect(() => {
    const resolveBatchWindow = (batch) => {
      const startedAt = batch?.started_at || batch?.date || batch?.created_at || null;
      const endedAt = batch?.completed_at || batch?.last_modified_at || batch?.date || startedAt;
      if (!parseApiDate(startedAt)) return null;
      return { startedAt, endedAt };
    };

    const loadBatchHistory = async ({ startedAt, endedAt = null }) => {
      const batchStartedAt = parseApiDate(startedAt);
      if (!batchStartedAt) return [];

      const parsedEndedAt = parseApiDate(endedAt) || new Date();
      const batchEndedAt =
        parsedEndedAt.getTime() >= batchStartedAt.getTime()
          ? parsedEndedAt
          : batchStartedAt;
      const elapsedMinutes = Math.max(
        1,
        Math.ceil((batchEndedAt.getTime() - batchStartedAt.getTime()) / 60000) + 2
      );
      const historyWindowMinutes = Math.max(60, elapsedMinutes);
      const historyRes = await plc.history(historyWindowMinutes);
      const historyRows = Array.isArray(historyRes?.data) ? historyRes.data : [];
      const startTs = batchStartedAt.getTime();
      const endTs = batchEndedAt.getTime();

      return historyRows.filter((row) => {
        const ts = parseApiDate(row?.recorded_at)?.getTime();
        return Number.isFinite(ts) && ts >= startTs && ts <= endTs;
      });
    };

    const refresh = async () => {
      try {
        const [latestRes, machineStatusRes] = await Promise.all([
          plc.latest(),
          plc.machineStatus(),
        ]);

        const latestData = latestRes?.data || null;
        const machineStatusData = machineStatusRes?.data || null;
        setPlcData(latestData);
        setMachineStatus(machineStatusData);

        const activeBatch = machineStatusData?.active_batch || null;
        const activeRunStatus = String(activeBatch?.run_status || "").toLowerCase();
        const batchStartedAt = parseApiDate(activeBatch?.started_at);
        const activeBatchId = activeBatch?.id ?? null;
        const isBatchRunning =
          Boolean(machineStatusData?.is_running) &&
          activeRunStatus === "running" &&
          Boolean(batchStartedAt);

        if (isBatchRunning && batchStartedAt) {
          const isNewBatch = displayedBatchIdRef.current !== activeBatchId;
          if (isNewBatch) {
            setPlcHistory([]);
            hasGraphHistoryRef.current = false;
          }

          const filteredBatchRows = await loadBatchHistory({
            startedAt: activeBatch?.started_at,
          });
          if (filteredBatchRows.length > 0) {
            setPlcHistory(filteredBatchRows);
            hasGraphHistoryRef.current = true;
          }
          displayedBatchIdRef.current = activeBatchId;
          return;
        }

        // Freeze the graph once a running batch stops; do not auto-switch
        // to older batches until a new batch starts or the page reloads.
        if (displayedBatchIdRef.current != null && hasGraphHistoryRef.current) {
          return;
        }

        const batchesRes = await productionApi.listBatches();
        const batches = Array.isArray(batchesRes?.data) ? batchesRes.data : [];
        const batchesWithWindow = batches
          .map((batch) => {
            const window = resolveBatchWindow(batch);
            if (!window) return null;
            const startedAtTs = parseApiDate(window.startedAt)?.getTime();
            if (!Number.isFinite(startedAtTs)) return null;
            const endedAtRawTs = parseApiDate(window.endedAt)?.getTime();
            const endedAtTs = Number.isFinite(endedAtRawTs)
              ? Math.max(startedAtTs, endedAtRawTs)
              : startedAtTs;
            return {
              batch,
              window,
              endedAtTs,
              status: String(batch?.run_status || "").toLowerCase(),
            };
          })
          .filter(Boolean)
          .sort((a, b) => b.endedAtTs - a.endedAtTs);
        const latestFinishedBatch =
          batchesWithWindow.find(
            (entry) => entry.status === "completed" || entry.status === "stopped"
          ) || batchesWithWindow[0] || null;

        if (!latestFinishedBatch) {
          return;
        }

        if (
          displayedBatchIdRef.current === (latestFinishedBatch.batch?.id ?? null) &&
          hasGraphHistoryRef.current
        ) {
          return;
        }

        const completedBatchRows = await loadBatchHistory({
          startedAt: latestFinishedBatch.window.startedAt,
          endedAt: latestFinishedBatch.window.endedAt,
        });
        if (completedBatchRows.length === 0) {
          return;
        }

        setPlcHistory(completedBatchRows);
        displayedBatchIdRef.current = latestFinishedBatch.batch?.id ?? null;
        hasGraphHistoryRef.current = true;
      } catch {
        // Keep latest visible graph data on transient API failures.
      }
    };
    refresh();
    const t = setInterval(refresh, 5000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    hasGraphHistoryRef.current = Array.isArray(plcHistory) && plcHistory.length > 0;
  }, [plcHistory]);

  //Graph Datta

  const graphData = plcHistory.map((d) => ({
    time: d.recorded_at ? formatTime24IST(d.recorded_at, "") : "",
    temp: d.ambient_temp ?? 0,
    humidity: d.humidity ?? 0,
    condTemp: d.conditioner_temp ?? 0,
    baggingTemp: d.bagging_temp ?? 0,
    feederSpeed: d.pellet_feeder_speed ?? 0,
    pelletMotorLoad: d.pellet_motor_load ?? 0,
    pressureBefore: d.pressure_before ?? 0,
    pressureAfter: d.pressure_after ?? 0,
  }));
  if (
    graphData.length === 0 &&
    plcData &&
    machineStatus?.is_running &&
    String(machineStatus?.active_batch?.run_status || "").toLowerCase() ===
      "running"
  ) {
    graphData.push({
      time: formatTime24IST(dateTime, ""),
      temp: plcData.ambient_temp ?? 0,
      humidity: plcData.humidity ?? 0,
      condTemp: plcData.conditioner_temp ?? 0,
      baggingTemp: plcData.bagging_temp ?? 0,
      feederSpeed: plcData.pellet_feeder_speed ?? 0,
      pelletMotorLoad: plcData.pellet_motor_load ?? 0,
      pressureBefore: plcData.pressure_before ?? 0,
      pressureAfter: plcData.pressure_after ?? 0,
    });
  }

  const tooltipStyle = {
    backgroundColor: "#fff",
    border: "1px solid #e2e8f0",
    borderRadius: "8px",
    boxShadow: "0 4px 6px -1px rgb(0 0 0 / 0.08)",
    padding: "10px 14px",
    fontSize: "12px",
  };
  const CustomTooltip = ({ active, payload, label, avgValues }) => {
    if (!active || !payload?.length) return null;

    return (
      <div style={tooltipStyle}>
        <p className="font-semibold mb-1">{label}</p>

        {/* live values */}
        {payload.map((entry, index) => (
          <p key={index} style={{ color: entry.color }}>
            {entry.name}: {entry.value.toFixed(2)}
          </p>
        ))}

        {/* average values */}
        <div className="mt-2 border-t pt-1 text-slate-600">
          {avgValues.map((avg, i) => (
            <p key={i}>
              Avg {avg.label}: <strong>{avg.value.toFixed(2)}</strong>
            </p>
          ))}
        </div>
      </div>
    );
  };
  // ---------- AVERAGE CALCULATION ----------
  const calculateAvg = (key) => {
    if (!graphData.length) return 0;
    return (
      graphData.reduce((sum, item) => sum + (item[key] || 0), 0) /
      graphData.length
    );
  };

  const avgTemp = calculateAvg("temp");
  const avgHumidity = calculateAvg("humidity");
  const avgCondTemp = calculateAvg("condTemp");
  const avgBaggingTemp = calculateAvg("baggingTemp");
  const avgFeederSpeed = calculateAvg("feederSpeed");
  const avgPelletMotorLoad = calculateAvg("pelletMotorLoad");
  const avgPressureBefore = calculateAvg("pressureBefore");
  const avgPressureAfter = calculateAvg("pressureAfter");
  const activeBatch = machineStatus?.active_batch || null;
  const activeRunStatus = (activeBatch?.run_status || "pending").toLowerCase();
  const activeMaterials = Array.isArray(activeBatch?.materials)
    ? activeBatch.materials
    : [];
  const activeBatchLabel = activeBatch
    ? `Batch #${activeBatch.batch_no || activeBatch.id}`
    : "N/A";
  const activeProgressLabel = activeBatch?.progress_label || "N/A";
  const isMachineRunning =
    typeof machineStatus?.is_running === "boolean"
      ? machineStatus.is_running
      : typeof plcData?.running_status === "boolean"
      ? plcData.running_status
      : String(plcData?.running_status || "").toLowerCase() === "running";
  const sensorDisplay = (value, unit = "") => {
    if (!isMachineRunning || value == null) {
      return "N/A";
    }
    return unit ? `${value} ${unit}` : String(value);
  };
  const hasGraphData = graphData.length > 0;
  const todayForDownload = todayDateInputIST();
  const todayRangeParams = {
    from_date: toApiDateTimeFromDateInputIST(todayForDownload, false),
    to_date: toApiDateTimeFromDateInputIST(todayForDownload, true),
  };

  const cards = [
    {
      title: "Raw Material Stock",
      value: formatMt(todayMetrics.rawMaterialStockKg),
      unit: "MT",
      color: "#1f4d3a",
      buttonTop: "#2e6b52",
      buttonBottom: "#163c2d",
      texture: "url('/textures/chalk.png')",
      icon: corn,
      download: () => stockApi.downloadRMIndividual("pdf"),
      fileName: "raw_material_available_stock.pdf",
    },
    {
      title: "Current Day Dispatch",
      value: formatMt(todayMetrics.currentDayDispatchKg),
      unit: "MT",
      color: "#D66816",
      buttonTop: "#e67d2a",
      buttonBottom: "#9f4a0d",
      texture: "url('/textures/chalk.png')",
      icon: truck,
      download: () => stockApi.downloadDispatch("pdf", todayRangeParams),
      fileName: "dispatch_current_day.pdf",
    },
    {
      title: "Current Day Production",
      value: formatMt(todayMetrics.currentDayProductionKg),
      unit: "MT",
      color: "#265B87",
      buttonTop: "#3e79a8",
      buttonBottom: "#1c4463",
      texture: "url('/textures/chalk.png')",
      icon: raw,
      download: () => stockApi.downloadProduction("pdf", todayRangeParams),
      fileName: "production_current_day.pdf",
    },
    {
      title: "Finished Goods Stock",
      value: formatMt(todayMetrics.finishedGoodsStockKg),
      unit: "MT",
      color: "#BC2B1C",
      buttonTop: "#d74636",
      buttonBottom: "#7e1a12",
      texture: "url('/textures/chalk.png')",
      icon: largegoods,
      download: () => stockApi.downloadFeed("pdf", todayRangeParams),
      fileName: "finished_goods_current_day.pdf",
    },
  ];

  return (
    <div className="space-y-6 ">
      {/* Page title ,Machine Running Status */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 ">
        <div className="flex flex-col items-center gap-4 sm:gap-0 sm:flex-row justify-between sm:items-center w-full">
          <div className="flex items-center justify-between gap-10 sm:block">
            <h1 className="text-2xl font-bold text-slate-800 tracking-tight">
              Dashboard
            </h1>
            <p className="text-slate-500 md:text-sm mt-1 font-medium tabular-nums text-xs ">
              {formatDateIST(dateTime)} - {formatTimeIST(dateTime)}
            </p>
          </div>
          <div className="flex items-center gap-16 justify-center md:mt-0 sm:gap-3">
            <h2 className="text-xs sm:text-sm font-semibold text-slate-600 uppercase tracking-widest">
              Machine Status :
            </h2>
            <span
              className={`inline-flex items-center gap-1.5 md:gap-2 px-2.5 py-1 md:px-4 md:py-1.5 text-xs md:text-sm rounded-md font-semibold border transition-all duration-300 ${
                isMachineRunning
                  ? "bg-emerald-100 text-emerald-800 border-emerald-300 shadow-inner"
                  : "bg-red-100 text-red-800 border-red-300 shadow-inner"
              }`}
            >
              <span
                className={`w-2 h-2 md:w-2.5 md:h-2.5 rounded-full ${
                  isMachineRunning
                    ? "bg-emerald-600 animate-pulse shadow-[0_0_6px_rgba(16,185,129,0.7)]"
                    : "bg-red-600 shadow-[0_0_6px_rgba(239,68,68,0.7)]"
                }`}
              />
              {isMachineRunning ? "RUNNING" : "STOPPED"}
            </span>
          </div>
        </div>
        {/* <div className="flex flex-wrap gap-3 text-sm text-slate-600 bg-white px-4 py-2 rounded-lg border border-slate-200 shadow-card">
          <span className="font-medium">{user?.company_name || 'Poultry Farm'}</span>
          <span className="text-slate-300">|</span>
          <span>{user?.address || 'N/A'}</span>
        </div> */}
      </div>

      {/* KPI row: Status, Product, Sensors */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">

        <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-card">
          <div className="flex items-center justify-between gap-3 mb-3">
            <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wider">
              Product & Batch
            </h2>
            <div className="text-right flex justify-center  align-center items-center gap-2">
              <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                Batch Count:
              </p>
              <p className="mt-1 inline-flex items-center rounded-md px-2.5 py-1 text-sm font-bold bg-slate-100 text-slate-800">
                {activeProgressLabel}
              </p>
            </div>
          </div>

          <div className="rounded-xl border border-slate-200 bg-gradient-to-br from-slate-50 to-white p-4">
            
                 <div className="flex items-center justify-between  md:gap-3">
              <div>
                <p className="text-xs text-slate-500">Current Running Batch</p>
                <p className="text-xl md:text-3xl font-extrabold text-[#245658] tracking-wide leading-none mt-1 mb-1">
                  {activeBatchLabel}
                </p>
              </div>
            <span
  className={`px-2 py-1 md:px-2.5 md:py-1.5 
  text-[10px] sm:text-xs md:text-sm 
  rounded-md font-semibold 
  whitespace-nowrap
  ${
    activeRunStatus === "running"
      ? "bg-green-100 text-green-700"
      : activeRunStatus === "completed"
      ? "bg-blue-100 text-blue-700"
      : activeRunStatus === "stopped"
      ? "bg-red-100 text-red-700"
      : "bg-slate-100 text-slate-700"
  }`}
>
  {activeRunStatus.toUpperCase()}
</span>
            </div>
            <p className="text-xs text-slate-500">Running Product</p>
            <p className="mt-1 text-xl md:text-2xl font-semibold text-[#245658] tracking-wide leading-normal">
              {activeBatch?.product_name || "N/A"}
            </p>

       
          </div>

          <div className="mt-4">
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
              Active Recipe
            </p>
            {activeMaterials.length === 0 ? (
              <div className="rounded-lg border custom-dashed-border border-dashed border-slate-300 px-3 py-3 text-sm text-slate-500">
                No active recipe materials.
              </div>
            ) : (
              <div className="rounded-lg custom-dashed-border border-slate-300 divide-y divide-slate-100">
                {activeMaterials.map((item, idx) => (
                  <div
                    key={`${item.rm_name}-${idx}`}
                    className="flex items-center justify-between px-3 py-2 text-sm"
                  >
                    <span className="font-medium text-slate-700">{item.rm_name}</span>
                    <span className="rounded-md bg-slate-100 px-2 py-0.5 font-semibold text-slate-800">
                      {item.quantity} kg
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        
        <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-card w-full">
          <div className="flex items-center  gap-2 mb-4">
            <img src={live} alt="live" className="w-6 h-6" />
            <h2 className="text-sm font-semibold text-slate-900 uppercase tracking-wider ">
              Live Sensors
            </h2>
          </div>

          {/* Sensor Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-4 lg:grid-cols-2  gap-4 text-sm">
            {/* Ambient */}
            <div className="flex items-center justify-between bg-slate-50 px-4 py-3 rounded-lg border border-slate-400">
              <div className="flex items-center gap-2 text-slate-900">
                <Thermometer size={18} />
                <span>Ambient</span>
              </div>
              <span className="font-semibold text-slate-800 tabular-nums">
                {sensorDisplay(plcData?.ambient_temp, "C")}
              </span>
            </div>

            {/* Humidity */}
            <div className="flex items-center justify-between bg-slate-50 px-4 py-3 rounded-lg border border-slate-400">
              <div className="flex items-center gap-2 text-slate-900">
                <Droplets size={18} />
                <span>Humidity</span>
              </div>
              <span className="font-semibold text-slate-800 tabular-nums">
                {sensorDisplay(plcData?.humidity, "%")}
              </span>
            </div>

            {/* Pressure Before */}
            <div className="flex items-center justify-between bg-slate-50 px-4 py-3 rounded-lg border border-slate-400">
              <div className="flex items-center gap-2 text-slate-900">
                <Gauge size={18} />
                <span>P Before</span>
              </div>
              <span className="font-semibold text-slate-800 tabular-nums">
                {sensorDisplay(plcData?.pressure_before, "bar")}
              </span>
            </div>

            {/* Pressure After */}
            <div className="flex items-center justify-between bg-slate-50 px-4 py-3 rounded-lg border border-slate-400">
              <div className="flex items-center gap-2 text-slate-900">
                <Gauge size={18} />
                <span>P After</span>
              </div>
              <span className="font-semibold text-slate-800 tabular-nums">
                {sensorDisplay(plcData?.pressure_after, "bar")}
              </span>
            </div>
            {/* FFEEDER SPEED */}
            <div className="flex items-center justify-between bg-slate-50 px-4 py-3 rounded-lg border border-slate-400">
              <div className="flex items-center gap-2 text-slate-900">
                <Activity size={18} />
                <span>Feeder Speed</span>
              </div>
              <span className="font-semibold text-slate-800 tabular-nums">
                {sensorDisplay(plcData?.pellet_feeder_speed, "rpm")}
              </span>
            </div>
            {/* Conditioner */}
            <div className="flex items-center justify-between bg-slate-50 px-4 py-3 rounded-lg border border-slate-400">
              <div className="flex items-center gap-2 text-slate-900">
                <Wind size={18} />
                <span>Conditioner</span>
              </div>
              <span className="font-semibold text-slate-800 tabular-nums">
                {sensorDisplay(plcData?.conditioner_temp, "C")}
              </span>
            </div>
            {/* Bagging Temperature */}
            <div className="flex items-center justify-between bg-slate-50 px-4 py-3 rounded-lg border border-slate-400">
              <div className="flex items-center gap-2 text-slate-900">
                <Thermometer size={18} />
                <span>Bagging Temp</span>
              </div>
              <span className="font-semibold text-slate-800 tabular-nums">
                {sensorDisplay(plcData?.bagging_temp, "C")}
              </span>
            </div>

            {/* Pellet Motor Load */}
            <div className="flex items-center justify-between bg-slate-50 px-4 py-3 rounded-lg border border-slate-400">
              <div className="flex items-center gap-2 text-slate-900">
                <Activity size={18} />
                <span>Pellet Motor Load</span>
              </div>
              <span className="font-semibold text-slate-800 tabular-nums">
                {sensorDisplay(plcData?.pellet_motor_load, "A")}
              </span>
            </div>
          </div>
        </div>
      </div>
      {/* Main Four Box calculate last 20 days  */}

      <div className="grid gap-6 xl:grid-cols-4 md:grid-cols-2">
        {cards.map((card, i) => {
          // const Icon = card.icon;
          return (
            <div
              key={i}
              className="relative rounded-lg shadow-[0_6px_12px_rgba(0,0,0,0.35)]
                       border border-slate-300 overflow-hidden
                       bg-white"
            >
              {/* TOP TEXTURED HEADER */}

              <div
                className="p-4 text-white relative"
                style={{
                  backgroundColor: card.color,
                  backgroundImage: card.texture,
                  backgroundBlendMode: "overlay",
                }}
              >
                {/* inner glow */}
                <div className="absolute inset-0 bg-gradient-to-b from-white/10 to-black/15 pointer-events-none"></div>
                <div className="relative flex items-center justify-center gap-2">
                  <span className="font-semibold tracking-wide text-[1.3rem] ">
                    {card.title}
                  </span>
                </div>

                <div className="relative text-center mt-3 text-3xl font-extrabold tracking-wide">
                  {card.value}
                  <span className="text-base ml-2 font-semibold opacity-90">
                    {card.unit}
                  </span>
                </div>
              </div>

              <img
                src={card.icon}
                alt="image"
                className="absolute right-1 top-[55%] translate-y-[-50%]
                 w-24 sm:w-28 md:w-32 lg:w-[6.5rem]
                 drop-shadow-[0_10px_10px_rgba(0,0,0,0.45)]
                 pointer-events-none select-none"
              />

              {/* FOOTER */}
              <div className="bg-[#E4E8EB] p-5  flex  justify-center">
                <button
                  className="relative mt-4 px-9 py-2 rounded-md text-sm font-semibold text-white
             border border-black/20 overflow-hidden
             active:translate-y-[1px]"
                  onClick={async () => {
                    try {
                      const { data } = await card.download();
                      const url = URL.createObjectURL(new Blob([data]));
                      const a = document.createElement("a");
                      a.href = url;
                      a.download = card.fileName;
                      a.click();
                      URL.revokeObjectURL(url);
                    } catch (err) {
                      console.error("Download failed", err);
                    }
                  }}
                  style={{
                    backgroundImage: `
      linear-gradient(to bottom, ${card.buttonTop}, ${card.buttonBottom}),
      ${card.texture}
    `,
                    backgroundBlendMode: "overlay",
                    boxShadow: `
      inset 0 2px 3px rgba(255,255,255,0.35),
      inset 0 -4px 6px rgba(0,0,0,0.45),
      0 3px 5px rgba(0,0,0,0.35)
    `,
                  }}
                >
                  {/* glossy shine */}
                  <span className="absolute inset-0 bg-gradient-to-b from-white/25 to-transparent pointer-events-none"></span>

                  <span className="relative tracking-wide">
                    Download Report
                  </span>
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {/* Quick actions & stock */}
      <div className="w-full">
        <h2 className="text-sm font-semibold text-slate-700 uppercase tracking-wider mb-4">
          Quick Access & Stock
        </h2>

        {/* responsive grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {/* Raw Material */}
          <Link
            to="raw-material"
            className="group rounded-xl overflow-hidden border border-slate-200 bg-white shadow-card hover:shadow-card-hover transition-all active:scale-[0.98]"
          >
            {/* Industrial header band with texture */}
            <div
              className="h-7 bg-emerald-800 bg-repeat opacity-95"
              style={{
                backgroundImage: "url('/textures/chalk.png')",
                backgroundBlendMode: "overlay",
              }}
            />

            <div className="p-4 sm:p-5 flex items-center justify-between">
              <div>
                <h3 className="font-semibold text-slate-800 group-hover:text-emerald-700 text-sm sm:text-base">
                  Raw Material Entry
                </h3>
                <p className="text-slate-500 text-xs sm:text-sm mt-1">
                  Add RM inward
                </p>
              </div>

              <div className="bg-emerald-50 p-2 sm:p-3 rounded-lg">
                <Boxes
                  size={20}
                  className="text-emerald-700 sm:w-[22px] sm:h-[22px]"
                />
              </div>
            </div>
          </Link>

          {/* Dispatch */}
          <Link
            to="dispatch"
            className="group rounded-xl overflow-hidden border border-slate-200 bg-white shadow-card hover:shadow-card-hover transition-all active:scale-[0.98]"
          >
            <div
              className="h-7 bg-sky-800 bg-repeat opacity-95"
              style={{
                backgroundImage: "url('/textures/chalk.png')",
                backgroundBlendMode: "overlay",
              }}
            />

            <div className="p-4 sm:p-5 flex items-center justify-between">
              <div>
                <h3 className="font-semibold text-slate-800 group-hover:text-sky-700 text-sm sm:text-base">
                  Dispatch Entry
                </h3>
                <p className="text-slate-500 text-xs sm:text-sm mt-1">
                  Outgoing finished goods
                </p>
              </div>

              <div className="bg-sky-50 p-2 sm:p-3 rounded-lg">
                <Truck
                  size={20}
                  className="text-sky-700 sm:w-[22px] sm:h-[22px]"
                />
              </div>
            </div>
          </Link>

          {/* Production */}
          <Link
            to="production"
            className="group rounded-xl overflow-hidden border border-slate-200 bg-white shadow-card hover:shadow-card-hover transition-all active:scale-[0.98]"
          >
            <div
              className="h-7 bg-amber-700 bg-repeat opacity-95"
              style={{
                backgroundImage: "url('/textures/chalk.png')",
                backgroundBlendMode: "overlay",
              }}
            />

            <div className="p-4 sm:p-5 flex items-center justify-between">
              <div>
                <h3 className="font-semibold text-slate-800 group-hover:text-amber-700 text-sm sm:text-base">
                  Production Entry
                </h3>
                <p className="text-slate-500 text-xs sm:text-sm mt-1">
                  Batches & reports
                </p>
              </div>

              <div className="bg-amber-50 p-2 sm:p-3 rounded-lg">
                <Factory
                  size={20}
                  className="text-amber-700 sm:w-[22px] sm:h-[22px]"
                />
              </div>
            </div>
          </Link>
        </div>
      </div>

      {/* Charts */}
      {/* <h2 className="text-sm font-semibold text-slate-700 uppercase tracking-wider mb-4">
    Graph Analysis
      </h2> */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6 ">
        <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-card">
          <div className="mb-4 flex items-start justify-between gap-3">
            <h3 className="text-sm font-semibold text-slate-700">
              Temp & Humidity
            </h3>
            <p className="text-[11px] text-right leading-4">
              <span style={{ color: chartColors.temp }}>
                Avg T: {hasGraphData ? avgTemp.toFixed(2) : "N/A"}
              </span>{" "}
              <span className="text-slate-400">|</span>{" "}
              <span style={{ color: chartColors.humidity }}>
                Avg H: {hasGraphData ? avgHumidity.toFixed(2) : "N/A"}
              </span>
            </p>
          </div>
          {/* <div className="h-52"> */}
          <div className="h-60 sm:h-64 md:h-72">
            {hasGraphData ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={graphData}>
                  <defs>
                    <linearGradient id="tempGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop
                        offset="0%"
                        stopColor={chartColors.temp}
                        stopOpacity={0.3}
                      />
                      <stop
                        offset="100%"
                        stopColor={chartColors.temp}
                        stopOpacity={0}
                      />
                    </linearGradient>
                    <linearGradient id="humGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop
                        offset="0%"
                        stopColor={chartColors.humidity}
                        stopOpacity={0.3}
                      />
                      <stop
                        offset="100%"
                        stopColor={chartColors.humidity}
                        stopOpacity={0}
                      />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis
                    dataKey="time"
                    stroke="#64748b"
                    fontSize={11}
                    tick={{ fill: "#64748b" }}
                  />
                  <YAxis
                    domain={[0, 100]}
                    ticks={fixedTicks(100)}
                    interval={0}
                    stroke="#64748b"
                    width={30}
                    fontSize={11}
                    tick={{ fill: "#64748b" }}
                  />

                  <Tooltip
                    content={
                      <CustomTooltip
                        avgValues={[
                          { label: "Temp", value: avgTemp },
                          { label: "Humidity", value: avgHumidity },
                        ]}
                      />
                    }
                  />
                  <Legend wrapperStyle={{ fontSize: "12px" }} />
                  <Area
                    type="monotone"
                    dataKey="temp"
                    stroke={chartColors.temp}
                    fill="url(#tempGrad)"
                    name="Temp C"
                    strokeWidth={2}
                  />
                  <Area
                    type="monotone"
                    dataKey="humidity"
                    stroke={chartColors.humidity}
                    fill="url(#humGrad)"
                    name="Humidity %"
                    strokeWidth={2}
                  />
                  <ReferenceLine
                    y={avgTemp}
                    stroke="#ff0000"
                    strokeDasharray="6 4"
                    strokeWidth={2}
                    label={{
                      value: `Avg Temp: ${avgTemp.toFixed(1)}`,
                      position: "right",
                      fill: "#ff0000",
                      fontSize: 10,
                    }}
                  />

                  <ReferenceLine
                    y={avgHumidity}
                    stroke="#0891b2"
                    strokeDasharray="6 4"
                    strokeWidth={2}
                    label={{
                      value: `Avg Hum: ${avgHumidity.toFixed(1)}`,
                      position: "right",
                      fill: "#0891b2",
                      fontSize: 10,
                    }}
                  />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center rounded-lg border border-dashed border-slate-300 bg-slate-50 text-xs text-slate-600 px-4 text-center">
                
              </div>
            )}
          </div>
        </div>
        <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-card">
          <div className="mb-4 flex items-start justify-between gap-3">
            <h3 className="text-sm font-semibold text-slate-700">
              Conditioner & Bagging Temp
            </h3>
            <p className="text-[11px] text-right leading-4">
              <span style={{ color: chartColors.condTemp }}>
                Avg C: {hasGraphData ? avgCondTemp.toFixed(2) : "N/A"}
              </span>{" "}
              <span className="text-slate-400">|</span>{" "}
              <span style={{ color: chartColors.baggingTemp }}>
                Avg B: {hasGraphData ? avgBaggingTemp.toFixed(2) : "N/A"}
              </span>
            </p>
          </div>
          {/* <div className="h-52"> */}
          <div className="h-60 sm:h-64 md:h-72">
            {hasGraphData ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={graphData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis
                    dataKey="time"
                    stroke="#64748b"
                    fontSize={11}
                    tick={{ fill: "#64748b" }}
                  />
                  <YAxis
                    domain={[0, 250]}
                    ticks={fixedTicks(250)}
                    interval={0}
                    stroke="#64748b"
                    width={30}
                    fontSize={11}
                    tick={{ fill: "#64748b" }}
                  />

                  <Tooltip
                    content={
                      <CustomTooltip
                        avgValues={[
                          { label: "Cond", value: avgCondTemp },
                          { label: "Bagging", value: avgBaggingTemp },
                        ]}
                      />
                    }
                  />
                  <Legend wrapperStyle={{ fontSize: "12px" }} />
                  <Area
                    type="monotone"
                    dataKey="condTemp"
                    stroke={chartColors.condTemp}
                    fill="url(#condGrad)"
                    strokeWidth={2}
                  />
                  <Area
                    type="monotone"
                    dataKey="baggingTemp"
                    stroke={chartColors.baggingTemp}
                    fill="url(#bagGrad)"
                    strokeWidth={2}
                  />
                  <defs>
                    <linearGradient id="condGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop
                        offset="0%"
                        stopColor={chartColors.condTemp}
                        stopOpacity={0.3}
                      />
                      <stop
                        offset="100%"
                        stopColor={chartColors.condTemp}
                        stopOpacity={0}
                      />
                    </linearGradient>

                    <linearGradient id="bagGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop
                        offset="0%"
                        stopColor={chartColors.baggingTemp}
                        stopOpacity={0.3}
                      />
                      <stop
                        offset="100%"
                        stopColor={chartColors.baggingTemp}
                        stopOpacity={0}
                      />
                    </linearGradient>
                  </defs>
                  <ReferenceLine
                    y={avgCondTemp}
                    stroke="#16a34a"
                    strokeDasharray="6 4"
                    strokeWidth={2}
                    label={{
                      value: `Avg Cond: ${avgCondTemp.toFixed(1)}`,
                      position: "right",
                      fill: "#16a34a",
                      fontSize: 10,
                    }}
                  />

                  <ReferenceLine
                    y={avgBaggingTemp}
                    stroke="#f97316"
                    strokeDasharray="6 4"
                    strokeWidth={2}
                    label={{
                      value: `Avg Bag: ${avgBaggingTemp.toFixed(1)}`,
                      position: "right",
                      fill: "#f97316",
                      fontSize: 10,
                    }}
                  />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center rounded-lg border border-dashed border-slate-300 bg-slate-50 text-xs text-slate-600 px-4 text-center">
                
              </div>
            )}
          </div>
        </div>
        <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-card">
          <div className="mb-4 flex items-start justify-between gap-3">
            <h3 className="text-sm font-semibold text-slate-700">
              Pellet Feeder Speed & Load
            </h3>
            <p className="text-[11px] text-right leading-4">
              <span style={{ color: chartColors.feederSpeed }}>
                Avg RPM: {hasGraphData ? avgFeederSpeed.toFixed(2) : "N/A"}
              </span>{" "}
              <span className="text-slate-400">|</span>{" "}
              <span style={{ color: chartColors.feederLoad }}>
                Avg Amp:{" "}
                {hasGraphData ? avgPelletMotorLoad.toFixed(2) : "N/A"}
              </span>
            </p>
          </div>
          {/* <div className="h-52"> */}
          <div className="h-60 sm:h-64 md:h-72">
            {hasGraphData ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={graphData}>
                  <defs>
                    <linearGradient id="speedGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop
                        offset="0%"
                        stopColor={chartColors.feederSpeed}
                        stopOpacity={0.35}
                      />
                      <stop
                        offset="100%"
                        stopColor={chartColors.feederSpeed}
                        stopOpacity={0}
                      />
                    </linearGradient>
                    <linearGradient id="loadGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop
                        offset="0%"
                        stopColor={chartColors.feederLoad}
                        stopOpacity={0.35}
                      />
                      <stop
                        offset="100%"
                        stopColor={chartColors.feederLoad}
                        stopOpacity={0}
                      />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis
                    dataKey="time"
                    stroke="#64748b"
                    fontSize={11}
                    tick={{ fill: "#64748b" }}
                  />
                  <YAxis
                    yAxisId="left"
                    domain={[0, 1500]}
                    ticks={fixedTicks(1500)}
                    interval={0}
                    width={36}
                    stroke="#64748b"
                    fontSize={11}
                    tick={{ fill: "#64748b" }}
                  />
                  <YAxis
                    yAxisId="right"
                    orientation="right"
                    domain={[0, 300]}
                    ticks={fixedTicks(300)}
                    interval={0}
                    width={36}
                    stroke="#64748b"
                    fontSize={11}
                    tick={{ fill: "#64748b" }}
                  />

                  <Tooltip
                    content={
                      <CustomTooltip
                        avgValues={[
                          { label: "Speed (RPM)", value: avgFeederSpeed },
                          { label: "Load (Amp)", value: avgPelletMotorLoad },
                        ]}
                      />
                    }
                  />
                  <Legend wrapperStyle={{ fontSize: "12px" }} />
                  <Area
                    type="monotone"
                    dataKey="feederSpeed"
                    yAxisId="left"
                    stroke={chartColors.feederSpeed}
                    fill="url(#speedGrad)"
                    name="Pellet Feeder Speed (RPM)"
                    strokeWidth={2}
                  />
                  <Area
                    type="monotone"
                    dataKey="pelletMotorLoad"
                    yAxisId="right"
                    stroke={chartColors.feederLoad}
                    fill="url(#loadGrad)"
                    name="Pellet Feeder Load (Amp)"
                    strokeWidth={2}
                  />
                  <ReferenceLine
                    yAxisId="left"
                    y={avgFeederSpeed}
                    stroke="#9333ea"
                    strokeDasharray="6 4"
                    strokeWidth={2}
                    label={{
                      value: `Avg RPM: ${avgFeederSpeed.toFixed(1)}`,
                      position: "right",
                      fill: "#9333ea",
                      fontSize: 10,
                    }}
                  />
                  <ReferenceLine
                    yAxisId="right"
                    y={avgPelletMotorLoad}
                    stroke="#0f766e"
                    strokeDasharray="6 4"
                    strokeWidth={2}
                    label={{
                      value: `Avg Amp: ${avgPelletMotorLoad.toFixed(1)}`,
                      position: "insideTopRight",
                      fill: "#0f766e",
                      fontSize: 10,
                    }}
                  />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center rounded-lg border border-dashed border-slate-300 bg-slate-50 text-xs text-slate-600 px-4 text-center">
                
              </div>
            )}
          </div>
        </div>
        <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-card">
          <div className="mb-4 flex items-start justify-between gap-3">
            <h3 className="text-sm font-semibold text-slate-700">
              Pressure Before & After
            </h3>
            <p className="text-[11px] text-right leading-4">
              <span style={{ color: chartColors.pressureBefore }}>
                Avg P1: {hasGraphData ? avgPressureBefore.toFixed(2) : "N/A"}
              </span>{" "}
              <span className="text-slate-400">|</span>{" "}
              <span style={{ color: chartColors.pressureAfter }}>
                Avg P2: {hasGraphData ? avgPressureAfter.toFixed(2) : "N/A"}
              </span>
            </p>
          </div>
          {/* <div className="h-52"> */}
          <div className="h-60 sm:h-64 md:h-72">
            {hasGraphData ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={graphData}>
                  <defs>
                    <linearGradient id="beforeGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop
                        offset="0%"
                        stopColor={chartColors.pressureBefore}
                        stopOpacity={0.2}
                      />
                      <stop
                        offset="100%"
                        stopColor={chartColors.pressureBefore}
                        stopOpacity={0}
                      />
                    </linearGradient>

                    <linearGradient id="afterGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop
                        offset="0%"
                        stopColor={chartColors.pressureAfter}
                        stopOpacity={0.2}
                      />
                      <stop
                        offset="100%"
                        stopColor={chartColors.pressureAfter}
                        stopOpacity={0}
                      />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis
                    dataKey="time"
                    stroke="#64748b"
                    fontSize={11}
                    tick={{ fill: "#64748b" }}
                  />
                  <YAxis
                    domain={[0, 20]}
                    ticks={fixedTicks(20)}
                    interval={0}
                    width={30}
                    stroke="#64748b"
                    fontSize={11}
                    tick={{ fill: "#64748b" }}
                  />

                  <Tooltip
                    content={
                      <CustomTooltip
                        avgValues={[
                          { label: "Before", value: avgPressureBefore },
                          { label: "After", value: avgPressureAfter },
                        ]}
                      />
                    }
                  />
                  <Legend wrapperStyle={{ fontSize: "12px" }} />
                  <Area
                    type="monotone"
                    dataKey="pressureBefore"
                    stroke={chartColors.pressureBefore}
                    fill="url(#beforeGrad)"
                    strokeWidth={2}
                  />

                  <Area
                    type="monotone"
                    dataKey="pressureAfter"
                    stroke={chartColors.pressureAfter}
                    fill="url(#afterGrad)"
                    strokeWidth={2}
                  />
                  <ReferenceLine
                    y={avgPressureBefore}
                    stroke="#0d9488"
                    strokeDasharray="6 4"
                    strokeWidth={2}
                    label={{
                      value: `Avg Before: ${avgPressureBefore.toFixed(2)}`,
                      position: "right",
                      fill: "#0d9488",
                      fontSize: 10,
                    }}
                  />

                  <ReferenceLine
                    y={avgPressureAfter}
                    stroke="#ca8a04"
                    strokeDasharray="6 4"
                    strokeWidth={2}
                    label={{
                      value: `Avg After: ${avgPressureAfter.toFixed(2)}`,
                      position: "right",
                      fill: "#ca8a04",
                      fontSize: 10,
                    }}
                  />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center rounded-lg border border-dashed border-slate-300 bg-slate-50 text-xs text-slate-600 px-4 text-center">
                
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
