import { describe, it, expect } from 'vitest';
import {
  formatINR,
  formatPercent,
  getRiskBadgeClass,
  getStatusBadgeClass,
  getResourceStatusBadgeClass,
  getSeverityBadgeClass,
} from '../utils/formatters';

describe('Formatters Utility', () => {
  it('formats INR correctly for zero and positive numbers', () => {
    expect(formatINR(0)).toBe('₹0');
    expect(formatINR(54000)).toMatch(/₹\s?54,000/);
    expect(formatINR(1485000)).toMatch(/₹\s?14,85,000/);
  });

  it('formats USD currency conversion correctly', () => {
    expect(formatINR(83500, 'USD')).toMatch(/\$1,000/);
  });

  it('formats percentages correctly', () => {
    expect(formatPercent(24.5)).toBe('24.5%');
    expect(formatPercent(0)).toBe('0.0%');
    expect(formatPercent(99.9)).toBe('99.9%');
  });

  it('returns proper risk badge styling classes', () => {
    expect(getRiskBadgeClass('HIGH')).toContain('text-rose-300');
    expect(getRiskBadgeClass('MEDIUM')).toContain('text-amber-300');
    expect(getRiskBadgeClass('LOW')).toContain('text-emerald-300');
  });

  it('returns proper recommendation status badge styling classes', () => {
    expect(getStatusBadgeClass('ACCEPTED')).toContain('text-emerald-300');
    expect(getStatusBadgeClass('REJECTED')).toContain('text-gray-400');
    expect(getStatusBadgeClass('PENDING')).toContain('text-blue-300');
  });

  it('returns proper resource status badge styling classes', () => {
    expect(getResourceStatusBadgeClass('ACTIVE')).toContain('text-emerald-300');
    expect(getResourceStatusBadgeClass('IDLE')).toContain('text-amber-300');
    expect(getResourceStatusBadgeClass('OVER_PROVISIONED')).toContain('text-purple-300');
    expect(getResourceStatusBadgeClass('ORPHANED')).toContain('text-rose-300');
  });

  it('returns proper alert severity badge styling classes', () => {
    expect(getSeverityBadgeClass('critical')).toContain('text-rose-400');
    expect(getSeverityBadgeClass('warning')).toContain('text-amber-400');
    expect(getSeverityBadgeClass('info')).toContain('text-blue-400');
  });
});
