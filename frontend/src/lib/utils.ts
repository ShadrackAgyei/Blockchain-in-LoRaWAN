import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatNumber(num: number): string {
  if (num >= 1000000) {
    return (num / 1000000).toFixed(1) + 'M';
  }
  if (num >= 1000) {
    return (num / 1000).toFixed(1) + 'K';
  }
  return num.toString();
}

export function formatMicroToUnit(microAmount: number): string {
  const amount = microAmount / 1000000;
  // Show enough decimals to see small amounts (e.g. $0.0058 instead of $0.01)
  if (amount === 0) return '0.00';
  if (Math.abs(amount) < 0.01) return amount.toFixed(6);
  if (Math.abs(amount) < 1) return amount.toFixed(4);
  return amount.toFixed(2);
}

export function formatTimestamp(timestamp: string): string {
  const date = new Date(timestamp);
  return date.toLocaleString();
}

export function formatTimeAgo(timestamp: string): string {
  const date = new Date(timestamp);
  const now = new Date();
  const seconds = Math.floor((now.getTime() - date.getTime()) / 1000);

  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

export function getTrustScoreColor(score: number): string {
  if (score >= 0.8) return 'text-trust-high';
  if (score >= 0.5) return 'text-trust-medium';
  return 'text-trust-low';
}

export function getTrustScoreBgColor(score: number): string {
  if (score >= 0.8) return 'bg-trust-high';
  if (score >= 0.5) return 'bg-trust-medium';
  return 'bg-trust-low';
}

export function getEventTypeColor(type: string): string {
  switch (type.toLowerCase()) {
    case 'uplink':
      return 'bg-blue-100 text-blue-800';
    case 'join':
      return 'bg-green-100 text-green-800';
    case 'downlink':
      return 'bg-purple-100 text-purple-800';
    case 'batch_flush':
      return 'bg-orange-100 text-orange-800';
    default:
      return 'bg-gray-100 text-gray-800';
  }
}
