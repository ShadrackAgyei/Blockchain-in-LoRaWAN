'use client';

import { useEffect, useState } from 'react';
import {
  CreditCard,
  RefreshCw,
  ArrowUpRight,
  ArrowDownLeft,
  DollarSign,
  FileText,
  Grid,
  List,
} from 'lucide-react';
import { StatsCard } from '@/components/StatsCard';
import { ChargeTable, ChargeMatrix } from '@/components/ChargeTable';
import { getBillingSummary } from '@/lib/api';
import { cn, formatMicroToUnit } from '@/lib/utils';
import type { BillingSummary, Charge } from '@/types';

export default function BillingPage() {
  const [summary, setSummary] = useState<BillingSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<'table' | 'matrix'>('table');

  const fetchData = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getBillingSummary();
      setSummary(data);
    } catch (err) {
      setError('Failed to load billing data');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  // Calculate organization-specific stats
  const getOrgStats = (charges: Charge[]) => {
    const stats: Record<string, { owes: number; owed: number }> = {};

    charges.forEach((charge) => {
      if (!stats[charge.debtorOrg]) {
        stats[charge.debtorOrg] = { owes: 0, owed: 0 };
      }
      if (!stats[charge.creditorOrg]) {
        stats[charge.creditorOrg] = { owes: 0, owed: 0 };
      }
      stats[charge.debtorOrg].owes += charge.totalAmountMicro;
      stats[charge.creditorOrg].owed += charge.totalAmountMicro;
    });

    return stats;
  };

  const orgStats = summary ? getOrgStats(summary.orgPairs) : {};

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Billing</h1>
          <p className="text-gray-500">
            Inter-organization charges and settlements
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

      {/* Error */}
      {error && (
        <div className="rounded-lg bg-red-50 p-4 border border-red-200">
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}

      {/* Summary Stats */}
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
        <StatsCard
          title="Total Pending"
          value={`$${formatMicroToUnit(summary?.totalCharges ?? 0)}`}
          subtitle="Awaiting settlement"
          icon={DollarSign}
        />
        <StatsCard
          title="Active Pairs"
          value={summary?.pendingSettlements ?? 0}
          subtitle="Org-to-org relationships"
          icon={FileText}
        />
        <StatsCard
          title="Total Packets"
          value={summary?.orgPairs.reduce((sum, c) => sum + c.totalPackets, 0) ?? 0}
          subtitle="Roaming traffic"
          icon={CreditCard}
        />
        <StatsCard
          title="Organizations"
          value={Object.keys(orgStats).length}
          subtitle="Participating orgs"
          icon={Grid}
        />
      </div>

      {/* Organization Balance Cards */}
      {Object.keys(orgStats).length > 0 && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Object.entries(orgStats).map(([org, stats]) => {
            const netBalance = stats.owed - stats.owes;
            const isPositive = netBalance >= 0;

            return (
              <div
                key={org}
                className="rounded-xl bg-white p-6 shadow-sm border border-gray-100"
              >
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-lg font-semibold text-gray-900">{org}</h3>
                  <span
                    className={cn(
                      'inline-flex items-center rounded-full px-2.5 py-0.5 text-sm font-medium',
                      isPositive
                        ? 'bg-green-100 text-green-700'
                        : 'bg-red-100 text-red-700'
                    )}
                  >
                    {isPositive ? '+' : ''}${formatMicroToUnit(netBalance)}
                  </span>
                </div>

                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 text-sm text-gray-500">
                      <ArrowDownLeft className="h-4 w-4 text-green-500" />
                      Receivable
                    </div>
                    <span className="font-medium text-green-600">
                      ${formatMicroToUnit(stats.owed)}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 text-sm text-gray-500">
                      <ArrowUpRight className="h-4 w-4 text-red-500" />
                      Payable
                    </div>
                    <span className="font-medium text-red-600">
                      ${formatMicroToUnit(stats.owes)}
                    </span>
                  </div>
                </div>

                <div className="mt-4 pt-4 border-t border-gray-100">
                  <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                    <div
                      className={cn(
                        'h-full rounded-full',
                        isPositive ? 'bg-green-500' : 'bg-red-500'
                      )}
                      style={{
                        width: `${Math.min(
                          100,
                          Math.abs(netBalance) /
                            (Math.max(stats.owed, stats.owes) || 1) *
                            100
                        )}%`,
                      }}
                    />
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Charges Detail */}
      <div className="rounded-xl bg-white shadow-sm border border-gray-100">
        <div className="flex items-center justify-between p-6 border-b border-gray-100">
          <h2 className="text-lg font-semibold text-gray-900">
            Pending Charges
          </h2>
          <div className="flex rounded-lg bg-gray-100 p-1">
            <button
              onClick={() => setView('table')}
              className={cn(
                'flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
                view === 'table'
                  ? 'bg-white text-gray-900 shadow-sm'
                  : 'text-gray-600 hover:text-gray-900'
              )}
            >
              <List className="h-4 w-4" />
              Table
            </button>
            <button
              onClick={() => setView('matrix')}
              className={cn(
                'flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
                view === 'matrix'
                  ? 'bg-white text-gray-900 shadow-sm'
                  : 'text-gray-600 hover:text-gray-900'
              )}
            >
              <Grid className="h-4 w-4" />
              Matrix
            </button>
          </div>
        </div>

        <div className="p-6">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600" />
            </div>
          ) : view === 'table' ? (
            <ChargeTable charges={summary?.orgPairs ?? []} />
          ) : (
            <ChargeMatrix charges={summary?.orgPairs ?? []} />
          )}
        </div>
      </div>

      {/* Settlement Info */}
      <div className="rounded-xl bg-blue-50 p-6 border border-blue-100">
        <h3 className="text-sm font-semibold text-blue-900 mb-2">
          About Settlements
        </h3>
        <p className="text-sm text-blue-700">
          Charges are recorded on the Hyperledger Fabric blockchain when devices
          roam across organization boundaries. Settlements are initiated when
          organizations agree to clear their balances. All transactions are
          immutable and auditable on the blockchain.
        </p>
      </div>
    </div>
  );
}
