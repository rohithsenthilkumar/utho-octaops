import React, { useState, useEffect } from 'react';
import {
  Settings,
  Save,
  RotateCcw,
  Sliders,
  Bell,
  MapPin,
  Building,
  CheckCircle2,
  Database,
  Cpu,
} from 'lucide-react';
import { AppSettings, Region } from '../types';
import { INITIAL_SETTINGS } from '../services/mockData';

interface SettingsPageProps {
  settings: AppSettings;
  onSaveSettings: (settings: AppSettings) => void;
  onResetSettings: () => void;
}

export const SettingsPage: React.FC<SettingsPageProps> = ({
  settings,
  onSaveSettings,
  onResetSettings,
}) => {
  const [formData, setFormData] = useState<AppSettings>({ ...settings });
  const [hasChanges, setHasChanges] = useState(false);

  useEffect(() => {
    setFormData({ ...settings });
  }, [settings]);

  const handleChange = <K extends keyof AppSettings>(key: K, value: AppSettings[K]) => {
    setFormData((prev) => ({ ...prev, [key]: value }));
    setHasChanges(true);
  };

  const handleToggleRegion = (reg: Region) => {
    const current = formData.regions || [];
    const updated = current.includes(reg)
      ? current.filter((r) => r !== reg)
      : [...current, reg];
    handleChange('regions', updated);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSaveSettings(formData);
    setHasChanges(false);
  };

  const handleReset = () => {
    setFormData({ ...INITIAL_SETTINGS });
    onResetSettings();
    setHasChanges(false);
  };

  return (
    <div className="max-w-4xl space-y-6">
      <form onSubmit={handleSubmit} className="space-y-6">
        {/* 1. General & Organization */}
        <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6 shadow-sm space-y-4">
          <div className="flex items-center gap-2 pb-3 border-b border-gray-800">
            <Building className="w-5 h-5 text-blue-400" />
            <div>
              <h2 className="text-base font-bold text-white tracking-tight">Organization Profile</h2>
              <p className="text-xs text-gray-400">Basic enterprise and currency preferences.</p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
            <div>
              <label className="block font-medium text-gray-300 mb-1.5">Company / Tenant Name</label>
              <input
                type="text"
                value={formData.company_name}
                onChange={(e) => handleChange('company_name', e.target.value)}
                className="w-full px-3.5 py-2 bg-gray-950 border border-gray-800 rounded-xl text-gray-200 focus:outline-none focus:border-blue-500 transition"
              />
            </div>

            <div>
              <label className="block font-medium text-gray-300 mb-1.5">Reporting Currency</label>
              <select
                value={formData.currency}
                onChange={(e) => handleChange('currency', e.target.value as 'INR' | 'USD')}
                className="w-full px-3.5 py-2 bg-gray-950 border border-gray-800 rounded-xl text-gray-200 focus:outline-none focus:border-blue-500 transition cursor-pointer"
              >
                <option value="INR">Indian Rupee (INR ₹)</option>
                <option value="USD">US Dollar (USD $)</option>
              </select>
            </div>

            <div className="md:col-span-2">
              <label className="block font-medium text-gray-300 mb-1.5">Timezone</label>
              <input
                type="text"
                value={formData.timezone}
                onChange={(e) => handleChange('timezone', e.target.value)}
                className="w-full px-3.5 py-2 bg-gray-950 border border-gray-800 rounded-xl text-gray-200 focus:outline-none focus:border-blue-500 transition"
              />
              <span className="text-[11px] text-gray-500 mt-1 block">
                Used to align peak usage metrics and off-hours auto-shutdown schedules.
              </span>
            </div>
          </div>
        </div>

        {/* 2. Sizing Engine Optimization Thresholds */}
        <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6 shadow-sm space-y-4">
          <div className="flex items-center gap-2 pb-3 border-b border-gray-800">
            <Cpu className="w-5 h-5 text-cyan-400" />
            <div>
              <h2 className="text-base font-bold text-white tracking-tight">Optimization Safety Engine</h2>
              <p className="text-xs text-gray-400">
                Configure peak-load behavior thresholds so the engine never recommends sizing down dangerously.
              </p>
            </div>
          </div>

          <div className="space-y-4 text-xs">
            {/* Peak Percentile selection */}
            <div>
              <label className="block font-medium text-gray-300 mb-1">
                Peak Load Calculation Metric
              </label>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-1.5">
                <label
                  onClick={() => handleChange('peak_metric', 'p99')}
                  className={`p-3.5 rounded-xl border cursor-pointer transition flex items-start gap-3 ${
                    formData.peak_metric === 'p99'
                      ? 'border-blue-500 bg-blue-500/10'
                      : 'border-gray-800 bg-gray-950/70 hover:border-gray-700'
                  }`}
                >
                  <input
                    type="radio"
                    name="peak_metric"
                    checked={formData.peak_metric === 'p99'}
                    onChange={() => handleChange('peak_metric', 'p99')}
                    className="mt-0.5"
                  />
                  <div>
                    <span className="font-semibold text-white block">P99 Peak Load (Recommended)</span>
                    <span className="text-gray-400 text-[11px] mt-0.5 block leading-relaxed">
                      Evaluates the top 1% peak burst window over 30 days. Highest safety margin for production.
                    </span>
                  </div>
                </label>

                <label
                  onClick={() => handleChange('peak_metric', 'p95')}
                  className={`p-3.5 rounded-xl border cursor-pointer transition flex items-start gap-3 ${
                    formData.peak_metric === 'p95'
                      ? 'border-blue-500 bg-blue-500/10'
                      : 'border-gray-800 bg-gray-950/70 hover:border-gray-700'
                  }`}
                >
                  <input
                    type="radio"
                    name="peak_metric"
                    checked={formData.peak_metric === 'p95'}
                    onChange={() => handleChange('peak_metric', 'p95')}
                    className="mt-0.5"
                  />
                  <div>
                    <span className="font-semibold text-white block">P95 Load (Aggressive)</span>
                    <span className="text-gray-400 text-[11px] mt-0.5 block leading-relaxed">
                      Ignores short anomalous outlier spikes. Suitable for batch and non-production clusters.
                    </span>
                  </div>
                </label>
              </div>
            </div>

            {/* Threshold sliders */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
              <div className="bg-gray-950 p-4 rounded-xl border border-gray-800">
                <div className="flex items-center justify-between mb-2">
                  <span className="font-medium text-gray-300">Idle CPU Upper Threshold</span>
                  <span className="font-mono font-bold text-blue-400">{formData.idle_cpu_threshold}%</span>
                </div>
                <input
                  type="range"
                  min={5}
                  max={30}
                  step={1}
                  value={formData.idle_cpu_threshold}
                  onChange={(e) => handleChange('idle_cpu_threshold', Number(e.target.value))}
                  className="w-full accent-blue-500 cursor-pointer"
                />
                <span className="text-[11px] text-gray-500 block mt-1">
                  Instances under this CPU utilization will be flagged as idle candidates.
                </span>
              </div>

              <div className="bg-gray-950 p-4 rounded-xl border border-gray-800">
                <div className="flex items-center justify-between mb-2">
                  <span className="font-medium text-gray-300">Target RAM Headroom Buffer</span>
                  <span className="font-mono font-bold text-purple-400">{formData.ram_headroom_pct}%</span>
                </div>
                <input
                  type="range"
                  min={15}
                  max={50}
                  step={5}
                  value={formData.ram_headroom_pct}
                  onChange={(e) => handleChange('ram_headroom_pct', Number(e.target.value))}
                  className="w-full accent-purple-500 cursor-pointer"
                />
                <span className="text-[11px] text-gray-500 block mt-1">
                  Guaranteed buffer reserved above maximum peak RAM load.
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* 3. Regions & Notifications */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Target Regions */}
          <div className="bg-gray-900 border border-gray-800 rounded-2xl p-5 shadow-sm space-y-3 text-xs">
            <div className="flex items-center gap-2 pb-2 border-b border-gray-800">
              <MapPin className="w-4 h-4 text-emerald-400" />
              <h3 className="font-bold text-white">Monitored Indian Regions</h3>
            </div>

            <div className="space-y-2 pt-1">
              {(['Bangalore', 'Mumbai', 'Noida'] as Region[]).map((reg) => {
                const isChecked = formData.regions?.includes(reg);
                return (
                  <label
                    key={reg}
                    className="flex items-center justify-between p-2.5 bg-gray-950 border border-gray-800 rounded-xl cursor-pointer hover:border-gray-700 transition"
                  >
                    <span className="font-medium text-gray-200">{reg} Region</span>
                    <input
                      type="checkbox"
                      checked={isChecked}
                      onChange={() => handleToggleRegion(reg)}
                      className="accent-blue-500 w-4 h-4 rounded cursor-pointer"
                    />
                  </label>
                );
              })}
            </div>
          </div>

          {/* Notifications */}
          <div className="bg-gray-900 border border-gray-800 rounded-2xl p-5 shadow-sm space-y-3 text-xs">
            <div className="flex items-center gap-2 pb-2 border-b border-gray-800">
              <Bell className="w-4 h-4 text-amber-400" />
              <h3 className="font-bold text-white">Notification Feeds</h3>
            </div>

            <div className="space-y-2 pt-1">
              <label className="flex items-center justify-between p-2.5 bg-gray-950 border border-gray-800 rounded-xl cursor-pointer hover:border-gray-700 transition">
                <div>
                  <span className="font-medium text-gray-200 block">Weekly Digest Email</span>
                  <span className="text-[11px] text-gray-500">Summary of realized savings</span>
                </div>
                <input
                  type="checkbox"
                  checked={formData.email_notifications}
                  onChange={(e) => handleChange('email_notifications', e.target.checked)}
                  className="accent-blue-500 w-4 h-4 rounded cursor-pointer"
                />
              </label>

              <label className="flex items-center justify-between p-2.5 bg-gray-950 border border-gray-800 rounded-xl cursor-pointer hover:border-gray-700 transition">
                <div>
                  <span className="font-medium text-gray-200 block">Slack Anomaly Webhook</span>
                  <span className="text-[11px] text-gray-500">Real-time alerts for spikes</span>
                </div>
                <input
                  type="checkbox"
                  checked={formData.slack_notifications}
                  onChange={(e) => handleChange('slack_notifications', e.target.checked)}
                  className="accent-blue-500 w-4 h-4 rounded cursor-pointer"
                />
              </label>
            </div>
          </div>
        </div>

        {/* 4. Backend API Integration & Staging */}
        <div className="bg-gray-900 border border-gray-800 rounded-2xl p-5 shadow-sm space-y-3 text-xs">
          <div className="flex items-center gap-2 pb-2 border-b border-gray-800">
            <Database className="w-4 h-4 text-purple-400" />
            <h3 className="font-bold text-white">Backend API Integration</h3>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 items-center">
            <div className="sm:col-span-2">
              <label className="block font-medium text-gray-300 mb-1">Backend Base API URL</label>
              <input
                type="text"
                value={formData.api_endpoint}
                onChange={(e) => handleChange('api_endpoint', e.target.value)}
                className="w-full px-3.5 py-2 bg-gray-950 border border-gray-800 rounded-xl text-gray-200 font-mono text-xs focus:outline-none focus:border-blue-500"
              />
            </div>
            <div className="bg-gray-950 p-2.5 rounded-xl border border-gray-800 text-[11px] text-gray-400 flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
              <span>Stage 1: In-Memory Simulated Telemetry</span>
            </div>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex items-center justify-between pt-2">
          <button
            type="button"
            onClick={handleReset}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-medium text-gray-400 hover:text-white bg-gray-900 hover:bg-gray-800 border border-gray-800 transition"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            <span>Reset to Defaults</span>
          </button>

          <button
            type="submit"
            className="flex items-center gap-2 px-6 py-2.5 rounded-xl text-xs font-semibold text-white bg-blue-600 hover:bg-blue-500 shadow-md shadow-blue-600/20 transition"
          >
            <Save className="w-4 h-4" />
            <span>Save Configuration</span>
          </button>
        </div>
      </form>
    </div>
  );
};
