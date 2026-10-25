import React from 'react';
import { RefreshCw, MapPin, Menu, Database, LogOut, User as UserIcon, Building, ShieldCheck } from 'lucide-react';
import { PageId } from './Sidebar';
import { UserProfile } from '../types';

interface HeaderProps {
  activePage: PageId;
  onRefresh: () => void;
  isRefreshing: boolean;
  onToggleMobileMenu: () => void;
  currentUser?: UserProfile | null;
  onSignOut?: () => void;
}

const PAGE_META: Record<PageId, { title: string; subtitle: string }> = {
  overview: {
    title: 'Fleet Cost & Sizing Overview',
    subtitle: 'High-level cost summary, potential savings, and regional distribution across Indian SaaS infrastructure.',
  },
  resources: {
    title: 'Cloud Resource Inventory',
    subtitle: 'Catalog of 138 provisioned VMs, block storage volumes, and public IPs with utilization statistics.',
  },
  recommendations: {
    title: 'Rightsizing & Cost Recommendations',
    subtitle: 'Safe, peak-aware configuration proposals designed to slash cloud waste without risking SLA breaches.',
  },
  monitoring: {
    title: 'Telemetry & Fleet Monitoring',
    subtitle: 'Real-time utilization curves, p95/p99 capacity tracking, and automated anomaly alert feeds.',
  },
  settings: {
    title: 'Application & Engine Settings',
    subtitle: 'Configure optimization sensitivity thresholds, regional scopes, and notification channels.',
  },
  'hosting-platform': {
    title: 'Multi-Tenant Hosting Platform & VM Governance',
    subtitle: 'Hosting company tenant management, VM ownership delegation, RBAC, vertical scaling, and approval queues.',
  },
};

export const Header: React.FC<HeaderProps> = ({
  activePage,
  onRefresh,
  isRefreshing,
  onToggleMobileMenu,
  currentUser,
  onSignOut,
}) => {
  const meta = PAGE_META[activePage] || PAGE_META.overview;
  const isAdmin = currentUser?.role === 'COMPANY_ADMIN';

  return (
    <header className="sticky top-0 z-30 bg-gray-900/90 backdrop-blur border-b border-gray-800 text-gray-100">
      <div className="px-4 sm:px-6 lg:px-8 py-3.5 flex flex-col md:flex-row md:items-center justify-between gap-4">
        {/* Left: Mobile hamburger & Page Title */}
        <div className="flex items-center gap-3">
          <button
            onClick={onToggleMobileMenu}
            className="md:hidden p-2 rounded-lg text-gray-400 hover:text-white hover:bg-gray-800 focus:outline-none"
            aria-label="Toggle Navigation Menu"
          >
            <Menu className="w-5 h-5" />
          </button>

          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-lg sm:text-xl font-bold text-white tracking-tight">
                {meta.title}
              </h1>
            </div>
            <p className="text-xs text-gray-400 hidden sm:block mt-0.5">
              {meta.subtitle}
            </p>
          </div>
        </div>

        {/* Right: User Profile, Regional Badges, Refresh & Sign Out */}
        <div className="flex items-center flex-wrap gap-2.5 self-end md:self-auto">
          {/* Authenticated User Pill */}
          {currentUser && (
            <div className="flex items-center gap-2 bg-gray-950/80 border border-gray-800 px-3 py-1.5 rounded-xl text-xs">
              <div className="w-6 h-6 rounded-lg bg-gray-800 border border-gray-700 flex items-center justify-center text-gray-300 shrink-0">
                <UserIcon className="w-3.5 h-3.5" />
              </div>
              <div className="text-left hidden sm:block">
                <div className="flex items-center gap-1.5 leading-tight">
                  <span className="font-semibold text-gray-200 truncate max-w-[130px]">
                    {currentUser.full_name || currentUser.email}
                  </span>
                  <span
                    className={`text-[9px] px-1.5 py-0.2 rounded border font-mono font-bold ${
                      isAdmin
                        ? 'bg-purple-500/20 text-purple-300 border-purple-500/40'
                        : 'bg-blue-500/20 text-blue-300 border-blue-500/40'
                    }`}
                  >
                    {isAdmin ? 'ADMIN' : 'VM_OWNER'}
                  </span>
                </div>
                <div className="text-[10px] text-gray-400 flex items-center gap-1 truncate max-w-[160px]">
                  <Building className="w-2.5 h-2.5 text-gray-500" />
                  <span>{currentUser.company_name || currentUser.tenant_id}</span>
                </div>
              </div>
            </div>
          )}

          {/* Data Center Region Badges */}
          <div className="hidden xl:flex items-center gap-1.5 bg-gray-950/70 border border-gray-800 px-3 py-1.5 rounded-xl text-xs text-gray-400">
            <MapPin className="w-3.5 h-3.5 text-blue-400" />
            <span className="font-medium text-gray-300">Regions:</span>
            <span className="px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-300 font-mono text-[11px]">BLR</span>
            <span className="px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-300 font-mono text-[11px]">BOM</span>
            <span className="px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-300 font-mono text-[11px]">DEL</span>
          </div>

          {/* Mode Pill */}
          <div className="flex items-center gap-1.5 bg-gray-950/70 border border-gray-800 px-3 py-1.5 rounded-xl text-xs">
            <Database className="w-3.5 h-3.5 text-purple-400" />
            <span className="text-gray-300 font-medium">Stage 6</span>
            <span className="text-[10px] text-gray-400">RBAC & Scaling</span>
          </div>

          {/* Refresh Button */}
          <button
            onClick={onRefresh}
            disabled={isRefreshing}
            className="flex items-center gap-2 px-3 py-1.5 bg-gray-800 hover:bg-gray-700 active:bg-gray-800 text-gray-200 hover:text-white rounded-xl text-xs font-medium border border-gray-700 transition shadow-sm disabled:opacity-50"
            title="Refresh dashboard state"
          >
            <RefreshCw className={`w-3.5 h-3.5 text-blue-400 ${isRefreshing ? 'animate-spin' : ''}`} />
            <span className="hidden sm:inline">Refresh Data</span>
          </button>

          {/* Sign Out Button */}
          {onSignOut && (
            <button
              onClick={onSignOut}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-rose-500/10 hover:bg-rose-500/20 active:bg-rose-500/30 text-rose-300 hover:text-rose-200 rounded-xl text-xs font-medium border border-rose-500/30 transition shadow-sm"
              title="Sign out of current workspace"
            >
              <LogOut className="w-3.5 h-3.5 text-rose-400" />
              <span>Sign Out</span>
            </button>
          )}
        </div>
      </div>
    </header>
  );
};
