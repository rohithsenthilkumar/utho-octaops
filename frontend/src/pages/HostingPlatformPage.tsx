import React, { useState, useEffect, useCallback } from 'react';
import {
  Building2,
  Server,
  Shield,
  Sliders,
  CheckCircle,
  XCircle,
  Clock,
  ArrowUpRight,
  TrendingDown,
  TrendingUp,
  AlertTriangle,
  FileText,
  UserCheck,
  RefreshCw,
  Cpu,
  Database,
  Layers,
  Lock,
  Zap,
  Play,
  Eye,
  Settings2,
} from 'lucide-react';
import {
  UserProfile,
  CompanyTenant,
  Resource,
  ResourcePolicy,
  ResourceChangeRequest,
  AuditEventItem,
  OptimizerStatus,
  OptimizerDecision,
  KvmHypervisorStatus,
  KvmDomain,
  KvmResizeResult,
  KvmOptimizerStatus,
  KvmOptimizerDecision,
} from '../types';
import {
  fetchCurrentUser,
  fetchCurrentCompany,
  fetchTenantUsers,
  fetchTenantResources,
  assignResourceOwner,
  updateResourcePolicy,
  fetchChangeRequests,
  reviewChangeRequest,
  executeVerticalScale,
  fetchAuditEvents,
  fetchOptimizerStatus,
  updateOptimizerConfig,
  evaluateOptimizerResource,
  fetchOptimizerDecisions,
  fetchKvmStatus,
  fetchKvmDomains,
  resizeKvmVm,
  fetchKvmOptimizerStatus,
  updateKvmOptimizerConfig,
  evaluateKvmVm,
  fetchKvmOptimizerDecisions,
} from '../services/api';
import { formatINR } from '../utils/formatters';

export const HostingPlatformPage: React.FC = () => {
  const [currentUser, setCurrentUser] = useState<UserProfile | null>(null);
  const [company, setCompany] = useState<CompanyTenant | null>(null);
  const [tenantUsers, setTenantUsers] = useState<UserProfile[]>([]);
  const [resources, setResources] = useState<Resource[]>([]);
  const [changeRequests, setChangeRequests] = useState<ResourceChangeRequest[]>([]);
  const [auditEvents, setAuditEvents] = useState<AuditEventItem[]>([]);
  const [optimizerStatus, setOptimizerStatus] = useState<OptimizerStatus | null>(null);
  const [optimizerDecisions, setOptimizerDecisions] = useState<OptimizerDecision[]>([]);
  const [evaluatingResId, setEvaluatingResId] = useState<string | null>(null);
  const [optimizerUpdating, setOptimizerUpdating] = useState(false);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'vms' | 'kvm' | 'optimizer' | 'approvals' | 'audit'>('vms');

  // Stage 9A: KVM State
  const [kvmStatus, setKvmStatus] = useState<KvmHypervisorStatus | null>(null);
  const [kvmDomains, setKvmDomains] = useState<KvmDomain[]>([]);
  const [kvmOptimizerStatus, setKvmOptimizerStatus] = useState<KvmOptimizerStatus | null>(null);
  const [kvmOptimizerDecisions, setKvmOptimizerDecisions] = useState<KvmOptimizerDecision[]>([]);
  const [selectedKvmVmForResize, setSelectedKvmVmForResize] = useState<KvmDomain | null>(null);
  const [kvmResizeCpu, setKvmResizeCpu] = useState<number>(2);
  const [kvmResizeMem, setKvmResizeMem] = useState<number>(2.0);
  const [kvmAllowShutdown, setKvmAllowShutdown] = useState<boolean>(false);
  const [kvmResizeSubmitting, setKvmResizeSubmitting] = useState<boolean>(false);
  const [kvmResizeFeedback, setKvmResizeFeedback] = useState<KvmResizeResult | null>(null);
  const [evaluatingKvmVmName, setEvaluatingKvmVmName] = useState<string | null>(null);

  // Modal States
  const [selectedVmForScale, setSelectedVmForScale] = useState<Resource | null>(null);
  const [scaleTargetCpu, setScaleTargetCpu] = useState<number>(2);
  const [scaleTargetMemory, setScaleTargetMemory] = useState<number>(2.0);
  const [scaleReason, setScaleReason] = useState<string>('Optimizing workload capacity');
  const [scaleSubmitting, setScaleSubmitting] = useState(false);
  const [scaleFeedback, setScaleFeedback] = useState<{ status: string; message: string } | null>(null);

  // Policy Modal
  const [selectedVmForPolicy, setSelectedVmForPolicy] = useState<Resource | null>(null);
  const [policyForm, setPolicyForm] = useState({
    min_cpu_cores: 1,
    max_cpu_cores: 16,
    min_memory_gb: 1.0,
    max_memory_gb: 64.0,
    allow_manual_scaling: true,
    requires_approval: false,
  });
  const [policySubmitting, setPolicySubmitting] = useState(false);

  // Owner Assign Modal
  const [selectedVmForOwner, setSelectedVmForOwner] = useState<Resource | null>(null);
  const [selectedOwnerId, setSelectedOwnerId] = useState<string>('');
  const [assignSubmitting, setAssignSubmitting] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [u, c, users, res, crs, audits, optStatus, optDecisions, kStatus, kDomains, kOptStatus, kOptDecisions] = await Promise.all([
        fetchCurrentUser(),
        fetchCurrentCompany(),
        fetchTenantUsers(),
        fetchTenantResources(),
        fetchChangeRequests(),
        fetchAuditEvents(40),
        fetchOptimizerStatus().catch(() => null),
        fetchOptimizerDecisions(40).catch(() => []),
        fetchKvmStatus().catch(() => null),
        fetchKvmDomains().catch(() => []),
        fetchKvmOptimizerStatus().catch(() => null),
        fetchKvmOptimizerDecisions(40).catch(() => []),
      ]);
      setCurrentUser(u);
      setCompany(c);
      setTenantUsers(users);
      setResources(res);
      setChangeRequests(crs);
      setAuditEvents(audits);
      setOptimizerStatus(optStatus);
      setOptimizerDecisions(optDecisions);
      setKvmStatus(kStatus);
      setKvmDomains(kDomains);
      setKvmOptimizerStatus(kOptStatus);
      setKvmOptimizerDecisions(kOptDecisions);
    } catch (err) {
      console.error('Error loading hosting platform data:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleResizeKvmVm = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedKvmVmForResize) return;
    setKvmResizeSubmitting(true);
    setKvmResizeFeedback(null);
    try {
      const res = await resizeKvmVm(
        selectedKvmVmForResize.name,
        kvmResizeCpu,
        kvmResizeMem,
        kvmAllowShutdown
      );
      setKvmResizeFeedback(res);
      await loadData();
      if (res.success) {
        setTimeout(() => {
          setSelectedKvmVmForResize(null);
          setKvmResizeFeedback(null);
        }, 2000);
      }
    } catch (err: any) {
      setKvmResizeFeedback({
        success: false,
        status: 'ERROR',
        message: err.response?.data?.detail || 'KVM VM Resize failed',
        requires_shutdown: false,
      });
    } finally {
      setKvmResizeSubmitting(false);
    }
  };

  const handleUpdateKvmOptimizerMode = async (mode: string) => {
    if (mode === 'AUTO') {
      const confirmed = window.confirm(
        '⚠️ KVM VM AUTO MODE CONFIRMATION: Enabling AUTO mode allows the dedicated KVM Optimizer to autonomously execute virsh limit adjustments on libvirt VMs without human approval. Note: This is strictly isolated from the Docker container optimizer. Are you sure you want to enable AUTO mode for KVM VMs?'
      );
      if (!confirmed) return;
    }
    try {
      const res = await updateKvmOptimizerConfig({ operating_mode: mode });
      if (res.config) {
        setKvmOptimizerStatus((prev) => prev ? { ...prev, config: res.config, operating_mode: mode as any } : null);
      }
      await loadData();
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to update KVM optimizer mode');
    }
  };

  const handleEvaluateKvmVm = async (domainName: string) => {
    setEvaluatingKvmVmName(domainName);
    try {
      await evaluateKvmVm(domainName, 88.0, 75.0, 'DRY_RUN');
      await loadData();
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Evaluation failed');
    } finally {
      setEvaluatingKvmVmName(null);
    }
  };


  useEffect(() => {
    loadData();
  }, [loadData]);

  const isAdmin = currentUser?.role === 'COMPANY_ADMIN';

  // Optimizer Actions
  const handleToggleOptimizerEnabled = async (enabled: boolean) => {
    setOptimizerUpdating(true);
    try {
      const updated = await updateOptimizerConfig({ enabled });
      setOptimizerStatus(updated);
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to update optimizer status');
    } finally {
      setOptimizerUpdating(false);
    }
  };

  const handleChangeOperatingMode = async (mode: string) => {
    if (mode === 'AUTO') {
      const confirmed = window.confirm(
        '⚠️ GOVERNANCE CONFIRMATION: Enabling AUTO mode allows the Unified Optimizer to autonomously execute vertical scaling and limit changes on live Docker workloads without human approval. Are you sure you want to enable AUTO mode?'
      );
      if (!confirmed) return;
    }
    setOptimizerUpdating(true);
    try {
      const updated = await updateOptimizerConfig({ operating_mode: mode });
      setOptimizerStatus(updated);
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to update operating mode');
    } finally {
      setOptimizerUpdating(false);
    }
  };

  const handleEvaluateResource = async (resourceId: string) => {
    setEvaluatingResId(resourceId);
    try {
      await evaluateOptimizerResource(resourceId);
      await loadData();
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Evaluation failed');
    } finally {
      setEvaluatingResId(null);
    }
  };

  // Handle Vertical Scaling submission
  const handleExecuteScale = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedVmForScale) return;
    setScaleSubmitting(true);
    setScaleFeedback(null);
    try {
      const res = await executeVerticalScale(
        selectedVmForScale.id,
        scaleTargetCpu,
        scaleTargetMemory,
        scaleReason
      );
      setScaleFeedback({
        status: res.status,
        message: res.message,
      });
      await loadData();
      setTimeout(() => {
        setSelectedVmForScale(null);
        setScaleFeedback(null);
      }, 2500);
    } catch (err: any) {
      setScaleFeedback({
        status: 'ERROR',
        message: err.response?.data?.detail || 'Vertical scale request failed.',
      });
    } finally {
      setScaleSubmitting(false);
    }
  };

  // Handle Review Change Request
  const handleReviewCr = async (id: string, decision: 'APPROVED' | 'REJECTED') => {
    try {
      await reviewChangeRequest(id, decision, `Reviewed by ${currentUser?.full_name}`);
      await loadData();
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to review request');
    }
  };

  // Handle Policy Update
  const handleUpdatePolicy = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedVmForPolicy) return;
    setPolicySubmitting(true);
    try {
      await updateResourcePolicy(selectedVmForPolicy.id, policyForm);
      setSelectedVmForPolicy(null);
      await loadData();
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to update policy');
    } finally {
      setPolicySubmitting(false);
    }
  };

  // Handle Owner Assignment
  const handleAssignOwner = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedVmForOwner) return;
    setAssignSubmitting(true);
    try {
      await assignResourceOwner(selectedVmForOwner.id, selectedOwnerId || null);
      setSelectedVmForOwner(null);
      await loadData();
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to assign owner');
    } finally {
      setAssignSubmitting(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Banner: Tenant & Role Context */}
      <div className="bg-gradient-to-r from-gray-900 via-purple-950/40 to-gray-900 border border-purple-500/20 rounded-2xl p-6 shadow-xl">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-xl bg-purple-600/20 border border-purple-500/30 flex items-center justify-center text-purple-400">
              <Building2 className="w-6 h-6" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-xl font-bold text-white tracking-tight">
                  {company?.name || 'CloudFlow Hosting'}
                </h2>
                <span className="px-2 py-0.5 rounded-full text-xs font-semibold bg-purple-500/20 text-purple-300 border border-purple-500/30">
                  Tenant: {currentUser?.tenant_id}
                </span>
              </div>
              <p className="text-xs text-gray-400 mt-0.5">
                Active User: <span className="text-gray-200 font-medium">{currentUser?.full_name}</span> ({currentUser?.email})
                &nbsp;•&nbsp; Role: <span className="font-semibold text-purple-400">{currentUser?.role}</span>
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div className="bg-gray-950/60 border border-gray-800 px-3.5 py-2 rounded-xl text-center">
              <div className="text-xs text-gray-400">Managed VMs</div>
              <div className="text-lg font-bold text-white">{resources.length}</div>
            </div>
            <div className="bg-gray-950/60 border border-gray-800 px-3.5 py-2 rounded-xl text-center">
              <div className="text-xs text-gray-400">Pending Approvals</div>
              <div className="text-lg font-bold text-amber-400">
                {changeRequests.filter((c) => c.status === 'PENDING').length}
              </div>
            </div>
            <button
              onClick={loadData}
              disabled={loading}
              className="p-2.5 rounded-xl bg-gray-800 hover:bg-gray-700 text-gray-300 border border-gray-700 transition"
              title="Refresh Platform Data"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-gray-800 space-x-2">
        <button
          onClick={() => setActiveTab('vms')}
          className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition ${
            activeTab === 'vms'
              ? 'border-purple-500 text-purple-400 bg-purple-500/10 rounded-t-lg'
              : 'border-transparent text-gray-400 hover:text-gray-200'
          }`}
        >
          <Server className="w-4 h-4" />
          Virtual Machines ({resources.length})
        </button>
        <button
          onClick={() => setActiveTab('kvm')}
          className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition ${
            activeTab === 'kvm'
              ? 'border-cyan-500 text-cyan-400 bg-cyan-500/10 rounded-t-lg'
              : 'border-transparent text-gray-400 hover:text-gray-200'
          }`}
        >
          <Cpu className="w-4 h-4 text-cyan-400" />
          KVM Virtual Machines (Stage 9A)
          <span className="text-[10px] uppercase font-bold px-1.5 py-0.5 rounded bg-cyan-500/20 text-cyan-300 border border-cyan-500/30">
            Libvirt
          </span>
        </button>
        <button
          onClick={() => setActiveTab('optimizer')}
          className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition ${
            activeTab === 'optimizer'
              ? 'border-purple-500 text-purple-400 bg-purple-500/10 rounded-t-lg'
              : 'border-transparent text-gray-400 hover:text-gray-200'
          }`}
        >
          <Zap className="w-4 h-4 text-purple-400" />
          Unified Optimizer (Stage 7)
          {optimizerStatus?.enabled && (
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse ml-0.5" />
          )}
        </button>
        <button
          onClick={() => setActiveTab('approvals')}
          className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition ${
            activeTab === 'approvals'
              ? 'border-purple-500 text-purple-400 bg-purple-500/10 rounded-t-lg'
              : 'border-transparent text-gray-400 hover:text-gray-200'
          }`}
        >
          <Clock className="w-4 h-4" />
          Approval Queue ({changeRequests.filter((c) => c.status === 'PENDING').length})
        </button>
        <button
          onClick={() => setActiveTab('audit')}
          className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition ${
            activeTab === 'audit'
              ? 'border-purple-500 text-purple-400 bg-purple-500/10 rounded-t-lg'
              : 'border-transparent text-gray-400 hover:text-gray-200'
          }`}
        >
          <FileText className="w-4 h-4" />
          Audit Trail ({auditEvents.length})
        </button>
      </div>

      {/* TAB 1: VIRTUAL MACHINES LIST */}
      {activeTab === 'vms' && (
        <div className="bg-gray-900 border border-gray-800 rounded-2xl overflow-hidden shadow-sm">
          <div className="px-6 py-4 border-b border-gray-800 flex items-center justify-between">
            <div>
              <h3 className="font-semibold text-white">
                {isAdmin ? 'All Tenant Virtual Machines' : 'Your Assigned Virtual Machines'}
              </h3>
              <p className="text-xs text-gray-400 mt-0.5">
                {isAdmin
                  ? 'Manage limits, define resource policies, assign owners, or vertically scale resources.'
                  : 'Manage capacity and submit vertical scaling requests within authorized bounds.'}
              </p>
            </div>
            {isAdmin && (
              <span className="text-xs font-medium px-2.5 py-1 rounded bg-purple-500/20 text-purple-300 border border-purple-500/30">
                Admin Full Access
              </span>
            )}
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-gray-300">
              <thead className="bg-gray-950/60 text-xs font-semibold text-gray-400 uppercase tracking-wider border-b border-gray-800">
                <tr>
                  <th className="py-3 px-4">VM / Workload</th>
                  <th className="py-3 px-4">Assigned Owner</th>
                  <th className="py-3 px-4">Current Allocation</th>
                  <th className="py-3 px-4">Policy Limits</th>
                  <th className="py-3 px-4">Est. Cost</th>
                  <th className="py-3 px-4 text-right">FinOps Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                {resources.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="py-8 text-center text-gray-400 text-sm">
                      No virtual machines found for current role/tenant scope.
                    </td>
                  </tr>
                ) : (
                  resources.map((vm) => {
                    const isDockerLive = vm.docker_container_name || vm.id.includes('demo');
                    return (
                      <tr key={vm.id} className="hover:bg-gray-800/40 transition">
                        <td className="py-3.5 px-4">
                          <div className="font-semibold text-white">{vm.name}</div>
                          <div className="flex items-center gap-2 mt-0.5 text-xs text-gray-400">
                            <span className="font-mono text-gray-400">{vm.id}</span>
                            <span>•</span>
                            <span>{vm.region}</span>
                            {isDockerLive && (
                              <span className="px-1.5 py-0.2 rounded bg-emerald-500/20 text-emerald-400 font-mono text-[10px] border border-emerald-500/30">
                                Docker Live Workload
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="py-3.5 px-4">
                          <div className="text-xs font-medium text-gray-200">
                            {vm.owner_email || vm.owner || 'Unassigned'}
                          </div>
                          {isAdmin && (
                            <button
                              onClick={() => {
                                setSelectedVmForOwner(vm);
                                setSelectedOwnerId(vm.owner_id || '');
                              }}
                              className="text-[11px] text-purple-400 hover:text-purple-300 underline mt-0.5"
                            >
                              Reassign Owner
                            </button>
                          )}
                        </td>
                        <td className="py-3.5 px-4">
                          <div className="flex items-center gap-2">
                            <span className="px-2 py-0.5 rounded bg-blue-500/10 text-blue-400 font-mono text-xs border border-blue-500/20">
                              {vm.cpu_cores} vCPU
                            </span>
                            <span className="px-2 py-0.5 rounded bg-cyan-500/10 text-cyan-400 font-mono text-xs border border-cyan-500/20">
                              {vm.memory} GB RAM
                            </span>
                          </div>
                          <div className="text-[11px] text-gray-500 mt-1">
                            Util: {vm.cpu_utilization?.toFixed(1)}%
                          </div>
                        </td>
                        <td className="py-3.5 px-4">
                          {vm.policy ? (
                            <div className="text-xs text-gray-300">
                              <div>
                                CPU: [{vm.policy.min_cpu_cores} - {vm.policy.max_cpu_cores}] cores
                              </div>
                              <div>
                                RAM: [{vm.policy.min_memory_gb} - {vm.policy.max_memory_gb}] GB
                              </div>
                              <div className="text-[11px] text-gray-400 mt-0.5 flex items-center gap-1">
                                {vm.policy.requires_approval ? (
                                  <span className="text-amber-400">Approval Required</span>
                                ) : (
                                  <span className="text-emerald-400">Self-Service</span>
                                )}
                              </div>
                            </div>
                          ) : (
                            <span className="text-xs text-gray-500">Default (1-16 cores)</span>
                          )}
                          {isAdmin && (
                            <button
                              onClick={() => {
                                setSelectedVmForPolicy(vm);
                                if (vm.policy) {
                                  setPolicyForm({
                                    min_cpu_cores: vm.policy.min_cpu_cores,
                                    max_cpu_cores: vm.policy.max_cpu_cores,
                                    min_memory_gb: vm.policy.min_memory_gb,
                                    max_memory_gb: vm.policy.max_memory_gb,
                                    allow_manual_scaling: vm.policy.allow_manual_scaling,
                                    requires_approval: vm.policy.requires_approval,
                                  });
                                }
                              }}
                              className="text-[11px] text-purple-400 hover:text-purple-300 underline block mt-0.5"
                            >
                              Configure Policy
                            </button>
                          )}
                        </td>
                        <td className="py-3.5 px-4 font-mono font-medium text-emerald-400">
                          {formatINR(vm.monthly_cost || 0)}
                          <span className="text-[10px] text-gray-500 block">/mo (est.)</span>
                        </td>
                        <td className="py-3.5 px-4 text-right">
                          <button
                            onClick={() => {
                              setSelectedVmForScale(vm);
                              setScaleTargetCpu(vm.cpu_cores || 2);
                              setScaleTargetMemory(vm.memory || 2.0);
                              setScaleFeedback(null);
                            }}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-purple-600 hover:bg-purple-500 text-white text-xs font-semibold shadow-sm transition"
                          >
                            <Sliders className="w-3.5 h-3.5" />
                            Scale VM
                          </button>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* TAB: KVM VIRTUAL MACHINES (STAGE 9A) */}
      {activeTab === 'kvm' && (
        <div className="space-y-6">
          {/* Hypervisor Status & Host Virtualization Overview */}
          <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6 shadow-sm">
            <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6 pb-6 border-b border-gray-800">
              <div className="flex items-center gap-4">
                <div
                  className={`w-12 h-12 rounded-xl flex items-center justify-center border ${
                    kvmStatus?.is_hypervisor_ready
                      ? 'bg-cyan-500/10 border-cyan-500/30 text-cyan-400'
                      : 'bg-amber-500/10 border-amber-500/30 text-amber-400'
                  }`}
                >
                  <Cpu className="w-6 h-6" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-lg font-bold text-white tracking-tight">KVM / QEMU Libvirt Hypervisor</h3>
                    <span
                      className={`px-2.5 py-0.5 rounded-full text-xs font-semibold border ${
                        kvmStatus?.is_hypervisor_ready
                          ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                          : 'bg-amber-500/10 text-amber-400 border-amber-500/20'
                      }`}
                    >
                      {kvmStatus?.status || 'CHECKING'}
                    </span>
                    <span className="text-xs px-2 py-0.5 rounded bg-cyan-500/10 text-cyan-300 border border-cyan-500/20">
                      Bare Metal VT-x
                    </span>
                  </div>
                  <p className="text-xs text-gray-400 mt-1">
                    {kvmStatus?.details || 'Local Linux KVM virtualization hypervisor adapter.'}
                  </p>
                </div>
              </div>

              {/* Status indicators */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="bg-gray-950/60 border border-gray-800 px-3.5 py-2.5 rounded-xl text-center">
                  <div className="text-[11px] text-gray-400">/dev/kvm Node</div>
                  <div className={`text-xs font-bold mt-1 ${kvmStatus?.kvm_device_writable ? 'text-emerald-400' : 'text-amber-400'}`}>
                    {kvmStatus?.kvm_device_writable ? 'Writable (OK)' : (kvmStatus?.kvm_device_exists ? 'Read-Only' : 'Missing')}
                  </div>
                </div>
                <div className="bg-gray-950/60 border border-gray-800 px-3.5 py-2.5 rounded-xl text-center">
                  <div className="text-[11px] text-gray-400">Virsh Binary</div>
                  <div className={`text-xs font-bold mt-1 ${kvmStatus?.virsh_available ? 'text-emerald-400' : 'text-amber-400'}`}>
                    {kvmStatus?.virsh_available ? 'Installed' : 'Not Installed'}
                  </div>
                </div>
                <div className="bg-gray-950/60 border border-gray-800 px-3.5 py-2.5 rounded-xl text-center">
                  <div className="text-[11px] text-gray-400">Host Cores</div>
                  <div className="text-sm font-bold text-white mt-1">
                    {kvmStatus?.host_cpu_cores || 20} Cores
                  </div>
                </div>
                <div className="bg-gray-950/60 border border-gray-800 px-3.5 py-2.5 rounded-xl text-center">
                  <div className="text-[11px] text-gray-400">Safe VM RAM</div>
                  <div className="text-sm font-bold text-cyan-400 mt-1">
                    {kvmStatus?.max_safe_allocatable_ram_gb || 6.0} GB
                  </div>
                  <div className="text-[9px] text-gray-500">2GB buffer kept</div>
                </div>
              </div>
            </div>

            {/* Diagnostic instructions banner if hypervisor packages not installed */}
            {kvmStatus?.instructions && (
              <div className="mt-4 p-4 rounded-xl bg-amber-500/10 border border-amber-500/20 text-xs text-amber-200">
                <div className="font-semibold flex items-center gap-1.5 mb-1.5 text-amber-300">
                  <AlertTriangle className="w-4 h-4 text-amber-400" />
                  Hypervisor Setup & Activation Instructions:
                </div>
                <p className="text-gray-300 mb-2">
                  VT-x hardware virtualization is supported on this Intel CPU, and <code className="text-amber-300 bg-gray-950 px-1 py-0.5 rounded">/dev/kvm</code> is active. To enable live libvirt VM management, run:
                </p>
                <pre className="bg-gray-950/80 p-2.5 rounded border border-gray-800 text-[11px] text-emerald-400 font-mono overflow-x-auto select-all">
                  {kvmStatus.instructions}
                </pre>
              </div>
            )}
          </div>

          {/* Real KVM VM Inventory Table */}
          <div className="bg-gray-900 border border-gray-800 rounded-2xl overflow-hidden shadow-sm">
            <div className="px-6 py-4 border-b border-gray-800 flex items-center justify-between">
              <div>
                <h3 className="font-semibold text-white flex items-center gap-2">
                  <Server className="w-4 h-4 text-cyan-400" />
                  Local KVM Virtual Machines
                </h3>
                <p className="text-xs text-gray-400 mt-0.5">
                  Real libvirt domains managed independently from Docker container cgroups. Only authorized test domains can be resized.
                </p>
              </div>
              <span className="text-xs font-semibold px-2.5 py-1 rounded bg-cyan-500/20 text-cyan-300 border border-cyan-500/30">
                FinOps Formula: ₹800/core + ₹200/GB
              </span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm text-gray-300">
                <thead className="bg-gray-950/60 text-xs font-semibold text-gray-400 uppercase tracking-wider border-b border-gray-800">
                  <tr>
                    <th className="py-3 px-4">Domain Name</th>
                    <th className="py-3 px-4">Hypervisor State</th>
                    <th className="py-3 px-4">Architecture / Type</th>
                    <th className="py-3 px-4">Configured Allocation</th>
                    <th className="py-3 px-4">Max Capacity Limits</th>
                    <th className="py-3 px-4">Est. Monthly Cost</th>
                    <th className="py-3 px-4 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-800">
                  {kvmDomains.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="py-8 text-center text-gray-400 text-sm">
                        No active libvirt domains found. Run tests or initialize an allowlisted test VM (<code className="text-cyan-400">smartcloud-test-vm</code>).
                      </td>
                    </tr>
                  ) : (
                    kvmDomains.map((domain) => (
                      <tr key={domain.name} className="hover:bg-gray-800/40 transition">
                        <td className="py-3.5 px-4">
                          <div className="font-semibold text-white">{domain.name}</div>
                          <div className="font-mono text-[11px] text-gray-500">{domain.uuid}</div>
                        </td>
                        <td className="py-3.5 px-4">
                          <span
                            className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border ${
                              domain.is_running
                                ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                                : 'bg-gray-800 text-gray-400 border-gray-700'
                            }`}
                          >
                            <span
                              className={`w-1.5 h-1.5 rounded-full ${
                                domain.is_running ? 'bg-emerald-400 animate-pulse' : 'bg-gray-500'
                              }`}
                            />
                            {domain.state.toUpperCase()}
                          </span>
                        </td>
                        <td className="py-3.5 px-4">
                          <span className="px-2 py-0.5 rounded text-xs bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 font-semibold">
                            LIVE LIBVIRT VM
                          </span>
                        </td>
                        <td className="py-3.5 px-4">
                          <div className="flex items-center gap-2">
                            <span className="px-2 py-0.5 rounded bg-blue-500/10 text-blue-400 font-mono text-xs border border-blue-500/20">
                              {domain.current_cpu_cores} vCPU
                            </span>
                            <span className="px-2 py-0.5 rounded bg-cyan-500/10 text-cyan-400 font-mono text-xs border border-cyan-500/20">
                              {domain.current_memory_gb} GB RAM
                            </span>
                          </div>
                        </td>
                        <td className="py-3.5 px-4 text-xs text-gray-400">
                          Max: {domain.max_cpu_cores} cores / {domain.max_memory_gb} GB
                        </td>
                        <td className="py-3.5 px-4 font-semibold text-white">
                          {formatINR(domain.estimated_monthly_cost)}
                        </td>
                        <td className="py-3.5 px-4 text-right">
                          <div className="flex items-center justify-end gap-2">
                            <button
                              onClick={() => handleEvaluateKvmVm(domain.name)}
                              disabled={evaluatingKvmVmName === domain.name}
                              className="px-2.5 py-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-300 text-xs font-medium border border-gray-700 transition"
                              title="Evaluate with KVM Optimizer (DRY_RUN)"
                            >
                              {evaluatingKvmVmName === domain.name ? 'Evaluating...' : 'Evaluate'}
                            </button>
                            {isAdmin && (
                              <button
                                onClick={() => {
                                  setSelectedKvmVmForResize(domain);
                                  setKvmResizeCpu(domain.current_cpu_cores);
                                  setKvmResizeMem(domain.current_memory_gb);
                                  setKvmAllowShutdown(false);
                                  setKvmResizeFeedback(null);
                                }}
                                className="px-3 py-1.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-semibold shadow-sm transition"
                              >
                                Resize VM
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* Dedicated KVM Capacity Optimizer Card */}
          <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6 shadow-sm">
            <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6 pb-6 border-b border-gray-800">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-lg font-bold text-white tracking-tight">Dedicated KVM VM Capacity Optimizer</h3>
                  <span className="text-xs px-2 py-0.5 rounded bg-purple-500/20 text-purple-300 border border-purple-500/30">
                    Isolated Engine
                  </span>
                </div>
                <p className="text-xs text-gray-400 mt-1">
                  Evaluates real guest VM CPU and RAM metrics. Strictly isolated from the Docker container autoscaler/optimizer.
                </p>
              </div>

              {/* Operating Mode Selector */}
              {isAdmin && (
                <div className="flex items-center gap-2 bg-gray-950 p-1.5 rounded-xl border border-gray-800">
                  {(['DRY_RUN', 'RECOMMENDATION', 'AUTO'] as const).map((m) => (
                    <button
                      key={m}
                      onClick={() => handleUpdateKvmOptimizerMode(m)}
                      className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
                        (kvmOptimizerStatus?.operating_mode || 'DRY_RUN') === m
                          ? 'bg-cyan-600 text-white shadow-sm'
                          : 'text-gray-400 hover:text-white'
                      }`}
                    >
                      {m}
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* Decisions list */}
            <div className="mt-6">
              <h4 className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-3">
                Recent KVM Optimization Decisions
              </h4>
              <div className="space-y-3">
                {kvmOptimizerDecisions.length === 0 ? (
                  <div className="p-4 rounded-xl bg-gray-950/40 border border-gray-800 text-center text-xs text-gray-500">
                    No KVM optimization decisions logged yet. Click "Evaluate" on any VM to test policy evaluation.
                  </div>
                ) : (
                  kvmOptimizerDecisions.slice(0, 5).map((d) => (
                    <div
                      key={d.correlation_id}
                      className="p-4 rounded-xl bg-gray-950/60 border border-gray-800 flex flex-col sm:flex-row sm:items-center justify-between gap-3"
                    >
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-white text-sm">{d.domain_name}</span>
                          <span
                            className={`px-2 py-0.5 rounded text-[11px] font-semibold border ${
                              d.decision.includes('SCALE_UP')
                                ? 'bg-amber-500/10 text-amber-400 border-amber-500/20'
                                : d.decision.includes('SCALE_DOWN')
                                ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                                : 'bg-gray-800 text-gray-400 border-gray-700'
                            }`}
                          >
                            {d.decision}
                          </span>
                          <span className="text-[10px] text-gray-500 font-mono">{d.correlation_id}</span>
                        </div>
                        <p className="text-xs text-gray-300 mt-1">{d.reason}</p>
                      </div>
                      <div className="text-right text-xs">
                        <div className="text-gray-400">
                          {d.current_allocation.cpu_cores}C / {d.current_allocation.memory_gb}GB &rarr;{' '}
                          <span className="text-cyan-400 font-semibold">
                            {d.proposed_allocation.cpu_cores}C / {d.proposed_allocation.memory_gb}GB
                          </span>
                        </div>
                        <div className="text-gray-500 text-[11px] mt-0.5">
                          {d.executed ? 'Executed on Libvirt' : 'Evaluation Only'}
                        </div>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: UNIFIED OPTIMIZATION ENGINE */}
      {activeTab === 'optimizer' && (
        <div className="space-y-6">
          {/* Engine Status & Mode Controls */}
          <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6 shadow-sm">
            <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6 pb-6 border-b border-gray-800">
              <div className="flex items-center gap-4">
                <div
                  className={`w-12 h-12 rounded-xl flex items-center justify-center border ${
                    optimizerStatus?.enabled
                      ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
                      : 'bg-gray-800/80 border-gray-700 text-gray-400'
                  }`}
                >
                  <Zap className="w-6 h-6" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-lg font-bold text-white tracking-tight">Unified Optimization Engine</h3>
                    <span
                      className={`px-2.5 py-0.5 rounded-full text-xs font-semibold border ${
                        optimizerStatus?.enabled
                          ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30'
                          : 'bg-gray-800 text-gray-400 border-gray-700'
                      }`}
                    >
                      {optimizerStatus?.enabled ? 'ACTIVE' : 'DISABLED'}
                    </span>
                    <span
                      className={`px-2 py-0.5 rounded-full text-[11px] font-medium border ${
                        optimizerStatus?.scheduler_running
                          ? 'bg-blue-500/10 text-blue-300 border-blue-500/30'
                          : 'bg-yellow-500/10 text-yellow-300 border-yellow-500/30'
                      }`}
                      title={optimizerStatus?.scheduler_state || 'Scheduler status'}
                    >
                      Scheduler: {optimizerStatus?.scheduler_running ? (optimizerStatus?.scheduler_state || 'RUNNING') : 'STOPPED'}
                    </span>
                  </div>
                  <p className="text-xs text-gray-400 mt-0.5">
                    Coordinated vertical scaling, horizontal scaling, policy enforcement, and FinOps calculations.
                  </p>
                </div>
              </div>

              {/* Mode Selector and Engine Toggle */}
              {isAdmin && (
                <div className="flex items-center gap-3">
                  <div className="bg-gray-950 border border-gray-800 rounded-xl px-3 py-1.5 flex items-center gap-2 text-xs">
                    <span className="text-gray-400 font-medium">Mode:</span>
                    <select
                      value={optimizerStatus?.operating_mode || 'DRY_RUN'}
                      onChange={(e) => handleChangeOperatingMode(e.target.value)}
                      disabled={optimizerUpdating}
                      className="bg-transparent text-white font-semibold focus:outline-none cursor-pointer"
                    >
                      <option value="DRY_RUN" className="bg-gray-900 text-blue-300">
                        DRY_RUN (Simulate Only)
                      </option>
                      <option value="RECOMMENDATION" className="bg-gray-900 text-purple-300">
                        RECOMMENDATION (Review)
                      </option>
                      <option value="AUTO" className="bg-gray-900 text-emerald-300">
                        AUTO (Autonomous Execution)
                      </option>
                    </select>
                  </div>

                  <button
                    onClick={() => handleToggleOptimizerEnabled(!optimizerStatus?.enabled)}
                    disabled={optimizerUpdating}
                    className={`px-4 py-2 rounded-xl text-xs font-semibold transition shadow-sm ${
                      optimizerStatus?.enabled
                        ? 'bg-rose-600/80 hover:bg-rose-500 text-white'
                        : 'bg-emerald-600 hover:bg-emerald-500 text-white'
                    }`}
                  >
                    {optimizerStatus?.enabled ? 'Disable Engine' : 'Enable Engine'}
                  </button>
                </div>
              )}
            </div>

            {/* Threshold & Health Cards */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-6">
              <div className="bg-gray-950/70 border border-gray-800 rounded-xl p-3.5">
                <div className="text-[11px] text-gray-400">Operating Mode</div>
                <div className="text-sm font-bold text-purple-400 mt-1 flex items-center gap-1.5">
                  {optimizerStatus?.operating_mode === 'DRY_RUN' && <Eye className="w-4 h-4 text-blue-400" />}
                  {optimizerStatus?.operating_mode === 'RECOMMENDATION' && <FileText className="w-4 h-4 text-purple-400" />}
                  {optimizerStatus?.operating_mode === 'AUTO' && <Play className="w-4 h-4 text-emerald-400" />}
                  {optimizerStatus?.operating_mode || 'DRY_RUN'}
                </div>
              </div>

              <div className="bg-gray-950/70 border border-gray-800 rounded-xl p-3.5">
                <div className="text-[11px] text-gray-400">Scale Up / Out Bounds</div>
                <div className="text-sm font-bold text-rose-400 mt-1">
                  CPU &gt; {optimizerStatus?.config?.scale_up_cpu_threshold || 75}% | RAM &gt; {optimizerStatus?.config?.scale_up_memory_threshold || 80}%
                </div>
              </div>

              <div className="bg-gray-950/70 border border-gray-800 rounded-xl p-3.5">
                <div className="text-[11px] text-gray-400">Scale Down / In Bounds</div>
                <div className="text-sm font-bold text-emerald-400 mt-1">
                  CPU &lt; {optimizerStatus?.config?.scale_down_cpu_threshold || 25}% | RAM &lt; {optimizerStatus?.config?.scale_down_memory_threshold || 40}%
                </div>
              </div>

              <div className="bg-gray-950/70 border border-gray-800 rounded-xl p-3.5">
                <div className="text-[11px] text-gray-400">Sustained Window & Cooldown</div>
                <div className="text-sm font-bold text-gray-200 mt-1">
                  {optimizerStatus?.config?.sustained_window_samples || 3} samples • {optimizerStatus?.config?.cooldown_seconds || 60}s
                </div>
                <div className="text-[10px] text-gray-500 mt-0.5">
                  Max sample gap: {optimizerStatus?.max_sample_gap_seconds || 12.5}s
                </div>
              </div>
            </div>
          </div>

          {/* On-Demand Resource Evaluation Action Table */}
          <div className="bg-gray-900 border border-gray-800 rounded-2xl overflow-hidden shadow-sm">
            <div className="px-6 py-4 border-b border-gray-800 flex items-center justify-between">
              <div>
                <h4 className="font-semibold text-white">Workload Optimization Evaluator</h4>
                <p className="text-xs text-gray-400 mt-0.5">
                  Evaluate live workloads through the multi-tenant policy engine.
                </p>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm text-gray-300">
                <thead className="bg-gray-950/60 text-xs font-semibold text-gray-400 uppercase tracking-wider border-b border-gray-800">
                  <tr>
                    <th className="py-3 px-4">Workload ID / Name</th>
                    <th className="py-3 px-4">Allocation</th>
                    <th className="py-3 px-4">Target Type</th>
                    <th className="py-3 px-4">Policy Bounds</th>
                    <th className="py-3 px-4 text-right">Trigger Evaluation</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-800">
                  {resources.map((r) => (
                    <tr key={r.id} className="hover:bg-gray-800/40 transition">
                      <td className="py-3.5 px-4">
                        <div className="font-semibold text-white">{r.name}</div>
                        <div className="text-xs text-gray-400 font-mono">{r.id}</div>
                      </td>
                      <td className="py-3.5 px-4 font-mono text-xs">
                        <span className="text-blue-400">{r.cpu_cores} vCPU</span>,{' '}
                        <span className="text-cyan-400">{r.memory} GB</span>
                      </td>
                      <td className="py-3.5 px-4">
                        {r.id.includes('demo') || r.id.includes('autoscal') ? (
                          <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                            Live Docker Workload
                          </span>
                        ) : (
                          <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-gray-800 text-gray-300">
                            Simulated VM
                          </span>
                        )}
                      </td>
                      <td className="py-3.5 px-4 text-xs text-gray-400">
                        {r.policy ? (
                          <span>
                            [{r.policy.min_cpu_cores}-{r.policy.max_cpu_cores}C, {r.policy.min_memory_gb}-{r.policy.max_memory_gb}G]
                          </span>
                        ) : (
                          <span>Default Policy</span>
                        )}
                      </td>
                      <td className="py-3.5 px-4 text-right">
                        <button
                          onClick={() => handleEvaluateResource(r.id)}
                          disabled={evaluatingResId === r.id}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-purple-600 hover:bg-purple-500 text-white text-xs font-semibold shadow-sm transition disabled:opacity-50"
                        >
                          <Play className={`w-3.5 h-3.5 ${evaluatingResId === r.id ? 'animate-spin' : ''}`} />
                          {evaluatingResId === r.id ? 'Evaluating...' : 'Evaluate Now'}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Recent Decisions Feed */}
          <div className="bg-gray-900 border border-gray-800 rounded-2xl overflow-hidden shadow-sm">
            <div className="px-6 py-4 border-b border-gray-800">
              <h4 className="font-semibold text-white">Recent Engine Decisions & Executions</h4>
              <p className="text-xs text-gray-400 mt-0.5">
                Timestamped decisions rendered by the unified engine with FinOps before/after cost estimates.
              </p>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm text-gray-300">
                <thead className="bg-gray-950/60 text-xs font-semibold text-gray-400 uppercase tracking-wider border-b border-gray-800">
                  <tr>
                    <th className="py-3 px-4">Time / ID</th>
                    <th className="py-3 px-4">Resource</th>
                    <th className="py-3 px-4">Decision</th>
                    <th className="py-3 px-4">Observed Metrics</th>
                    <th className="py-3 px-4">Proposed Target</th>
                    <th className="py-3 px-4">Cost Impact</th>
                    <th className="py-3 px-4">Result / Mode</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-800 text-xs">
                  {optimizerDecisions.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="py-8 text-center text-gray-400">
                        No optimization decisions recorded yet. Click &quot;Evaluate Now&quot; above to run a cycle.
                      </td>
                    </tr>
                  ) : (
                    optimizerDecisions.map((d) => (
                      <tr key={d.correlation_id} className="hover:bg-gray-800/40 transition">
                        <td className="py-3 px-4">
                          <span className="font-mono text-purple-300 text-[11px]">{d.correlation_id}</span>
                          <div className="text-[10px] text-gray-500 mt-0.5">
                            {new Date(d.timestamp).toLocaleTimeString()}
                          </div>
                        </td>
                        <td className="py-3 px-4 font-semibold text-white">{d.resource_name || d.resource_id}</td>
                        <td className="py-3 px-4">
                          <span
                            className={`px-2 py-0.5 rounded font-mono text-[11px] font-bold ${
                              d.decision.includes('SCALE_UP') || d.decision.includes('SCALE_OUT')
                                ? 'bg-purple-500/20 text-purple-300 border border-purple-500/30'
                                : d.decision.includes('SCALE_DOWN') || d.decision.includes('SCALE_IN')
                                ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                                : d.decision === 'APPROVAL_REQUIRED'
                                ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                                : d.decision === 'BLOCKED_BY_POLICY'
                                ? 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
                                : 'bg-gray-800 text-gray-400'
                            }`}
                          >
                            {d.decision}
                          </span>
                          <div className="text-[11px] text-gray-400 mt-1 max-w-xs">{d.reason}</div>
                        </td>
                        <td className="py-3 px-4 font-mono text-[11px]">
                          <div>CPU: {d.observed_metrics?.cpu_utilization_percent ?? 'N/A'}%</div>
                          <div>RAM: {d.observed_metrics?.memory_utilization_percent ?? 'N/A'}%</div>
                        </td>
                        <td className="py-3 px-4 font-mono text-[11px]">
                          {d.proposed_allocation?.replicas !== d.current_allocation?.replicas ? (
                            <span className="text-cyan-400 font-bold">{d.proposed_allocation?.replicas} replicas</span>
                          ) : (
                            <span className="text-purple-300">
                              {d.proposed_allocation?.cpu_cores}C / {d.proposed_allocation?.memory_gb}G
                            </span>
                          )}
                        </td>
                        <td className="py-3 px-4 font-mono">
                          <span className="text-white">{formatINR(d.estimated_cost_after_inr)}</span>
                          {d.estimated_monthly_savings_inr !== 0 && (
                            <div
                              className={`text-[10px] ${
                                d.estimated_monthly_savings_inr > 0 ? 'text-emerald-400' : 'text-rose-400'
                              }`}
                            >
                              {d.estimated_monthly_savings_inr > 0 ? 'Savings: ' : 'Increase: '}
                              {formatINR(Math.abs(d.estimated_monthly_savings_inr))}
                            </div>
                          )}
                        </td>
                        <td className="py-3 px-4">
                          <div className="flex items-center gap-1.5">
                            <span className="px-1.5 py-0.5 rounded bg-gray-800 text-gray-300 text-[10px] font-mono">
                              {d.operating_mode}
                            </span>
                            {d.executed && d.verified && (
                              <span title="Verified in Docker">
                                <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />
                              </span>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* TAB 3: APPROVAL QUEUE */}
      {activeTab === 'approvals' && (
        <div className="bg-gray-900 border border-gray-800 rounded-2xl overflow-hidden shadow-sm">
          <div className="px-6 py-4 border-b border-gray-800 flex items-center justify-between">
            <div>
              <h3 className="font-semibold text-white">Vertical Scaling Approval Queue</h3>
              <p className="text-xs text-gray-400 mt-0.5">
                Requests initiated by VM owners requiring Company Administrator sign-off.
              </p>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-gray-300">
              <thead className="bg-gray-950/60 text-xs font-semibold text-gray-400 uppercase tracking-wider border-b border-gray-800">
                <tr>
                  <th className="py-3 px-4">Request ID / Time</th>
                  <th className="py-3 px-4">VM Resource</th>
                  <th className="py-3 px-4">Requester</th>
                  <th className="py-3 px-4">Requested Change</th>
                  <th className="py-3 px-4">FinOps Cost Delta</th>
                  <th className="py-3 px-4">Status</th>
                  {isAdmin && <th className="py-3 px-4 text-right">Review Action</th>}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                {changeRequests.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="py-8 text-center text-gray-400 text-sm">
                      No change requests in queue.
                    </td>
                  </tr>
                ) : (
                  changeRequests.map((cr) => {
                    const isPending = cr.status === 'PENDING';
                    const isApproved = cr.status === 'APPROVED';
                    return (
                      <tr key={cr.id} className="hover:bg-gray-800/40 transition">
                        <td className="py-3.5 px-4">
                          <span className="font-mono text-xs text-purple-300">{cr.id}</span>
                          <div className="text-[11px] text-gray-500 mt-0.5">
                            {new Date(cr.created_at || '').toLocaleDateString()}
                          </div>
                        </td>
                        <td className="py-3.5 px-4 font-semibold text-white">{cr.resource_name || cr.resource_id}</td>
                        <td className="py-3.5 px-4 text-xs text-gray-300">
                          {cr.requester_email || cr.requester_id}
                          <div className="text-[11px] text-gray-500 italic mt-0.5">{cr.reason}</div>
                        </td>
                        <td className="py-3.5 px-4 font-mono text-xs">
                          <span className="text-gray-400">
                            {cr.current_cpu_cores}C/{cr.current_memory_gb}G
                          </span>
                          &nbsp;→&nbsp;
                          <span className="text-purple-400 font-bold">
                            {cr.target_cpu_cores}C/{cr.target_memory_gb}G
                          </span>
                        </td>
                        <td className="py-3.5 px-4 font-mono text-xs">
                          {cr.cost_difference_inr > 0 ? (
                            <span className="text-rose-400 flex items-center gap-1">
                              <TrendingUp className="w-3.5 h-3.5" />
                              +{formatINR(cr.cost_difference_inr)}
                            </span>
                          ) : cr.cost_difference_inr < 0 ? (
                            <span className="text-emerald-400 flex items-center gap-1">
                              <TrendingDown className="w-3.5 h-3.5" />
                              {formatINR(cr.cost_difference_inr)}
                            </span>
                          ) : (
                            <span className="text-gray-400">₹0</span>
                          )}
                        </td>
                        <td className="py-3.5 px-4">
                          <span
                            className={`px-2 py-0.5 rounded text-xs font-semibold ${
                              isPending
                                ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                                : isApproved
                                ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                                : 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
                            }`}
                          >
                            {cr.status}
                          </span>
                        </td>
                        {isAdmin && (
                          <td className="py-3.5 px-4 text-right">
                            {isPending ? (
                              <div className="flex items-center justify-end gap-2">
                                <button
                                  onClick={() => handleReviewCr(cr.id, 'APPROVED')}
                                  className="px-2.5 py-1 rounded bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold transition"
                                >
                                  Approve
                                </button>
                                <button
                                  onClick={() => handleReviewCr(cr.id, 'REJECTED')}
                                  className="px-2.5 py-1 rounded bg-rose-600 hover:bg-rose-500 text-white text-xs font-semibold transition"
                                >
                                  Reject
                                </button>
                              </div>
                            ) : (
                              <span className="text-xs text-gray-500">Reviewed</span>
                            )}
                          </td>
                        )}
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* TAB 3: AUDIT TRAIL */}
      {activeTab === 'audit' && (
        <div className="bg-gray-900 border border-gray-800 rounded-2xl overflow-hidden shadow-sm">
          <div className="px-6 py-4 border-b border-gray-800">
            <h3 className="font-semibold text-white">Immutable Governance Audit Trail</h3>
            <p className="text-xs text-gray-400 mt-0.5">
              Cryptographically timestamped audit log of all vertical scaling decisions, policy changes, and ownership delegations.
            </p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-gray-300">
              <thead className="bg-gray-950/60 text-xs font-semibold text-gray-400 uppercase tracking-wider border-b border-gray-800">
                <tr>
                  <th className="py-3 px-4">Timestamp</th>
                  <th className="py-3 px-4">Actor & Role</th>
                  <th className="py-3 px-4">Action</th>
                  <th className="py-3 px-4">Resource</th>
                  <th className="py-3 px-4">Outcome</th>
                  <th className="py-3 px-4">Audit Details</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800 font-mono text-xs">
                {auditEvents.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="py-8 text-center text-gray-400 text-sm font-sans">
                      No audit events recorded yet.
                    </td>
                  </tr>
                ) : (
                  auditEvents.map((e) => (
                    <tr key={e.id} className="hover:bg-gray-800/40 transition">
                      <td className="py-3 px-4 text-gray-400">
                        {new Date(e.timestamp || '').toLocaleTimeString()}
                      </td>
                      <td className="py-3 px-4">
                        <span className="text-purple-300 font-semibold">{e.details.actor_id}</span>
                        <div className="text-[10px] text-gray-500">{e.details.actor_role}</div>
                      </td>
                      <td className="py-3 px-4 text-cyan-400 font-semibold">{e.action}</td>
                      <td className="py-3 px-4 text-gray-300">{e.resource_id || 'Tenant Scope'}</td>
                      <td className="py-3 px-4">
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                            e.details.outcome === 'SUCCESS'
                              ? 'bg-emerald-500/20 text-emerald-400'
                              : e.details.outcome === 'PENDING_APPROVAL'
                              ? 'bg-amber-500/20 text-amber-400'
                              : 'bg-rose-500/20 text-rose-400'
                          }`}
                        >
                          {e.details.outcome}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-gray-400 font-sans text-xs">
                        {e.details.reason}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* MODAL 1: VERTICAL SCALING DIALOG */}
      {selectedVmForScale && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-lg p-6 shadow-2xl">
            <h3 className="text-lg font-bold text-white flex items-center gap-2">
              <Sliders className="w-5 h-5 text-purple-400" />
              Vertical Scale Resource: {selectedVmForScale.name}
            </h3>
            <p className="text-xs text-gray-400 mt-1">
              Adjust compute and memory parameters. Changes are validated against company policy and applied directly to local Docker workload if live.
            </p>

            <form onSubmit={handleExecuteScale} className="mt-5 space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-medium text-gray-300 mb-1">Target vCPUs</label>
                  <input
                    type="number"
                    min="1"
                    max="64"
                    step="1"
                    value={scaleTargetCpu}
                    onChange={(e) => setScaleTargetCpu(parseInt(e.target.value) || 1)}
                    className="w-full bg-gray-950 border border-gray-700 rounded-lg px-3 py-2 text-white font-mono text-sm focus:border-purple-500 focus:outline-none"
                    required
                  />
                  <span className="text-[11px] text-gray-500">Current: {selectedVmForScale.cpu_cores} cores</span>
                </div>

                <div>
                  <label className="block text-xs font-medium text-gray-300 mb-1">Target RAM (GB)</label>
                  <input
                    type="number"
                    min="0.25"
                    max="128"
                    step="0.25"
                    value={scaleTargetMemory}
                    onChange={(e) => setScaleTargetMemory(parseFloat(e.target.value) || 1.0)}
                    className="w-full bg-gray-950 border border-gray-700 rounded-lg px-3 py-2 text-white font-mono text-sm focus:border-purple-500 focus:outline-none"
                    required
                  />
                  <span className="text-[11px] text-gray-500">Current: {selectedVmForScale.memory} GB</span>
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-300 mb-1">Justification / Reason</label>
                <input
                  type="text"
                  value={scaleReason}
                  onChange={(e) => setScaleReason(e.target.value)}
                  placeholder="e.g. Preparing for scheduled peak traffic"
                  className="w-full bg-gray-950 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:border-purple-500 focus:outline-none"
                  required
                />
              </div>

              {/* FinOps Cost Preview Box */}
              <div className="bg-gray-950/80 border border-gray-800 rounded-xl p-3 text-xs">
                <div className="font-semibold text-gray-300 flex items-center justify-between">
                  <span>FinOps Compute Tier Preview</span>
                  <span className="text-gray-500 text-[10px]">₹800/core + ₹200/GB</span>
                </div>
                <div className="grid grid-cols-2 gap-2 mt-2 font-mono">
                  <div>
                    <span className="text-gray-400">Current Cost:</span>{' '}
                    <span className="text-white">{formatINR(selectedVmForScale.monthly_cost || 0)}</span>
                  </div>
                  <div>
                    <span className="text-gray-400">Proposed:</span>{' '}
                    <span className="text-purple-400 font-bold">
                      {formatINR(roundCost(scaleTargetCpu * 800 + scaleTargetMemory * 200))}
                    </span>
                  </div>
                </div>
              </div>

              {scaleFeedback && (
                <div
                  className={`p-3 rounded-xl text-xs flex items-center gap-2 ${
                    scaleFeedback.status === 'APPLIED'
                      ? 'bg-emerald-500/10 text-emerald-300 border border-emerald-500/30'
                      : scaleFeedback.status === 'PENDING_APPROVAL'
                      ? 'bg-amber-500/10 text-amber-300 border border-amber-500/30'
                      : 'bg-rose-500/10 text-rose-300 border border-rose-500/30'
                  }`}
                >
                  {scaleFeedback.status === 'APPLIED' ? (
                    <CheckCircle className="w-4 h-4 text-emerald-400" />
                  ) : scaleFeedback.status === 'PENDING_APPROVAL' ? (
                    <Clock className="w-4 h-4 text-amber-400" />
                  ) : (
                    <AlertTriangle className="w-4 h-4 text-rose-400" />
                  )}
                  <span>{scaleFeedback.message}</span>
                </div>
              )}

              <div className="flex items-center justify-end gap-3 pt-3 border-t border-gray-800">
                <button
                  type="button"
                  onClick={() => setSelectedVmForScale(null)}
                  className="px-4 py-2 rounded-xl text-gray-300 hover:text-white bg-gray-800 hover:bg-gray-700 text-xs font-medium transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={scaleSubmitting}
                  className="px-4 py-2 rounded-xl bg-purple-600 hover:bg-purple-500 text-white text-xs font-semibold transition flex items-center gap-2"
                >
                  {scaleSubmitting && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
                  Submit Vertical Scale
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL 2: POLICY CONFIGURATION DIALOG */}
      {selectedVmForPolicy && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-lg p-6 shadow-2xl">
            <h3 className="text-lg font-bold text-white flex items-center gap-2">
              <Shield className="w-5 h-5 text-purple-400" />
              Configure Policy: {selectedVmForPolicy.name}
            </h3>
            <p className="text-xs text-gray-400 mt-1">
              Set authorized boundaries and governance approval requirements for this virtual machine.
            </p>

            <form onSubmit={handleUpdatePolicy} className="mt-5 space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-medium text-gray-300 mb-1">Min vCPUs</label>
                  <input
                    type="number"
                    min="1"
                    max="64"
                    value={policyForm.min_cpu_cores}
                    onChange={(e) => setPolicyForm({ ...policyForm, min_cpu_cores: parseInt(e.target.value) || 1 })}
                    className="w-full bg-gray-950 border border-gray-700 rounded-lg px-3 py-2 text-white font-mono text-sm"
                    required
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-300 mb-1">Max vCPUs</label>
                  <input
                    type="number"
                    min="1"
                    max="128"
                    value={policyForm.max_cpu_cores}
                    onChange={(e) => setPolicyForm({ ...policyForm, max_cpu_cores: parseInt(e.target.value) || 1 })}
                    className="w-full bg-gray-950 border border-gray-700 rounded-lg px-3 py-2 text-white font-mono text-sm"
                    required
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-medium text-gray-300 mb-1">Min Memory (GB)</label>
                  <input
                    type="number"
                    min="0.25"
                    max="128"
                    step="0.25"
                    value={policyForm.min_memory_gb}
                    onChange={(e) => setPolicyForm({ ...policyForm, min_memory_gb: parseFloat(e.target.value) || 0.5 })}
                    className="w-full bg-gray-950 border border-gray-700 rounded-lg px-3 py-2 text-white font-mono text-sm"
                    required
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-300 mb-1">Max Memory (GB)</label>
                  <input
                    type="number"
                    min="0.5"
                    max="256"
                    step="0.5"
                    value={policyForm.max_memory_gb}
                    onChange={(e) => setPolicyForm({ ...policyForm, max_memory_gb: parseFloat(e.target.value) || 1.0 })}
                    className="w-full bg-gray-950 border border-gray-700 rounded-lg px-3 py-2 text-white font-mono text-sm"
                    required
                  />
                </div>
              </div>

              <div className="space-y-2 pt-2">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={policyForm.allow_manual_scaling}
                    onChange={(e) => setPolicyForm({ ...policyForm, allow_manual_scaling: e.target.checked })}
                    className="rounded bg-gray-950 border-gray-700 text-purple-600 focus:ring-0"
                  />
                  <span className="text-xs text-gray-300 font-medium">Allow VM owner manual scaling within bounds</span>
                </label>

                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={policyForm.requires_approval}
                    onChange={(e) => setPolicyForm({ ...policyForm, requires_approval: e.target.checked })}
                    className="rounded bg-gray-950 border-gray-700 text-purple-600 focus:ring-0"
                  />
                  <span className="text-xs text-gray-300 font-medium">
                    Require Company Admin approval before applying scaling changes
                  </span>
                </label>
              </div>

              <div className="flex items-center justify-end gap-3 pt-3 border-t border-gray-800">
                <button
                  type="button"
                  onClick={() => setSelectedVmForPolicy(null)}
                  className="px-4 py-2 rounded-xl text-gray-300 hover:text-white bg-gray-800 hover:bg-gray-700 text-xs font-medium transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={policySubmitting}
                  className="px-4 py-2 rounded-xl bg-purple-600 hover:bg-purple-500 text-white text-xs font-semibold transition"
                >
                  Save Policy
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL 3: OWNER ASSIGNMENT DIALOG */}
      {selectedVmForOwner && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-md p-6 shadow-2xl">
            <h3 className="text-lg font-bold text-white flex items-center gap-2">
              <UserCheck className="w-5 h-5 text-purple-400" />
              Assign VM Owner
            </h3>
            <p className="text-xs text-gray-400 mt-1">
              Select an authorized user in <span className="text-purple-300">{company?.name}</span> to delegate ownership of {selectedVmForOwner.name}.
            </p>

            <form onSubmit={handleAssignOwner} className="mt-5 space-y-4">
              <div>
                <label className="block text-xs font-medium text-gray-300 mb-1">Target Owner</label>
                <select
                  value={selectedOwnerId}
                  onChange={(e) => setSelectedOwnerId(e.target.value)}
                  className="w-full bg-gray-950 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:border-purple-500 focus:outline-none"
                >
                  <option value="">-- Unassigned --</option>
                  {tenantUsers.map((u) => (
                    <option key={u.id} value={u.id}>
                      {u.full_name} ({u.email}) [{u.role}]
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex items-center justify-end gap-3 pt-3 border-t border-gray-800">
                <button
                  type="button"
                  onClick={() => setSelectedVmForOwner(null)}
                  className="px-4 py-2 rounded-xl text-gray-300 hover:text-white bg-gray-800 hover:bg-gray-700 text-xs font-medium transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={assignSubmitting}
                  className="px-4 py-2 rounded-xl bg-purple-600 hover:bg-purple-500 text-white text-xs font-semibold transition"
                >
                  Confirm Assignment
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL 4: KVM VM RESIZE DIALOG */}
      {selectedKvmVmForResize && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-lg p-6 shadow-2xl">
            <div className="flex items-center justify-between border-b border-gray-800 pb-4">
              <div>
                <h3 className="text-lg font-bold text-white flex items-center gap-2">
                  <Sliders className="w-5 h-5 text-cyan-400" />
                  Resize KVM Virtual Machine
                </h3>
                <p className="text-xs text-gray-400 mt-0.5">
                  Modifying real libvirt domain: <span className="text-cyan-300 font-semibold">{selectedKvmVmForResize.name}</span>
                </p>
              </div>
              <span
                className={`px-2 py-0.5 rounded text-xs font-semibold ${
                  selectedKvmVmForResize.is_running ? 'bg-emerald-500/20 text-emerald-400' : 'bg-gray-800 text-gray-400'
                }`}
              >
                {selectedKvmVmForResize.state.toUpperCase()}
              </span>
            </div>

            <form onSubmit={handleResizeKvmVm} className="mt-5 space-y-4">
              {/* vCPU Slider */}
              <div>
                <div className="flex justify-between text-xs text-gray-300 mb-1">
                  <span>Target vCPU Cores</span>
                  <span className="font-mono text-cyan-400 font-bold">{kvmResizeCpu} Cores</span>
                </div>
                <input
                  type="range"
                  min="1"
                  max={Math.min(selectedKvmVmForResize.max_cpu_cores || 8, kvmStatus?.host_cpu_cores || 16)}
                  step="1"
                  value={kvmResizeCpu}
                  onChange={(e) => setKvmResizeCpu(parseInt(e.target.value, 10))}
                  className="w-full h-2 bg-gray-800 rounded-lg appearance-none cursor-pointer accent-cyan-500"
                />
                <div className="flex justify-between text-[10px] text-gray-500 mt-0.5">
                  <span>Current: {selectedKvmVmForResize.current_cpu_cores}C</span>
                  <span>Max: {selectedKvmVmForResize.max_cpu_cores}C</span>
                </div>
              </div>

              {/* Memory Slider */}
              <div>
                <div className="flex justify-between text-xs text-gray-300 mb-1">
                  <span>Target Memory (RAM)</span>
                  <span className="font-mono text-cyan-400 font-bold">{kvmResizeMem} GB</span>
                </div>
                <input
                  type="range"
                  min="0.5"
                  max={Math.min(selectedKvmVmForResize.max_memory_gb || 16, kvmStatus?.max_safe_allocatable_ram_gb || 8)}
                  step="0.5"
                  value={kvmResizeMem}
                  onChange={(e) => setKvmResizeMem(parseFloat(e.target.value))}
                  className="w-full h-2 bg-gray-800 rounded-lg appearance-none cursor-pointer accent-cyan-500"
                />
                <div className="flex justify-between text-[10px] text-gray-500 mt-0.5">
                  <span>Current: {selectedKvmVmForResize.current_memory_gb} GB</span>
                  <span>Safe Headroom Limit: {kvmStatus?.max_safe_allocatable_ram_gb || 6} GB</span>
                </div>
              </div>

              {/* FinOps Cost Projection */}
              <div className="p-3.5 rounded-xl bg-gray-950 border border-gray-800 flex items-center justify-between text-xs">
                <div>
                  <div className="text-gray-400">Projected Monthly Cost</div>
                  <div className="text-[10px] text-gray-500">₹800/core + ₹200/GB RAM</div>
                </div>
                <div className="text-right">
                  <div className="font-bold text-white text-sm">
                    {formatINR((kvmResizeCpu * 800) + (kvmResizeMem * 200))}
                  </div>
                  <div className={`text-[11px] font-semibold ${
                    (kvmResizeCpu * 800 + kvmResizeMem * 200) < selectedKvmVmForResize.estimated_monthly_cost
                      ? 'text-emerald-400'
                      : 'text-gray-400'
                  }`}>
                    Current: {formatINR(selectedKvmVmForResize.estimated_monthly_cost)}
                  </div>
                </div>
              </div>

              {/* Shutdown Warning Banner if Live Shrinking */}
              {selectedKvmVmForResize.is_running && kvmResizeCpu < selectedKvmVmForResize.current_cpu_cores && (
                <div className="p-3.5 rounded-xl bg-amber-500/10 border border-amber-500/30 text-xs">
                  <div className="flex items-center gap-1.5 text-amber-300 font-bold mb-1">
                    <AlertTriangle className="w-4 h-4 text-amber-400" />
                    Guest Reboot/Shutdown Required
                  </div>
                  <p className="text-gray-300 text-[11px] leading-relaxed">
                    Live vCPU shrinking ({selectedKvmVmForResize.current_cpu_cores} &rarr; {kvmResizeCpu} cores) is unsupported by KVM while running.
                    Zero unplanned downtime protocol: SmartCloud Optimizer will never shut down a running VM without explicit confirmation.
                  </p>
                  <label className="flex items-center gap-2 mt-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={kvmAllowShutdown}
                      onChange={(e) => setKvmAllowShutdown(e.target.checked)}
                      className="rounded bg-gray-950 border-gray-700 text-cyan-500 focus:ring-0"
                    />
                    <span className="text-xs font-semibold text-amber-200">
                      Explicitly authorize guest reboot/shutdown for this resize
                    </span>
                  </label>
                </div>
              )}

              {/* Feedback Alert */}
              {kvmResizeFeedback && (
                <div
                  className={`p-3 rounded-xl border text-xs ${
                    kvmResizeFeedback.success
                      ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
                      : kvmResizeFeedback.requires_shutdown
                      ? 'bg-amber-500/10 border-amber-500/30 text-amber-300'
                      : 'bg-rose-500/10 border-rose-500/30 text-rose-300'
                  }`}
                >
                  <div className="font-semibold">{kvmResizeFeedback.status}</div>
                  <div className="text-[11px] mt-0.5">{kvmResizeFeedback.message || kvmResizeFeedback.error}</div>
                </div>
              )}

              <div className="flex items-center justify-end gap-3 pt-3 border-t border-gray-800">
                <button
                  type="button"
                  onClick={() => {
                    setSelectedKvmVmForResize(null);
                    setKvmResizeFeedback(null);
                  }}
                  className="px-4 py-2 rounded-xl text-gray-300 hover:text-white bg-gray-800 hover:bg-gray-700 text-xs font-medium transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={kvmResizeSubmitting}
                  className="px-4 py-2 rounded-xl bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-semibold transition"
                >
                  {kvmResizeSubmitting ? 'Verifying & Resizing...' : 'Execute Resize'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

function roundCost(v: number): number {
  return Math.round(v * 100) / 100;
}
