import React from 'react';
import {
  IndianRupee,
  PiggyBank,
  Server,
  Lightbulb,
  TrendingDown,
  ArrowDownRight,
  TrendingUp,
  MapPin,
  ArrowRight,
  ShieldCheck,
  CheckCircle2,
  Clock,
} from 'lucide-react';
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend,
} from 'recharts';
import { DashboardSummary, Recommendation, SpendingHistoryPoint } from '../types';
import { MOCK_SPENDING_HISTORY } from '../services/mockData';
import { formatINR, getRiskBadgeClass } from '../utils/formatters';

interface OverviewPageProps {
  summary: DashboardSummary | null;
  recommendations: Recommendation[];
  onSelectResource: (rec: Recommendation) => void;
  onNavigate: (page: any) => void;
}

export const OverviewPage: React.FC<OverviewPageProps> = ({
  summary,
  recommendations,
  onSelectResource,
  onNavigate,
}) => {
  const data = summary || {
    total_resources: 138,
    current_monthly_cost: 1485000,
    projected_cost: 1042200,
    total_savings: 442800,
    savings_percentage: 29.8,
    total_recommendations: 10,
    accepted_recommendations: 2,
    pending_recommendations: 7,
    rejected_recommendations: 1,
    idle_resources_count: 5,
  };

  const pendingRecs = recommendations
    .filter((r) => r.status === 'PENDING')
    .slice(0, 4);

  // Regional breakdown calculations
  const regionalStats = [
    { name: 'Bangalore (BLR)', count: '48 VMs', cost: 650000, savings: 215000, color: '#3b82f6' },
    { name: 'Mumbai (BOM)', count: '52 VMs', cost: 580000, savings: 178000, color: '#10b981' },
    { name: 'Noida (DEL)', count: '38 VMs', cost: 255000, savings: 89000, color: '#f59e0b' },
  ];

  return (
    <div className="space-y-6">
      {/* 1. Key Metrics Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Current Monthly Cost */}
        <div className="bg-gray-900 border border-gray-800 hover:border-gray-700 rounded-2xl p-5 transition-all shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-gray-400 text-xs font-medium uppercase tracking-wider">
              Current Monthly Cost
            </span>
            <div className="w-10 h-10 rounded-xl bg-rose-500/10 border border-rose-500/20 flex items-center justify-center">
              <IndianRupee className="w-5 h-5 text-rose-400" />
            </div>
          </div>
          <div className="mt-3">
            <div className="text-2xl font-bold text-white tracking-tight">
              {formatINR(data.current_monthly_cost)}
            </div>
            <div className="mt-1 flex items-center gap-1.5 text-xs text-rose-400 font-medium">
              <TrendingUp className="w-3.5 h-3.5" />
              <span>+40% in last 6 months</span>
            </div>
          </div>
        </div>

        {/* Potential Savings */}
        <div className="bg-gray-900 border border-gray-800 hover:border-gray-700 rounded-2xl p-5 transition-all shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-gray-400 text-xs font-medium uppercase tracking-wider">
              Potential Savings
            </span>
            <div className="w-10 h-10 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center">
              <PiggyBank className="w-5 h-5 text-emerald-400" />
            </div>
          </div>
          <div className="mt-3">
            <div className="text-2xl font-bold text-emerald-400 tracking-tight">
              {formatINR(data.total_savings)}
            </div>
            <div className="mt-1 flex items-center gap-1.5 text-xs text-emerald-400 font-medium">
              <ArrowDownRight className="w-3.5 h-3.5" />
              <span>{data.savings_percentage}% possible reduction</span>
            </div>
          </div>
        </div>

        {/* Total Resources */}
        <div className="bg-gray-900 border border-gray-800 hover:border-gray-700 rounded-2xl p-5 transition-all shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-gray-400 text-xs font-medium uppercase tracking-wider">
              Total Resources
            </span>
            <div className="w-10 h-10 rounded-xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center">
              <Server className="w-5 h-5 text-blue-400" />
            </div>
          </div>
          <div className="mt-3">
            <div className="text-2xl font-bold text-white tracking-tight">
              {data.total_resources} <span className="text-sm font-normal text-gray-400">items</span>
            </div>
            <div className="mt-1 flex items-center gap-2 text-xs text-gray-400">
              <span className="inline-block w-2 h-2 rounded-full bg-emerald-400"></span>
              <span>138 active across 3 DC regions</span>
            </div>
          </div>
        </div>

        {/* Actionable Recommendations */}
        <div className="bg-gray-900 border border-gray-800 hover:border-gray-700 rounded-2xl p-5 transition-all shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-gray-400 text-xs font-medium uppercase tracking-wider">
              Recommendations
            </span>
            <div className="w-10 h-10 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center">
              <Lightbulb className="w-5 h-5 text-amber-400" />
            </div>
          </div>
          <div className="mt-3">
            <div className="text-2xl font-bold text-white tracking-tight">
              {data.total_recommendations} <span className="text-sm font-normal text-gray-400">actions</span>
            </div>
            <div className="mt-1 flex items-center gap-3 text-xs">
              <span className="flex items-center gap-1 text-emerald-400">
                <CheckCircle2 className="w-3.5 h-3.5" />
                {data.accepted_recommendations} accepted
              </span>
              <span className="flex items-center gap-1 text-amber-400">
                <Clock className="w-3.5 h-3.5" />
                {data.pending_recommendations} pending
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* 2. Spending Trend Chart (Recharts) */}
      <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6 shadow-sm">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-6">
          <div>
            <div className="flex items-center gap-2">
              <TrendingDown className="w-5 h-5 text-blue-400" />
              <h2 className="text-base font-bold text-white tracking-tight">
                Monthly Cloud Spending & Optimization Target
              </h2>
            </div>
            <p className="text-xs text-gray-400 mt-1">
              Historical bill trajectory over 6 months vs projected cost trajectory post-optimization.
            </p>
          </div>

          <div className="flex items-center gap-4 text-xs font-medium">
            <div className="flex items-center gap-1.5">
              <span className="w-3 h-3 rounded-sm bg-rose-500/80"></span>
              <span className="text-gray-300">Actual Monthly Spend</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-3 h-3 rounded-sm bg-emerald-500/80"></span>
              <span className="text-gray-300">Optimized Target</span>
            </div>
          </div>
        </div>

        <div className="h-72 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={MOCK_SPENDING_HISTORY} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
              <defs>
                <linearGradient id="actualGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#f43f5e" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#f43f5e" stopOpacity={0.0} />
                </linearGradient>
                <linearGradient id="targetGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#10b981" stopOpacity={0.0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" vertical={false} />
              <XAxis dataKey="month" stroke="#6b7280" fontSize={11} tickLine={false} />
              <YAxis
                stroke="#6b7280"
                fontSize={10}
                tickLine={false}
                tickFormatter={(v) => `₹${(v / 100000).toFixed(1)}L`}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#111827',
                  borderColor: '#374151',
                  borderRadius: '0.75rem',
                  fontSize: '12px',
                  color: '#f3f4f6',
                }}
                formatter={(val: any, name: string) => [
                  formatINR(Number(val)),
                  name === 'actual_spend' ? 'Actual Spend' : 'Optimized Target',
                ]}
              />
              <Area
                type="monotone"
                dataKey="actual_spend"
                name="actual_spend"
                stroke="#f43f5e"
                strokeWidth={2}
                fillOpacity={1}
                fill="url(#actualGradient)"
              />
              <Area
                type="monotone"
                dataKey="optimized_target"
                name="optimized_target"
                stroke="#10b981"
                strokeWidth={2}
                strokeDasharray="4 4"
                fillOpacity={1}
                fill="url(#targetGradient)"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* 3. Bottom Row: Regional Breakdown & Quick Recommendations */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Regional Distribution */}
        <div className="bg-gray-900 border border-gray-800 rounded-2xl p-5 shadow-sm space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <MapPin className="w-4 h-4 text-blue-400" />
              <h3 className="text-sm font-semibold text-white">Regional Spend Breakdown</h3>
            </div>
            <span className="text-[11px] text-gray-400">3 Cloud Hubs</span>
          </div>

          <div className="space-y-3 pt-1">
            {regionalStats.map((reg) => (
              <div
                key={reg.name}
                className="bg-gray-950/60 border border-gray-800/80 rounded-xl p-3.5 space-y-2"
              >
                <div className="flex items-center justify-between text-xs">
                  <div className="flex items-center gap-2">
                    <span
                      className="w-2.5 h-2.5 rounded-full"
                      style={{ backgroundColor: reg.color }}
                    />
                    <span className="font-semibold text-gray-200">{reg.name}</span>
                  </div>
                  <span className="text-gray-400">{reg.count}</span>
                </div>

                <div className="flex items-center justify-between text-xs">
                  <span className="text-gray-400">Current Cost: {formatINR(reg.cost)}</span>
                  <span className="text-emerald-400 font-mono font-medium">
                    Save {formatINR(reg.savings)}
                  </span>
                </div>

                {/* Progress bar representing potential savings proportion */}
                <div className="w-full bg-gray-800 h-1.5 rounded-full overflow-hidden">
                  <div
                    className="bg-emerald-500 h-full rounded-full"
                    style={{ width: `${Math.round((reg.savings / reg.cost) * 100)}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Top Priority Recommendations */}
        <div className="lg:col-span-2 bg-gray-900 border border-gray-800 rounded-2xl p-5 shadow-sm space-y-4 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-emerald-400" />
                <h3 className="text-sm font-semibold text-white">Top High-Impact Recommendations</h3>
              </div>
              <button
                onClick={() => onNavigate('recommendations')}
                className="text-xs text-blue-400 hover:text-blue-300 font-medium flex items-center gap-1 transition"
              >
                <span>View all ({data.total_recommendations})</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </button>
            </div>

            <div className="space-y-2.5">
              {pendingRecs.map((rec) => (
                <div
                  key={rec.id}
                  onClick={() => onSelectResource(rec)}
                  className="group cursor-pointer bg-gray-950/60 hover:bg-gray-800/80 border border-gray-800 hover:border-gray-700 rounded-xl p-3 transition flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs"
                >
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-gray-200 group-hover:text-blue-400 transition">
                        {rec.resource_name}
                      </span>
                      <span
                        className={`text-[10px] font-bold px-1.5 py-0.5 rounded border ${getRiskBadgeClass(
                          rec.risk_level
                        )}`}
                      >
                        {rec.risk_level} RISK
                      </span>
                      <span className="text-[10px] text-gray-400 uppercase font-mono">
                        {rec.region}
                      </span>
                    </div>
                    <div className="text-[11px] text-gray-400">
                      <span>{rec.action}: </span>
                      <span className="text-gray-300 font-mono">{rec.current_spec}</span>
                      <span className="mx-1 text-gray-500">→</span>
                      <span className="text-blue-300 font-mono">{rec.recommended_spec}</span>
                    </div>
                  </div>

                  <div className="flex items-center justify-between sm:justify-end gap-3 self-end sm:self-auto">
                    <div className="text-right">
                      <span className="font-mono font-bold text-emerald-400 block">
                        +{formatINR(rec.monthly_savings)}/mo
                      </span>
                      <span className="text-[10px] text-emerald-400/80 font-medium">
                        {rec.savings_pct}% cut
                      </span>
                    </div>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onSelectResource(rec);
                      }}
                      className="px-2.5 py-1.5 rounded-lg bg-gray-800 group-hover:bg-blue-600 text-gray-300 group-hover:text-white transition font-medium"
                    >
                      Review
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="pt-2 border-t border-gray-800/80 flex items-center justify-between text-xs text-gray-400">
            <span>Recommendations respect p99 peak behavior to safeguard SLA availability.</span>
            <button
              onClick={() => onNavigate('recommendations')}
              className="text-blue-400 hover:underline font-medium"
            >
              Manage all recommendations →
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
