import type {
  Gateway,
  GatewayHistoryEntry,
  Event,
  Charge,
  BillingSummary,
  StatsOverview,
  EventFilters,
} from '@/types';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

async function fetchApi<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE}${endpoint}`;
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });

  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`);
  }

  return response.json();
}

// Gateway endpoints
export async function getGateways(minTrust: number = 0.0): Promise<Gateway[]> {
  return fetchApi<Gateway[]>(`/api/gateways?min_trust=${minTrust}`);
}

export async function getGateway(eui: string): Promise<Gateway> {
  return fetchApi<Gateway>(`/api/gateways/${eui}`);
}

export async function getGatewayHistory(
  eui: string,
  days: number = 7
): Promise<GatewayHistoryEntry[]> {
  return fetchApi<GatewayHistoryEntry[]>(`/api/gateways/${eui}/history?days=${days}`);
}

// Event endpoints
export async function getRecentEvents(filters?: EventFilters): Promise<Event[]> {
  const params = new URLSearchParams();
  if (filters?.limit) params.set('limit', String(filters.limit));
  if (filters?.eventType) params.set('event_type', filters.eventType);
  if (filters?.gatewayEui) params.set('gateway_eui', filters.gatewayEui);
  if (filters?.devEui) params.set('dev_eui', filters.devEui);

  const queryString = params.toString();
  return fetchApi<Event[]>(`/api/events/recent${queryString ? '?' + queryString : ''}`);
}

// Billing endpoints
export async function getBillingCharges(): Promise<Charge[]> {
  return fetchApi<Charge[]>('/api/billing/charges');
}

export async function getBillingSummary(): Promise<BillingSummary> {
  return fetchApi<BillingSummary>('/api/billing/summary');
}

// Stats endpoints
export async function getStatsOverview(): Promise<StatsOverview> {
  return fetchApi<StatsOverview>('/api/stats/overview');
}

// SSE stream URL
export function getEventStreamUrl(): string {
  return `${API_BASE}/api/events/stream`;
}
