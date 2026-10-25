import React, { useEffect, useState } from 'react';
import {
  X,
  Cpu,
  HardDrive,
  Check,
  RotateCcw,
  AlertTriangle,
  ArrowRight,
  TrendingDown,
  Layers,
  MapPin,
  Calendar,
} from 'lucide-react';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  CartesianGrid,
  ReferenceLine,
} from 'recharts';
import { Recommendation, Resource, TelemetryPoint, RecommendationStatus } from '../types';
import { fetchMetrics } from '../services/api';
import { formatINR, formatPercent, getRiskBadgeClass, getStatusBadgeClass } from '../utils/formatters';

interface ResourceDetailModalProps {
  item: Recommendation | Resource | null;
  recommendation?: Recommendation | null;
  onClose: () => void;
  onUpdateStatus?: (id: string, status: RecommendationStatus) => void;
  isUpdating?: boolean;
}

export const ResourceDetailModal: React.FC<ResourceDetailModalProps> = ({
  item,
  recommendation,
  onClose,
  onUpdateStatus,
  isUpdating = false,
}) => {
  const [telemetry, setTelemetry] = useState<TelemetryPoint[]>([]);
  const [loading, setLoading] = useState(true);

  if (!item) return null;

  const resourceId = 'resource_id' in item ? item.resource_id : item.id;
  const resourceName = 'resource_name' in item ? item.resource_name : item.name;
  const rec = recommendation || ('action' in item ? (item as Recommendation) : null);

  useEffect(() => {
    let mounted = true;
    setLoading(true);

    fetchMetrics(resourceId)
      .then((res) => {
        if (mounted) {
          setTelemetry(res.data);
        }
      })
      .catch((err) => console.error('Failed to load metrics', err))
      .finally(() => {
        if (mounted) setLoading(false);
      });

    return () => {
      mounted = false;
    };
  }, [resourceId]);

  // Handle escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm overflow-y-auto">
      <div
        className="relative w-full max-w-4xl bg-gray-900 border border-gray-800 rounded-2xl shadow-2xl overflow-hidden my-8"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div className="px-6 py-4 border-b border-gray-800 flex items-center justify-between bg-gray-950/60">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center">
              <Cpu className="w-5 h-5 text-blue-400" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-bold text-white tracking-tight">{resourceName}</h2>
                <span className="font-mono text-xs px-2 py-0.5 rounded bg-gray-800 text-gray-300 border border-gray-700">
                  {resourceId}
                </span>
                {rec && (
                  <span
                    className={`text-[10px] font-bold px-2 py-0.5 rounded-full uppercase border ${getStatusBadgeClass(
                      rec.status
                    )}`}
                  >
                    {rec.status}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-3 text-xs text-gray-400 mt-0.5">
                <span className="flex items-center gap-1">
                  <MapPin className="w-3 h-3 text-blue-400" />
                  {item.region}
                </span>
                <span>•</span>
                <span className="uppercase text-[11px] font-semibold text-gray-300">
                  {item.environment}
                </span>
                <span>•</span>
                <span className="flex items-center gap-1">
                  <Layers className="w-3 h-3 text-purple-400" />
                  {(item as any).type || (rec as any)?.resource_type || 'VM'}
                </span>
              </div>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-gray-800 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-6 space-y-6 max-h-[calc(85vh-130px)] overflow-y-auto">
          {/* Sizing / Cost Proposal if Recommendation exists */}
          {rec && (
            <div className="bg-gray-950/70 border border-gray-800 rounded-xl p-4 space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-gray-800/80">
                <div className="flex items-center gap-2">
                  <TrendingDown className="w-4 h-4 text-emerald-400" />
                  <span className="text-sm font-semibold text-white">Recommended Action:</span>
                  <span className="text-sm font-bold text-emerald-400">{rec.action}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-gray-400">Risk Assessment:</span>
                  <span
                    className={`text-xs font-bold px-2.5 py-0.5 rounded border ${getRiskBadgeClass(
                      rec.risk_level
                    )}`}
                  >
                    {rec.risk_level} RISK ({rec.confidence_score}% Confidence)
                  </span>
                </div>
              </div>

              {/* Spec & Cost Comparison */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
                {/* Current */}
                <div className="bg-gray-900/80 border border-gray-800 p-3 rounded-lg">
                  <span className="text-gray-400 block font-medium">Current Allocation</span>
                  <span className="text-white font-mono font-semibold block mt-1 text-sm">
                    {rec.current_spec}
                  </span>
                  <span className="text-rose-400 font-mono block mt-1">
                    {formatINR(rec.current_cost)} / mo
                  </span>
                </div>

                {/* Target */}
                <div className="bg-gray-900/80 border border-blue-900/40 p-3 rounded-lg">
                  <span className="text-gray-400 block font-medium">Optimized Target</span>
                  <span className="text-blue-300 font-mono font-semibold block mt-1 text-sm">
                    {rec.recommended_spec}
                  </span>
                  <span className="text-emerald-400 font-mono block mt-1">
                    {formatINR(rec.recommended_cost)} / mo
                  </span>
                </div>

                {/* Savings */}
                <div className="bg-emerald-950/20 border border-emerald-800/40 p-3 rounded-lg flex flex-col justify-between">
                  <span className="text-emerald-300/80 font-medium">Estimated Monthly Savings</span>
                  <div>
                    <span className="text-xl font-bold text-emerald-400 font-mono block">
                      {formatINR(rec.monthly_savings)}
                    </span>
                    <span className="text-[11px] text-emerald-400/80 font-medium">
                      {rec.savings_pct}% monthly reduction
                    </span>
                  </div>
                </div>
              </div>

              {/* Justification & Peak Load Analysis */}
              <div className="bg-gray-900/60 p-3.5 rounded-lg border border-gray-800/80 space-y-1.5 text-xs">
                <div className="text-gray-200 font-semibold flex items-center gap-1.5">
                  <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
                  Peak Behavior & Safety Justification
                </div>
                <p className="text-gray-400 leading-relaxed">{rec.justification}</p>
                {rec.peak_behavior && (
                  <p className="text-gray-400 leading-relaxed text-[11px] pt-1 border-t border-gray-800/60 font-mono">
                    <span className="text-blue-400">Peak profile:</span> {rec.peak_behavior}
                  </p>
                )}
              </div>
            </div>
          )}

          {/* 30-Day Utilization Telemetry Chart */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                  <Cpu className="w-4 h-4 text-cyan-400" />
                  30-Day Historical Utilization Telemetry
                </h3>
                <p className="text-xs text-gray-400">
                  Hourly CPU % and RAM % utilization showing diurnal cycle and safety headroom.
                </p>
              </div>

              <div className="flex items-center gap-3 text-xs font-mono">
                <span className="text-cyan-400">P99 CPU: {formatPercent(rec?.p99_cpu || (item as any).p99_cpu || 24.5)}</span>
                <span className="text-purple-400">P99 RAM: {formatPercent(rec?.p99_ram || (item as any).p99_ram || 38.2)}</span>
              </div>
            </div>

            <div className="h-64 w-full bg-gray-950/60 border border-gray-800 rounded-xl p-3">
              {loading ? (
                <div className="h-full flex items-center justify-center text-xs text-gray-500">
                  Loading telemetry time series...
                </div>
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={telemetry} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" vertical={false} />
                    <XAxis
                      dataKey="date"
                      stroke="#6b7280"
                      fontSize={10}
                      tickLine={false}
                      interval={20}
                    />
                    <YAxis
                      stroke="#6b7280"
                      fontSize={10}
                      domain={[0, 100]}
                      tickLine={false}
                      tickFormatter={(v) => `${v}%`}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: '#111827',
                        borderColor: '#374151',
                        borderRadius: '0.5rem',
                        fontSize: '11px',
                        color: '#f3f4f6',
                      }}
                      formatter={(val: any, name: string) => [
                        `${val}%`,
                        name === 'cpu_percent' ? 'CPU Utilization' : 'RAM Utilization',
                      ]}
                      labelFormatter={(_label, payload) => {
                        if (payload && payload[0]?.payload) {
                          const p = payload[0].payload;
                          return `${p.date} ${p.time}`;
                        }
                        return '';
                      }}
                    />
                    <Legend
                      verticalAlign="top"
                      height={30}
                      iconType="circle"
                      wrapperStyle={{ fontSize: '11px' }}
                    />
                    {/* Capacity Threshold Reference Line */}
                    <ReferenceLine
                      y={80}
                      stroke="#ef4444"
                      strokeDasharray="4 4"
                      label={{ value: 'Capacity Limit 80%', fill: '#ef4444', fontSize: 10, position: 'insideTopRight' }}
                    />
                    <Line
                      type="monotone"
                      dataKey="cpu_percent"
                      name="CPU %"
                      stroke="#06b6d4"
                      strokeWidth={1.5}
                      dot={false}
                      activeDot={{ r: 4 }}
                    />
                    <Line
                      type="monotone"
                      dataKey="ram_percent"
                      name="RAM %"
                      stroke="#a855f7"
                      strokeWidth={1.5}
                      dot={false}
                      activeDot={{ r: 4 }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              )}
            </div>
          </div>
        </div>

        {/* Modal Footer with Actions */}
        <div className="px-6 py-4 border-t border-gray-800 bg-gray-950/60 flex items-center justify-between">
          <div className="text-xs text-gray-500 font-mono">
            Resource: {resourceId}
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={onClose}
              className="px-4 py-2 rounded-xl text-xs font-medium text-gray-300 hover:text-white bg-gray-800 hover:bg-gray-700 transition"
            >
              Close
            </button>

            {rec && onUpdateStatus && (
              <>
                {rec.status !== 'REJECTED' && (
                  <button
                    disabled={isUpdating}
                    onClick={() => {
                      onUpdateStatus(rec.id, 'REJECTED');
                      onClose();
                    }}
                    className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-medium text-rose-300 bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/30 transition disabled:opacity-50"
                  >
                    <X className="w-3.5 h-3.5" />
                    <span>Reject</span>
                  </button>
                )}

                {rec.status !== 'ACCEPTED' && (
                  <button
                    disabled={isUpdating}
                    onClick={() => {
                      onUpdateStatus(rec.id, 'ACCEPTED');
                      onClose();
                    }}
                    className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold text-white bg-emerald-600 hover:bg-emerald-500 shadow-md shadow-emerald-600/20 transition disabled:opacity-50"
                  >
                    <Check className="w-3.5 h-3.5" />
                    <span>Accept & Apply</span>
                  </button>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
