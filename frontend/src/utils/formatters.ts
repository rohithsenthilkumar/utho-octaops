export const formatINR = (amount: number, currency: 'INR' | 'USD' = 'INR'): string => {
  if (amount === undefined || amount === null || isNaN(amount)) return '₹0';
  
  if (currency === 'USD') {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      maximumFractionDigits: 0,
    }).format(Math.round(amount / 83.5));
  }

  // Format with Indian numbering system (Lakhs, Crores)
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(amount);
};

export const formatPercent = (val: number): string => {
  if (val === undefined || val === null || isNaN(val)) return '0%';
  return `${val.toFixed(1)}%`;
};

export const getRiskBadgeClass = (level: string = 'LOW'): string => {
  switch (level.toUpperCase()) {
    case 'HIGH':
      return 'bg-rose-500/15 text-rose-300 border-rose-500/30';
    case 'MEDIUM':
      return 'bg-amber-500/15 text-amber-300 border-amber-500/30';
    case 'LOW':
    default:
      return 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30';
  }
};

export const getStatusBadgeClass = (status: string = 'PENDING'): string => {
  switch (status.toUpperCase()) {
    case 'ACCEPTED':
      return 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30';
    case 'REJECTED':
      return 'bg-gray-700/50 text-gray-400 border-gray-600/50';
    case 'PENDING':
    default:
      return 'bg-blue-500/15 text-blue-300 border-blue-500/30';
  }
};

export const getResourceStatusBadgeClass = (status: string = 'ACTIVE'): string => {
  switch (status.toUpperCase()) {
    case 'ACTIVE':
      return 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30';
    case 'IDLE':
      return 'bg-amber-500/15 text-amber-300 border-amber-500/30';
    case 'OVER_PROVISIONED':
      return 'bg-purple-500/15 text-purple-300 border-purple-500/30';
    case 'ORPHANED':
      return 'bg-rose-500/15 text-rose-300 border-rose-500/30';
    default:
      return 'bg-gray-800 text-gray-300 border-gray-700';
  }
};

export const getSeverityBadgeClass = (severity: string = 'info'): string => {
  switch (severity.toLowerCase()) {
    case 'critical':
      return 'bg-rose-500/20 text-rose-400 border-rose-500/30';
    case 'warning':
      return 'bg-amber-500/20 text-amber-400 border-amber-500/30';
    case 'info':
    default:
      return 'bg-blue-500/20 text-blue-400 border-blue-500/30';
  }
};
