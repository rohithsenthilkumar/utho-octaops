import React, { useState, useMemo } from 'react';
import {
  Lightbulb,
  Check,
  X,
  RotateCcw,
  AlertTriangle,
  ArrowRight,
  TrendingDown,
  ShieldCheck,
  Search,
  CheckCircle2,
  Clock,
  ExternalLink,
  ArrowUpDown,
  Zap,
  Cpu,
  Database,
  Info,
} from 'lucide-react';
import { Recommendation, RiskLevel, RecommendationStatus } from '../types';
import { formatINR, formatPercent, getRiskBadgeClass, getStatusBadgeClass } from '../utils/formatters';

interface RecommendationsPageProps {
  recommendations: Recommendation[];
  onUpdateStatus: (id: string, status: RecommendationStatus) => void;
  onSelectResource: (rec: Recommendation) => void;
  isUpdatingId: string | null;
}

export const RecommendationsPage: React.FC<RecommendationsPageProps> = ({
  recommendations,
  onUpdateStatus,
  onSelectResource,
  isUpdatingId,
}) => {
  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [riskFilter, setRiskFilter] = useState<string>('ALL');
  const [envFilter, setEnvFilter] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState('');
  const [sortField, setSortField] = useState<'savings' | 'risk' | 'name'>('savings');
  const [sortOrder, setSortOrder] = useState<'desc' | 'asc'>('desc');

  // Filter recommendations
  const filteredRecs = useMemo(() => {
    return recommendations.filter((item) => {
      // Search
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase().trim();
        const matchesName = item.resource_name.toLowerCase().includes(q);
        const matchesId = item.resource_id.toLowerCase().includes(q);
        const matchesAction = item.action.toLowerCase().includes(q);
        if (!matchesName && !matchesId && !matchesAction) return false;
      }
      // Status
      if (statusFilter !== 'ALL') {
        const s = item.status.toUpperCase();
        if (statusFilter === 'INSUFFICIENT' && s !== 'INSUFFICIENT_DATA') return false;
        if (statusFilter === 'OPTIMAL' && s !== 'OPTIMAL' && s !== 'HIGH_UTILIZATION') return false;
        if (statusFilter === 'PENDING' && s !== 'PENDING' && s !== 'RECOMMENDED') return false;
        if (statusFilter === 'ACCEPTED' && s !== 'ACCEPTED') return false;
        if (statusFilter === 'REJECTED' && s !== 'REJECTED') return false;
      }
      // Risk
      if (riskFilter !== 'ALL' && item.risk_level.toUpperCase() !== riskFilter) {
        return false;
      }
      // Environment
      if (envFilter !== 'ALL' && item.environment.toLowerCase() !== envFilter.toLowerCase()) {
        return false;
      }
      return true;
    });
  }, [recommendations, searchQuery, statusFilter, riskFilter, envFilter]);

  // Sort
  const sortedRecs = useMemo(() => {
    const list = [...filteredRecs];
    list.sort((a, b) => {
      if (sortField === 'savings') {
        return sortOrder === 'desc'
          ? b.monthly_savings - a.monthly_savings
          : a.monthly_savings - b.monthly_savings;
      } else if (sortField === 'risk') {
        const weights = { LOW: 1, MEDIUM: 2, HIGH: 3 };
        const wA = weights[a.risk_level] || 0;
        const wB = weights[b.risk_level] || 0;
        return sortOrder === 'desc' ? wB - wA : wA - wB;
      } else {
        return sortOrder === 'desc'
          ? b.resource_name.localeCompare(a.resource_name)
          : a.resource_name.localeCompare(b.resource_name);
      }
    });
    return list;
  }, [filteredRecs, sortField, sortOrder]);

  // Summary impact calculations
  const totalPotentialSavings = useMemo(() => {
    return recommendations.reduce((acc, r) => acc + (r.monthly_savings || 0), 0);
  }, [recommendations]);

  const acceptedSavings = useMemo(() => {
    return recommendations
      .filter((r) => r.status === 'ACCEPTED')
      .reduce((acc, r) => acc + (r.monthly_savings || 0), 0);
  }, [recommendations]);

  const pendingCount = recommendations.filter(
    (r) => r.status === 'PENDING' || r.status === 'RECOMMENDED'
  ).length;
  const acceptedCount = recommendations.filter((r) => r.status === 'ACCEPTED').length;

  return (
    <div className="space-y-6">
      {/* 1. Impact Banner */}
      <div className="bg-gradient-to-r from-blue-950/40 via-gray-900 to-emerald-950/30 border border-gray-800 rounded-2xl p-5 shadow-sm">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 items-center">
          <div className="md:col-span-2">
            <div className="flex items-center gap-2 text-cyan-400 text-xs font-semibold uppercase tracking-wider mb-1">
              <Zap className="w-4 h-4" />
              <span>Stage 3: Peak-Safe Rightsizing Engine</span>
              <span className="px-1.5 py-0.5 rounded bg-cyan-500/10 text-cyan-300 border border-cyan-500/20 text-[10px] font-mono">
                SIMULATED BENCHMARK
              </span>
            </div>
            <h2 className="text-xl font-bold text-white tracking-tight">
              Deterministic Cloud Rightsizing Intelligence
            </h2>
            <p className="text-xs text-gray-400 mt-1 leading-relaxed">
              Considers P95/peak CPU utilization and memory headroom with environment-specific safety buffers (25% for prod).
              Refuses to guess when metrics are insufficient (&lt; 24 samples).
            </p>
          </div>

          <div className="bg-gray-950/60 border border-gray-800 p-3.5 rounded-xl">
            <span className="text-xs text-gray-400 block font-medium">Realized Savings (Accepted)</span>
            <span className="text-xl font-bold text-emerald-400 font-mono block mt-0.5">
              {formatINR(acceptedSavings)}
            </span>
            <span className="text-[11px] text-gray-500">{acceptedCount} changes applied</span>
          </div>

          <div className="bg-gray-950/60 border border-gray-800 p-3.5 rounded-xl">
            <span className="text-xs text-gray-400 block font-medium">Available Unlocked Savings</span>
            <span className="text-xl font-bold text-blue-400 font-mono block mt-0.5">
              {formatINR(totalPotentialSavings - acceptedSavings)}
            </span>
            <span className="text-[11px] text-gray-500">{pendingCount} pending reviews</span>
          </div>
        </div>
      </div>

      {/* 2. Filters & Sort Controls */}
      <div className="bg-gray-900 border border-gray-800 rounded-2xl p-4 shadow-sm space-y-3">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
          {/* Search */}
          <div className="relative flex-1 max-w-sm">
            <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
            <input
              type="text"
              placeholder="Search resource, action, or justification..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-2 bg-gray-950 border border-gray-800 rounded-xl text-xs text-gray-200 placeholder-gray-500 focus:outline-none focus:border-blue-500 transition"
            />
          </div>

          {/* Filter Pills */}
          <div className="flex flex-wrap items-center gap-2 text-xs">
            {/* Status Tabs */}
            <div className="flex items-center bg-gray-950 p-1 rounded-xl border border-gray-800">
              {['ALL', 'PENDING', 'ACCEPTED', 'REJECTED'].map((st) => (
                <button
                  key={st}
                  onClick={() => setStatusFilter(st)}
                  className={`px-3 py-1 rounded-lg font-medium transition ${
                    statusFilter === st
                      ? 'bg-blue-600 text-white shadow-sm'
                      : 'text-gray-400 hover:text-gray-200'
                  }`}
                >
                  {st.charAt(0) + st.slice(1).toLowerCase()}
                </button>
              ))}
            </div>

            {/* Risk Dropdown */}
            <select
              value={riskFilter}
              onChange={(e) => setRiskFilter(e.target.value)}
              className="bg-gray-950 border border-gray-800 rounded-xl px-3 py-2 text-gray-200 font-medium focus:outline-none cursor-pointer"
            >
              <option value="ALL">All Risk Levels</option>
              <option value="LOW">Low Risk</option>
              <option value="MEDIUM">Medium Risk</option>
              <option value="HIGH">High Risk</option>
            </select>

            {/* Environment Dropdown */}
            <select
              value={envFilter}
              onChange={(e) => setEnvFilter(e.target.value)}
              className="bg-gray-950 border border-gray-800 rounded-xl px-3 py-2 text-gray-200 font-medium focus:outline-none cursor-pointer uppercase"
            >
              <option value="ALL">All Envs</option>
              <option value="prod">Prod</option>
              <option value="staging">Staging</option>
              <option value="dev">Dev</option>
              <option value="qa">QA</option>
            </select>

            {/* Sort Toggle */}
            <button
              onClick={() => {
                setSortOrder(sortOrder === 'desc' ? 'asc' : 'desc');
              }}
              className="flex items-center gap-1.5 px-3 py-2 bg-gray-950 border border-gray-800 rounded-xl text-gray-300 hover:text-white transition font-medium"
              title="Toggle sort direction"
            >
              <ArrowUpDown className="w-3.5 h-3.5 text-blue-400" />
              <span>{sortOrder === 'desc' ? 'Highest Savings First' : 'Lowest Savings First'}</span>
            </button>
          </div>
        </div>
      </div>

      {/* 3. Recommendations List */}
      <div className="space-y-3.5">
        {sortedRecs.length === 0 ? (
          <div className="bg-gray-900 border border-gray-800 rounded-2xl p-12 text-center text-gray-500">
            <Lightbulb className="w-8 h-8 mx-auto mb-2 opacity-40 text-gray-400" />
            <p className="font-semibold text-gray-300">No recommendations match the selected filters.</p>
            <p className="text-xs text-gray-500 mt-1">Adjust your filters to see all rightsizing candidates.</p>
          </div>
        ) : (
          sortedRecs.map((rec) => {
            const isUpdating = isUpdatingId === rec.id;
            const isInsufficient =
              rec.action === 'INSUFFICIENT_DATA' || rec.status === 'INSUFFICIENT_DATA';
            const isHighUtil =
              rec.status === 'HIGH_UTILIZATION' || rec.action === 'KEEP_CURRENT';

            return (
              <div
                key={rec.id}
                className="bg-gray-900 border border-gray-800 hover:border-gray-700/80 rounded-2xl p-5 shadow-sm transition space-y-4"
              >
                {/* Header row */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div className="flex items-center gap-2.5 flex-wrap">
                    <span className="text-base font-bold text-white tracking-tight">
                      {rec.resource_name}
                    </span>
                    <span className="font-mono text-xs px-2 py-0.5 rounded bg-gray-950 text-gray-400 border border-gray-800">
                      {rec.resource_id}
                    </span>
                    <span className="text-[9px] font-bold px-1.5 py-0.2 rounded bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 uppercase tracking-tight">
                      SIMULATED
                    </span>
                    <span
                      className={`text-[10px] font-bold px-2 py-0.5 rounded-full uppercase border ${
                        isInsufficient
                          ? 'bg-amber-500/15 text-amber-300 border-amber-500/30'
                          : getStatusBadgeClass(rec.status)
                      }`}
                    >
                      {rec.status.replace('_', ' ')}
                    </span>
                    <span className="text-[11px] text-gray-400">
                      {rec.region} • <span className="uppercase font-semibold">{rec.environment}</span>
                    </span>
                  </div>

                  <div className="flex items-center gap-2">
                    <span
                      className={`text-xs font-bold px-2.5 py-0.5 rounded border ${
                        isInsufficient
                          ? 'bg-gray-800 text-gray-400 border-gray-700'
                          : getRiskBadgeClass(rec.risk_level)
                      }`}
                    >
                      {rec.risk_level} RISK
                    </span>
                    <span className="text-xs text-gray-400">({rec.confidence_score}% confidence)</span>
                  </div>
                </div>

                {/* Sizing Comparison Cards */}
                <div className="grid grid-cols-1 md:grid-cols-4 gap-3 text-xs">
                  {/* Proposed Action */}
                  <div className="bg-gray-950/70 border border-gray-800 p-3 rounded-xl flex flex-col justify-between">
                    <span className="text-gray-400 font-medium">Proposed Action</span>
                    <div
                      className={`font-bold text-sm mt-1 ${
                        isInsufficient
                          ? 'text-amber-400'
                          : isHighUtil
                          ? 'text-gray-300'
                          : 'text-emerald-400'
                      }`}
                    >
                      {rec.action.replace('_', ' ')}
                    </div>
                    <span className="text-[11px] text-gray-500 mt-0.5">
                      {isInsufficient ? 'Metrics Insufficient (<24h)' : 'Peak Headroom Safe'}
                    </span>
                  </div>

                  {/* Current Configuration */}
                  <div className="bg-gray-950/70 border border-gray-800 p-3 rounded-xl flex flex-col justify-between">
                    <span className="text-gray-400 font-medium">Current Allocation</span>
                    <div className="font-mono text-gray-200 font-semibold mt-1">
                      {rec.current_configuration?.spec_display || rec.current_spec}
                    </div>
                    <span className="text-rose-400 font-mono mt-0.5">
                      {formatINR(rec.current_cost)} / mo
                    </span>
                  </div>

                  {/* Proposed Configuration */}
                  <div
                    className={`bg-gray-950/70 border p-3 rounded-xl flex flex-col justify-between ${
                      isInsufficient
                        ? 'border-amber-900/40'
                        : 'border-blue-900/40'
                    }`}
                  >
                    <span className="text-gray-400 font-medium">Target Recommendation</span>
                    <div className="font-mono text-blue-300 font-semibold mt-1">
                      {isInsufficient
                        ? '(Insufficient Data - No Guess)'
                        : rec.recommended_spec}
                    </div>
                    <span className="text-emerald-400 font-mono mt-0.5">
                      {isInsufficient ? 'N/A' : `${formatINR(rec.recommended_cost)} / mo`}
                    </span>
                  </div>

                  {/* Projected Savings */}
                  <div className="bg-emerald-950/20 border border-emerald-800/40 p-3 rounded-xl flex flex-col justify-between">
                    <span className="text-emerald-300/80 font-medium">Projected Savings</span>
                    <div className="text-emerald-400 font-mono font-bold text-lg mt-0.5">
                      +{formatINR(rec.monthly_savings)}
                      <span className="text-xs font-normal text-emerald-400/80 ml-1">/mo</span>
                    </div>
                    <span className="text-[11px] text-emerald-400 font-medium">
                      {rec.savings_pct}% monthly cost reduction
                    </span>
                  </div>
                </div>

                {/* Evidence & Justification Box */}
                <div className="bg-gray-950/50 border border-gray-800/80 rounded-xl p-3.5 text-xs space-y-2">
                  <div className="flex items-center justify-between flex-wrap gap-2">
                    <div className="flex items-center gap-2 text-gray-200 font-semibold">
                      <ShieldCheck className="w-4 h-4 text-cyan-400" />
                      <span>Rightsizing Engine Evidence & Peak Load Analysis:</span>
                    </div>

                    {rec.evidence && (
                      <div className="flex items-center gap-3 font-mono text-[11px]">
                        {rec.evidence.p95_cpu !== undefined && (
                          <span className="text-cyan-400">
                            P95 CPU: <span className="text-white">{rec.evidence.p95_cpu}%</span>
                          </span>
                        )}
                        {rec.evidence.p99_cpu !== undefined && (
                          <span className="text-blue-400">
                            Peak P99 CPU: <span className="text-white">{rec.evidence.p99_cpu}%</span>
                          </span>
                        )}
                        {rec.evidence.p95_ram !== undefined && (
                          <span className="text-purple-400">
                            P95 RAM: <span className="text-white">{rec.evidence.p95_ram}%</span>
                          </span>
                        )}
                        {rec.evidence.sample_count !== undefined && (
                          <span className="text-gray-400">
                            ({rec.evidence.sample_count} samples)
                          </span>
                        )}
                      </div>
                    )}
                  </div>

                  <p className="text-gray-300 leading-relaxed pl-6">{rec.justification}</p>

                  {isInsufficient && (
                    <div className="pl-6 pt-1 flex items-center gap-1.5 text-amber-400 text-[11px]">
                      <AlertTriangle className="w-3.5 h-3.5 min-w-3.5" />
                      <span>
                        Deterministic safety policy: Engine will not estimate rightsizing without at least 24 hourly samples.
                      </span>
                    </div>
                  )}
                </div>

                {/* Footer Controls: Inspect Telemetry & Accept/Reject Buttons */}
                <div className="pt-2 flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-t border-gray-800/80 text-xs">
                  <button
                    onClick={() => onSelectResource(rec)}
                    className="flex items-center gap-1.5 text-blue-400 hover:text-blue-300 font-medium transition"
                  >
                    <ExternalLink className="w-3.5 h-3.5" />
                    <span>Inspect 30-Day Telemetry & Sizing Headroom</span>
                  </button>

                  <div className="flex items-center gap-2 self-end sm:self-auto">
                    {isInsufficient ? (
                      <span className="text-gray-500 font-medium italic">
                        Action disabled (insufficient data)
                      </span>
                    ) : rec.status === 'ACCEPTED' ? (
                      <div className="flex items-center gap-2">
                        <span className="flex items-center gap-1.5 text-emerald-400 font-medium px-3 py-1.5 bg-emerald-500/10 border border-emerald-500/20 rounded-xl">
                          <CheckCircle2 className="w-3.5 h-3.5" />
                          <span>Accepted & Scheduled</span>
                        </span>
                        <button
                          disabled={isUpdating}
                          onClick={() => onUpdateStatus(rec.id, 'PENDING')}
                          className="p-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-gray-200 transition"
                          title="Reset to Pending"
                        >
                          <RotateCcw className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    ) : rec.status === 'REJECTED' ? (
                      <div className="flex items-center gap-2">
                        <span className="flex items-center gap-1.5 text-gray-400 font-medium px-3 py-1.5 bg-gray-800 border border-gray-700 rounded-xl">
                          <X className="w-3.5 h-3.5" />
                          <span>Rejected</span>
                        </span>
                        <button
                          disabled={isUpdating}
                          onClick={() => onUpdateStatus(rec.id, 'PENDING')}
                          className="p-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-gray-200 transition"
                          title="Reset to Pending"
                        >
                          <RotateCcw className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    ) : (
                      <>
                        <button
                          disabled={isUpdating}
                          onClick={() => onUpdateStatus(rec.id, 'REJECTED')}
                          className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-rose-300 hover:text-white bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/30 transition disabled:opacity-50 font-medium"
                        >
                          <X className="w-3.5 h-3.5" />
                          <span>Reject</span>
                        </button>

                        <button
                          disabled={isUpdating}
                          onClick={() => onUpdateStatus(rec.id, 'ACCEPTED')}
                          className="flex items-center gap-1.5 px-4 py-1.5 rounded-xl text-white bg-emerald-600 hover:bg-emerald-500 shadow-md shadow-emerald-600/20 transition disabled:opacity-50 font-semibold"
                        >
                          <Check className="w-3.5 h-3.5" />
                          <span>Accept & Apply</span>
                        </button>
                      </>
                    )}
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
