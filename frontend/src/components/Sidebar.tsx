import React from 'react';
import {
  LayoutDashboard,
  Server,
  Lightbulb,
  Activity,
  Settings,
  Cloud,
  ChevronLeft,
  ChevronRight,
  ShieldCheck,
  Building2,
} from 'lucide-react';

export type PageId = 'overview' | 'resources' | 'recommendations' | 'monitoring' | 'settings' | 'hosting-platform';

interface SidebarProps {
  activePage: PageId;
  onPageChange: (page: PageId) => void;
  pendingRecCount: number;
  alertCount: number;
  collapsed: boolean;
  onToggleCollapse: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  activePage,
  onPageChange,
  pendingRecCount,
  alertCount,
  collapsed,
  onToggleCollapse,
}) => {
  const navItems = [
    {
      id: 'overview' as PageId,
      label: 'Overview',
      icon: LayoutDashboard,
      badge: null,
    },
    {
      id: 'hosting-platform' as PageId,
      label: 'Hosting & VMs',
      icon: Building2,
      badge: 'Stage 6',
      badgeColor: 'bg-purple-500/20 text-purple-300 border border-purple-500/30',
    },
    {
      id: 'resources' as PageId,
      label: 'Resources',
      icon: Server,
      badge: null,
    },
    {
      id: 'recommendations' as PageId,
      label: 'Recommendations',
      icon: Lightbulb,
      badge: pendingRecCount > 0 ? pendingRecCount : null,
      badgeColor: 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30',
    },
    {
      id: 'monitoring' as PageId,
      label: 'Monitoring',
      icon: Activity,
      badge: alertCount > 0 ? alertCount : null,
      badgeColor: 'bg-rose-500/20 text-rose-400 border border-rose-500/30',
    },
    {
      id: 'settings' as PageId,
      label: 'Settings',
      icon: Settings,
      badge: null,
    },
  ];

  return (
    <aside
      className={`fixed top-0 bottom-0 left-0 z-40 flex flex-col bg-gray-900 border-r border-gray-800 transition-all duration-300 ${
        collapsed ? 'w-20' : 'w-64'
      }`}
    >
      {/* Brand Header */}
      <div className="h-16 flex items-center justify-between px-4 border-b border-gray-800">
        <div className="flex items-center gap-3 overflow-hidden">
          <div className="w-10 h-10 min-w-10 rounded-xl bg-gradient-to-tr from-cyan-600 to-blue-600 flex items-center justify-center shadow-lg shadow-blue-500/20">
            <Cloud className="w-5 h-5 text-white" />
          </div>
          {!collapsed && (
            <div className="truncate">
              <div className="flex items-center gap-1.5">
                <span className="font-bold text-white tracking-tight">SmartCloud</span>
                <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-cyan-500/20 text-cyan-400 border border-cyan-500/30">
                  Optimizer
                </span>
              </div>
              <p className="text-[11px] text-gray-400 truncate">Cloud Cost & Efficiency</p>
            </div>
          )}
        </div>
      </div>

      {/* Navigation Links */}
      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        <div className="mb-2">
          {!collapsed && (
            <span className="px-3 text-[10px] font-semibold tracking-wider text-gray-500 uppercase">
              Navigation
            </span>
          )}
        </div>

        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = activePage === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onPageChange(item.id)}
              title={collapsed ? item.label : undefined}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all ${
                isActive
                  ? 'bg-blue-600 text-white shadow-md shadow-blue-600/30 font-semibold'
                  : 'text-gray-400 hover:text-gray-100 hover:bg-gray-800/60'
              }`}
            >
              <Icon className={`w-5 h-5 min-w-5 ${isActive ? 'text-white' : 'text-gray-400'}`} />
              {!collapsed && (
                <div className="flex-1 flex items-center justify-between text-left truncate">
                  <span className="truncate">{item.label}</span>
                  {item.badge !== null && (
                    <span
                      className={`text-[11px] px-2 py-0.5 rounded-full font-bold ${
                        item.badgeColor || 'bg-gray-800 text-gray-300'
                      }`}
                    >
                      {item.badge}
                    </span>
                  )}
                </div>
              )}
            </button>
          );
        })}
      </nav>

      {/* Infrastructure Stage Badge & Collapse Toggle */}
      <div className="p-3 border-t border-gray-800 space-y-2">
        {!collapsed && (
          <div className="p-2.5 rounded-xl bg-gray-950/60 border border-gray-800 text-xs">
            <div className="flex items-center gap-2 text-emerald-400 mb-1 font-medium">
              <ShieldCheck className="w-3.5 h-3.5" />
              <span>Stage 1 Base Frontend</span>
            </div>
            <p className="text-[11px] text-gray-400 leading-relaxed">
              Standalone prototype. Ready for backend API integrations.
            </p>
          </div>
        )}

        <button
          onClick={onToggleCollapse}
          className="w-full flex items-center justify-center gap-2 px-3 py-2 text-xs font-medium text-gray-400 hover:text-gray-200 bg-gray-950/40 hover:bg-gray-800/60 rounded-lg border border-gray-800 transition"
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {collapsed ? (
            <ChevronRight className="w-4 h-4" />
          ) : (
            <>
              <ChevronLeft className="w-4 h-4" />
              <span>Collapse Sidebar</span>
            </>
          )}
        </button>
      </div>
    </aside>
  );
};
