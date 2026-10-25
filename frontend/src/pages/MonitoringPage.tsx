import React, { useState, useEffect } from 'react';
import {
  Activity,
  AlertTriangle,
  Shield,
  ShieldAlert,
  HardDrive,
  Cpu,
  Network,
  CheckCircle2,
  X,
  ExternalLink,
  Info,
  Clock,
  Radio,
  RefreshCw,
  Server,
  Zap,
  Play,
  Square,
  RotateCcw,
  Sliders,
  Layers,
  Terminal,
  ArrowUpRight,
  ArrowDownRight,
  Check,
} from 'lucide-react';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  CartesianGrid,
  ReferenceLine,
} from 'recharts';
import {
  AlertItem,
  LocalHostMetric,
  LocalHostReadingPoint,
  AutoscalingStatus,
  DockerWorkloadMetric,
  StorageTelemetryData,
} from '../types';
import {
  fetchLocalMonitoring,
  fetchAutoscalingStatus,
  triggerManualScale,
  triggerK6LoadTest,
  stopAutoscalingStack,
  startAutoscalingStack,
  fetchDockerWorkloadTelemetry,
  fetchStorageTelemetry,
} from '../services/api';
import { generate30DayTelemetry } from '../services/mockData';
import { getSeverityBadgeClass } from '../utils/formatters';

interface MonitoringPageProps {
  alerts: AlertItem[];
  onDismissAlert: (id: string) => void;
  onSelectResourceById: (resourceId: string) => void;
}

export const MonitoringPage: React.FC<MonitoringPageProps> = ({
  alerts,
  onDismissAlert,
  onSelectResourceById,
}) => {
  // Page Tab state: "telemetry" (Stage 4 & Stage 1-3) vs "autoscaling" (Stage 5)
  const [activeTab, setActiveTab] = useState<'telemetry' | 'autoscaling'>('autoscaling');

  // Stage 4: Live Local Host System Telemetry State
  const [latestMetric, setLatestMetric] = useState<LocalHostMetric | null>(null);
  const [recentReadings, setRecentReadings] = useState<LocalHostReadingPoint[]>([]);
  const [isLoadingHost, setIsLoadingHost] = useState(true);
  const [hostError, setHostError] = useState<string | null>(null);
  const [lastUpdatedTime, setLastUpdatedTime] = useState<string>('');

  // Live Docker Workload (cgroups) & Storage Telemetry State
  const [dockerWorkload, setDockerWorkload] = useState<DockerWorkloadMetric | null>(null);
  const [storageTelemetry, setStorageTelemetry] = useState<StorageTelemetryData | null>(null);

  // Stage 5: Live Autoscaling Lab State
  const [autoscalingStatus, setAutoscalingStatus] = useState<AutoscalingStatus | null>(null);
  const [isLoadingAutoscaler, setIsLoadingAutoscaler] = useState(false);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [actionType, setActionType] = useState<'success' | 'error' | 'info'>('info');

  // Fleet simulated telemetry
  const [fleetTelemetry] = useState(() => generate30DayTelemetry());

  // Polling loop for Host Monitoring (Stage 4)
  useEffect(() => {
    let isMounted = true;
    let pollTimer: any = null;

    const pollMetrics = async (isInitial = false) => {
      try {
        if (isInitial) setIsLoadingHost(true);
        const data = await fetchLocalMonitoring(0.5);
        if (!isMounted) return;

        setLatestMetric(data);
        setHostError(null);

        const dateObj = new Date(data.timestamp);
        const timeStr = dateObj.toLocaleTimeString([], {
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
        });
        setLastUpdatedTime(timeStr);

        const newPoint: LocalHostReadingPoint = {
          time: timeStr,
          timestamp: data.timestamp,
          cpu_percent: data.cpu_utilization,
          ram_percent: data.ram_utilization,
          used_ram_gb: data.used_ram_gb,
          total_ram_gb: data.total_ram_gb,
        };

        setRecentReadings((prev) => {
          const next = [...prev, newPoint];
          return next.length > 20 ? next.slice(next.length - 20) : next;
        });
      } catch (err: any) {
        if (!isMounted) return;
        setHostError(err?.message || 'Failed to poll live host metrics');
      } finally {
        if (isMounted && isInitial) setIsLoadingHost(false);
      }
    };

    pollMetrics(true);
    pollTimer = setInterval(() => {
      pollMetrics(false);
    }, 3000);

    return () => {
      isMounted = false;
      if (pollTimer) clearInterval(pollTimer);
    };
  }, []);

  // Polling loop for Autoscaler State (Stage 5)
  useEffect(() => {
    let isMounted = true;
    let autoscalerTimer: any = null;

    const pollAutoscaler = async () => {
      try {
        const data = await fetchAutoscalingStatus();
        if (isMounted) {
          setAutoscalingStatus(data);
        }
      } catch (err) {
        console.warn('Autoscaler poll error:', err);
      }
    };

    pollAutoscaler();
    autoscalerTimer = setInterval(pollAutoscaler, 3000);

    return () => {
      isMounted = false;
      if (autoscalerTimer) clearInterval(autoscalerTimer);
    };
  }, []);

  // Polling loop for Isolated Docker Workload & Host Storage Telemetry
  useEffect(() => {
    let isMounted = true;
    let workloadTimer: any = null;

    const pollWorkloadAndStorage = async () => {
      try {
        const [wData, sData] = await Promise.all([
          fetchDockerWorkloadTelemetry().catch(() => null),
          fetchStorageTelemetry().catch(() => null),
        ]);
        if (!isMounted) return;
        if (wData) setDockerWorkload(wData);
        if (sData) setStorageTelemetry(sData);
      } catch (err) {
        console.warn('Docker workload / storage poll error:', err);
      }
    };

    pollWorkloadAndStorage();
    workloadTimer = setInterval(pollWorkloadAndStorage, 3000);

    return () => {
      isMounted = false;
      if (workloadTimer) clearInterval(workloadTimer);
    };
  }, []);

  // Autoscaling Action Handlers
  const handleTriggerLoadTest = async () => {
    try {
      setIsLoadingAutoscaler(true);
      setActionMessage('Launching k6 load test surge (20 VUs for 20s)...');
      setActionType('info');
      await triggerK6LoadTest(20, '20s');
      setActionMessage('k6 load test surge active! Generating container CPU load to demonstrate scale-out.');
      setActionType('success');
      const updated = await fetchAutoscalingStatus();
      setAutoscalingStatus(updated);
    } catch (err: any) {
      setActionMessage(`Load test launch error: ${err?.response?.data?.detail || err.message}`);
      setActionType('error');
    } finally {
      setIsLoadingAutoscaler(false);
    }
  };

  const handleResetReplicas = async (replicas = 1) => {
    try {
      setIsLoadingAutoscaler(true);
      await triggerManualScale(replicas);
      setActionMessage(`Workload replicas set to ${replicas}.`);
      setActionType('success');
      const updated = await fetchAutoscalingStatus();
      setAutoscalingStatus(updated);
    } catch (err: any) {
      setActionMessage(`Scale error: ${err.message}`);
      setActionType('error');
    } finally {
      setIsLoadingAutoscaler(false);
    }
  };

  const handleStopStack = async () => {
    try {
      setIsLoadingAutoscaler(true);
      setActionMessage('Stopping and cleaning up Docker Compose stack...');
      setActionType('info');
      await stopAutoscalingStack();
      setActionMessage('Docker Compose containers safely stopped and cleaned up.');
      setActionType('success');
      const updated = await fetchAutoscalingStatus();
      setAutoscalingStatus(updated);
    } catch (err: any) {
      setActionMessage(`Stop error: ${err.message}`);
      setActionType('error');
    } finally {
      setIsLoadingAutoscaler(false);
    }
  };

  const handleStartStack = async () => {
    try {
      setIsLoadingAutoscaler(true);
      setActionMessage('Starting Docker Compose workload stack...');
      setActionType('info');
      await startAutoscalingStack();
      setActionMessage('Docker Compose stack active on http://127.0.0.1:8080.');
      setActionType('success');
      const updated = await fetchAutoscalingStatus();
      setAutoscalingStatus(updated);
    } catch (err: any) {
      setActionMessage(`Start error: ${err.message}`);
      setActionType('error');
    } finally {
      setIsLoadingAutoscaler(false);
    }
  };

  const criticalCount = alerts.filter((a) => a.severity === 'critical').length;
  const warningCount = alerts.filter((a) => a.severity === 'warning').length;

  return (
    <div className="space-y-6">
      {/* Top Navigation Mode Pill Tabs */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-gray-800 pb-3">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setActiveTab('autoscaling')}
            className={`px-4 py-2 rounded-xl text-xs font-bold transition flex items-center gap-2 ${
              activeTab === 'autoscaling'
                ? 'bg-blue-600 text-white shadow-lg shadow-blue-500/20'
                : 'bg-gray-900 text-gray-400 hover:text-white hover:bg-gray-800 border border-gray-800'
            }`}
          >
            <Layers className="w-3.5 h-3.5" />
            <span>Autoscaling Demonstration Lab (Stage 5)</span>
            {autoscalingStatus && (
              <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-blue-900/60 text-blue-200 border border-blue-400/30">
                {autoscalingStatus.current_replicas} Replicas
              </span>
            )}
          </button>

          <button
            onClick={() => setActiveTab('telemetry')}
            className={`px-4 py-2 rounded-xl text-xs font-bold transition flex items-center gap-2 ${
              activeTab === 'telemetry'
                ? 'bg-blue-600 text-white shadow-lg shadow-blue-500/20'
                : 'bg-gray-900 text-gray-400 hover:text-white hover:bg-gray-800 border border-gray-800'
            }`}
          >
            <Activity className="w-3.5 h-3.5" />
            <span>Live Host & Cloud Fleet Telemetry</span>
          </button>
        </div>

        <div className="flex items-center gap-2 text-xs text-gray-400">
          <span className="inline-flex h-2 w-2 rounded-full bg-emerald-400 animate-ping"></span>
          <span>Live Telemetry Engine Active</span>
        </div>
      </div>

      {/* ============================================================== */}
      {/* TAB 1: STAGE 5 — LOCAL DOCKER AUTOSCALING DEMONSTRATION LAB     */}
      {/* ============================================================== */}
      {activeTab === 'autoscaling' && (
        <div className="space-y-6">
          {/* Main Lab Header & Control Console */}
          <section className="bg-gray-900/90 border border-blue-500/40 rounded-3xl p-5 sm:p-6 shadow-2xl relative overflow-hidden backdrop-blur-sm space-y-6">
            <div className="absolute top-0 right-0 w-80 h-80 bg-blue-600/10 rounded-full blur-3xl pointer-events-none" />

            {/* Header info */}
            <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 border-b border-gray-800 pb-5">
              <div className="space-y-1.5 max-w-2xl">
                <div className="flex items-center gap-2.5 flex-wrap">
                  <span className="flex h-3 w-3 relative">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-3 w-3 bg-emerald-500"></span>
                  </span>
                  <h2 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
                    Local Docker Autoscaling Lab
                  </h2>
                  <span className="px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-blue-500/20 text-blue-300 border border-blue-500/30">
                    Docker Compose & Nginx Gateway
                  </span>
                  <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-purple-500/20 text-purple-300 border border-purple-500/30">
                    k6 Load Generator
                  </span>
                </div>
                <p className="text-xs text-gray-400">
                  Autonomous scaling controller measuring real Docker container CPU metrics. Dynamically scales
                  FastAPI workload replicas behind an Nginx load balancer based on measured load, sustained evaluation
                  windows, and cooldown anti-oscillation safeguards.
                </p>
                <div className="text-[11px] text-gray-500 flex items-center gap-2 pt-1 font-mono">
                  <span>Entrypoint:</span>
                  <a
                    href="http://127.0.0.1:8080/health"
                    target="_blank"
                    rel="noreferrer"
                    className="text-blue-400 hover:underline flex items-center gap-1"
                  >
                    http://127.0.0.1:8080/health
                    <ExternalLink className="w-3 h-3" />
                  </a>
                  <span>•</span>
                  <span>Isolation: Separate local lab (no cloud credentials or billing)</span>
                </div>
              </div>

              {/* Lab Control Actions */}
              <div className="flex flex-wrap items-center gap-2.5">
                <button
                  onClick={handleTriggerLoadTest}
                  disabled={isLoadingAutoscaler || autoscalingStatus?.is_load_test_running}
                  className={`px-3.5 py-2 rounded-xl text-xs font-bold flex items-center gap-2 transition shadow-md ${
                    autoscalingStatus?.is_load_test_running
                      ? 'bg-amber-600/30 text-amber-300 border border-amber-500/40 cursor-not-allowed'
                      : 'bg-emerald-600 hover:bg-emerald-500 text-white'
                  }`}
                  title="Run k6 load test surge to trigger automated scale-out"
                >
                  <Play className={`w-3.5 h-3.5 ${autoscalingStatus?.is_load_test_running ? 'animate-spin' : ''}`} />
                  <span>{autoscalingStatus?.is_load_test_running ? 'k6 Surge Running...' : 'Trigger k6 Load Surge'}</span>
                </button>

                <button
                  onClick={() => handleResetReplicas(1)}
                  disabled={isLoadingAutoscaler}
                  className="px-3 py-2 rounded-xl bg-gray-800 hover:bg-gray-700 text-gray-200 text-xs font-medium border border-gray-700 transition flex items-center gap-1.5"
                  title="Reset replica count to 1"
                >
                  <RotateCcw className="w-3.5 h-3.5 text-blue-400" />
                  <span>Reset to 1</span>
                </button>

                <button
                  onClick={handleStartStack}
                  disabled={isLoadingAutoscaler}
                  className="px-3 py-2 rounded-xl bg-gray-800 hover:bg-gray-700 text-gray-200 text-xs font-medium border border-gray-700 transition flex items-center gap-1.5"
                  title="Start compose stack"
                >
                  <Check className="w-3.5 h-3.5 text-emerald-400" />
                  <span>Start Stack</span>
                </button>

                <button
                  onClick={handleStopStack}
                  disabled={isLoadingAutoscaler}
                  className="px-3 py-2 rounded-xl bg-rose-500/10 hover:bg-rose-500/20 text-rose-300 text-xs font-medium border border-rose-500/30 transition flex items-center gap-1.5"
                  title="Safely stop and remove Docker compose containers"
                >
                  <Square className="w-3.5 h-3.5 text-rose-400" />
                  <span>Stop & Cleanup</span>
                </button>
              </div>
            </div>

            {/* Action Feedback Banner */}
            {actionMessage && (
              <div
                className={`p-3 rounded-xl text-xs flex items-center justify-between border ${
                  actionType === 'success'
                    ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
                    : actionType === 'error'
                    ? 'bg-rose-500/10 border-rose-500/30 text-rose-300'
                    : 'bg-blue-500/10 border-blue-500/30 text-blue-300'
                }`}
              >
                <span>{actionMessage}</span>
                <button onClick={() => setActionMessage(null)} className="text-gray-400 hover:text-white">
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            )}

            {/* Autoscaling KPI Grid */}
            {autoscalingStatus && (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                {/* 1. Active Replicas */}
                <div className="bg-gray-950/70 border border-gray-800 rounded-2xl p-4 shadow-sm">
                  <div className="flex items-center justify-between">
                    <span className="text-gray-400 text-xs font-medium uppercase tracking-wider">
                      Workload Replicas
                    </span>
                    <div className="w-8 h-8 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-center justify-center">
                      <Layers className="w-4 h-4 text-blue-400" />
                    </div>
                  </div>
                  <div className="text-3xl font-extrabold text-white tracking-tight mt-2 flex items-baseline gap-2">
                    <span>{autoscalingStatus.current_replicas}</span>
                    <span className="text-xs text-gray-500 font-normal">
                      active (min {autoscalingStatus.min_replicas}, max {autoscalingStatus.max_replicas})
                    </span>
                  </div>
                  <div className="text-[11px] text-gray-400 mt-2 flex items-center justify-between">
                    <span>Nginx Upstream Pool:</span>
                    <span className="text-emerald-400 font-semibold">{autoscalingStatus.current_replicas} endpoints</span>
                  </div>
                </div>

                {/* 2. Measured Workload CPU */}
                <div className="bg-gray-950/70 border border-gray-800 rounded-2xl p-4 shadow-sm">
                  <div className="flex items-center justify-between">
                    <span className="text-gray-400 text-xs font-medium uppercase tracking-wider">
                      Workload Container CPU
                    </span>
                    <div className="w-8 h-8 rounded-lg bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center">
                      <Cpu className="w-4 h-4 text-cyan-400" />
                    </div>
                  </div>
                  <div className="text-3xl font-extrabold text-white tracking-tight mt-2 flex items-baseline gap-2">
                    <span>{autoscalingStatus.average_cpu_percent.toFixed(1)}%</span>
                    <span className="text-xs text-gray-500 font-normal">avg container load</span>
                  </div>
                  <div className="w-full bg-gray-800/80 rounded-full h-1.5 mt-2.5 overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all duration-500 ${
                        autoscalingStatus.average_cpu_percent > autoscalingStatus.scale_out_threshold
                          ? 'bg-rose-500'
                          : autoscalingStatus.average_cpu_percent < autoscalingStatus.scale_in_threshold
                          ? 'bg-blue-400'
                          : 'bg-emerald-400'
                      }`}
                      style={{ width: `${Math.min(100, Math.max(3, autoscalingStatus.average_cpu_percent))}%` }}
                    />
                  </div>
                  <div className="text-[10px] text-gray-400 mt-2 flex items-center justify-between font-mono">
                    <span>Scale-In &lt; {autoscalingStatus.scale_in_threshold}%</span>
                    <span>Scale-Out &gt; {autoscalingStatus.scale_out_threshold}%</span>
                  </div>
                </div>

                {/* 3. Autoscaling State & Cooldown */}
                <div className="bg-gray-950/70 border border-gray-800 rounded-2xl p-4 shadow-sm">
                  <div className="flex items-center justify-between">
                    <span className="text-gray-400 text-xs font-medium uppercase tracking-wider">
                      Autoscaler State
                    </span>
                    <div className="w-8 h-8 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-center justify-center">
                      <Sliders className="w-4 h-4 text-amber-400" />
                    </div>
                  </div>
                  <div className="mt-2">
                    <span
                      className={`inline-block px-2.5 py-1 rounded-lg text-xs font-bold uppercase tracking-wider border ${
                        autoscalingStatus.last_action === 'SCALE_OUT'
                          ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30'
                          : autoscalingStatus.last_action === 'SCALE_IN'
                          ? 'bg-blue-500/20 text-blue-300 border-blue-500/30'
                          : autoscalingStatus.last_action === 'COOLDOWN_ACTIVE'
                          ? 'bg-amber-500/20 text-amber-300 border-amber-500/30'
                          : 'bg-gray-800 text-gray-300 border-gray-700'
                      }`}
                    >
                      {autoscalingStatus.last_action}
                    </span>
                  </div>
                  <div className="text-[11px] text-gray-400 mt-2">
                    {autoscalingStatus.remaining_cooldown_seconds > 0 ? (
                      <span className="text-amber-400 font-mono">
                        Cooldown active: {autoscalingStatus.remaining_cooldown_seconds}s
                      </span>
                    ) : (
                      <span className="text-emerald-400 font-mono">Cooldown ready (no lock)</span>
                    )}
                  </div>
                </div>

                {/* 4. Load Balancer Gateway Health */}
                <div className="bg-gray-950/70 border border-gray-800 rounded-2xl p-4 shadow-sm">
                  <div className="flex items-center justify-between">
                    <span className="text-gray-400 text-xs font-medium uppercase tracking-wider">
                      Gateway & Health
                    </span>
                    <div className="w-8 h-8 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center">
                      <Network className="w-4 h-4 text-emerald-400" />
                    </div>
                  </div>
                  <div className="text-lg font-bold text-white tracking-tight mt-2 flex items-center gap-2">
                    <span
                      className={`w-2.5 h-2.5 rounded-full ${
                        autoscalingStatus.is_healthy ? 'bg-emerald-400' : 'bg-rose-500'
                      }`}
                    ></span>
                    <span>{autoscalingStatus.is_healthy ? 'Nginx 200 OK' : 'Unhealthy / Offline'}</span>
                  </div>
                  <div className="text-xs text-gray-400 mt-1 font-mono truncate">
                    Port 8080 • DNS 127.0.0.11
                  </div>
                  <div className="text-[10px] text-gray-500 mt-1 font-mono">
                    Round-robin across all active replicas
                  </div>
                </div>
              </div>
            )}

            {/* Live Replicas Inspection Table */}
            {autoscalingStatus && autoscalingStatus.replicas_detail.length > 0 && (
              <div className="bg-gray-950/80 border border-gray-800 rounded-2xl p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                    <Server className="w-4 h-4 text-blue-400" />
                    <span>Active Application Containers in Upstream Pool</span>
                  </h3>
                  <span className="text-xs text-gray-400 font-mono">
                    Direct Docker stats telemetry
                  </span>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-gray-800 text-gray-400 font-medium uppercase tracking-wider text-[10px]">
                        <th className="py-2.5 px-3">Container Name</th>
                        <th className="py-2.5 px-3">Workload Status</th>
                        <th className="py-2.5 px-3">Measured CPU %</th>
                        <th className="py-2.5 px-3">Memory Footprint</th>
                        <th className="py-2.5 px-3 text-right">Routing Target</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-800/60 font-mono">
                      {autoscalingStatus.replicas_detail.map((rep, idx) => (
                        <tr key={rep.name} className="hover:bg-gray-900/60 transition">
                          <td className="py-2.5 px-3 font-semibold text-white flex items-center gap-2">
                            <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
                            <span>{rep.name}</span>
                          </td>
                          <td className="py-2.5 px-3 text-emerald-400">{rep.status}</td>
                          <td className="py-2.5 px-3">
                            <span className="text-cyan-300 font-bold">{rep.cpu_percent.toFixed(2)}%</span>
                          </td>
                          <td className="py-2.5 px-3 text-gray-300">{rep.memory}</td>
                          <td className="py-2.5 px-3 text-right text-gray-400 text-[11px]">
                            app:8000 / replica #{idx + 1}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Scaling Decision Audit Log Table */}
            {autoscalingStatus && (
              <div className="bg-gray-950/80 border border-gray-800 rounded-2xl p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                      <Clock className="w-4 h-4 text-purple-400" />
                      <span>Scaling Decision Audit Trail</span>
                    </h3>
                    <p className="text-[11px] text-gray-400">
                      Every scaling event logged with timestamp, measured workload metrics, previous/new replica count,
                      and explanation.
                    </p>
                  </div>
                  <span className="text-xs font-mono text-gray-500">
                    {autoscalingStatus.recent_events.length} decisions logged
                  </span>
                </div>

                <div className="overflow-x-auto max-h-72 overflow-y-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-gray-800 text-gray-400 font-medium uppercase tracking-wider text-[10px] sticky top-0 bg-gray-950">
                        <th className="py-2 px-3">Timestamp (UTC)</th>
                        <th className="py-2 px-3">Action</th>
                        <th className="py-2 px-3">Replicas</th>
                        <th className="py-2 px-3">Measured CPU</th>
                        <th className="py-2 px-3">Controller Decision & Justification</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-800/60 font-mono text-[11px]">
                      {autoscalingStatus.recent_events.length === 0 ? (
                        <tr>
                          <td colSpan={5} className="py-6 text-center text-gray-500">
                            No scaling events yet. Trigger a k6 surge to observe live scaling decisions.
                          </td>
                        </tr>
                      ) : (
                        autoscalingStatus.recent_events.map((evt, idx) => (
                          <tr key={idx} className="hover:bg-gray-900/40 transition">
                            <td className="py-2 px-3 text-gray-400 whitespace-nowrap">
                              {new Date(evt.timestamp).toLocaleTimeString()}
                            </td>
                            <td className="py-2 px-3 whitespace-nowrap">
                              <span
                                className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase border ${
                                  evt.action === 'SCALE_OUT'
                                    ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30'
                                    : evt.action === 'SCALE_IN'
                                    ? 'bg-blue-500/20 text-blue-300 border-blue-500/30'
                                    : evt.action === 'COOLDOWN_ACTIVE'
                                    ? 'bg-amber-500/20 text-amber-300 border-amber-500/30'
                                    : evt.action === 'SUSTAINED_WINDOW_EVALUATING'
                                    ? 'bg-purple-500/20 text-purple-300 border-purple-500/30'
                                    : 'bg-gray-800 text-gray-400 border-gray-700'
                                }`}
                              >
                                {evt.action}
                              </span>
                            </td>
                            <td className="py-2 px-3 whitespace-nowrap font-semibold text-white">
                              {evt.previous_replicas} &rarr; {evt.new_replicas}
                            </td>
                            <td className="py-2 px-3 text-cyan-300 whitespace-nowrap">
                              {evt.measured_cpu_percent.toFixed(1)}%
                            </td>
                            <td className="py-2 px-3 text-gray-300 font-sans text-xs">
                              {evt.reason}
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Safe Stop / Reset & Local Command Guide */}
            <div className="bg-gray-950/60 border border-gray-800/80 rounded-2xl p-4 space-y-2.5 text-xs text-gray-400">
              <div className="flex items-center gap-2 text-white font-semibold">
                <Terminal className="w-4 h-4 text-emerald-400" />
                <span>Safe Stop / Reset Procedure & Local Test Commands</span>
              </div>
              <p className="text-[11px] text-gray-400">
                You can run and inspect the entire autoscaling demonstration directly from your terminal:
              </p>
              <div className="bg-gray-900 border border-gray-800 rounded-xl p-3 font-mono text-[11px] text-gray-300 space-y-1.5 overflow-x-auto">
                <div><span className="text-gray-500"># 1. Start Docker stack with 1 replica</span></div>
                <div className="text-emerald-400">DOCKER_HOST=unix:///var/run/docker.sock docker compose -f autoscaling-lab/docker-compose.yml up -d</div>
                <div className="pt-1"><span className="text-gray-500"># 2. Run k6 load test surge (triggers scale-out from 1 to 2-3 replicas)</span></div>
                <div className="text-cyan-400">k6 run --vus 20 --duration 20s autoscaling-lab/k6/load-test.js</div>
                <div className="pt-1"><span className="text-gray-500"># 3. Query the load balancer entry point directly</span></div>
                <div className="text-blue-400">curl -i http://127.0.0.1:8080/work</div>
                <div className="pt-1"><span className="text-gray-500"># 4. Safe stop and cleanup procedure</span></div>
                <div className="text-rose-400">DOCKER_HOST=unix:///var/run/docker.sock docker compose -f autoscaling-lab/docker-compose.yml down</div>
              </div>
            </div>
          </section>
        </div>
      )}

      {/* ============================================================== */}
      {/* TAB 2: LIVE HOST & CLOUD FLEET TELEMETRY (STAGES 1, 3, 4)      */}
      {/* ============================================================== */}
      {activeTab === 'telemetry' && (
        <div className="space-y-8">
          {/* Section 1: Live Local Host Metrics (Stage 4) */}
          <section className="bg-gray-900/90 border border-blue-500/30 rounded-3xl p-5 sm:p-6 shadow-xl space-y-6 relative overflow-hidden backdrop-blur-sm">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-gray-800/80 pb-4">
              <div className="space-y-1">
                <div className="flex items-center gap-2.5 flex-wrap">
                  <span className="flex h-3 w-3 relative">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-3 w-3 bg-emerald-500"></span>
                  </span>
                  <h2 className="text-lg sm:text-xl font-bold text-white tracking-tight flex items-center gap-2">
                    Live Local Host Metrics
                  </h2>
                  <span className="px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-blue-500/20 text-blue-300 border border-blue-500/30">
                    Kali Linux Host Telemetry
                  </span>
                  <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-gray-800 text-gray-300 border border-gray-700">
                    psutil collector (non-blocking)
                  </span>
                </div>
                <p className="text-xs text-gray-400 max-w-2xl">
                  Live hardware telemetry polled directly from your local Kali Linux machine every{' '}
                  <span className="text-gray-200 font-medium">3 seconds</span>. Kept strictly isolated from simulated
                  cloud inventory and cloud cost models.
                </p>
              </div>

              <div className="flex items-center gap-3 self-start sm:self-auto">
                {lastUpdatedTime && (
                  <div className="text-right text-[11px] text-gray-400 font-mono">
                    <span className="text-gray-500">Last poll:</span>{' '}
                    <span className="text-emerald-400 font-semibold">{lastUpdatedTime}</span>
                  </div>
                )}
                <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-xl bg-gray-800/80 border border-gray-700/80 text-xs text-gray-300">
                  <Radio className="w-3.5 h-3.5 text-emerald-400 animate-pulse" />
                  <span>3s Stream</span>
                </div>
              </div>
            </div>

            {/* Error Notification */}
            {hostError && (
              <div className="bg-rose-500/10 border border-rose-500/30 rounded-2xl p-4 flex items-center justify-between text-xs text-rose-300">
                <div className="flex items-center gap-2.5">
                  <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
                  <span>Host Collection Warning: {hostError}</span>
                </div>
                <button
                  onClick={() => {
                    setHostError(null);
                    fetchLocalMonitoring(0.5).then((data) => {
                      setLatestMetric(data);
                      setLastUpdatedTime(new Date(data.timestamp).toLocaleTimeString());
                    });
                  }}
                  className="px-3 py-1 bg-rose-500/20 hover:bg-rose-500/30 rounded-lg text-rose-200 text-[11px] font-medium transition"
                >
                  Retry Poll
                </button>
              </div>
            )}

            {/* Host Telemetry Cards Grid */}
            {latestMetric && (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                <div className="bg-gray-950/70 border border-gray-800/90 rounded-2xl p-4 shadow-sm">
                  <div className="flex items-center justify-between">
                    <span className="text-gray-400 text-xs font-medium uppercase tracking-wider">
                      Live CPU Utilization
                    </span>
                    <div className="w-8 h-8 rounded-lg bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center">
                      <Cpu className="w-4 h-4 text-cyan-400" />
                    </div>
                  </div>
                  <div className="mt-2 flex items-baseline gap-2">
                    <span className="text-3xl font-extrabold text-white tracking-tight">
                      {latestMetric.cpu_utilization.toFixed(1)}%
                    </span>
                    <span className="text-xs text-gray-500">utilization</span>
                  </div>
                  <div className="w-full bg-gray-800/80 rounded-full h-1.5 mt-2.5 overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all duration-500 ${
                        latestMetric.cpu_utilization > 80
                           ? 'bg-rose-500'
                          : latestMetric.cpu_utilization > 60
                          ? 'bg-amber-400'
                          : 'bg-cyan-400'
                      }`}
                      style={{ width: `${Math.min(100, Math.max(2, latestMetric.cpu_utilization))}%` }}
                    />
                  </div>
                  <div className="text-[11px] text-gray-400 mt-2 flex items-center justify-between">
                    <span>Sampling: {latestMetric.sampling_interval_seconds}s</span>
                    <span className="text-emerald-400">Normal</span>
                  </div>
                </div>

                <div className="bg-gray-950/70 border border-gray-800/90 rounded-2xl p-4 shadow-sm">
                  <div className="flex items-center justify-between">
                    <span className="text-gray-400 text-xs font-medium uppercase tracking-wider">
                      Live RAM Utilization
                    </span>
                    <div className="w-8 h-8 rounded-lg bg-purple-500/10 border border-purple-500/20 flex items-center justify-center">
                      <HardDrive className="w-4 h-4 text-purple-400" />
                    </div>
                  </div>
                  <div className="mt-2 flex items-baseline gap-2">
                    <span className="text-3xl font-extrabold text-white tracking-tight">
                      {latestMetric.ram_utilization.toFixed(1)}%
                    </span>
                    <span className="text-xs text-gray-500">memory used</span>
                  </div>
                  <div className="w-full bg-gray-800/80 rounded-full h-1.5 mt-2.5 overflow-hidden">
                    <div
                      className="h-full rounded-full bg-purple-400 transition-all duration-500"
                      style={{ width: `${Math.min(100, Math.max(2, latestMetric.ram_utilization))}%` }}
                    />
                  </div>
                  <div className="text-[11px] text-gray-400 mt-2 flex items-center justify-between">
                    <span>Used: {latestMetric.used_ram_gb} GB</span>
                    <span>Total: {latestMetric.total_ram_gb} GB</span>
                  </div>
                </div>

                <div className="bg-gray-950/70 border border-gray-800/90 rounded-2xl p-4 shadow-sm">
                  <div className="flex items-center justify-between">
                    <span className="text-gray-400 text-xs font-medium uppercase tracking-wider">
                      Physical RAM Footprint
                    </span>
                    <div className="w-8 h-8 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center">
                      <Server className="w-4 h-4 text-emerald-400" />
                    </div>
                  </div>
                  <div className="mt-2">
                    <span className="text-2xl font-extrabold text-emerald-400 tracking-tight">
                      {latestMetric.used_ram_gb.toFixed(2)}{' '}
                      <span className="text-xs font-normal text-gray-400">
                        / {latestMetric.total_ram_gb.toFixed(2)} GB
                      </span>
                    </span>
                  </div>
                  <div className="text-[11px] text-gray-400 mt-2">
                    {(latestMetric.total_ram_gb - latestMetric.used_ram_gb).toFixed(2)} GB Available
                  </div>
                  <div className="text-[10px] text-gray-500 font-mono truncate mt-0.5">
                    {latestMetric.used_ram_bytes.toLocaleString()} bytes active
                  </div>
                </div>

                {/* 4. Live Host Storage (Root Filesystem) */}
                <div className="bg-gray-950/70 border border-gray-800/90 rounded-2xl p-4 shadow-sm">
                  <div className="flex items-center justify-between">
                    <span className="text-gray-400 text-xs font-medium uppercase tracking-wider">
                      Live Host Storage
                    </span>
                    <div className="w-8 h-8 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-center justify-center">
                      <HardDrive className="w-4 h-4 text-amber-400" />
                    </div>
                  </div>
                  <div className="mt-2 flex items-baseline gap-2">
                    <span className="text-2xl font-extrabold text-amber-400 tracking-tight">
                      {latestMetric.disk_used_gb !== undefined ? latestMetric.disk_used_gb.toFixed(1) : '--'}
                      <span className="text-xs font-normal text-gray-400">
                        {' '}/ {latestMetric.disk_total_gb !== undefined ? latestMetric.disk_total_gb.toFixed(1) : '--'} GB
                      </span>
                    </span>
                  </div>
                  <div className="w-full bg-gray-800/80 rounded-full h-1.5 mt-2.5 overflow-hidden">
                    <div
                      className="h-full rounded-full bg-amber-400 transition-all duration-500"
                      style={{ width: `${Math.min(100, Math.max(2, latestMetric.disk_percent || 0))}%` }}
                    />
                  </div>
                  <div className="text-[11px] text-gray-400 mt-2 flex items-center justify-between">
                    <span>{latestMetric.disk_free_gb !== undefined ? `${latestMetric.disk_free_gb.toFixed(1)} GB free` : 'Root fs'}</span>
                    <span className="text-amber-400 font-mono text-[10px]">{latestMetric.disk_percent !== undefined ? `${latestMetric.disk_percent.toFixed(1)}% used` : ''}</span>
                  </div>
                </div>

                {/* 5. Storage Resizing Status */}
                <div className="bg-gray-950/70 border border-gray-800/90 rounded-2xl p-4 shadow-sm">
                  <div className="flex items-center justify-between">
                    <span className="text-gray-400 text-xs font-medium uppercase tracking-wider">
                      Storage Resizing
                    </span>
                    <div className="w-8 h-8 rounded-lg bg-purple-500/10 border border-purple-500/20 flex items-center justify-center">
                      <Shield className="w-4 h-4 text-purple-400" />
                    </div>
                  </div>
                  <div className="mt-2 flex items-center gap-2">
                    <span className="px-2 py-0.5 rounded text-[11px] font-bold font-mono bg-purple-500/20 text-purple-300 border border-purple-500/30">
                      NOT CONFIGURED
                    </span>
                  </div>
                  <div className="text-xs text-gray-300 mt-2 font-medium">
                    Cloud Provider Required
                  </div>
                  <div className="text-[10px] text-gray-500 mt-1 line-clamp-2">
                    Local root disk resize blocked for safety. AWS EBS / GCP PD adapter required.
                  </div>
                </div>

                {/* 6. Collector Engine */}
                <div className="bg-gray-950/70 border border-gray-800/90 rounded-2xl p-4 shadow-sm">
                  <div className="flex items-center justify-between">
                    <span className="text-gray-400 text-xs font-medium uppercase tracking-wider">
                      Telemetry Engine
                    </span>
                    <div className="w-8 h-8 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-center justify-center">
                      <Zap className="w-4 h-4 text-blue-400" />
                    </div>
                  </div>
                  <div className="mt-2 flex items-center gap-2">
                    <span className="text-lg font-bold text-white tracking-tight">Active & Healthy</span>
                    <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
                  </div>
                  <div className="text-xs text-gray-400 mt-2">
                    psutil non-blocking collector
                  </div>
                  <div className="text-[10px] text-emerald-400/90 mt-1 font-mono truncate">
                    Host: {latestMetric.host_id ? latestMetric.host_id.slice(0, 12) : 'local-host'}
                  </div>
                </div>
              </div>
            )}

            {/* Rolling Chart */}
            <div className="bg-gray-950/80 border border-gray-800/90 rounded-2xl p-5 space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-semibold text-white">Rolling Host Telemetry (Recent Readings)</h3>
                  <p className="text-xs text-gray-400">
                    Sliding window of actual host CPU and RAM utilization updated every 3s.
                  </p>
                </div>
                <div className="flex items-center gap-4 text-xs font-mono">
                  <span className="text-cyan-400">● CPU %</span>
                  <span className="text-purple-400">● RAM %</span>
                </div>
              </div>

              <div className="h-60 w-full pt-2">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={recentReadings} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" vertical={false} />
                    <XAxis dataKey="time" stroke="#6b7280" fontSize={10} tickLine={false} />
                    <YAxis stroke="#6b7280" fontSize={10} domain={[0, 100]} tickLine={false} tickFormatter={(v) => `${v}%`} />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: '#111827',
                        borderColor: '#374151',
                        borderRadius: '0.5rem',
                        fontSize: '11px',
                        color: '#f3f4f6',
                      }}
                      formatter={(val: any, name: string) => [
                        `${Number(val).toFixed(1)}%`,
                        name === 'cpu_percent' ? 'Host CPU' : 'Host RAM',
                      ]}
                    />
                    <ReferenceLine y={80} stroke="#ef4444" strokeDasharray="3 3" />
                    <Line type="monotone" dataKey="cpu_percent" stroke="#06b6d4" strokeWidth={2} dot={false} isAnimationActive={false} />
                    <Line type="monotone" dataKey="ram_percent" stroke="#a855f7" strokeWidth={2} dot={false} isAnimationActive={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Dedicated Isolated Docker Workload cgroup Telemetry */}
            <div className="bg-gray-950/90 border border-cyan-500/30 rounded-2xl p-5 space-y-4 shadow-lg">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-gray-800 pb-3">
                <div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <h3 className="text-sm font-bold text-white flex items-center gap-2">
                      <Server className="w-4 h-4 text-cyan-400" />
                      <span>Docker Workload Container cgroup Telemetry</span>
                    </h3>
                    <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-cyan-500/20 text-cyan-300 border border-cyan-500/30">
                      Isolated cgroup metrics (docker stats)
                    </span>
                  </div>
                  <p className="text-xs text-gray-400 mt-1">
                    Direct cgroup measurements of target workload <span className="font-mono text-cyan-300">autoscaling-lab-app-1</span>.
                    Strictly isolated from Kali host hardware telemetry.
                  </p>
                </div>
                <div className="text-[11px] font-mono text-gray-400 flex items-center gap-2">
                  <span>Gateway:</span>
                  <a
                    href="http://127.0.0.1:8080/health"
                    target="_blank"
                    rel="noreferrer"
                    className="text-cyan-400 hover:underline flex items-center gap-1"
                  >
                    http://127.0.0.1:8080/health
                    <ExternalLink className="w-3 h-3" />
                  </a>
                </div>
              </div>

              {dockerWorkload ? (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                  <div className="bg-gray-900/80 border border-gray-800 rounded-xl p-3.5">
                    <div className="text-[11px] text-gray-400 uppercase font-medium">Container cgroup CPU</div>
                    <div className="text-2xl font-extrabold text-cyan-400 mt-1">
                      {dockerWorkload.actual_cpu_percent.toFixed(2)}%
                    </div>
                    <div className="text-[10px] text-gray-500 mt-1">
                      Target: {dockerWorkload.container_name}
                    </div>
                  </div>

                  <div className="bg-gray-900/80 border border-gray-800 rounded-xl p-3.5">
                    <div className="text-[11px] text-gray-400 uppercase font-medium">Container cgroup Memory</div>
                    <div className="text-xl font-extrabold text-purple-400 mt-1">
                      {dockerWorkload.actual_memory_mb.toFixed(1)} MB
                      <span className="text-xs font-normal text-gray-400"> / {dockerWorkload.actual_memory_limit_mb.toFixed(0)} MB</span>
                    </div>
                    <div className="text-[10px] text-purple-300 mt-1">
                      {dockerWorkload.actual_memory_percent.toFixed(1)}% of allocated limit
                    </div>
                  </div>

                  <div className="bg-gray-900/80 border border-gray-800 rounded-xl p-3.5">
                    <div className="text-[11px] text-gray-400 uppercase font-medium">Docker Inspect Limits</div>
                    <div className="mt-1">
                      {dockerWorkload.is_unconstrained ? (
                        <span className="px-2 py-0.5 rounded text-[11px] font-bold font-mono bg-amber-500/20 text-amber-300 border border-amber-500/30">
                          UNCONSTRAINED
                        </span>
                      ) : (
                        <div className="text-sm font-bold text-white font-mono">
                          <span className="text-cyan-400">{dockerWorkload.configured_cpu_cores} vCPU</span>
                          <span className="text-gray-400"> • </span>
                          <span className="text-purple-400">{dockerWorkload.configured_memory_gb} GB RAM</span>
                        </div>
                      )}
                    </div>
                    <div className="text-[10px] text-gray-500 mt-1">
                      Status: {dockerWorkload.limit_status}
                    </div>
                  </div>

                  <div className="bg-gray-900/80 border border-gray-800 rounded-xl p-3.5">
                    <div className="text-[11px] text-gray-400 uppercase font-medium">Workload Cluster State</div>
                    <div className="text-lg font-bold text-emerald-400 mt-1 flex items-center gap-2">
                      <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                      <span>{dockerWorkload.running_replicas} Replicas Active</span>
                    </div>
                    <div className="text-[10px] text-gray-400 mt-1">
                      Load-balanced by Nginx Gateway
                    </div>
                  </div>
                </div>
              ) : (
                <div className="text-xs text-gray-500 py-4 text-center font-mono">
                  Connecting to Docker workload telemetry socket...
                </div>
              )}
            </div>
          </section>

          {/* Section 2: Simulated Cloud Fleet Metrics & Anomaly Alerts */}
          <div className="space-y-6 pt-2">
            <div className="border-b border-gray-800 pb-3">
              <h2 className="text-base font-bold text-white tracking-tight flex items-center gap-2">
                <span>Simulated Cloud Fleet Telemetry</span>
                <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-gray-800 text-gray-400 border border-gray-700">
                  Simulated Fleet Benchmarks
                </span>
              </h2>
              <p className="text-xs text-gray-400">
                Aggregated compute telemetry across Bangalore, Mumbai, and Noida cloud regions.
              </p>
            </div>

            {/* Fleet KPI Cards */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <div className="bg-gray-900 border border-gray-800 rounded-2xl p-4 shadow-sm">
                <span className="text-gray-400 text-xs font-medium uppercase tracking-wider">Fleet Health</span>
                <div className="text-2xl font-bold text-white tracking-tight mt-2">99.98% uptime</div>
                <div className="text-xs text-gray-400 mt-1">138 instances streaming metrics</div>
              </div>
              <div className="bg-gray-900 border border-gray-800 rounded-2xl p-4 shadow-sm">
                <span className="text-gray-400 text-xs font-medium uppercase tracking-wider">Critical Alerts</span>
                <div className="text-2xl font-bold text-rose-400 tracking-tight mt-2">{criticalCount} anomalies</div>
                <div className="text-xs text-rose-400/80 mt-1">Capacity risk requires attention</div>
              </div>
              <div className="bg-gray-900 border border-gray-800 rounded-2xl p-4 shadow-sm">
                <span className="text-gray-400 text-xs font-medium uppercase tracking-wider">Waste Warnings</span>
                <div className="text-2xl font-bold text-amber-400 tracking-tight mt-2">{warningCount} flagged</div>
                <div className="text-xs text-amber-400/80 mt-1">Orphaned storage & weekend idle</div>
              </div>
              <div className="bg-gray-900 border border-gray-800 rounded-2xl p-4 shadow-sm">
                <span className="text-gray-400 text-xs font-medium uppercase tracking-wider">Sample Rate</span>
                <div className="text-2xl font-bold text-blue-400 tracking-tight mt-2">5 min cadence</div>
                <div className="text-xs text-gray-400 mt-1">30-day retention window</div>
              </div>
            </div>

            {/* Fleet Charts Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div className="bg-gray-900 border border-gray-800 rounded-2xl p-5 shadow-sm space-y-3">
                <h3 className="text-sm font-semibold text-white">Fleet CPU Utilization (30-Day Curve)</h3>
                <div className="h-56 w-full pt-2">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={fleetTelemetry} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" vertical={false} />
                      <XAxis dataKey="date" stroke="#6b7280" fontSize={10} tickLine={false} interval={20} />
                      <YAxis stroke="#6b7280" fontSize={10} domain={[0, 100]} tickLine={false} tickFormatter={(v) => `${v}%`} />
                      <Tooltip contentStyle={{ backgroundColor: '#111827', borderColor: '#374151', borderRadius: '0.5rem', fontSize: '11px' }} />
                      <Line type="monotone" dataKey="cpu_percent" stroke="#06b6d4" strokeWidth={1.5} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>

              <div className="bg-gray-900 border border-gray-800 rounded-2xl p-5 shadow-sm space-y-3">
                <h3 className="text-sm font-semibold text-white">Fleet Memory Allocation</h3>
                <div className="h-56 w-full pt-2">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={fleetTelemetry} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" vertical={false} />
                      <XAxis dataKey="date" stroke="#6b7280" fontSize={10} tickLine={false} interval={20} />
                      <YAxis stroke="#6b7280" fontSize={10} domain={[0, 100]} tickLine={false} tickFormatter={(v) => `${v}%`} />
                      <Tooltip contentStyle={{ backgroundColor: '#111827', borderColor: '#374151', borderRadius: '0.5rem', fontSize: '11px' }} />
                      <Line type="monotone" dataKey="ram_percent" stroke="#a855f7" strokeWidth={1.5} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>

            {/* Active Alerts */}
            <div className="bg-gray-900 border border-gray-800 rounded-2xl p-5 shadow-sm space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-base font-bold text-white tracking-tight">Active Anomaly Alerts</h3>
                <span className="px-2.5 py-0.5 rounded-full text-xs font-bold bg-rose-500/20 text-rose-400">
                  {alerts.length} Active
                </span>
              </div>
              <div className="space-y-3">
                {alerts.map((alert) => (
                  <div
                    key={alert.id}
                    className="bg-gray-950/70 border border-gray-800 rounded-xl p-4 flex flex-col md:flex-row md:items-center justify-between gap-4 text-xs"
                  >
                    <div>
                      <div className="flex items-center gap-2">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase border ${getSeverityBadgeClass(alert.severity)}`}>
                          {alert.severity}
                        </span>
                        <span className="font-bold text-gray-100">{alert.title}</span>
                        <span className="text-gray-400 font-mono">({alert.resource_id})</span>
                      </div>
                      <p className="text-gray-300 mt-1">{alert.message}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => onSelectResourceById(alert.resource_id)}
                        className="px-3 py-1.5 bg-gray-800 hover:bg-blue-600 rounded-xl text-gray-200 hover:text-white transition"
                      >
                        Investigate
                      </button>
                      <button onClick={() => onDismissAlert(alert.id)} className="p-1.5 text-gray-500 hover:text-gray-300">
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
