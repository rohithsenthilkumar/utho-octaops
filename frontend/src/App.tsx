import React, { useState, useEffect, useCallback } from 'react';
import { Cloud, Loader2 } from 'lucide-react';
import { Sidebar, PageId } from './components/Sidebar';
import { Header } from './components/Header';
import { Toast } from './components/Toast';
import { ResourceDetailModal } from './components/ResourceDetailModal';
import { OverviewPage } from './pages/OverviewPage';
import { ResourcesPage } from './pages/ResourcesPage';
import { RecommendationsPage } from './pages/RecommendationsPage';
import { MonitoringPage } from './pages/MonitoringPage';
import { SettingsPage } from './pages/SettingsPage';
import { HostingPlatformPage } from './pages/HostingPlatformPage';
import { LoginPage } from './pages/LoginPage';
import {
  DashboardSummary,
  Recommendation,
  Resource,
  AlertItem,
  AppSettings,
  ToastMessage,
  RecommendationStatus,
  UserProfile,
} from './types';
import {
  fetchDashboardSummary,
  fetchInventory,
  fetchRecommendations,
  updateRecommendationStatus,
  fetchAlerts,
  dismissAlert,
  fetchSettings,
  updateSettings,
  getAuthToken,
  fetchCurrentUser,
  logoutUser,
} from './services/api';
import { INITIAL_SETTINGS } from './services/mockData';

export default function App() {
  const [activePage, setActivePage] = useState<PageId>('overview');
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  // Authentication State
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);
  const [currentUser, setCurrentUser] = useState<UserProfile | null>(null);
  const [isCheckingAuth, setIsCheckingAuth] = useState<boolean>(true);

  // Core Data State
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [resources, setResources] = useState<Resource[]>([]);
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [settings, setSettings] = useState<AppSettings>(INITIAL_SETTINGS);

  // UI Interactive State
  const [selectedItem, setSelectedItem] = useState<Resource | Recommendation | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isUpdatingId, setIsUpdatingId] = useState<string | null>(null);
  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  const showToast = useCallback(
    (title: string, message?: string, type: 'success' | 'error' | 'info' | 'warning' = 'success') => {
      const id = `${Date.now()}-${Math.random()}`;
      setToasts((prev) => [...prev, { id, title, message, type }]);
      setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
      }, 4000);
    },
    []
  );

  const dismissToast = (id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  };

  // Verify stored session on mount
  useEffect(() => {
    let isMounted = true;

    const verifySession = async () => {
      const token = getAuthToken();
      if (!token) {
        if (isMounted) {
          setIsAuthenticated(false);
          setCurrentUser(null);
          setIsCheckingAuth(false);
        }
        return;
      }

      try {
        const user = await fetchCurrentUser();
        if (isMounted) {
          setCurrentUser(user);
          setIsAuthenticated(true);
          setIsCheckingAuth(false);
        }
      } catch (err) {
        console.warn('Session verification failed, logging out:', err);
        logoutUser();
        if (isMounted) {
          setIsAuthenticated(false);
          setCurrentUser(null);
          setIsCheckingAuth(false);
        }
      }
    };

    verifySession();

    // Listen for 401 unauthorized events from Axios interceptor
    const handleUnauthorized = () => {
      if (isMounted) {
        setIsAuthenticated(false);
        setCurrentUser(null);
        showToast('Session Expired', 'Please sign in again to continue.', 'warning');
      }
    };

    window.addEventListener('auth:unauthorized', handleUnauthorized);
    return () => {
      isMounted = false;
      window.removeEventListener('auth:unauthorized', handleUnauthorized);
    };
  }, [showToast]);

  // Load all initial state
  const loadData = useCallback(
    async (showNotification = false) => {
      setIsRefreshing(true);
      try {
        const [sumData, recData, resData, alertData, settingsData] = await Promise.all([
          fetchDashboardSummary(),
          fetchRecommendations(),
          fetchInventory(),
          fetchAlerts(),
          fetchSettings(),
        ]);

        setSummary(sumData);
        setRecommendations(recData);
        setResources(resData);
        setAlerts(alertData);
        setSettings(settingsData);

        if (showNotification) {
          showToast('Dashboard Refreshed', 'Telemetry and sizing models re-synchronized.', 'success');
        }
      } catch (err: any) {
        console.error('Data loading error:', err);
        showToast('Sync Notice', 'Backend API disconnected. Using Stage 1 local telemetry.', 'info');
      } finally {
        setIsRefreshing(false);
      }
    },
    [showToast]
  );

  useEffect(() => {
    if (isAuthenticated) {
      loadData(false);
    }
  }, [isAuthenticated, loadData]);

  const handleLoginSuccess = (user: UserProfile) => {
    setCurrentUser(user);
    setIsAuthenticated(true);
    showToast('Signed In', `Welcome back, ${user.full_name || user.email}!`, 'success');
  };

  const handleSignOut = () => {
    logoutUser();
    setIsAuthenticated(false);
    setCurrentUser(null);
    setActivePage('overview');
    showToast('Signed Out', 'You have been securely signed out.', 'info');
  };

  // Handle recommendation accept / reject
  const handleUpdateRecommendationStatus = async (id: string, newStatus: RecommendationStatus) => {
    setIsUpdatingId(id);
    try {
      await updateRecommendationStatus(id, newStatus);
      const rec = recommendations.find((r) => r.id === id);
      const actionLabel = newStatus === 'ACCEPTED' ? 'accepted & applied' : newStatus === 'REJECTED' ? 'rejected' : 'reset';
      showToast(
        `Recommendation ${actionLabel.toUpperCase()}`,
        `${rec?.resource_name || id}: ${newStatus === 'ACCEPTED' ? `Saves ₹${rec?.monthly_savings?.toLocaleString('en-IN') || 0}/mo` : 'No changes made.'}`,
        newStatus === 'ACCEPTED' ? 'success' : 'info'
      );
      // Re-fetch to update KPI cards immediately
      await loadData(false);
    } catch (err: any) {
      console.error('Update status failed', err);
      showToast('Error', 'Failed to update recommendation status', 'error');
    } finally {
      setIsUpdatingId(null);
    }
  };

  // Handle alert dismiss
  const handleDismissAlert = async (id: string) => {
    await dismissAlert(id);
    setAlerts((prev) => prev.filter((a) => a.id !== id));
    showToast('Alert Dismissed', 'Anomaly acknowledged and removed from active feed.', 'info');
  };

  // Handle drilldown by resource ID from alerts or table
  const handleSelectResourceById = (resourceId: string) => {
    const rec = recommendations.find(
      (r) => r.resource_id === resourceId || r.id === resourceId
    );
    if (rec) {
      setSelectedItem(rec);
      return;
    }
    const res = resources.find((r) => r.id === resourceId);
    if (res) {
      setSelectedItem(res);
      return;
    }
    // Fallback item
    setSelectedItem({
      id: resourceId,
      name: resourceId,
      type: 'VM',
      region: 'Bangalore',
      environment: 'prod',
      owner: 'Platform Team',
      specs: { vcpu: 16, ram_gb: 64 },
      current_spec_display: '16 vCPU, 64 GB RAM',
      status: 'ACTIVE',
      monthly_cost: 54000,
      created_at: '2024-01-01',
      mean_cpu: 18,
      p95_cpu: 28,
      p99_cpu: 32,
      mean_ram: 34,
      p95_ram: 44,
      p99_ram: 48,
    });
  };

  // Handle save settings
  const handleSaveSettings = async (newSettings: AppSettings) => {
    try {
      const saved = await updateSettings(newSettings);
      setSettings(saved);
      showToast('Settings Saved', 'Optimization thresholds and preferences updated.', 'success');
    } catch (err) {
      showToast('Save Error', 'Failed to save settings', 'error');
    }
  };

  const handleResetSettings = () => {
    setSettings({ ...INITIAL_SETTINGS });
    showToast('Settings Reset', 'Restored default sizing safety thresholds.', 'info');
  };

  const pendingRecCount = recommendations.filter((r) => r.status === 'PENDING').length;
  const activeAlertCount = alerts.length;

  // 1. Session Verification Loading Screen
  if (isCheckingAuth) {
    return (
      <div className="min-h-screen bg-gray-950 text-gray-100 flex flex-col items-center justify-center p-4">
        <div className="flex flex-col items-center gap-4">
          <div className="w-12 h-12 rounded-2xl bg-gradient-to-tr from-cyan-600 to-blue-600 flex items-center justify-center shadow-lg shadow-blue-500/20 animate-pulse border border-cyan-400/30">
            <Cloud className="w-6 h-6 text-white" />
          </div>
          <div className="flex items-center gap-2 text-sm text-gray-400">
            <Loader2 className="w-4 h-4 animate-spin text-cyan-400" />
            <span>Validating workspace session...</span>
          </div>
        </div>
      </div>
    );
  }

  // 2. Unauthenticated State -> Render Login Page
  if (!isAuthenticated) {
    return (
      <div className="min-h-screen bg-gray-950 text-gray-100">
        <Toast toasts={toasts} onDismiss={dismissToast} />
        <LoginPage onLoginSuccess={handleLoginSuccess} />
      </div>
    );
  }

  // 3. Authenticated State -> Render Full Dashboard
  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 flex font-sans selection:bg-blue-600 selection:text-white">
      {/* Toast Notifications */}
      <Toast toasts={toasts} onDismiss={dismissToast} />

      {/* Sidebar Navigation */}
      <Sidebar
        activePage={activePage}
        onPageChange={(page) => {
          setActivePage(page);
          setMobileMenuOpen(false);
        }}
        pendingRecCount={pendingRecCount}
        alertCount={activeAlertCount}
        collapsed={sidebarCollapsed}
        onToggleCollapse={() => setSidebarCollapsed(!sidebarCollapsed)}
      />

      {/* Mobile Drawer Backdrop */}
      {mobileMenuOpen && (
        <div
          onClick={() => setMobileMenuOpen(false)}
          className="fixed inset-0 z-30 bg-black/70 md:hidden"
        />
      )}

      {/* Main Content Area */}
      <div
        className={`flex-1 flex flex-col min-w-0 transition-all duration-300 ${
          sidebarCollapsed ? 'md:ml-20' : 'md:ml-64'
        }`}
      >
        {/* Top Header */}
        <Header
          activePage={activePage}
          onRefresh={() => loadData(true)}
          isRefreshing={isRefreshing}
          onToggleMobileMenu={() => setMobileMenuOpen(!mobileMenuOpen)}
          currentUser={currentUser}
          onSignOut={handleSignOut}
        />

        {/* Dynamic Page Rendering */}
        <main className="flex-1 p-4 sm:p-6 lg:p-8 max-w-7xl w-full mx-auto">
          {activePage === 'overview' && (
            <OverviewPage
              summary={summary}
              recommendations={recommendations}
              onSelectResource={(rec) => setSelectedItem(rec)}
              onNavigate={(page) => setActivePage(page)}
            />
          )}

          {activePage === 'hosting-platform' && (
            <HostingPlatformPage />
          )}

          {activePage === 'resources' && (
            <ResourcesPage
              onSelectResource={(res) => setSelectedItem(res)}
              onResourceCreated={(newRes) => {
                showToast(
                  'Resource Created in SQLite',
                  `${newRes.name} (${newRes.id}) saved to backend.`,
                  'success'
                );
                loadData(false);
              }}
            />
          )}

          {activePage === 'recommendations' && (
            <RecommendationsPage
              recommendations={recommendations}
              onUpdateStatus={handleUpdateRecommendationStatus}
              onSelectResource={(rec) => setSelectedItem(rec)}
              isUpdatingId={isUpdatingId}
            />
          )}

          {activePage === 'monitoring' && (
            <MonitoringPage
              alerts={alerts}
              onDismissAlert={handleDismissAlert}
              onSelectResourceById={handleSelectResourceById}
            />
          )}

          {activePage === 'settings' && (
            <SettingsPage
              settings={settings}
              onSaveSettings={handleSaveSettings}
              onResetSettings={handleResetSettings}
            />
          )}
        </main>

        {/* Footer */}
        <footer className="border-t border-gray-900 bg-gray-950/80 px-6 py-4 text-xs text-gray-500 flex flex-col sm:flex-row items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-gray-400">SmartCloud Optimizer</span>
            <span>•</span>
            <span>Stage 1 Base Frontend Prototype</span>
          </div>
          <div>
            Indian SaaS Cloud Infrastructure: Bangalore • Mumbai • Noida
          </div>
        </footer>
      </div>

      {/* Resource Detail & Telemetry Modal */}
      {selectedItem && (
        <ResourceDetailModal
          item={selectedItem}
          recommendation={
            (selectedItem as any).action
              ? (selectedItem as Recommendation)
              : recommendations.find(
                  (r) => r.resource_id === selectedItem.id || r.id === selectedItem.id
                ) || null
          }
          onClose={() => setSelectedItem(null)}
          onUpdateStatus={handleUpdateRecommendationStatus}
          isUpdating={isUpdatingId !== null}
        />
      )}
    </div>
  );
}
