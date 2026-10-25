import React, { useState, useEffect, useMemo, useCallback } from 'react';
import {
  Search,
  Server,
  HardDrive,
  Globe,
  Database,
  ExternalLink,
  Plus,
  RefreshCw,
  AlertCircle,
  CheckCircle2,
  X,
  Layers,
  MapPin,
  Cpu,
} from 'lucide-react';
import { Resource, ResourceType, ResourceCreatePayload } from '../types';
import { fetchInventory, createResource } from '../services/api';
import { formatINR, formatPercent, getResourceStatusBadgeClass } from '../utils/formatters';

interface ResourcesPageProps {
  onSelectResource: (resource: Resource) => void;
  onResourceCreated?: (resource: Resource) => void;
}

export const ResourcesPage: React.FC<ResourcesPageProps> = ({
  onSelectResource,
  onResourceCreated,
}) => {
  const [resources, setResources] = useState<Resource[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Search & Filter state
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedRegion, setSelectedRegion] = useState<string>('All');
  const [selectedEnv, setSelectedEnv] = useState<string>('All');
  const [selectedType, setSelectedType] = useState<string>('All');

  // Create Resource Modal state
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [formData, setFormData] = useState<ResourceCreatePayload>({
    name: '',
    resource_type: 'VM',
    region: 'Bangalore',
    environment: 'prod',
    cpu_cores: 8,
    memory: 32,
    cpu_utilization: 25.0,
    estimated_monthly_cost: 32000,
    owner: 'Platform Team',
    status: 'ACTIVE',
    is_simulated: true,
  });

  // Load resources from backend API
  const loadResources = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchInventory();
      setResources(data);
    } catch (err: any) {
      console.error('Error fetching inventory from backend:', err);
      setError(
        err.response?.data?.detail ||
          'Failed to connect to backend resource API. Ensure FastAPI server is running on port 8000.'
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadResources();
  }, [loadResources]);

  // Handle Create Resource Submission
  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);

    if (!formData.name.trim()) {
      setFormError('Resource name is required.');
      return;
    }
    if (formData.cpu_cores < 1) {
      setFormError('CPU cores must be at least 1.');
      return;
    }
    if (formData.memory <= 0) {
      setFormError('Memory must be greater than 0 GB.');
      return;
    }
    if (formData.estimated_monthly_cost < 0) {
      setFormError('Estimated monthly cost cannot be negative.');
      return;
    }

    setIsSubmitting(true);
    try {
      const created = await createResource({
        ...formData,
        name: formData.name.includes('[Simulated]')
          ? formData.name
          : `${formData.name} [Simulated]`,
      });
      setShowCreateModal(false);
      setFormData({
        name: '',
        resource_type: 'VM',
        region: 'Bangalore',
        environment: 'prod',
        cpu_cores: 8,
        memory: 32,
        cpu_utilization: 25.0,
        estimated_monthly_cost: 32000,
        owner: 'Platform Team',
        status: 'ACTIVE',
        is_simulated: true,
      });
      // Re-fetch to update table
      await loadResources();
      if (onResourceCreated) onResourceCreated(created);
    } catch (err: any) {
      console.error('Error creating resource:', err);
      setFormError(err.response?.data?.detail || 'Failed to create resource on backend.');
    } finally {
      setIsSubmitting(false);
    }
  };

  // Filtered resources
  const filteredResources = useMemo(() => {
    return resources.filter((item) => {
      // Search
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase().trim();
        const matchesName = item.name.toLowerCase().includes(q);
        const matchesId = item.id.toLowerCase().includes(q);
        const matchesOwner = item.owner?.toLowerCase().includes(q);
        if (!matchesName && !matchesId && !matchesOwner) return false;
      }
      // Region
      if (selectedRegion !== 'All' && item.region.toLowerCase() !== selectedRegion.toLowerCase()) {
        return false;
      }
      // Environment
      if (selectedEnv !== 'All' && item.environment.toLowerCase() !== selectedEnv.toLowerCase()) {
        return false;
      }
      // Type
      if (selectedType !== 'All' && item.type.toLowerCase() !== selectedType.toLowerCase()) {
        return false;
      }
      return true;
    });
  }, [resources, searchQuery, selectedRegion, selectedEnv, selectedType]);

  const totalFilteredCost = useMemo(() => {
    return filteredResources.reduce((acc, r) => acc + (r.monthly_cost || 0), 0);
  }, [filteredResources]);

  const renderTypeIcon = (type: string) => {
    const t = type.toLowerCase();
    if (t.includes('volume') || t.includes('block')) {
      return <HardDrive className="w-3.5 h-3.5 text-purple-400" />;
    }
    if (t.includes('ip') || t.includes('public')) {
      return <Globe className="w-3.5 h-3.5 text-emerald-400" />;
    }
    if (t.includes('storage')) {
      return <Database className="w-3.5 h-3.5 text-amber-400" />;
    }
    return <Server className="w-3.5 h-3.5 text-blue-400" />;
  };

  return (
    <div className="space-y-5">
      {/* Search, Filters, and Add Resource Controls */}
      <div className="bg-gray-900 border border-gray-800 rounded-2xl p-4 shadow-sm space-y-3">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
          {/* Search box */}
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
            <input
              type="text"
              placeholder="Search by resource name, ID, or owner..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-2 bg-gray-950 border border-gray-800 rounded-xl text-xs text-gray-200 placeholder-gray-500 focus:outline-none focus:border-blue-500 transition"
            />
          </div>

          {/* Action buttons and filter dropdowns */}
          <div className="flex flex-wrap items-center gap-2.5 text-xs">
            {/* Region Filter */}
            <div className="flex items-center gap-1.5 bg-gray-950 border border-gray-800 rounded-xl px-3 py-1.5">
              <MapPin className="w-3.5 h-3.5 text-gray-400" />
              <span className="text-gray-400">Region:</span>
              <select
                value={selectedRegion}
                onChange={(e) => setSelectedRegion(e.target.value)}
                className="bg-transparent text-gray-200 font-medium focus:outline-none cursor-pointer"
              >
                <option value="All" className="bg-gray-900">All Regions</option>
                <option value="Bangalore" className="bg-gray-900">Bangalore</option>
                <option value="Mumbai" className="bg-gray-900">Mumbai</option>
                <option value="Noida" className="bg-gray-900">Noida</option>
              </select>
            </div>

            {/* Environment Filter */}
            <div className="flex items-center gap-1.5 bg-gray-950 border border-gray-800 rounded-xl px-3 py-1.5">
              <span className="text-gray-400">Env:</span>
              <select
                value={selectedEnv}
                onChange={(e) => setSelectedEnv(e.target.value)}
                className="bg-transparent text-gray-200 font-medium focus:outline-none cursor-pointer uppercase"
              >
                <option value="All" className="bg-gray-900">All Envs</option>
                <option value="prod" className="bg-gray-900">Prod</option>
                <option value="staging" className="bg-gray-900">Staging</option>
                <option value="dev" className="bg-gray-900">Dev</option>
                <option value="qa" className="bg-gray-900">QA</option>
              </select>
            </div>

            {/* Type Filter */}
            <div className="flex items-center gap-1.5 bg-gray-950 border border-gray-800 rounded-xl px-3 py-1.5">
              <Layers className="w-3.5 h-3.5 text-gray-400" />
              <span className="text-gray-400">Type:</span>
              <select
                value={selectedType}
                onChange={(e) => setSelectedType(e.target.value)}
                className="bg-transparent text-gray-200 font-medium focus:outline-none cursor-pointer"
              >
                <option value="All" className="bg-gray-900">All Types</option>
                <option value="VM" className="bg-gray-900">VMs</option>
                <option value="Block Volume" className="bg-gray-900">Block Volumes</option>
                <option value="Public IP" className="bg-gray-900">Public IPs</option>
              </select>
            </div>

            {/* Refresh from API button */}
            <button
              onClick={loadResources}
              disabled={loading}
              className="p-2 bg-gray-950 hover:bg-gray-800 border border-gray-800 rounded-xl text-gray-300 hover:text-white transition disabled:opacity-50"
              title="Refresh inventory from SQLite backend"
            >
              <RefreshCw className={`w-3.5 h-3.5 text-blue-400 ${loading ? 'animate-spin' : ''}`} />
            </button>

            {/* + Add Resource Button */}
            <button
              onClick={() => setShowCreateModal(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded-xl font-semibold shadow-md shadow-blue-600/20 transition"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>Add Resource</span>
            </button>
          </div>
        </div>

        {/* Filter stats count */}
        <div className="flex items-center justify-between text-xs text-gray-400 pt-2 border-t border-gray-800/80">
          <div>
            Showing <span className="font-semibold text-white">{filteredResources.length}</span> of{' '}
            <span className="font-semibold text-white">{resources.length}</span> cataloged resources
            <span className="ml-2 px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20 text-[10px] font-mono">
              SQLite Backend
            </span>
          </div>
          <div>
            Total monthly cost of filtered set:{' '}
            <span className="font-mono font-semibold text-white">{formatINR(totalFilteredCost)}</span>
          </div>
        </div>
      </div>

      {/* ERROR STATE */}
      {error && (
        <div className="bg-rose-950/40 border border-rose-800/80 rounded-2xl p-5 flex items-start gap-3.5 text-xs">
          <AlertCircle className="w-5 h-5 text-rose-400 min-w-5 mt-0.5" />
          <div className="flex-1">
            <h3 className="font-bold text-rose-300 text-sm">Failed to Load Backend Resources</h3>
            <p className="text-rose-400/90 mt-1 leading-relaxed">{error}</p>
            <button
              onClick={loadResources}
              className="mt-3 px-3.5 py-1.5 rounded-lg bg-rose-600 hover:bg-rose-500 text-white font-medium transition inline-flex items-center gap-1.5"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              <span>Retry Connection</span>
            </button>
          </div>
        </div>
      )}

      {/* LOADING STATE */}
      {loading && !error && (
        <div className="bg-gray-900 border border-gray-800 rounded-2xl p-12 text-center text-xs text-gray-400 space-y-3">
          <RefreshCw className="w-8 h-8 mx-auto text-blue-400 animate-spin opacity-80" />
          <p className="font-medium text-gray-200">Querying cloud resources from SQLite database...</p>
          <p className="text-[11px] text-gray-500">Connecting to /api/resources</p>
        </div>
      )}

      {/* INVENTORY TABLE */}
      {!loading && !error && (
        <div className="bg-gray-900 border border-gray-800 rounded-2xl overflow-hidden shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-gray-800 bg-gray-950/70 text-gray-400 text-xs font-semibold uppercase tracking-wider">
                  <th className="py-3 px-4">Resource</th>
                  <th className="py-3 px-4">Type</th>
                  <th className="py-3 px-4">Region & Env</th>
                  <th className="py-3 px-4">Allocation & Specs</th>
                  <th className="py-3 px-4">CPU Utilization</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-4 text-right">Monthly Cost</th>
                  <th className="py-3 px-4 text-center">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800/80 text-xs">
                {/* EMPTY STATE */}
                {filteredResources.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="py-12 text-center text-gray-500">
                      <Server className="w-8 h-8 mx-auto mb-2 opacity-40 text-gray-400" />
                      <p className="font-medium text-gray-400">No cloud resources found in SQLite database.</p>
                      <p className="text-[11px] text-gray-600 mt-1">
                        Try resetting your filters or click "+ Add Resource" above to create one.
                      </p>
                    </td>
                  </tr>
                ) : (
                  filteredResources.map((item) => (
                    <tr
                      key={item.id}
                      onClick={() => onSelectResource(item)}
                      className="hover:bg-gray-800/50 cursor-pointer transition-colors group"
                    >
                      {/* Resource Name and ID */}
                      <td className="py-3.5 px-4">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-gray-100 group-hover:text-blue-400 transition">
                            {item.name}
                          </span>
                          {item.is_simulated && (
                            <span className="text-[9px] font-bold px-1.5 py-0.2 rounded bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 uppercase tracking-tight">
                              Simulated
                            </span>
                          )}
                        </div>
                        <div className="font-mono text-[11px] text-gray-400 flex items-center gap-1.5 mt-0.5">
                          <span>{item.id}</span>
                          <span className="text-gray-600">•</span>
                          <span className="text-gray-400">{item.owner}</span>
                        </div>
                      </td>

                      {/* Type */}
                      <td className="py-3.5 px-4">
                        <div className="flex items-center gap-1.5 text-gray-300 font-medium">
                          {renderTypeIcon(item.type)}
                          <span>{item.type}</span>
                        </div>
                      </td>

                      {/* Region & Env */}
                      <td className="py-3.5 px-4">
                        <div className="text-gray-200 font-medium">{item.region}</div>
                        <span className="inline-block mt-0.5 text-[10px] font-bold px-1.5 py-0.2 rounded uppercase bg-gray-800 text-gray-400 border border-gray-700">
                          {item.environment}
                        </span>
                      </td>

                      {/* Specs */}
                      <td className="py-3.5 px-4 font-mono text-gray-300">
                        {item.cpu_cores ? `${item.cpu_cores} vCPU, ${item.memory} GB RAM` : item.current_spec_display}
                      </td>

                      {/* CPU Utilization */}
                      <td className="py-3.5 px-4 font-mono">
                        <div className="flex items-center gap-2">
                          <div className="w-16 bg-gray-800 h-1.5 rounded-full overflow-hidden">
                            <div
                              className={`h-full rounded-full ${
                                (item.cpu_utilization ?? item.p99_cpu) > 75
                                  ? 'bg-rose-500'
                                  : (item.cpu_utilization ?? item.p99_cpu) < 20
                                  ? 'bg-amber-400'
                                  : 'bg-emerald-400'
                              }`}
                              style={{ width: `${Math.min(100, item.cpu_utilization ?? item.p99_cpu)}%` }}
                            />
                          </div>
                          <span className="text-cyan-400">
                            {formatPercent(item.cpu_utilization ?? item.p99_cpu)}
                          </span>
                        </div>
                      </td>

                      {/* Status Badge */}
                      <td className="py-3.5 px-4">
                        <span
                          className={`inline-block px-2 py-0.5 rounded text-[10px] font-bold uppercase border ${getResourceStatusBadgeClass(
                            item.status
                          )}`}
                        >
                          {item.status.replace('_', ' ')}
                        </span>
                      </td>

                      {/* Monthly Cost */}
                      <td className="py-3.5 px-4 text-right font-mono font-bold text-gray-100">
                        {formatINR(item.monthly_cost)}
                      </td>

                      {/* Action */}
                      <td className="py-3.5 px-4 text-center">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            onSelectResource(item);
                          }}
                          className="px-2.5 py-1 rounded-lg bg-gray-800 hover:bg-blue-600 text-gray-300 hover:text-white transition font-medium text-[11px] inline-flex items-center gap-1"
                          title="View utilization details and specs"
                        >
                          <span>Details</span>
                          <ExternalLink className="w-3.5 h-3.5" />
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* CREATE RESOURCE MODAL (POST /api/resources) */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm overflow-y-auto">
          <div
            className="relative w-full max-w-lg bg-gray-900 border border-gray-800 rounded-2xl shadow-2xl overflow-hidden my-8"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="px-6 py-4 border-b border-gray-800 flex items-center justify-between bg-gray-950/60">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-center justify-center">
                  <Plus className="w-4 h-4 text-blue-400" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-white">Create Cloud Resource</h3>
                  <p className="text-[11px] text-gray-400">Add a simulated resource to the SQLite database</p>
                </div>
              </div>
              <button
                onClick={() => setShowCreateModal(false)}
                className="p-1 rounded-lg text-gray-400 hover:text-white hover:bg-gray-800 transition"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Modal Form */}
            <form onSubmit={handleCreateSubmit} className="p-6 space-y-4 text-xs">
              {formError && (
                <div className="p-3 bg-rose-500/15 border border-rose-500/30 rounded-xl text-rose-300 flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 min-w-4 text-rose-400" />
                  <span>{formError}</span>
                </div>
              )}

              {/* Resource Name */}
              <div>
                <label className="block text-gray-300 font-medium mb-1">Resource Name *</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. prod-payment-gateway-03"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  className="w-full px-3 py-2 bg-gray-950 border border-gray-800 rounded-xl text-gray-100 placeholder-gray-600 focus:outline-none focus:border-blue-500"
                />
              </div>

              {/* Region and Environment */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-gray-300 font-medium mb-1">Region *</label>
                  <select
                    value={formData.region}
                    onChange={(e) => setFormData({ ...formData, region: e.target.value })}
                    className="w-full px-3 py-2 bg-gray-950 border border-gray-800 rounded-xl text-gray-100 focus:outline-none focus:border-blue-500 cursor-pointer"
                  >
                    <option value="Bangalore">Bangalore</option>
                    <option value="Mumbai">Mumbai</option>
                    <option value="Noida">Noida</option>
                  </select>
                </div>
                <div>
                  <label className="block text-gray-300 font-medium mb-1">Environment *</label>
                  <select
                    value={formData.environment}
                    onChange={(e) => setFormData({ ...formData, environment: e.target.value })}
                    className="w-full px-3 py-2 bg-gray-950 border border-gray-800 rounded-xl text-gray-100 focus:outline-none focus:border-blue-500 cursor-pointer uppercase"
                  >
                    <option value="prod">prod</option>
                    <option value="staging">staging</option>
                    <option value="dev">dev</option>
                    <option value="qa">qa</option>
                  </select>
                </div>
              </div>

              {/* Resource Type and Status */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-gray-300 font-medium mb-1">Resource Type *</label>
                  <select
                    value={formData.resource_type}
                    onChange={(e) => setFormData({ ...formData, resource_type: e.target.value })}
                    className="w-full px-3 py-2 bg-gray-950 border border-gray-800 rounded-xl text-gray-100 focus:outline-none focus:border-blue-500 cursor-pointer"
                  >
                    <option value="VM">VM (Virtual Machine)</option>
                    <option value="Block Volume">Block Volume</option>
                    <option value="Public IP">Public IP</option>
                  </select>
                </div>
                <div>
                  <label className="block text-gray-300 font-medium mb-1">Status</label>
                  <select
                    value={formData.status}
                    onChange={(e) => setFormData({ ...formData, status: e.target.value })}
                    className="w-full px-3 py-2 bg-gray-950 border border-gray-800 rounded-xl text-gray-100 focus:outline-none focus:border-blue-500 cursor-pointer"
                  >
                    <option value="ACTIVE">ACTIVE</option>
                    <option value="OVER_PROVISIONED">OVER_PROVISIONED</option>
                    <option value="IDLE">IDLE</option>
                    <option value="ORPHANED">ORPHANED</option>
                  </select>
                </div>
              </div>

              {/* Specs: CPU and RAM */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-gray-300 font-medium mb-1">CPU Cores (vCPU) *</label>
                  <input
                    type="number"
                    min={1}
                    max={256}
                    value={formData.cpu_cores}
                    onChange={(e) => setFormData({ ...formData, cpu_cores: parseInt(e.target.value) || 1 })}
                    className="w-full px-3 py-2 bg-gray-950 border border-gray-800 rounded-xl text-gray-100 focus:outline-none focus:border-blue-500"
                  />
                </div>
                <div>
                  <label className="block text-gray-300 font-medium mb-1">Memory (RAM GB) *</label>
                  <input
                    type="number"
                    min={1}
                    max={2048}
                    value={formData.memory}
                    onChange={(e) => setFormData({ ...formData, memory: parseFloat(e.target.value) || 1 })}
                    className="w-full px-3 py-2 bg-gray-950 border border-gray-800 rounded-xl text-gray-100 focus:outline-none focus:border-blue-500"
                  />
                </div>
              </div>

              {/* CPU Utilization and Estimated Monthly Cost */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-gray-300 font-medium mb-1">CPU Utilization (%)</label>
                  <input
                    type="number"
                    min={0}
                    max={100}
                    step={0.1}
                    value={formData.cpu_utilization}
                    onChange={(e) => setFormData({ ...formData, cpu_utilization: parseFloat(e.target.value) || 0 })}
                    className="w-full px-3 py-2 bg-gray-950 border border-gray-800 rounded-xl text-gray-100 focus:outline-none focus:border-blue-500"
                  />
                </div>
                <div>
                  <label className="block text-gray-300 font-medium mb-1">Monthly Cost (INR ₹) *</label>
                  <input
                    type="number"
                    min={0}
                    value={formData.estimated_monthly_cost}
                    onChange={(e) => setFormData({ ...formData, estimated_monthly_cost: parseFloat(e.target.value) || 0 })}
                    className="w-full px-3 py-2 bg-gray-950 border border-gray-800 rounded-xl text-gray-100 focus:outline-none focus:border-blue-500"
                  />
                </div>
              </div>

              {/* Owner Team */}
              <div>
                <label className="block text-gray-300 font-medium mb-1">Owner / Team</label>
                <input
                  type="text"
                  value={formData.owner}
                  onChange={(e) => setFormData({ ...formData, owner: e.target.value })}
                  className="w-full px-3 py-2 bg-gray-950 border border-gray-800 rounded-xl text-gray-100 focus:outline-none focus:border-blue-500"
                />
              </div>

              {/* Actions */}
              <div className="pt-3 border-t border-gray-800 flex items-center justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="px-4 py-2 rounded-xl text-gray-300 hover:text-white bg-gray-800 hover:bg-gray-700 transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="px-4 py-2 rounded-xl text-white bg-blue-600 hover:bg-blue-500 font-semibold shadow-md shadow-blue-600/20 transition disabled:opacity-50"
                >
                  {isSubmitting ? 'Creating...' : 'Create in SQLite'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
