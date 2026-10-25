import React, { useState } from 'react';
import {
  Cloud,
  Lock,
  Mail,
  Eye,
  EyeOff,
  AlertCircle,
  Loader2,
  ShieldCheck,
  UserCheck,
  Building,
  KeyRound,
} from 'lucide-react';
import { loginUser, fetchCurrentUser } from '../services/api';
import { UserProfile } from '../types';

interface LoginPageProps {
  onLoginSuccess: (user: UserProfile) => void;
}

interface PersonaPreset {
  name: string;
  role: string;
  company: string;
  email: string;
  password: string;
  badgeColor: string;
}

const PRESET_PERSONAS: PersonaPreset[] = [
  {
    name: 'Rohith (Admin)',
    role: 'COMPANY_ADMIN',
    company: 'CloudFlow Hosting',
    email: 'admin@cloudflow.com',
    password: 'CloudFlowAdmin#2026',
    badgeColor: 'border-purple-500/40 bg-purple-500/10 text-purple-300',
  },
  {
    name: 'Aarav (VM Owner)',
    role: 'VM_OWNER',
    company: 'CloudFlow Hosting',
    email: 'devops@cloudflow.com',
    password: 'DevOpsOwner#2026',
    badgeColor: 'border-blue-500/40 bg-blue-500/10 text-blue-300',
  },
  {
    name: 'Vikram (Admin)',
    role: 'COMPANY_ADMIN',
    company: 'HostMatrix Ltd',
    email: 'admin@hostmatrix.com',
    password: 'HostMatrixAdmin#2026',
    badgeColor: 'border-amber-500/40 bg-amber-500/10 text-amber-300',
  },
  {
    name: 'Neha (VM Owner)',
    role: 'VM_OWNER',
    company: 'HostMatrix Ltd',
    email: 'owner@hostmatrix.com',
    password: 'HostOwner#2026',
    badgeColor: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300',
  },
];

export const LoginPage: React.FC<LoginPageProps> = ({ onLoginSuccess }) => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<{ email?: string; password?: string }>({});

  const validate = (): boolean => {
    const errors: { email?: string; password?: string } = {};
    if (!email.trim()) {
      errors.email = 'Email address is required.';
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
      errors.email = 'Please enter a valid work email address.';
    }

    if (!password) {
      errors.password = 'Password is required.';
    }

    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);

    if (!validate()) {
      return;
    }

    setLoading(true);
    try {
      // 1. Post credentials to /api/auth/login
      const loginRes = await loginUser(email.trim(), password);
      if (!loginRes || !loginRes.access_token) {
        throw new Error('Authentication response did not return an access token.');
      }

      // 2. Fetch authenticated identity via /api/auth/me
      const profile = await fetchCurrentUser();
      onLoginSuccess(profile);
    } catch (err: any) {
      const detail =
        err.response?.data?.detail ||
        err.message ||
        'Authentication failed. Please verify your credentials.';
      setErrorMessage(detail);
    } finally {
      setLoading(false);
    }
  };

  const handleApplyPreset = (preset: PersonaPreset) => {
    setEmail(preset.email);
    setPassword(preset.password);
    setFieldErrors({});
    setErrorMessage(null);
  };

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 flex flex-col justify-center items-center p-4 sm:p-6 selection:bg-blue-600 selection:text-white">
      {/* Background Accent Gradient */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-40 -left-40 w-96 h-96 bg-blue-600/10 rounded-full blur-3xl" />
        <div className="absolute top-1/2 -right-40 w-96 h-96 bg-purple-600/10 rounded-full blur-3xl" />
      </div>

      <div className="w-full max-w-md relative z-10 space-y-6">
        {/* Brand Header */}
        <div className="text-center space-y-2">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-gradient-to-tr from-cyan-600 to-blue-600 shadow-xl shadow-blue-500/20 mb-2 border border-cyan-400/30">
            <Cloud className="w-8 h-8 text-white" />
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-white flex items-center justify-center gap-2">
            SmartCloud <span className="text-cyan-400">Optimizer</span>
          </h1>
          <p className="text-xs text-gray-400">
            FinOps Resource Management & Cloud Governance Platform
          </p>
        </div>

        {/* Main Card */}
        <div className="bg-gray-900/90 border border-gray-800 rounded-2xl p-6 sm:p-8 shadow-2xl backdrop-blur-sm space-y-6">
          <div className="border-b border-gray-800/80 pb-4">
            <h2 className="text-base font-semibold text-white">Sign In to Your Workspace</h2>
            <p className="text-xs text-gray-400 mt-0.5">
              Enter your credentials to access tenant resources, rightsizing, and KVM governance.
            </p>
          </div>

          {/* Error Banner */}
          {errorMessage && (
            <div
              role="alert"
              className="p-3.5 rounded-xl bg-rose-500/10 border border-rose-500/30 flex items-start gap-3 text-xs text-rose-300 animate-in fade-in duration-200"
            >
              <AlertCircle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
              <div className="flex-1">
                <span className="font-semibold block">Authentication Error</span>
                <span>{errorMessage}</span>
              </div>
            </div>
          )}

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-4" noValidate>
            {/* Email Field */}
            <div className="space-y-1.5">
              <label
                htmlFor="login-email"
                className="block text-xs font-medium text-gray-300"
              >
                Work Email Address
              </label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-gray-500">
                  <Mail className="w-4 h-4" />
                </div>
                <input
                  id="login-email"
                  type="email"
                  value={email}
                  onChange={(e) => {
                    setEmail(e.target.value);
                    if (fieldErrors.email) {
                      setFieldErrors((prev) => ({ ...prev, email: undefined }));
                    }
                  }}
                  autoFocus
                  autoComplete="email"
                  placeholder="admin@cloudflow.com"
                  disabled={loading}
                  className={`w-full pl-10 pr-3.5 py-2.5 bg-gray-950/80 border rounded-xl text-sm text-gray-100 placeholder-gray-500 focus:outline-none transition ${
                    fieldErrors.email
                      ? 'border-rose-500 focus:border-rose-500 focus:ring-1 focus:ring-rose-500/40'
                      : 'border-gray-700/80 focus:border-blue-500 focus:ring-1 focus:ring-blue-500/40'
                  }`}
                />
              </div>
              {fieldErrors.email && (
                <p className="text-[11px] text-rose-400 font-medium pl-1">
                  {fieldErrors.email}
                </p>
              )}
            </div>

            {/* Password Field */}
            <div className="space-y-1.5">
              <label
                htmlFor="login-password"
                className="block text-xs font-medium text-gray-300"
              >
                Password
              </label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-gray-500">
                  <Lock className="w-4 h-4" />
                </div>
                <input
                  id="login-password"
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => {
                    setPassword(e.target.value);
                    if (fieldErrors.password) {
                      setFieldErrors((prev) => ({ ...prev, password: undefined }));
                    }
                  }}
                  autoComplete="current-password"
                  placeholder="••••••••••••"
                  disabled={loading}
                  className={`w-full pl-10 pr-10 py-2.5 bg-gray-950/80 border rounded-xl text-sm text-gray-100 placeholder-gray-500 focus:outline-none transition ${
                    fieldErrors.password
                      ? 'border-rose-500 focus:border-rose-500 focus:ring-1 focus:ring-rose-500/40'
                      : 'border-gray-700/80 focus:border-blue-500 focus:ring-1 focus:ring-blue-500/40'
                  }`}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute inset-y-0 right-0 pr-3 flex items-center text-gray-500 hover:text-gray-300 focus:outline-none"
                  tabIndex={-1}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
              {fieldErrors.password && (
                <p className="text-[11px] text-rose-400 font-medium pl-1">
                  {fieldErrors.password}
                </p>
              )}
            </div>

            {/* Submit Button */}
            <button
              type="submit"
              disabled={loading}
              className="w-full mt-2 py-2.5 px-4 bg-gradient-to-r from-blue-600 to-cyan-600 hover:from-blue-500 hover:to-cyan-500 text-white font-semibold rounded-xl text-sm shadow-lg shadow-blue-600/25 transition disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Signing in...</span>
                </>
              ) : (
                <>
                  <KeyRound className="w-4 h-4" />
                  <span>Sign In</span>
                </>
              )}
            </button>
          </form>

          {/* Quick-Fill Seeded Personas */}
          <div className="pt-4 border-t border-gray-800 space-y-2.5">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-gray-400 flex items-center gap-1.5">
                <UserCheck className="w-3.5 h-3.5 text-cyan-400" />
                Seeded Test Personas
              </span>
              <span className="text-[10px] text-gray-500">Click to fill</span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {PRESET_PERSONAS.map((preset) => (
                <button
                  key={preset.email}
                  type="button"
                  onClick={() => handleApplyPreset(preset)}
                  disabled={loading}
                  className="p-2.5 rounded-xl bg-gray-950/60 hover:bg-gray-800/80 border border-gray-800 hover:border-gray-700 text-left transition flex flex-col justify-between group"
                >
                  <div className="flex items-center justify-between w-full">
                    <span className="text-xs font-semibold text-gray-200 group-hover:text-white truncate">
                      {preset.name}
                    </span>
                    <span
                      className={`text-[9px] px-1.5 py-0.5 rounded border font-mono font-medium ${preset.badgeColor}`}
                    >
                      {preset.role === 'COMPANY_ADMIN' ? 'ADMIN' : 'OWNER'}
                    </span>
                  </div>
                  <div className="text-[10px] text-gray-400 truncate mt-1">
                    {preset.company}
                  </div>
                  <div className="text-[10px] font-mono text-gray-500 truncate">
                    {preset.email}
                  </div>
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Security Footer Notice */}
        <div className="text-center text-[11px] text-gray-500 space-y-1">
          <div className="flex items-center justify-center gap-1 text-gray-400">
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
            <span>Role-Based Access Control (RBAC) & Signed Bearer Token Auth</span>
          </div>
          <p>Passwords hashed with PBKDF2-HMAC-SHA256 (100k iterations).</p>
        </div>
      </div>
    </div>
  );
};
