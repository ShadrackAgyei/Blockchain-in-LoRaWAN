import { ArrowRight } from 'lucide-react';
import { formatMicroToUnit, formatNumber } from '@/lib/utils';
import type { Charge } from '@/types';

interface ChargeTableProps {
  charges: Charge[];
}

export function ChargeTable({ charges }: ChargeTableProps) {
  if (charges.length === 0) {
    return (
      <div className="text-center py-8 text-gray-500">
        No pending charges
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead className="bg-gray-50">
          <tr>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
              From / To
            </th>
            <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">
              Uplinks
            </th>
            <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">
              Downlinks
            </th>
            <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">
              Joins
            </th>
            <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">
              Total Packets
            </th>
            <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">
              Amount
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {charges.map((charge, index) => (
            <tr key={index} className="hover:bg-gray-50">
              <td className="px-4 py-3">
                <div className="flex items-center gap-2">
                  <span className="inline-flex items-center rounded-full bg-blue-100 px-2.5 py-0.5 text-xs font-medium text-blue-800">
                    {charge.debtorOrg}
                  </span>
                  <ArrowRight className="h-4 w-4 text-gray-400" />
                  <span className="inline-flex items-center rounded-full bg-green-100 px-2.5 py-0.5 text-xs font-medium text-green-800">
                    {charge.creditorOrg}
                  </span>
                </div>
              </td>
              <td className="px-4 py-3 text-right text-sm text-gray-600">
                {formatNumber(charge.uplinkCount)}
              </td>
              <td className="px-4 py-3 text-right text-sm text-gray-600">
                {formatNumber(charge.downlinkCount)}
              </td>
              <td className="px-4 py-3 text-right text-sm text-gray-600">
                {formatNumber(charge.joinCount)}
              </td>
              <td className="px-4 py-3 text-right text-sm font-medium text-gray-900">
                {formatNumber(charge.totalPackets)}
              </td>
              <td className="px-4 py-3 text-right">
                <span className="text-sm font-semibold text-gray-900">
                  ${formatMicroToUnit(charge.totalAmountMicro)}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
        <tfoot className="bg-gray-50">
          <tr>
            <td className="px-4 py-3 text-sm font-medium text-gray-900" colSpan={4}>
              Total
            </td>
            <td className="px-4 py-3 text-right text-sm font-semibold text-gray-900">
              {formatNumber(charges.reduce((sum, c) => sum + c.totalPackets, 0))}
            </td>
            <td className="px-4 py-3 text-right text-sm font-bold text-gray-900">
              ${formatMicroToUnit(charges.reduce((sum, c) => sum + c.totalAmountMicro, 0))}
            </td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}

export function ChargeMatrix({ charges }: ChargeTableProps) {
  // Get unique orgs
  const orgs = Array.from(
    new Set([...charges.map((c) => c.debtorOrg), ...charges.map((c) => c.creditorOrg)])
  );

  // Build matrix
  const matrix: Record<string, Record<string, number>> = {};
  orgs.forEach((org) => {
    matrix[org] = {};
    orgs.forEach((other) => {
      matrix[org][other] = 0;
    });
  });

  charges.forEach((charge) => {
    matrix[charge.debtorOrg][charge.creditorOrg] = charge.totalAmountMicro;
  });

  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead className="bg-gray-50">
          <tr>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
              Debtor \ Creditor
            </th>
            {orgs.map((org) => (
              <th
                key={org}
                className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase"
              >
                {org}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {orgs.map((debtor) => (
            <tr key={debtor}>
              <td className="px-4 py-3 text-sm font-medium text-gray-900">
                {debtor}
              </td>
              {orgs.map((creditor) => (
                <td
                  key={creditor}
                  className={`px-4 py-3 text-center text-sm ${
                    debtor === creditor
                      ? 'bg-gray-100 text-gray-400'
                      : matrix[debtor][creditor] > 0
                      ? 'font-medium text-gray-900'
                      : 'text-gray-400'
                  }`}
                >
                  {debtor === creditor
                    ? '-'
                    : matrix[debtor][creditor] > 0
                    ? `$${formatMicroToUnit(matrix[debtor][creditor])}`
                    : '$0.00'}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
