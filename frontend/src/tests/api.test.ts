import { describe, it, expect } from 'vitest';
import {
  fetchInventory,
  fetchRightsizingRecommendations,
  fetchLocalMonitoring,
  fetchAutoscalingStatus,
  fetchDashboardSummary,
  fetchAlerts,
  fetchSettings,
  loginUser,
  fetchCurrentUser,
  getAuthToken,
  isAuthenticated,
  logoutUser,
  fetchKvmDomains,
} from '../services/api';


describe('Frontend API Service Layer', () => {
  it('fetchInventory maps backend resources properly', async () => {
    const resources = await fetchInventory();
    expect(Array.isArray(resources)).toBe(true);
    expect(resources.length).toBeGreaterThan(0);
    const first = resources[0];
    expect(first).toHaveProperty('id');
    expect(first).toHaveProperty('name');
    expect(first).toHaveProperty('type');
    expect(first).toHaveProperty('region');
    expect(first).toHaveProperty('environment');
    expect(first).toHaveProperty('monthly_cost');
  });

  it('fetchRightsizingRecommendations returns recommendations array', async () => {
    const recs = await fetchRightsizingRecommendations();
    expect(Array.isArray(recs)).toBe(true);
    expect(recs.length).toBeGreaterThan(0);
    const first = recs[0];
    expect(first).toHaveProperty('id');
    expect(first).toHaveProperty('resource_name');
    expect(first).toHaveProperty('action');
    expect(first).toHaveProperty('risk_level');
  });

  it('fetchLocalMonitoring returns live host metrics structure', async () => {
    const metric = await fetchLocalMonitoring(0.1);
    expect(metric).toHaveProperty('timestamp');
    expect(metric).toHaveProperty('cpu_utilization');
    expect(metric).toHaveProperty('ram_utilization');
    expect(metric).toHaveProperty('used_ram_gb');
    expect(metric).toHaveProperty('total_ram_gb');
    expect(metric).toHaveProperty('metric_source');
    expect(metric).toHaveProperty('status');

    // Bounds check without asserting a fixed percentage
    expect(metric.cpu_utilization).toBeGreaterThanOrEqual(0);
    expect(metric.cpu_utilization).toBeLessThanOrEqual(100);
    expect(metric.ram_utilization).toBeGreaterThanOrEqual(0);
    expect(metric.ram_utilization).toBeLessThanOrEqual(100);
    expect(metric.total_ram_gb).toBeGreaterThan(0);
    expect(metric.used_ram_gb).toBeLessThanOrEqual(metric.total_ram_gb);
    expect(metric.metric_source).toContain('Live local host metrics');
  });

  it('fetchAutoscalingStatus returns autoscaling state schema', async () => {
    const status = await fetchAutoscalingStatus();
    expect(status).toHaveProperty('current_replicas');
    expect(status).toHaveProperty('min_replicas');
    expect(status).toHaveProperty('max_replicas');
    expect(status).toHaveProperty('scale_out_threshold');
    expect(status).toHaveProperty('scale_in_threshold');
    expect(status).toHaveProperty('average_cpu_percent');
    expect(status).toHaveProperty('recent_events');
    expect(status).toHaveProperty('is_healthy');

    expect(status.min_replicas).toBeGreaterThanOrEqual(1);
    expect(status.max_replicas).toBeGreaterThanOrEqual(status.min_replicas);
    expect(status.scale_out_threshold).toBeGreaterThan(status.scale_in_threshold);
  });

  it('createResource payload validation structure', () => {
    const payload = {
      name: 'test-vm-01 [Simulated]',
      resource_type: 'VM',
      environment: 'dev',
      region: 'Bangalore',
      cpu_cores: 4,
      memory: 16.0,
      cpu_utilization: 12.0,
      estimated_monthly_cost: 15000.0,
    };
    expect(payload.cpu_cores).toBeGreaterThan(0);
    expect(payload.memory).toBeGreaterThan(0);
    expect(payload.estimated_monthly_cost).toBeGreaterThanOrEqual(0);
  });

  it('fetchDashboardSummary returns valid summary metrics schema', async () => {
    const summary = await fetchDashboardSummary();
    expect(summary).toHaveProperty('total_resources');
    expect(summary).toHaveProperty('current_monthly_cost');
    expect(summary).toHaveProperty('projected_cost');
    expect(summary).toHaveProperty('total_savings');
    expect(summary).toHaveProperty('savings_percentage');
    expect(summary).toHaveProperty('total_recommendations');
    expect(summary).toHaveProperty('accepted_recommendations');
    expect(summary).toHaveProperty('pending_recommendations');
    expect(summary).toHaveProperty('rejected_recommendations');
    expect(summary).toHaveProperty('idle_resources_count');

    expect(summary.total_resources).toBeGreaterThanOrEqual(0);
    expect(summary.current_monthly_cost).toBeGreaterThanOrEqual(0);
    expect(summary.projected_cost).toBeLessThanOrEqual(summary.current_monthly_cost);
  });

  it('fetchAlerts returns local alerts array without HTTP 404', async () => {
    const alerts = await fetchAlerts();
    expect(Array.isArray(alerts)).toBe(true);
    expect(alerts.length).toBeGreaterThan(0);
    const first = alerts[0];
    expect(first).toHaveProperty('id');
    expect(first).toHaveProperty('title');
    expect(first).toHaveProperty('severity');
  });

  it('fetchSettings returns app settings without HTTP 404', async () => {
    const settings = await fetchSettings();
    expect(settings).toHaveProperty('company_name');
    expect(settings).toHaveProperty('currency');
    expect(settings.currency).toBe('INR');
  });

  describe('Authentication & Session Persistence', () => {
    it('loginUser succeeds with valid credentials and stores smartcloud_token', async () => {
      const res = await loginUser('admin@cloudflow.com', 'CloudFlowAdmin#2026');
      expect(res).toHaveProperty('access_token');
      expect(res).toHaveProperty('user');
      expect(res.user.email).toBe('admin@cloudflow.com');
      expect(res.user.role).toBe('COMPANY_ADMIN');
      expect(getAuthToken()).toBe(res.access_token);
      expect(isAuthenticated()).toBe(true);
    });

    it('fetchCurrentUser succeeds when bearer token is present', async () => {
      const me = await fetchCurrentUser();
      expect(me).toHaveProperty('id');
      expect(me.email).toBe('admin@cloudflow.com');
      expect(me.role).toBe('COMPANY_ADMIN');
      expect(me.company_name).toBe('CloudFlow Hosting');
    });

    it('authenticated user can list real KVM domains', async () => {
      const domains = await fetchKvmDomains();
      expect(Array.isArray(domains)).toBe(true);
      expect(domains.length).toBeGreaterThan(0);
      const vm = domains.find((d: any) => d.name === 'sco-test-vm');
      expect(vm).toBeDefined();
      expect(vm.name).toBe('sco-test-vm');
      expect(vm.state).toBe('running');
    });

    it('loginUser fails with invalid credentials and throws HTTP 401', async () => {
      let failed = false;
      try {
        await loginUser('admin@cloudflow.com', 'WrongPassword123!');
      } catch (err: any) {
        failed = true;
        expect(err.response?.status).toBe(401);
      }
      expect(failed).toBe(true);
    });

    it('logoutUser clears token and unsets authenticated state', async () => {
      logoutUser();
      expect(getAuthToken()).toBeNull();
      expect(isAuthenticated()).toBe(false);
    });

    it('unauthenticated request to fetchCurrentUser is rejected with HTTP 401', async () => {
      logoutUser();
      let failed = false;
      try {
        await fetchCurrentUser();
      } catch (err: any) {
        failed = true;
        expect(err.response?.status).toBe(401);
      }
      expect(failed).toBe(true);
    });

    it('unauthenticated request to fetchKvmDomains is rejected with HTTP 401', async () => {
      logoutUser();
      let failed = false;
      try {
        await fetchKvmDomains();
      } catch (err: any) {
        failed = true;
        expect(err.response?.status).toBe(401);
      }
      expect(failed).toBe(true);
    });
  });
});




