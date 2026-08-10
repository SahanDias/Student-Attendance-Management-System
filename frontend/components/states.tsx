function EmptyIllustration() {
  return (
    <div>
      {/* Empty illustration */}
    </div>
  );
}

export function ErrorState({
  message,
  onRetry,
  className,
}: {
  message: string;
  onRetry: () => void;
  className?: string;
}) {
  return (
    <div
      role="alert"
      className={cn(
        "flex flex-col items-center justify-center gap-3 rounded-lg border border-absent/30 bg-absent-soft/60 px-6 py-12 text-center",
        className,
      )}
    >
      <AlertTriangle />
      <div>Couldn't load this data</div>
      <div>{message}</div>

      <Button onClick={onRetry}>
        <RefreshCw />
        Retry
      </Button>
    </div>
  );
}

export function TableSkeleton({
  rows = 6,
  cols = 5,
}: {
  rows?: number;
  cols?: number;
}) {
  return (
    <div>
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r}>
          {Array.from({ length: cols }).map((_, c) => (
            <Skeleton key={c} />
          ))}
        </div>
      ))}
    </div>
  );
}

export function ChartSkeleton({ height = 260 }: { height?: number }) {
  return (
    <div className="flex items-end gap-2 p-4" style={{ height }}>
      {[55, 72, 40, 88, 64, 78, 50, 82, 60, 70].map((h, i) => (
        <Skeleton
          key={i}
          className="flex-1"
          style={{ height: `${h}%` }}
        />
      ))}
    </div>
  );
}

export function CardGridSkeleton({ count = 6 }: { count?: number }) {
  return (
    <div>
      {Array.from({ length: count }).map((_, i) => (
        <Skeleton key={i} />
      ))}
    </div>
  );
}