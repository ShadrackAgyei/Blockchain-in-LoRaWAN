'use client';

import { useEffect, useState } from 'react';
import { Radio, Smartphone, Activity, CreditCard, RefreshCw } from 'lucide-react';
import { StatsCard } from '@/components/StatsCard';
import { getStatsOverview, getRecentEvents } from '@/lib/api';
import { formatTimestamp, formatMicroToUnit, getEventTypeColor } from '@/lib/utils';
import type { StatsOverview, Event } from '@/types';

export default function DashboardPage() {
  const [stats, setStats] = useState<StatsOverview | null>(null);
  const [recentEvents, setRecentEvents] = useState<Event[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
    try {
      setLoading(true);
      setError(null);
      const [statsData, eventsData] = await Promise.all([
        getStatsOverview(),
        getRecentEvents({ limit: 5 }),
      ]);
      setStats(statsData);
      setRecentEvents(eventsData);
    } catch (err) {
      setError('Failed to load dashboard data. Is the backend running?');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    // Refresh every 30 seconds
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, []);

  if (loading && !stats) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
          <p className="text-gray-500">
            Overview of your LoRaWAN blockchain network
          </p>
        </div>
        <button
          onClick={fetchData}
          disabled={loading}
          className="flex items-center gap-2 rounded-lg bg-white px-4 py-2 text-sm font-medium text-gray-700 shadow-sm border border-gray-200 hover:bg-gray-50 disabled:opacity-50"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Error banner */}
      {error && (
        <div className="rounded-lg bg-red-50 p-4 border border-red-200">
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}

      {/* Stats Grid */}
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
        <StatsCard
          title="Total Gateways"
          value={stats?.totalGateways ?? 0}
          subtitle={`${stats?.activeGateways ?? 0} active`}
          icon={Radio}
        />
        <StatsCard
          title="Active Devices"
          value={stats?.totalDevices ?? 0}
          subtitle="Connected devices"
          icon={Smartphone}
        />
        <StatsCard
          title="Events Today"
          value={stats?.eventsToday ?? 0}
          subtitle="Packets processed"
          icon={Activity}
        />
        <StatsCard
          title="Pending Charges"
          value={`$${formatMicroToUnit(stats?.pendingCharges ?? 0)}`}
          subtitle="Awaiting settlement"
          icon={CreditCard}
        />
      </div>

      {/* Recent Events */}
      <div className="rounded-xl bg-white p-6 shadow-sm border border-gray-100">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-900">Recent Events</h2>
          <a
            href="/events"
            className="text-sm font-medium text-primary-600 hover:text-primary-700"
          >
            View all
          </a>
        </div>

        {recentEvents.length === 0 ? (
          <p className="text-gray-500 text-center py-8">No recent events</p>
        ) : (
          <div className="space-y-3">
            {recentEvents.map((event) => (
              <div
                key={event.id}
                className="flex items-center justify-between rounded-lg bg-gray-50 p-3"
              >
                <div className="flex items-center gap-3">
                  <span
                    className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${getEventTypeColor(
                      event.eventType
                    )}`}
                  >
                    {event.eventType}
                  </span>
                  <div>
                    <p className="text-sm font-medium text-gray-900">
                      Device: {event.devEui.slice(0, 8)}...
                    </p>
                    <p className="text-xs text-gray-500">
                      Gateway: {event.gatewayEui?.slice(0, 8) ?? 'N/A'}
                    </p>
                  </div>
                </div>
                <div className="text-right">
                  {event.rssi && (
                    <p className="text-sm text-gray-600">
                      RSSI: {event.rssi} dBm
                    </p>
                  )}
                  <p className="text-xs text-gray-400">
                    {formatTimestamp(event.timestamp)}
                  </p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Last Updated */}
      {stats?.lastUpdated && (
        <p className="text-xs text-gray-400 text-center">
          Last updated: {formatTimestamp(stats.lastUpdated)}
        </p>
      )}
    </div>
  );
}
