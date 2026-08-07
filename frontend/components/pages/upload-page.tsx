"use client";

import { useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, FileCode2, FileImage, RotateCcw, UploadCloud, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { PageHeader } from "@/components/page-header";
import {
  BeforeAfterSlider,
  PipelineStepper,
  StepGallery,
  initialSteps,
  type StepState,
} from "@/components/pipeline";
import { ResultsTable } from "@/components/results-table";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { loadProcessingSettings, toProcessOptionsPayload } from "@/lib/processing-settings";
import {
  getResults,
  startProcessing,
  subscribeProcessing,
  uploadSheet,
} from "@/services/sessions.service";
import type { SheetResult } from "@/types/api";

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

function DropZone({
  label,
  hint,
  accept,
  file,
  onFile,
  icon: Icon,
  preview,
}: {
  label: string;
  hint: string;
  accept: string;
  file: File | null;
  onFile: (f: File | null) => void;
  icon: typeof FileImage;
  preview?: string | null;
}) {
  const [over, setOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        const dropped = e.dataTransfer.files[0];
        if (dropped) onFile(dropped);
      }}
      className={cn(
        "flex flex-col gap-3 rounded-lg border border-dashed p-4 transition-colors",
        over ? "border-primary bg-accent/60" : "border-border bg-card",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-sm font-medium text-foreground">{label}</p>
          <p className="text-xs text-muted-foreground">{hint}</p>
        </div>
        <Icon className="size-4 text-muted-foreground" aria-hidden />
      </div>

      {file ? (
        <div className="flex items-center gap-3 rounded-md border border-border bg-background p-2.5">
          {preview ? (
            <img
              src={preview}
              alt={`${label} preview`}
              className="h-16 w-14 rounded border border-border object-cover"
            />
          ) : (
            <div className="flex h-16 w-14 items-center justify-center rounded border border-border bg-muted">
              <FileCode2 className="size-5 text-muted-foreground" aria-hidden />
            </div>
          )}
          <div className="min-w-0 flex-1">
            <p className="text-num truncate text-xs font-medium text-foreground">{file.name}</p>
            <p className="text-num text-xs text-muted-foreground">{formatBytes(file.size)}</p>
          </div>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => onFile(null)}
            aria-label={`Remove ${file.name}`}
          >
            <X className="size-4" />
          </Button>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          className="flex flex-col items-center gap-2 rounded-md border border-border bg-muted/40 px-4 py-7 text-center transition-colors hover:bg-accent/50"
        >
          <UploadCloud className="size-5 text-muted-foreground" aria-hidden />
          <span className="text-xs text-muted-foreground">
            Drag &amp; drop or <span className="font-medium text-primary">browse</span>
          </span>
        </button>
      )}

      <input
        ref={inputRef}
        type="file"
        accept={accept}
        className="hidden"
        onChange={(e) => onFile(e.target.files?.[0] ?? null)}
      />
    </div>
  );
}

type Phase = "idle" | "processing" | "failed" | "done";

export function UploadPage() {
  const queryClient = useQueryClient();
  const [image, setImage] = useState<File | null>(null);
  const [xml, setXml] = useState<File | null>(null);
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [subject, setSubject] = useState("CS 202");
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10));
  // Initialized from the Settings page's persisted default so it doesn't
  // silently diverge from what an operator configured there -- still
  // editable per-upload below, which takes precedence over that default.
  const [headerRows, setHeaderRows] = useState(() => loadProcessingSettings().headerRows);
  const [signatureCol, setSignatureCol] = useState("-1");
  const [simulateFailure, setSimulateFailure] = useState(false);

  const [phase, setPhase] = useState<Phase>("idle");
  const [steps, setSteps] = useState<StepState[]>(initialSteps());
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<SheetResult[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const unsubscribe = useRef<(() => void) | null>(null);

  useEffect(() => {
    if (!image) {
      // Clears the preview left over from a removed file; part of the same
      // object-URL lifecycle as the create/revoke pair below, so it isn't a
      // plain derived value.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setImagePreview(null);
      return;
    }
    const url = URL.createObjectURL(image);
    setImagePreview(url);
    return () => URL.revokeObjectURL(url);
  }, [image]);

  useEffect(() => () => unsubscribe.current?.(), []);

  const reset = () => {
    unsubscribe.current?.();
    setPhase("idle");
    setSteps(initialSteps());
    setError(null);
    setResults([]);
  };

  const start = async () => {
    if (!image || !xml) return;
    reset();
    setPhase("processing");
    try {
      const { session_id } = await uploadSheet(image, xml, subject, date);
      setSessionId(session_id);
      await startProcessing(session_id, {
        ...toProcessOptionsPayload(loadProcessingSettings()),
        header_rows: headerRows,
        signature_col: Number(signatureCol),
      });

      unsubscribe.current = subscribeProcessing(session_id, {
        failAtStep: simulateFailure ? 6 : undefined,
        onEvent: (event) => {
          // The terminal "complete" event describes the whole session, not
          // one step -- it has no `order` to match against and its status
          // isn't a valid StepStatus, so it's handled entirely via onDone.
          if (event.status === "complete") return;
          // Destructured so the narrowed (non-"complete") status carries into
          // the closure below -- TS doesn't propagate the early-return
          // narrowing of `event` itself through a nested closure.
          const { status, order, path, message } = event;
          setSteps((prev) =>
            prev.map((s) =>
              s.order === order ? { ...s, status, path: path || s.path, message } : s,
            ),
          );
        },
        onError: (message) => {
          setError(message);
          setPhase("failed");
        },
        onDone: async () => {
          try {
            setResults(await getResults(session_id));
            setPhase("done");
            // The dashboard's "sessions" query was fetched before this
            // session finished processing -- without invalidating it here,
            // its cached data stays stale until a manual reload.
            await queryClient.invalidateQueries({ queryKey: ["sessions"] });
          } catch (e) {
            setError((e as Error).message);
            setPhase("failed");
          }
        },
      });
    } catch (e) {
      setError((e as Error).message);
      setPhase("failed");
    }
  };

  const lastDone = [...steps].reverse().find((s) => s.status === "done");

  return (
    <div className="space-y-6">
      <PageHeader
        title="Upload sheet"
        description="Send a photographed signing sheet and its info.xml roster through the OpenCV presence-detection pipeline."
        actions={
          phase !== "idle" ? (
            <Button variant="outline" size="sm" onClick={reset}>
              <RotateCcw className="size-3.5" /> New upload
            </Button>
          ) : null
        }
      />

      {phase === "idle" ? (
        <div className="space-y-4">
          <div className="grid gap-4 lg:grid-cols-2">
            <DropZone
              label="Sheet image"
              hint="JPG or PNG photograph of the signed sheet"
              accept="image/jpeg,image/png"
              file={image}
              onFile={setImage}
              icon={FileImage}
              preview={imagePreview}
            />
            <DropZone
              label="info.xml"
              hint="Roster metadata exported for this session"
              accept=".xml,text/xml,application/xml"
              file={xml}
              onFile={setXml}
              icon={FileCode2}
            />
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Processing settings</CardTitle>
              <CardDescription>
                Optional — defaults match the standard department sheet layout.
              </CardDescription>
            </CardHeader>
            <CardContent className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <div className="space-y-1.5">
                <Label htmlFor="subject">Subject code</Label>
                <Input
                  id="subject"
                  value={subject}
                  onChange={(e) => setSubject(e.target.value)}
                  className="text-num"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="date">Session date</Label>
                <Input
                  id="date"
                  type="date"
                  value={date}
                  onChange={(e) => setDate(e.target.value)}
                  className="text-num"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="headers">Header rows</Label>
                <Input
                  id="headers"
                  type="number"
                  min={0}
                  max={5}
                  value={headerRows}
                  onChange={(e) => setHeaderRows(Number(e.target.value))}
                  className="text-num"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="sigcol">Signature column</Label>
                <Select value={signatureCol} onValueChange={setSignatureCol}>
                  <SelectTrigger id="sigcol">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="-1">Last column (default)</SelectItem>
                    <SelectItem value="1">Column 1</SelectItem>
                    <SelectItem value="2">Column 2</SelectItem>
                    <SelectItem value="3">Column 3</SelectItem>
                    <SelectItem value="4">Column 4</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </CardContent>
          </Card>

          <div className="flex flex-wrap items-center gap-3">
            <Button onClick={start} disabled={!image || !xml}>
              Start processing
            </Button>
            {!image || !xml ? (
              <p className="text-xs text-muted-foreground">
                Both the sheet image and info.xml are required.
              </p>
            ) : null}
            <label className="ml-auto flex items-center gap-2 text-xs text-muted-foreground">
              <input
                type="checkbox"
                checked={simulateFailure}
                onChange={(e) => setSimulateFailure(e.target.checked)}
                className="accent-[var(--primary)]"
              />
              Simulate a backend failure (demo)
            </label>
          </div>
        </div>
      ) : (
        <div className="space-y-6">
          {phase === "failed" && error ? (
            <div
              role="alert"
              className="flex flex-col gap-3 rounded-lg border border-absent/40 bg-absent-soft/70 p-4 sm:flex-row sm:items-start"
            >
              <AlertTriangle className="mt-0.5 size-5 shrink-0 text-absent" aria-hidden />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-foreground">Processing failed</p>
                <p className="text-num mt-1 break-words text-xs text-muted-foreground">{error}</p>
                <p className="mt-2 text-xs text-muted-foreground">
                  Completed stages remain below so you can see exactly where the pipeline broke.
                </p>
              </div>
              <Button variant="outline" size="sm" onClick={start}>
                <RotateCcw className="size-3.5" /> Retry processing
              </Button>
            </div>
          ) : null}

          <div className="grid gap-6 lg:grid-cols-[minmax(0,20rem)_minmax(0,1fr)]">
            <Card className="h-fit">
              <CardHeader>
                <CardTitle className="text-base">Pipeline</CardTitle>
                <CardDescription className="text-num">{sessionId}</CardDescription>
              </CardHeader>
              <CardContent>
                <PipelineStepper steps={steps} />
              </CardContent>
            </Card>

            <div className="space-y-6">
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Stage outputs</CardTitle>
                  <CardDescription>
                    Click a thumbnail for the full image and the technique used.
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <StepGallery steps={steps} />
                </CardContent>
              </Card>

              {imagePreview ? (
                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">Original vs binarized</CardTitle>
                    <CardDescription>
                      Drag the slider to compare the photo with the thresholded page.
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <BeforeAfterSlider src={imagePreview} afterStep={lastDone} />
                  </CardContent>
                </Card>
              ) : null}
            </div>
          </div>

          {phase === "done" ? (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Detected attendance</CardTitle>
                <CardDescription>
                  Presence decided by ink ratio per extracted signature cell.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <ResultsTable
                  results={results}
                  filename={`${subject.replace(/\s/g, "")}-${date}.csv`}
                />
              </CardContent>
            </Card>
          ) : null}
        </div>
      )}
    </div>
  );
}
