"use client";

import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { RefreshCw } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/badges";
import {
  ImageWithFallback,
  PipelineStepper,
  StepGallery,
  type StepState,
} from "@/components/pipeline";
import { ResultsTable } from "@/components/results-table";
import { CardGridSkeleton, ErrorState, TableSkeleton } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { loadProcessingSettings, toProcessOptionsPayload } from "@/lib/processing-settings";
import { staticUrl } from "@/services/api";
import { getResults, getSession, getSteps, startProcessing } from "@/services/sessions.service";

export function SessionDetail() {
  const { id } = useParams<{ id: string }>();
  const session = useQuery({ queryKey: ["session", id], queryFn: () => getSession(id) });
  const steps = useQuery({ queryKey: ["steps", id], queryFn: () => getSteps(id) });
  const results = useQuery({ queryKey: ["results", id], queryFn: () => getResults(id) });

  // Initialized from the Settings page's persisted default -- still
  // editable per-reprocess below, which takes precedence over that default.
  const [headerRows, setHeaderRows] = useState(() => loadProcessingSettings().headerRows);
  const [signatureCol, setSignatureCol] = useState("-1");
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  const stepStates: StepState[] = (steps.data ?? []).map((s) => ({
    name: s.name,
    order: s.order,
    status: "done",
    path: s.path,
  }));

  const reprocess = async () => {
    setBusy(true);
    try {
      await startProcessing(id, {
        ...toProcessOptionsPayload(loadProcessingSettings()),
        header_rows: headerRows,
        signature_col: Number(signatureCol),
      });
      toast.success("Reprocessing queued", {
        description: `header_rows=${headerRows}, signature_col=${signatureCol}`,
      });
      setOpen(false);
      await Promise.all([steps.refetch(), results.refetch(), session.refetch()]);
    } catch (e) {
      toast.error("Reprocess failed", { description: (e as Error).message });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title={
          session.data ? `${session.data.subject_code} — ${session.data.session_date}` : "Session"
        }
        description={`Session ${id}`}
        actions={
          <>
            {session.data ? <StatusBadge status={session.data.status} /> : null}
            <Dialog open={open} onOpenChange={setOpen}>
              <DialogTrigger asChild>
                <Button variant="outline" size="sm">
                  <RefreshCw className="size-3.5" /> Reprocess
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Reprocess this sheet</DialogTitle>
                  <DialogDescription>
                    Re-runs the OpenCV pipeline on the stored photograph with different grid
                    assumptions.
                  </DialogDescription>
                </DialogHeader>
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="space-y-1.5">
                    <Label htmlFor="rp-headers">Header rows</Label>
                    <Input
                      id="rp-headers"
                      type="number"
                      min={0}
                      max={5}
                      value={headerRows}
                      onChange={(e) => setHeaderRows(Number(e.target.value))}
                      className="text-num"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="rp-col">Signature column</Label>
                    <Select value={signatureCol} onValueChange={setSignatureCol}>
                      <SelectTrigger id="rp-col">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="-1">Last column (default)</SelectItem>
                        <SelectItem value="2">Column 2</SelectItem>
                        <SelectItem value="3">Column 3</SelectItem>
                        <SelectItem value="4">Column 4</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
                <DialogFooter>
                  <Button onClick={reprocess} disabled={busy}>
                    {busy ? "Reprocessing…" : "Run again"}
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </>
        }
      />

      {session.isError ? (
        <ErrorState message={(session.error as Error).message} onRetry={() => session.refetch()} />
      ) : null}

      {session.data ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {[
            { label: "Students detected", value: session.data.students_detected },
            { label: "Present", value: session.data.present_count },
            { label: "Absent", value: session.data.absent_count },
            { label: "Flagged", value: session.data.flagged_count },
          ].map((stat) => (
            <Card key={stat.label}>
              <CardHeader className="pb-2">
                <CardDescription>{stat.label}</CardDescription>
              </CardHeader>
              <CardContent>
                <p className="text-num text-2xl font-semibold">{stat.value}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,20rem)_minmax(0,1fr)]">
        <Card className="h-fit">
          <CardHeader>
            <CardTitle className="text-base">Pipeline stages</CardTitle>
            <CardDescription>Read-only record of the run.</CardDescription>
          </CardHeader>
          <CardContent>
            {steps.isPending ? (
              <TableSkeleton rows={8} cols={1} />
            ) : steps.isError ? (
              <ErrorState
                message={(steps.error as Error).message}
                onRetry={() => steps.refetch()}
              />
            ) : (
              <PipelineStepper steps={stepStates} />
            )}
          </CardContent>
        </Card>

        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Stage outputs</CardTitle>
              <CardDescription>Click a thumbnail to inspect the stage image.</CardDescription>
            </CardHeader>
            <CardContent>
              {steps.isPending ? (
                <CardGridSkeleton count={6} />
              ) : (
                <StepGallery steps={stepStates} />
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Original sheet</CardTitle>
              <CardDescription>The photograph submitted by the operator.</CardDescription>
            </CardHeader>
            <CardContent>
              <ImageWithFallback
                src={staticUrl(session.data?.image_path ?? "")}
                alt={`Original attendance sheet for session ${id}`}
                className="w-full rounded-md border border-border"
                emptyMessage="No uploaded photograph path reported for this session"
              />
            </CardContent>
          </Card>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Attendance results</CardTitle>
          <CardDescription>Presence decided per extracted signature cell.</CardDescription>
        </CardHeader>
        <CardContent>
          {results.isPending ? (
            <TableSkeleton cols={6} />
          ) : results.isError ? (
            <ErrorState
              message={(results.error as Error).message}
              onRetry={() => results.refetch()}
            />
          ) : (
            <ResultsTable results={results.data ?? []} filename={`${id}.csv`} />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
