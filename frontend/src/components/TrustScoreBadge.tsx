import { cn, getTrustScoreBgColor } from '@/lib/utils';

interface TrustScoreBadgeProps {
  score: number;
  showLabel?: boolean;
  size?: 'sm' | 'md' | 'lg';
}

export function TrustScoreBadge({
  score,
  showLabel = true,
  size = 'md',
}: TrustScoreBadgeProps) {
  const percentage = Math.round(score * 100);

  const sizeClasses = {
    sm: 'h-8 w-8 text-xs',
    md: 'h-12 w-12 text-sm',
    lg: 'h-16 w-16 text-base',
  };

  return (
    <div className="flex items-center gap-2">
      <div
        className={cn(
          'rounded-full flex items-center justify-center text-white font-bold',
          getTrustScoreBgColor(score),
          sizeClasses[size]
        )}
      >
        {percentage}
      </div>
      {showLabel && (
        <div className="text-sm">
          <p className="font-medium text-gray-900">Trust Score</p>
          <p className="text-gray-500">
            {score >= 0.8 ? 'High' : score >= 0.5 ? 'Medium' : 'Low'}
          </p>
        </div>
      )}
    </div>
  );
}

export function TrustScoreBar({ score }: { score: number }) {
  const percentage = Math.round(score * 100);

  return (
    <div className="w-full">
      <div className="flex justify-between text-sm mb-1">
        <span className="font-medium text-gray-700">Trust Score</span>
        <span className="text-gray-500">{percentage}%</span>
      </div>
      <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
        <div
          className={cn('h-full rounded-full', getTrustScoreBgColor(score))}
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  );
}
