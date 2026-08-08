import { Check, CircleAlert, Clock, Loader2, X } from "lucide-react";

import { cn } from "@/lib/utils";
import type { SessionStatus } from "@/types/api";

/** Presence is never conveyed by colour alone — icon + text label always present. */
export function PresenceBadge({ present }: { present: boolean }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium",
        present
          ? "border-present/30 bg-present-soft text-present"
          : "border-absent/30 bg-absent-soft text-absent",
      )}
    >
      {present ? (
        <Check className="size-3.5" aria-hidden />
      ) : (
        <X className="size-3.5" aria-hidden />
      )}
      {present ? "Present" : "Absent"}
    </span>
  );
}

const STATUS_MAP: Partial<Record<SessionStatus, { label: string; className: string; icon: typeof Check }>> =
  {
    uploaded: {
      label: "Uploaded",
      className: "border-border bg-muted text-muted-foreground",
      icon: Clock,
    },
    queued: {
      label: "Queued",
      className: "border-border bg-muted text-muted-foreground",
      icon: Clock,
    },
    processing: {
      label: "Processing",
      className: "border-primary/30 bg-accent text-accent-foreground",
      icon: Loader2,
    },
    processed: {
      label: "Processed",
      className: "border-present/30 bg-present-soft text-present",
      icon: Check,
    },
    completed: {
      label: "Completed",
      className: "border-present/30 bg-present-soft text-present",
      icon: Check,
    },
    needs_review: {
      label: "Needs review",
      className: "border-review/40 bg-review-soft text-review",
      icon: CircleAlert,
    },
    failed: { label: "Failed", className: "border-absent/30 bg-absent-soft text-absent", icon: X },
  };

// `status` is only typed as SessionStatus -- at runtime it's whatever the API
// (or a future status value) actually sends, so a lookup miss must render
// gracefully rather than crash on an undefined meta.
export function StatusBadge({ status }: { status: SessionStatus | string | undefined | null }) {
  const meta = status ? STATUS_MAP[status as SessionStatus] : undefined;
  const label = meta?.label ?? (status ? status.replace(/_/g, " ") : "Unknown");
  const className = meta?.className ?? "border-border bg-muted text-muted-foreground";
  const Icon = meta?.icon ?? CircleAlert;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium",
        className,
      )}
    >
      <Icon className={cn("size-3.5", status === "processing" && "animate-spin")} aria-hidden />
      {label}
    </span>
  );
}

export function AttendanceBar({ value, label }: { value?: number | null; label?: string }) {
  const percentage = Number.isFinite(value ?? 0) ? (value ?? 0) : 0;
  const tone = percentage >= 75 ? "bg-present" : percentage >= 50 ? "bg-review" : "bg-absent";
  return (
    <div className="flex items-center gap-2">
      <div
        className="h-2 w-28 overflow-hidden rounded-full bg-muted"
        role="img"
        aria-label={label ?? `${percentage}% attendance`}
      >
        <div
          className={cn("h-full rounded-full", tone)}
          style={{ width: `${Math.min(100, Math.max(0, percentage))}%` }}
        />
      </div>
      <span className="text-num text-xs text-muted-foreground">{percentage.toFixed(1)}%</span>
    </div>
  );
}

export function InkRatioBar({ value }: { value: number }) {
  const pct = Math.min(100, value * 400);
  return (
    <div className="flex items-center gap-2">
      <div
        className="h-1.5 w-20 overflow-hidden rounded-full bg-muted"
        role="img"
        aria-label={`Ink ratio ${value}`}
      >
        <div
          className={cn("h-full rounded-full", value >= 0.03 ? "bg-present" : "bg-absent")}
          style={{ width: `${Math.max(3, pct)}%` }}
        />
      </div>
      <span className="text-num text-xs text-muted-foreground">{value.toFixed(3)}</span>
    </div>
  );
}
