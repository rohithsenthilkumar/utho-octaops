import axios from 'axios';
import {
  Resource,
  Recommendation,
  DashboardSummary,
  AlertItem,
  TelemetryPoint,
  AppSettings,
  RecommendationStatus,
  ResourceCreatePayload,
  LocalHostMetric,
  AutoscalingStatus,
  DockerWorkloadMetric,
  StorageTelemetryData,
} from '../types';


import {
  MOCK_RESOURCES,
  MOCK_RECOMMENDATIONS,
  MOCK_ALERTS,
  INITIAL_SETTINGS,
  generate30DayTelemetry,
} from './mockData';

const getBaseURL = () => {
  if (typeof process !== 'undefined' && process.env && process.env.NODE_ENV === 'test') {
    return 'http://127.0.0.1:8000/api';
  }
  return '/api';
};

const api = axios.create({
  baseURL: getBaseURL(),
  timeout: 5000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// In-memory storage fallback for Node.js / test environments where browser localStorage is not present
class MemoryStorage {
  private store: Record<string, string> = {};
  getItem(key: string): string | null {
    return this.store[key] ?? null;
  }
  setItem(key: string, value: string): void {
    this.store[key] = String(value);
  }
  removeItem(key: string): void {
    delete this.store[key];
  }
  clear(): void {
    this.store = {};
  }
}

const memoryStorage = new MemoryStorage();

const getStorage = () => {
  if (typeof localStorage !== 'undefined') {
    return localStorage;
  }
  return memoryStorage;
};

// Attach bearer token dynamically from storage only if present
api.interceptors.request.use((config) => {
  const storage = getStorage();
  const token = storage.getItem('smartcloud_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
    config.headers['X-Auth-Token'] = token;
    const demoEmail = storage.getItem('smartcloud_demo_user');
    if (demoEmail) {
      config.headers['X-Demo-User'] = demoEmail;
    }
  } else {
    // Never treat demo user as proof of authentication
    if (config.headers) {
      delete config.headers.Authorization;
      delete config.headers['X-Auth-Token'];
      delete config.headers['X-Demo-User'];
    }
  }
  return config;
});

// Intercept 401 Unauthorized responses to clear invalid/expired sessions
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error?.response?.status === 401) {
      getStorage().removeItem('smartcloud_token');
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent('auth:unauthorized'));
      }
    }
    // Remove non-cloneable Axios config object so test runners (Vitest/Node) don't throw DataCloneError
    if (error && error.config) {
      delete error.config;
    }
    return Promise.reject(error);
  }
);

export const getAuthToken = (): string | null => {
  return getStorage().getItem('smartcloud_token');
};

export const isAuthenticated = (): boolean => {
  return Boolean(getAuthToken());
};

export const logoutUser = (): void => {
  const storage = getStorage();
  storage.removeItem('smartcloud_token');
  storage.removeItem('smartcloud_demo_user');
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('auth:logout'));
  }
};

// In-memory state for local persistence in Stage 1
let localRecommendations: Recommendation[] = [...MOCK_RECOMMENDATIONS];
let localResources: Resource[] = [...MOCK_RESOURCES];
let localAlerts: AlertItem[] = [...MOCK_ALERTS];
let localSettings: AppSettings = { ...INITIAL_SETTINGS };

export const fetchDashboardSummary = async (): Promise<DashboardSummary> => {
  try {
    const res = await api.get('/dashboard/summary');
    return res.data;
  } catch (err) {
    console.warn('API /dashboard/summary failed, dynamic calculation fallback:', err);
    const total_resources = localResources.length;
    const current_monthly_cost = localResources.reduce((acc, r) => acc + (r.monthly_cost || 0), 0);
    const total_savings = localRecommendations.reduce((acc, r) => acc + (r.monthly_savings || 0), 0);
    const projected_cost = Math.max(0, current_monthly_cost - total_savings);
    const savings_percentage = current_monthly_cost > 0 ? +((total_savings / current_monthly_cost) * 100).toFixed(1) : 0;

    const accepted_count = localRecommendations.filter(
      (r) => r.status.toUpperCase() === 'ACCEPTED'
    ).length;
    const pending_count = localRecommendations.filter(
      (r) => r.status.toUpperCase() === 'PENDING'
    ).length;
    const rejected_count = localRecommendations.filter(
      (r) => r.status.toUpperCase() === 'REJECTED'
    ).length;
    const idle_count = localResources.filter(
      (r) => r.status === 'IDLE' || r.status === 'ORPHANED'
    ).length;

    return {
      total_resources,
      current_monthly_cost,
      projected_cost,
      total_savings,
      savings_percentage,
      total_recommendations: localRecommendations.length,
      accepted_recommendations: accepted_count,
      pending_recommendations: pending_count,
      rejected_recommendations: rejected_count,
      idle_resources_count: idle_count,
    };
  }
};

const mapBackendResource = (item: any): Resource => {
  const vcpu = item.cpu_cores || item.specs?.vcpu || 4;
  const ram = item.memory || item.specs?.ram_gb || 16;
  const util = item.cpu_utilization !== undefined ? item.cpu_utilization : item.p99_cpu || 20.0;
  const cost = item.estimated_monthly_cost !== undefined ? item.estimated_monthly_cost : item.monthly_cost || 0;

  return {
    id: item.id,
    name: item.name,
    type: item.resource_type || item.type || 'VM',
    region: item.region || 'Bangalore',
    environment: item.environment || 'prod',
    owner: item.owner || 'Platform Team',
    specs: {
      vcpu,
      ram_gb: ram,
    },
    current_spec_display: item.current_spec_display || `${vcpu} vCPU, ${ram} GB RAM`,
    status: item.status || 'ACTIVE',
    monthly_cost: cost,
    created_at: item.created_at || new Date().toISOString(),
    cpu_cores: vcpu,
    memory: ram,
    cpu_utilization: util,
    is_simulated: item.is_simulated ?? true,
    tenant_id: item.tenant_id,
    owner_id: item.owner_id,
    owner_email: item.owner_email,
    policy: item.policy,
    docker_container_name: item.docker_container_name,
    mean_cpu: item.mean_cpu || +(util * 0.6).toFixed(1),
    p95_cpu: item.p95_cpu || +(util * 0.9).toFixed(1),
    p99_cpu: item.p99_cpu || util,
    mean_ram: item.mean_ram || 28.0,
    p95_ram: item.p95_ram || 40.0,
    p99_ram: item.p99_ram || 45.0,
  };
};

export const fetchInventory = async (): Promise<Resource[]> => {
  try {
    const res = await api.get('/resources');
    if (Array.isArray(res.data) && res.data.length > 0) {
      return res.data.map(mapBackendResource);
    }
    return localResources;
  } catch (err) {
    console.warn('API /resources failed, falling back to local list:', err);
    return [...localResources];
  }
};

export const createResource = async (payload: ResourceCreatePayload): Promise<Resource> => {
  const res = await api.post('/resources', payload);
  return mapBackendResource(res.data);
};

export const fetchHealth = async (): Promise<any> => {
  const res = await api.get('/health');
  return res.data;
};

const mapBackendRecommendation = (item: any): Recommendation => {
  const currentSpec = item.current_configuration?.spec_display || item.current_spec || '16 vCPU, 64 GB RAM';
  const proposedSpec = item.proposed_configuration
    ? item.proposed_configuration.spec_display || item.recommended_spec
    : item.action === 'INSUFFICIENT_DATA'
    ? '(Insufficient Metrics)'
    : '(Maintain Allocation)';
  const currentCost = item.estimated_monthly_cost_before ?? item.current_cost ?? 0;
  const proposedCost = item.estimated_monthly_cost_after ?? item.recommended_cost ?? currentCost;
  const savings = item.estimated_inr_savings ?? item.monthly_savings ?? (currentCost - proposedCost);
  const savingsPct = item.savings_percentage ?? item.savings_pct ?? 0;

  return {
    id: item.recommendation_id || item.id,
    resource_id: item.resource_id,
    resource_name: item.resource_name,
    resource_type: (item.resource_type || 'VM') as any,
    region: item.region || 'Bangalore',
    environment: item.environment || 'prod',
    action: item.action || 'DOWNSIZE',
    current_spec: currentSpec,
    recommended_spec: proposedSpec,
    current_cost: currentCost,
    recommended_cost: proposedCost,
    monthly_savings: savings,
    savings_pct: savingsPct,
    risk_level: (item.risk_level || 'LOW') as any,
    confidence_score: item.confidence_score || (item.risk_level === 'LOW' ? 95 : item.risk_level === 'MEDIUM' ? 85 : 70),
    status: (item.status || 'PENDING') as any,
    justification: item.justification || '',
    peak_behavior: item.evidence ? `P95 CPU: ${item.evidence.p95_cpu}% | P95 RAM: ${item.evidence.p95_ram}% (Safety buffer: ${item.evidence.safety_buffer_pct}%)` : '',
    p95_cpu: item.evidence?.p95_cpu || item.p95_cpu || 20,
    p99_cpu: item.evidence?.p99_cpu || item.p99_cpu || 25,
    mean_cpu: item.evidence?.avg_cpu || item.mean_cpu || 15,
    p95_ram: item.evidence?.p95_ram || item.p95_ram || 30,
    p99_ram: item.evidence?.p99_ram || item.p99_ram || 35,
    mean_ram: item.evidence?.avg_ram || item.mean_ram || 25,
    burst_ratio: item.evidence?.burst_ratio || item.burst_ratio || 1.1,
    current_configuration: item.current_configuration,
    proposed_configuration: item.proposed_configuration,
    evidence: item.evidence,
    estimated_monthly_cost_before: currentCost,
    estimated_monthly_cost_after: proposedCost,
    estimated_inr_savings: savings,
    savings_percentage: savingsPct,
    is_simulated: item.is_simulated ?? true,
  };
};

export const fetchRightsizingRecommendations = async (): Promise<Recommendation[]> => {
  try {
    const res = await api.get('/recommendations/rightsizing');
    if (Array.isArray(res.data) && res.data.length > 0) {
      return res.data.map(mapBackendRecommendation);
    }
    return [...localRecommendations];
  } catch (err) {
    console.warn('API /recommendations/rightsizing failed, fallback:', err);
    return [...localRecommendations];
  }
};

export const fetchRecommendations = fetchRightsizingRecommendations;

export const updateRecommendationStatus = async (
  id: string,
  newStatus: RecommendationStatus
): Promise<{ success: boolean; id: string; status: RecommendationStatus }> => {
  try {
    const res = await api.post(`/recommendations/${id}/status`, { status: newStatus });
    localRecommendations = localRecommendations.map((r) =>
      r.id === id || r.resource_id === id ? { ...r, status: newStatus } : r
    );
    return res.data;
  } catch (_err) {
    localRecommendations = localRecommendations.map((r) =>
      r.id === id || r.resource_id === id ? { ...r, status: newStatus } : r
    );
    return { success: true, id, status: newStatus };
  }
};

export const fetchMetrics = async (resourceId: string): Promise<{
  resource_id: string;
  p99_cpu: number;
  p99_ram: number;
  data: TelemetryPoint[];
}> => {
  try {
    const res = await api.get(`/metrics/${resourceId}`);
    return res.data;
  } catch (_err) {
    const rec = localRecommendations.find(
      (r) => r.resource_id === resourceId || r.id === resourceId
    );
    const telemetry = generate30DayTelemetry(rec);
    return {
      resource_id: resourceId,
      p99_cpu: rec?.p99_cpu ?? 24.5,
      p99_ram: rec?.p99_ram ?? 38.2,
      data: telemetry,
    };
  }
};

export const fetchAlerts = async (): Promise<AlertItem[]> => {
  // Local-only alerts state; avoids obsolete HTTP calls while preserving UI alerts behavior
  return [...localAlerts];
};

export const dismissAlert = async (id: string): Promise<boolean> => {
  localAlerts = localAlerts.filter((a) => a.id !== id);
  return true;
};

export const fetchSettings = async (): Promise<AppSettings> => {
  // Local-only settings state; avoids obsolete HTTP calls while preserving UI settings behavior
  return { ...localSettings };
};

export const updateSettings = async (settings: AppSettings): Promise<AppSettings> => {
  localSettings = { ...settings };
  return { ...localSettings };
};

export const fetchLocalMonitoring = async (interval: number = 0.5): Promise<LocalHostMetric> => {
  try {
    const res = await api.get(`/monitoring/local?interval=${interval}`);
    return res.data;
  } catch (err) {
    // If backend is momentarily unreachable, return fallback with simulated local flag
    return {
      timestamp: new Date().toISOString(),
      cpu_utilization: 12.4,
      cpu_percent: 12.4,
      ram_utilization: 45.2,
      ram_percent: 45.2,
      used_ram_gb: 7.23,
      total_ram_gb: 16.0,
      used_ram_bytes: 7763394560,
      total_ram_bytes: 17179869184,
      sampling_interval_seconds: interval,
      metric_source: 'Live local host metrics (Fallback)',
      status: 'offline',
    };
  }
};

export const fetchDockerWorkloadTelemetry = async (): Promise<DockerWorkloadMetric> => {
  try {
    const res = await api.get('/monitoring/docker/workload');
    return res.data;
  } catch (_err) {
    return {
      timestamp: new Date().toISOString(),
      container_name: 'autoscaling-lab-app-1',
      status: 'disconnected',
      is_healthy: false,
      actual_cpu_percent: 0.0,
      actual_memory_mb: 0.0,
      actual_memory_limit_mb: 0.0,
      actual_memory_percent: 0.0,
      configured_cpu_cores: 2.0,
      configured_memory_gb: 1.0,
      is_unconstrained: false,
      limit_status: 'DISCONNECTED',
      running_replicas: 0,
      replicas_detail: [],
      gateway_url: 'http://127.0.0.1:8080',
      storage_resizing: 'NOT_CONFIGURED',
      metric_source: 'Docker daemon (disconnected)',
    };
  }
};

export const fetchStorageTelemetry = async (): Promise<StorageTelemetryData> => {
  try {
    const res = await api.get('/monitoring/storage');
    return res.data;
  } catch (_err) {
    return {
      telemetry: {
        mount_point: '/',
        filesystem_type: 'ext4',
        total_gb: 0.0,
        used_gb: 0.0,
        free_gb: 0.0,
        percent_used: 0.0,
        status: 'disconnected',
        timestamp: new Date().toISOString(),
        collection_source: 'Local host storage',
      },
      resizing_capability: {
        status: 'NOT_CONFIGURED',
        can_auto_expand: false,
        can_shrink: false,
        reason: 'Storage expansion requires cloud provider volume integration.',
        supported_cloud_providers: ['AWS EBS', 'GCP PD', 'Azure Managed Disk'],
        safety_constraints: ['Laptop root disk protected from resizing'],
      },
    };
  }
};

export const fetchAutoscalingStatus = async (): Promise<AutoscalingStatus> => {
  try {
    const res = await api.get('/autoscaling/status');
    return res.data;
  } catch (err) {
    // Fallback representation if backend is disconnected
    return {
      status: 'offline',
      timestamp: new Date().toISOString(),
      current_replicas: 1,
      target_replicas: 1,
      min_replicas: 1,
      max_replicas: 5,
      scale_out_threshold: 45.0,
      scale_in_threshold: 20.0,
      average_cpu_percent: 0.0,
      replicas_detail: [],
      is_healthy: false,
      remaining_cooldown_seconds: 0,
      last_action: 'DISCONNECTED',
      latest_decision: {
        timestamp: new Date().toISOString(),
        measured_cpu_percent: 0.0,
        previous_replicas: 1,
        new_replicas: 1,
        action: 'DISCONNECTED',
        reason: 'Backend autoscaler API is currently disconnected.',
        is_healthy: false,
      },
      recent_events: [],
      metric_history: [],
      load_balancer_url: 'http://127.0.0.1:8080',
      is_load_test_running: false,
    };
  }
};

export const triggerManualScale = async (targetReplicas: number): Promise<any> => {
  const res = await api.post('/autoscaling/scale', { target_replicas: targetReplicas });
  return res.data;
};

export const triggerK6LoadTest = async (vus: number = 20, duration: string = '20s'): Promise<any> => {
  const res = await api.post(`/autoscaling/load-test?vus=${vus}&duration=${duration}`);
  return res.data;
};

export const stopAutoscalingStack = async (): Promise<any> => {
  const res = await api.post('/autoscaling/stop');
  return res.data;
};

export const startAutoscalingStack = async (): Promise<any> => {
  const res = await api.post('/autoscaling/start');
  return res.data;
};

// =========================================================================
// Stage 6: Multi-Tenant Platform & VM Ownership API Methods
// =========================================================================

export const loginUser = async (email: string, password: string): Promise<any> => {
  const res = await api.post('/auth/login', { email, password });
  if (res.data.access_token) {
    const storage = getStorage();
    storage.setItem('smartcloud_token', res.data.access_token);
    if (res.data.user?.email) {
      storage.setItem('smartcloud_demo_user', res.data.user.email);
    }
  }
  return res.data;
};

export const switchDemoUser = async (email: string): Promise<any> => {
  const res = await api.post('/auth/switch-demo', { email });
  if (res.data.access_token) {
    const storage = getStorage();
    storage.setItem('smartcloud_token', res.data.access_token);
    if (res.data.user?.email) {
      storage.setItem('smartcloud_demo_user', res.data.user.email);
    }
  }
  return res.data;
};

export const fetchCurrentUser = async (): Promise<any> => {
  const res = await api.get('/auth/me');
  return res.data;
};

export const fetchCurrentCompany = async (): Promise<any> => {
  const res = await api.get('/tenants/current');
  return res.data;
};

export const fetchTenantUsers = async (): Promise<any[]> => {
  const res = await api.get('/tenants/users');
  return res.data;
};

export const fetchTenantResources = async (): Promise<Resource[]> => {
  const res = await api.get('/tenants/resources');
  return (res.data || []).map(mapBackendResource);
};

export const assignResourceOwner = async (resourceId: string, ownerId: string | null): Promise<any> => {
  const res = await api.post(`/tenants/resources/${resourceId}/assign`, { owner_id: ownerId });
  return res.data;
};

export const fetchResourcePolicy = async (resourceId: string): Promise<any> => {
  const res = await api.get(`/tenants/resources/${resourceId}/policy`);
  return res.data;
};

export const updateResourcePolicy = async (resourceId: string, policy: any): Promise<any> => {
  const res = await api.put(`/tenants/resources/${resourceId}/policy`, policy);
  return res.data;
};

export const fetchChangeRequests = async (): Promise<any[]> => {
  const res = await api.get('/tenants/change-requests');
  return res.data;
};

export const reviewChangeRequest = async (requestId: string, decision: 'APPROVED' | 'REJECTED', comment?: string): Promise<any> => {
  const res = await api.post(`/tenants/change-requests/${requestId}/review`, { decision, comment });
  return res.data;
};

export const executeVerticalScale = async (resourceId: string, targetCpu: number, targetMemoryGb: number, reason: string): Promise<any> => {
  const res = await api.post('/tenants/vertical-scale', {
    resource_id: resourceId,
    target_cpu_cores: targetCpu,
    target_memory_gb: targetMemoryGb,
    reason,
  });
  return res.data;
};

export const fetchAuditEvents = async (limit: number = 50): Promise<any[]> => {
  const res = await api.get(`/tenants/audit-events?limit=${limit}`);
  return res.data;
};

// =========================================================================
// Stage 7: Unified Optimization Engine API Methods
// =========================================================================

export const fetchOptimizerStatus = async (): Promise<any> => {
  const res = await api.get('/optimizer/status');
  return res.data;
};

export const updateOptimizerConfig = async (configUpdate: any): Promise<any> => {
  const res = await api.put('/optimizer/config', configUpdate);
  return res.data;
};

export const evaluateOptimizerResource = async (resourceId: string, modeOverride?: string): Promise<any> => {
  const res = await api.post('/optimizer/evaluate', {
    resource_id: resourceId,
    mode_override: modeOverride,
  });
  return res.data;
};

export const fetchOptimizerDecisions = async (limit: number = 50): Promise<any[]> => {
  const res = await api.get(`/optimizer/decisions?limit=${limit}`);
  return res.data;
};

// =========================================================================
// Stage 9A: KVM / Libvirt Real Virtual Machine API Methods
// =========================================================================

export const fetchKvmStatus = async (): Promise<any> => {
  const res = await api.get('/kvm/status');
  return res.data;
};

export const fetchKvmDomains = async (): Promise<any[]> => {
  const res = await api.get('/kvm/domains');
  return res.data;
};

export const inspectKvmDomain = async (domainName: string): Promise<any> => {
  const res = await api.get(`/kvm/domains/${domainName}`);
  return res.data;
};

export const resizeKvmVm = async (
  domainName: string,
  targetCpu: number,
  targetMemoryGb: number,
  allowShutdown: boolean = false,
): Promise<any> => {
  const res = await api.post(`/kvm/domains/${domainName}/resize`, {
    target_cpu: targetCpu,
    target_memory_gb: targetMemoryGb,
    allow_shutdown: allowShutdown,
  });
  return res.data;
};

export const fetchKvmOptimizerStatus = async (): Promise<any> => {
  const res = await api.get('/kvm/optimizer/status');
  return res.data;
};

export const updateKvmOptimizerConfig = async (configUpdate: any): Promise<any> => {
  const res = await api.put('/kvm/optimizer/config', configUpdate);
  return res.data;
};

export const evaluateKvmVm = async (
  domainName: string,
  guestCpu?: number,
  guestRam?: number,
  modeOverride?: string,
  allowShutdown: boolean = false,
): Promise<any> => {
  const res = await api.post('/kvm/optimizer/evaluate', {
    domain_name: domainName,
    observed_guest_cpu: guestCpu,
    observed_guest_ram_percent: guestRam,
    mode_override: modeOverride,
    allow_shutdown: allowShutdown,
  });
  return res.data;
};

export const fetchKvmOptimizerDecisions = async (limit: number = 50): Promise<any[]> => {
  const res = await api.get(`/kvm/optimizer/decisions?limit=${limit}`);
  return res.data;
};


