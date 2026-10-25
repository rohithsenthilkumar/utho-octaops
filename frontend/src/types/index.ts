export type Region = 'Bangalore' | 'Mumbai' | 'Noida';
export type Environment = 'prod' | 'staging' | 'dev' | 'qa';
export type ResourceType = 'VM' | 'Block Volume' | 'Public IP' | 'Object Storage';
export type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH';
export type RecommendationStatus =
  | 'PENDING'
  | 'ACCEPTED'
  | 'REJECTED'
  | 'RECOMMENDED'
  | 'OPTIMAL'
  | 'INSUFFICIENT_DATA'
  | 'HIGH_UTILIZATION';
export type ResourceStatus = 'ACTIVE' | 'IDLE' | 'OVER_PROVISIONED' | 'ORPHANED';
export type AlertSeverity = 'critical' | 'warning' | 'info';

export interface ResourceSpecs {
  vcpu?: number;
  ram_gb?: number;
  disk_gb?: number;
  iops?: number;
}

export interface Resource {
  id: string;
  name: string;
  type: ResourceType;
  region: Region;
  environment: Environment;
  owner: string;
  specs: ResourceSpecs;
  current_spec_display: string;
  status: ResourceStatus;
  monthly_cost: number;
  created_at: string;
  cpu_cores?: number;
  memory?: number;
  cpu_utilization?: number;
  is_simulated?: boolean;
  tenant_id?: string;
  owner_id?: string;
  owner_email?: string;
  policy?: ResourcePolicy;
  docker_container_name?: string;
  p95_cpu: number;
  p99_cpu: number;
  mean_cpu: number;
  p95_ram: number;
  p99_ram: number;
  mean_ram: number;
}

export interface ResourceCreatePayload {
  id?: string;
  name: string;
  resource_type: string;
  environment: string;
  region: string;
  cpu_cores: number;
  memory: number;
  cpu_utilization: number;
  estimated_monthly_cost: number;
  status?: string;
  owner?: string;
  is_simulated?: boolean;
}

export interface Recommendation {
  id: string;
  resource_id: string;
  resource_name: string;
  resource_type: ResourceType;
  region: Region;
  environment: Environment;
  action: string;
  current_spec: string;
  recommended_spec: string;
  current_cost: number;
  recommended_cost: number;
  monthly_savings: number;
  savings_pct: number;
  risk_level: RiskLevel;
  confidence_score: number;
  status: RecommendationStatus;
  justification: string;
  peak_behavior: string;
  p95_cpu: number;
  p99_cpu: number;
  mean_cpu: number;
  p95_ram: number;
  p99_ram: number;
  mean_ram: number;
  burst_ratio: number;
  current_configuration?: any;
  proposed_configuration?: any;
  evidence?: any;
  estimated_monthly_cost_before?: number;
  estimated_monthly_cost_after?: number;
  estimated_inr_savings?: number;
  savings_percentage?: number;
  is_simulated?: boolean;
}

export interface AlertItem {
  id: string;
  resource_id: string;
  resource_name: string;
  severity: AlertSeverity;
  title: string;
  message: string;
  metric: string;
  value: string;
  timestamp: string;
  region: Region;
  is_dismissed?: boolean;
}

export interface DashboardSummary {
  total_resources: number;
  current_monthly_cost: number;
  projected_cost: number;
  total_savings: number;
  savings_percentage: number;
  total_recommendations: number;
  accepted_recommendations: number;
  pending_recommendations: number;
  rejected_recommendations: number;
  idle_resources_count: number;
}

export interface SpendingHistoryPoint {
  month: string;
  actual_spend: number;
  optimized_target: number;
}

export interface TelemetryPoint {
  timestamp: string;
  date: string;
  time: string;
  cpu_percent: number;
  ram_percent: number;
  disk_iops?: number;
  network_mbps?: number;
}

export interface AppSettings {
  company_name: string;
  currency: 'INR' | 'USD';
  timezone: string;
  peak_metric: 'p95' | 'p99';
  idle_cpu_threshold: number;
  ram_headroom_pct: number;
  regions: Region[];
  email_notifications: boolean;
  slack_notifications: boolean;
  api_endpoint: string;
}

export interface ToastMessage {
  id: string;
  title: string;
  message?: string;
  type: 'success' | 'error' | 'info' | 'warning';
}

export interface LocalHostMetric {
  timestamp: string;
  host_id?: string;
  cpu_utilization: number;
  cpu_percent: number;
  ram_utilization: number;
  ram_percent: number;
  used_ram_gb: number;
  available_ram_gb?: number;
  total_ram_gb: number;
  used_ram_bytes: number;
  total_ram_bytes: number;
  disk_total_gb?: number;
  disk_used_gb?: number;
  disk_free_gb?: number;
  disk_percent?: number;
  disk_mount_point?: string;
  storage_resizing?: string;
  sampling_interval_seconds: number;
  metric_source: string;
  status: string;
}

export interface DockerWorkloadMetric {
  timestamp: string;
  container_name: string;
  status: string;
  is_healthy: boolean;
  actual_cpu_percent: number;
  actual_memory_mb: number;
  actual_memory_limit_mb: number;
  actual_memory_percent: number;
  configured_cpu_cores?: number | null;
  configured_memory_gb?: number | null;
  is_unconstrained: boolean;
  limit_status: string;
  running_replicas: number;
  replicas_detail: Array<{
    name: string;
    cpu_percent: number;
    memory: string;
    memory_used_mb?: number;
    memory_limit_mb?: number;
    memory_percent?: number;
    status: string;
  }>;
  gateway_url: string;
  storage_resizing: string;
  metric_source: string;
}

export interface StorageTelemetryData {
  telemetry: {
    mount_point: string;
    filesystem_type: string;
    total_gb: number;
    used_gb: number;
    free_gb: number;
    percent_used: number;
    status: string;
    timestamp: string;
    collection_source: string;
  };
  resizing_capability: {
    status: string;
    can_auto_expand: boolean;
    can_shrink: boolean;
    reason: string;
    supported_cloud_providers: string[];
    safety_constraints: string[];
  };
}

export interface LocalHostReadingPoint {
  time: string;
  timestamp: string;
  cpu_percent: number;
  ram_percent: number;
  used_ram_gb: number;
  total_ram_gb: number;
}

export interface AutoscalingReplicaDetail {
  name: string;
  cpu_percent: number;
  memory: string;
  status: string;
}

export interface AutoscalingDecision {
  timestamp: string;
  measured_cpu_percent: number;
  previous_replicas: number;
  new_replicas: number;
  action: string;
  reason: string;
  is_healthy: boolean;
}

export interface AutoscalingMetricPoint {
  timestamp: string;
  average_cpu_percent: number;
  replicas_count: number;
  is_healthy: boolean;
}

export interface AutoscalingStatus {
  status: string;
  timestamp: string;
  current_replicas: number;
  target_replicas: number;
  min_replicas: number;
  max_replicas: number;
  scale_out_threshold: number;
  scale_in_threshold: number;
  average_cpu_percent: number;
  replicas_detail: AutoscalingReplicaDetail[];
  is_healthy: boolean;
  remaining_cooldown_seconds: number;
  last_action: string;
  latest_decision: AutoscalingDecision;
  recent_events: AutoscalingDecision[];
  metric_history: AutoscalingMetricPoint[];
  load_balancer_url: string;
  is_load_test_running: boolean;
}

// Stage 6: Multi-Tenant Platform & VM Ownership Types
export type UserRole = 'COMPANY_ADMIN' | 'VM_OWNER' | 'OPTIMIZER_SERVICE';

export interface UserProfile {
  id: string;
  tenant_id: string;
  email: string;
  full_name: string;
  role: UserRole;
  company_name?: string;
  created_at?: string;
}

export interface CompanyTenant {
  id: string;
  name: string;
  slug: string;
  resources_count?: number;
  users_count?: number;
  created_at?: string;
}

export interface ResourcePolicy {
  id: string;
  tenant_id: string;
  resource_id?: string;
  min_cpu_cores: number;
  max_cpu_cores: number;
  min_memory_gb: number;
  max_memory_gb: number;
  allow_manual_scaling: boolean;
  requires_approval: boolean;
  updated_at?: string;
}

export interface ResourceChangeRequest {
  id: string;
  tenant_id: string;
  resource_id: string;
  resource_name?: string;
  requester_id: string;
  requester_email?: string;
  current_cpu_cores: number;
  current_memory_gb: number;
  target_cpu_cores: number;
  target_memory_gb: number;
  status: 'PENDING' | 'APPROVED' | 'REJECTED' | 'APPLIED';
  reason?: string;
  approver_id?: string;
  approver_email?: string;
  cost_difference_inr: number;
  created_at?: string;
  reviewed_at?: string;
}

export interface VerticalScaleResult {
  status: 'APPLIED' | 'PENDING_APPROVAL';
  message: string;
  resource_id: string;
  resource_name: string;
  applied_limits: {
    cpu_cores: number;
    memory_gb: number;
  };
  previous_limits: {
    cpu_cores: number;
    memory_gb: number;
  };
  cost_impact: {
    monthly_cost_before_inr: number;
    monthly_cost_after_inr: number;
    monthly_cost_diff_inr: number;
    cost_change_direction: 'INCREASE' | 'SAVINGS' | 'UNCHANGED';
    formula: string;
  };
  change_request_id?: string;
  is_live_container: boolean;
  container_name?: string;
}

export interface AuditEventItem {
  id: string;
  tenant_id: string;
  user_id?: string;
  user_email?: string;
  action: string;
  resource_id?: string;
  details: {
    action: string;
    outcome: string;
    actor_id: string;
    actor_role: string;
    reason: string;
    previous_values?: any;
    requested_values?: any;
    resulting_values?: any;
  };
  timestamp?: string;
}

// Stage 7: Unified Optimization Engine Types
export type OperatingMode = 'DRY_RUN' | 'RECOMMENDATION' | 'AUTO';

export interface OptimizerDecision {
  correlation_id: string;
  timestamp: string;
  resource_id: string;
  resource_name: string;
  tenant_id?: string;
  operating_mode: OperatingMode;
  observed_metrics: {
    cpu_utilization_percent?: number | null;
    memory_utilization_percent?: number | null;
  };
  current_allocation: {
    cpu_cores: number;
    memory_gb: number;
    replicas: number;
  };
  proposed_allocation: {
    cpu_cores: number;
    memory_gb: number;
    replicas: number;
  };
  decision: string;
  reason: string;
  estimated_cost_before_inr: number;
  estimated_cost_after_inr: number;
  estimated_monthly_savings_inr: number;
  requires_approval: boolean;
  executed: boolean;
  verified: boolean;
  execution_error?: string | null;
  change_request_id?: string | null;
}

export interface OptimizerStatus {
  status: string;
  enabled: boolean;
  scheduler_running?: boolean;
  scheduler_state?: string;
  operating_mode: OperatingMode;
  evaluation_interval_seconds: number;
  max_sample_gap_seconds?: number;
  config: {
    enabled: boolean;
    operating_mode: OperatingMode;
    evaluation_interval_seconds: number;
    scale_up_cpu_threshold: number;
    scale_down_cpu_threshold: number;
    scale_up_memory_threshold: number;
    scale_down_memory_threshold: number;
    sustained_window_samples: number;
    cooldown_seconds: number;
    max_sample_gap_seconds?: number;
  };
  last_run_timestamp?: string | null;
  last_evaluation_timestamp?: string | null;
  next_run_timestamp?: string | null;
  recent_decisions_count: number;
  recent_errors_count: number;
  recent_decisions: OptimizerDecision[];
  recent_errors: any[];
}

// Stage 9A: KVM / Libvirt Real VM Management Types
export interface KvmHypervisorStatus {
  is_hypervisor_ready: boolean;
  status: string;
  details: string;
  virsh_path?: string | null;
  virsh_available: boolean;
  virsh_version?: string | null;
  virsh_error?: string | null;
  kvm_device_path: string;
  kvm_device_exists: boolean;
  kvm_device_readable: boolean;
  kvm_device_writable: boolean;
  host_cpu_cores: number;
  host_total_ram_gb: number;
  host_available_ram_gb: number;
  safety_headroom_ram_gb: number;
  max_safe_allocatable_ram_gb: number;
  instructions?: string | null;
  allowed_test_vms?: string[];
  checked_at?: string;
}

export interface KvmDomain {
  name: string;
  uuid: string;
  state: string;
  is_running: boolean;
  is_shutoff: boolean;
  current_cpu_cores: number;
  max_cpu_cores: number;
  current_memory_gb: number;
  max_memory_gb: number;
  is_test_vm: boolean;
  adapter_type: string;
  estimated_monthly_cost: number;
  inspected_at: string;
}

export interface KvmResizePayload {
  target_cpu: number;
  target_memory_gb: number;
  allow_shutdown?: boolean;
}

export interface KvmResizeResult {
  success: boolean;
  status: string;
  message?: string | null;
  error?: string | null;
  requires_shutdown: boolean;
  current_allocation?: { cpu_cores: number; memory_gb: number } | null;
  requested_allocation?: { cpu_cores: number; memory_gb: number } | null;
  new_allocation?: { cpu_cores: number; memory_gb: number } | null;
  verified?: boolean | null;
  audit_event_id?: string | null;
}

export interface KvmOptimizerDecision {
  correlation_id: string;
  timestamp: string;
  domain_name: string;
  operating_mode: OperatingMode;
  observed_metrics: {
    guest_cpu_percent?: number | null;
    guest_ram_percent?: number | null;
  };
  current_allocation: {
    cpu_cores: number;
    memory_gb: number;
  };
  proposed_allocation: {
    cpu_cores: number;
    memory_gb: number;
  };
  decision: string;
  reason: string;
  estimated_cost_before_inr: number;
  estimated_cost_after_inr: number;
  estimated_monthly_savings_inr: number;
  requires_approval: boolean;
  executed: boolean;
  verified: boolean;
  execution_error?: string | null;
  requires_shutdown: boolean;
}

export interface KvmOptimizerStatus {
  status: string;
  enabled: boolean;
  operating_mode: OperatingMode;
  scheduler_state?: string;
  config: {
    enabled: boolean;
    operating_mode: OperatingMode;
    evaluation_interval_seconds: number;
    scale_up_cpu_threshold: number;
    scale_down_cpu_threshold: number;
    scale_up_memory_threshold: number;
    scale_down_memory_threshold: number;
    sustained_window_samples: number;
    cooldown_seconds: number;
    max_sample_gap_seconds?: number;
  };
  recent_decisions_count: number;
  recent_decisions: KvmOptimizerDecision[];
  recent_errors: any[];
}


