'use client';

import { useEffect, useState } from 'react';
import { Radio, MapPin, RefreshCw, List, Map } from 'lucide-react';
import { GatewayMap } from '@/components/GatewayMap';
import { TrustScoreBadge, TrustScoreBar } from '@/components/TrustScoreBadge';
import { getGateways, getGatewayHistory } from '@/lib/api';
import { cn, formatTimestamp } from '@/lib/utils';
import type { Gateway, GatewayHistoryEntry } from '@/types';

// Import Leaflet CSS
import 'leaflet/dist/leaflet.css';

export default function GatewaysPage() {
  const [gateways, setGateways] = useState<Gateway[]>([]);
  const [selectedGateway, setSelectedGateway] = useState<Gateway | null>(null);
  const [gatewayHistory, setGatewayHistory] = useState<GatewayHistoryEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [view, setView] = useState<'map' | 'list'>('map');
  const [error, setError] = useState<string | null>(null);

  const fetchGateways = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getGateways();
      setGateways(data);
    } catch (err) {
      setError('Failed to load gateways');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const fetchGatewayHistory = async (eui: string) => {
    try {
      setHistoryLoading(true);
      const data = await getGatewayHistory(eui, 7);
      setGatewayHistory(data);
    } catch (err) {
      console.error('Failed to load gateway history:', err);
      setGatewayHistory([]);
    } finally {
      setHistoryLoading(false);
    }
  };

  useEffect(() => {
    fetchGateways();
  }, []);

  useEffect(() => {
    if (selectedGateway) {
      fetchGatewayHistory(selectedGateway.gatewayEUI);
    }
  }, [selectedGateway]);

  const handleGatewayClick = (gateway: Gateway) => {
    setSelectedGateway(gateway);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Gateways</h1>
          <p className="text-gray-500">
            {gateways.length} gateways in network
          </p>
        </div>
        <div className="flex items-center gap-2">
          {/* View Toggle */}
          <div className="flex rounded-lg bg-gray-100 p-1">
            <button
              onClick={() => setView('map')}
              className={cn(
                'flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
                view === 'map'
                  ? 'bg-white text-gray-900 shadow-sm'
                  : 'text-gray-600 hover:text-gray-900'
              )}
            >
              <Map className="h-4 w-4" />
              Map
            </button>
            <button
              onClick={() => setView('list')}
              className={cn(
                'flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
                view === 'list'
                  ? 'bg-white text-gray-900 shadow-sm'
                  : 'text-gray-600 hover:text-gray-900'
              )}
            >
              <List className="h-4 w-4" />
              List
            </button>
          </div>
          <button
            onClick={fetchGateways}
            disabled={loading}
            className="flex items-center gap-2 rounded-lg bg-white px-4 py-2 text-sm font-medium text-gray-700 shadow-sm border border-gray-200 hover:bg-gray-50 disabled:opacity-50"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-lg bg-red-50 p-4 border border-red-200">
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}

      {/* Main Content */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Map or List View */}
        <div className="lg:col-span-2">
          {view === 'map' ? (
            <div className="h-[500px] rounded-xl bg-white shadow-sm border border-gray-100 overflow-hidden">
              {loading ? (
                <div className="h-full flex items-center justify-center">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600" />
                </div>
              ) : (
                <GatewayMap
                  gateways={gateways}
                  onGatewayClick={handleGatewayClick}
                  selectedGateway={selectedGateway?.gatewayEUI}
                />
              )}
            </div>
          ) : (
            <div className="rounded-xl bg-white shadow-sm border border-gray-100 overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                        Gateway
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                        Owner
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                        Trust Score
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                        Status
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                        Location
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {gateways.map((gateway) => (
                      <tr
                        key={gateway.gatewayEUI}
                        onClick={() => handleGatewayClick(gateway)}
                        className={cn(
                          'cursor-pointer hover:bg-gray-50',
                          selectedGateway?.gatewayEUI === gateway.gatewayEUI &&
                            'bg-primary-50'
                        )}
                      >
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            <Radio className="h-4 w-4 text-gray-400" />
                            <span className="font-mono text-sm">
                              {gateway.gatewayEUI.slice(0, 12)}...
                            </span>
                          </div>
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-600">
                          {gateway.ownerOrg}
                        </td>
                        <td className="px-4 py-3">
                          <TrustScoreBadge
                            score={gateway.trustScore}
                            showLabel={false}
                            size="sm"
                          />
                        </td>
                        <td className="px-4 py-3">
                          <span
                            className={cn(
                              'inline-flex items-center rounded-full px-2 py-1 text-xs font-medium',
                              gateway.status === 'ACTIVE'
                                ? 'bg-green-100 text-green-700'
                                : 'bg-gray-100 text-gray-700'
                            )}
                          >
                            {gateway.status}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-500">
                          <div className="flex items-center gap-1">
                            <MapPin className="h-3 w-3" />
                            {gateway.location.latitude.toFixed(3)},{' '}
                            {gateway.location.longitude.toFixed(3)}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>

        {/* Gateway Details Sidebar */}
        <div className="space-y-4">
          {selectedGateway ? (
            <>
              {/* Gateway Info */}
              <div className="rounded-xl bg-white p-6 shadow-sm border border-gray-100">
                <div className="flex items-start justify-between mb-4">
                  <div>
                    <h2 className="text-lg font-semibold text-gray-900">
                      Gateway Details
                    </h2>
                    <p className="text-sm text-gray-500 font-mono">
                      {selectedGateway.gatewayEUI}
                    </p>
                  </div>
                  <span
                    className={cn(
                      'inline-flex items-center rounded-full px-2 py-1 text-xs font-medium',
                      selectedGateway.status === 'ACTIVE'
                        ? 'bg-green-100 text-green-700'
                        : 'bg-gray-100 text-gray-700'
                    )}
                  >
                    {selectedGateway.status}
                  </span>
                </div>

                <TrustScoreBar score={selectedGateway.trustScore} />

                <div className="mt-4 space-y-3">
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-500">Owner</span>
                    <span className="font-medium">{selectedGateway.ownerOrg}</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-500">Latitude</span>
                    <span className="font-mono">
                      {selectedGateway.location.latitude.toFixed(6)}
                    </span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-500">Longitude</span>
                    <span className="font-mono">
                      {selectedGateway.location.longitude.toFixed(6)}
                    </span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-500">Altitude</span>
                    <span className="font-mono">
                      {selectedGateway.location.altitude}m
                    </span>
                  </div>
                  {selectedGateway.lastActive && (
                    <div className="flex justify-between text-sm">
                      <span className="text-gray-500">Last Active</span>
                      <span>{formatTimestamp(selectedGateway.lastActive)}</span>
                    </div>
                  )}
                </div>
              </div>

              {/* Forwarding History */}
              <div className="rounded-xl bg-white p-6 shadow-sm border border-gray-100">
                <h3 className="text-sm font-semibold text-gray-900 mb-4">
                  Recent Activity (7 days)
                </h3>
                {historyLoading ? (
                  <div className="flex justify-center py-4">
                    <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-primary-600" />
                  </div>
                ) : gatewayHistory.length === 0 ? (
                  <p className="text-sm text-gray-500 text-center py-4">
                    No activity recorded
                  </p>
                ) : (
                  <div className="space-y-2">
                    {gatewayHistory.slice(0, 5).map((entry, i) => (
                      <div
                        key={i}
                        className="flex justify-between items-center text-sm py-2 border-b border-gray-50 last:border-0"
                      >
                        <div>
                          <p className="font-medium text-gray-900">
                            {entry.uplinkCount + entry.downlinkCount + entry.joinCount} packets
                          </p>
                          <p className="text-xs text-gray-500">
                            {entry.errorCount} errors
                          </p>
                        </div>
                        <div className="text-right">
                          <p className="text-gray-600">
                            RSSI: {entry.avgRssi?.toFixed(1) ?? 'N/A'}
                          </p>
                          <p className="text-xs text-gray-400">
                            SNR: {entry.avgSnr?.toFixed(1) ?? 'N/A'}
                          </p>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="rounded-xl bg-white p-6 shadow-sm border border-gray-100">
              <div className="text-center text-gray-500 py-8">
                <Radio className="h-12 w-12 mx-auto mb-4 text-gray-300" />
                <p>Select a gateway to view details</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
