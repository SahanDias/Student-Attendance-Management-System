"use client";

import { Check, CircleDashed, ImageOff, Loader2, X, ZoomIn } from "lucide-react";
import { useEffect, useState } from "react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { PIPELINE_STAGES } from "@/lib/pipeline-stages";
import { staticUrl } from "@/services/api";
import { cn } from "@/lib/utils";

export type StepStatus = "pending" | "running" | "done" | "failed";

export interface StepState {
  name: string;
  order: number;
  status: StepStatus;
  path: string;
  message?: string | undefined;
}

export function stageMeta(name: string) {
  return (
    PIPELINE_STAGES.find((s) => s.name.toLowerCase() === name.toLowerCase()) ?? {
      name,
      description: "Custom pipeline stage reported by the backend.",
      filter: "none",
    }
  );
}

export function initialSteps(): StepState[] {
  return PIPELINE_STAGES.map((s, i) => ({
    name: s.name,
    order: i + 1,
    status: "pending",
    path: "",
  }));
}

/**
 * Renders `src` via a plain <img>, falling back to a broken-image state
 * (icon + the attempted URL, or an empty-path message) when there's no path
 * at all or the browser fails to load it -- shared by StepImage below and by
 * SessionDetail's "Original sheet" card, so neither ever falls back to a
 * bundled placeholder image instead.
 */
export function ImageWithFallback({
  src,
  alt,
  className,
  emptyMessage = "No path reported for this image",
  width = 1024,
  height = 1280,
}: {
  src: string;
  alt: string;
  className?: string | undefined;
  emptyMessage?: string | undefined;
  width?: number | undefined;
  height?: number | undefined;
}) {
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    // Clears a stale broken-image flag from a previous src (e.g. a path
    // going from empty to real once processing completes) -- not a pure
    // derived value, since the actual "did it fail" answer only comes from
    // the <img> element's own load attempt below.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setFailed(false);
  }, [src]);

  if (!src || failed) {
    return (
      <div
        className={cn(
          "flex flex-col items-center justify-center gap-1.5 bg-muted p-3 text-center",
          className,
        )}
      >
        <ImageOff className="size-5 text-muted-foreground" aria-hidden />
        <p className="text-num break-all text-[10px] leading-tight text-muted-foreground">
          {src || emptyMessage}
        </p>
      </div>
    );
  }

  return (
    <img
      src={src}
      alt={alt}
      loading="lazy"
      width={width}
      height={height}
      className={className}
      onError={() => setFailed(true)}
    />
  );
}

function StepImage({ step, className }: { step: StepState; className?: string }) {
  const src = staticUrl(step.path);

  useEffect(() => {
    if (process.env.NODE_ENV === "development" && src) {
      console.log(`[StepImage] ${step.name} (order ${step.order}) -> ${src}`);
    }
  }, [src, step.name, step.order]);

  return (
    <ImageWithFallback
      src={src}
      alt={`${step.name} stage output`}
      className={className}
      emptyMessage="No path reported for this step"
    />
  );
}

const STATUS_ICON: Record<StepStatus, typeof Check> = {
  pending: CircleDashed,
  running: Loader2,
  done: Check,
  failed: X,
};

export function PipelineStepper({ steps }: { steps: StepState[] }) {
  return (
    <ol className="relative space-y-1">
      {steps.map((step, i) => {
        const Icon = STATUS_ICON[step.status];
        const meta = stageMeta(step.name);
        return (
          <li key={step.name} className="relative flex gap-3 pb-3 last:pb-0">
            {i < steps.length - 1 && (
              <span
                aria-hidden
                className={cn(
                  "absolute left-[13px] top-7 h-[calc(100%-1rem)] w-px",
                  step.status === "done" ? "bg-present/50" : "bg-border",
                )}
              />
            )}
            <span
              className={cn(
                "z-10 mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full border bg-card",
                step.status === "done" && "border-present/40 bg-present-soft text-present",
                step.status === "running" && "border-primary/50 bg-accent text-accent-foreground",
                step.status === "failed" && "border-absent/40 bg-absent-soft text-absent",
                step.status === "pending" && "border-border text-muted-foreground",
              )}
            >
              <Icon
                className={cn("size-4", step.status === "running" && "animate-spin")}
                aria-hidden
              />
            </span>
            <div className="min-w-0 pt-0.5">
              <p
                className={cn(
                  "text-sm font-medium",
                  step.status === "pending" ? "text-muted-foreground" : "text-foreground",
                )}
              >
                <span className="text-num mr-1.5 text-xs text-muted-foreground">
                  {String(step.order).padStart(2, "0")}
                </span>
                {step.name}
                <span className="sr-only"> — {step.status}</span>
              </p>
              <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">
                {step.status === "failed" && step.message ? step.message : meta.description}
              </p>
            </div>
            <span className="ml-auto shrink-0 self-start pt-1 text-[11px] capitalize text-muted-foreground">
              {step.status}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

export function StepGallery({ steps }: { steps: StepState[] }) {
  const [open, setOpen] = useState<StepState | null>(null);
  const visible = steps.filter((s) => s.status === "done" || s.status === "failed");

  if (visible.length === 0) {
    return (
      <div className="flex h-full min-h-48 items-center justify-center rounded-lg border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
        Stage outputs appear here as each OpenCV step completes.
      </div>
    );
  }

  return (
    <>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {visible.map((step) => (
          <button
            key={step.name}
            type="button"
            onClick={() => setOpen(step)}
            className="group relative overflow-hidden rounded-md border border-border bg-muted text-left transition-colors hover:border-primary/50"
          >
            <div className="aspect-4/5 overflow-hidden bg-card">
              <StepImage step={step} className="size-full object-cover object-top" />
            </div>
            <div className="flex items-center justify-between gap-1 border-t border-border bg-card px-2 py-1.5">
              <span className="truncate text-xs font-medium text-foreground">
                <span className="text-num mr-1 text-muted-foreground">
                  {String(step.order).padStart(2, "0")}
                </span>
                {step.name}
              </span>
              <ZoomIn
                className="size-3.5 shrink-0 text-muted-foreground group-hover:text-primary"
                aria-hidden
              />
            </div>
          </button>
        ))}
      </div>

      <Dialog open={!!open} onOpenChange={(v) => !v && setOpen(null)}>
        <DialogContent className="max-w-3xl">
          {open ? (
            <>
              <DialogHeader>
                <DialogTitle>
                  Step {String(open.order).padStart(2, "0")} — {open.name}
                </DialogTitle>
                <DialogDescription>{stageMeta(open.name).description}</DialogDescription>
              </DialogHeader>
              <div className="max-h-[60vh] overflow-auto rounded-md border border-border bg-muted">
                <StepImage step={open} className="w-full object-contain" />
              </div>
              {open.path ? (
                <p className="text-num text-xs text-muted-foreground">{open.path}</p>
              ) : null}
            </>
          ) : null}
        </DialogContent>
      </Dialog>
    </>
  );
}

export function BeforeAfterSlider({
  afterStep,
  src,
}: {
  afterStep?: StepState | undefined;
  src: string;
}) {
  const [pos, setPos] = useState(55);
  const filter = afterStep
    ? stageMeta(afterStep.name).filter
    : "grayscale(1) contrast(2.6) brightness(1.15)";

  return (
    <div className="space-y-3">
      <div className="relative overflow-hidden rounded-lg border border-border bg-muted">
        <img src={src} alt="Original photographed sheet" loading="lazy" className="block w-full" />
        <div
          className="absolute inset-0 overflow-hidden"
          style={{ clipPath: `inset(0 0 0 ${pos}%)` }}
        >
          <img
            src={src}
            alt="Binarized output"
            loading="lazy"
            className="block w-full"
            style={{ filter }}
          />
        </div>
        <span
          aria-hidden
          className="pointer-events-none absolute inset-y-0 w-px bg-primary"
          style={{ left: `${pos}%` }}
        />
        <span className="pointer-events-none absolute bottom-2 left-2 rounded bg-card/90 px-2 py-0.5 text-xs text-foreground">
          Original
        </span>
        <span className="pointer-events-none absolute bottom-2 right-2 rounded bg-card/90 px-2 py-0.5 text-xs text-foreground">
          Binarized
        </span>
      </div>
      <label className="block space-y-1.5">
        <span className="text-xs font-medium text-muted-foreground">
          Compare original vs processed
        </span>
        <input
          type="range"
          min={0}
          max={100}
          value={pos}
          onChange={(e) => setPos(Number(e.target.value))}
          className="w-full accent-[var(--primary)]"
          aria-label="Before and after comparison position"
        />
      </label>
    </div>
  );
}
