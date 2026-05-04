// Gateway types
export interface Location {
  latitude: number;
  longitude: number;
  altitude: number;
}

export interface Gateway {
  gatewayEUI: string;
  ownerOrg: string;
  location: Location;
  trustScore: number;
  status: string;
  registeredAt?: string;
  lastActive?: string;
}

export interface GatewayHistoryEntry {
  periodStart: string;
  periodEnd: string;
  uplinkCount: number;
  downlinkCount: number;
  joinCount: number;
  errorCount: number;
  avgRssi?: number;
  avgSnr?: number;
}

// Event types
export interface Event {
  id: number;
  eventType: string;
  devEui: string;
  gatewayEui?: string;
  rssi?: number;
  snr?: number;
  timestamp: string;
  processed: boolean;
}

export interface LiveEvent {
  type: string;
  devEui?: string;
  gatewayEui?: string;
  rssi?: number;
  snr?: number;
  timestamp: string;
  // For batch_flush events
  uplinkCount?: number;
  downlinkCount?: number;
  joinCount?: number;
  txId?: string;
}

// Billing types
export interface Charge {
  debtorOrg: string;
  creditorOrg: string;
  totalPackets: number;
  uplinkCount: number;
  downlinkCount: number;
  joinCount: number;
  totalAmountMicro: number;
}

export interface BillingSummary {
  totalCharges: number;
  pendingSettlements: number;
  orgPairs: Charge[];
}

// Stats types
export interface StatsOverview {
  totalGateways: number;
  activeGateways: number;
  totalDevices: number;
  eventsToday: number;
  pendingCharges: number;
  lastUpdated: string;
}

// Filter types
export interface EventFilters {
  eventType?: string;
  gatewayEui?: string;
  devEui?: string;
  limit?: number;
}
