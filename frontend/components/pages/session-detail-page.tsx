"use client";

import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/badges";
import {
  ImageWithFallback,
  PipelineStepper,
  StepGallery,
  type StepState,
} from "@/components/pipeline";
import { CardGridSkeleton, ErrorState, TableSkeleton } from "@/components/states";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { getSession, getSteps } from "@/services/sessions.service";

export function SessionDetail() {
  const { id } = useParams<{ id: string }>();
  const session = useQuery({ queryKey: ["session", id], queryFn: () => getSession(id) });
  const steps = useQuery({ queryKey: ["steps", id], queryFn: () => getSteps(id) });

  const stepStates: StepState[] = (steps.data ?? []).map((step) => ({
    name: step.name,
    order: step.order,
    status: "done",
    path: step.path,
  }));

  return (
    <div className="space-y-6">
      <PageHeader
        title={session.data ? `${session.data.subject_code} — ${session.data.session_date}` : "Session"}
        description={`Session ${id}`}
        actions={session.data ? <StatusBadge status={session.data.status} /> : null}
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
              <ErrorState message={(steps.error as Error).message} onRetry={() => steps.refetch()} />
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
              {steps.isPending ? <CardGridSkeleton count={6} /> : <StepGallery steps={stepStates} />}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Original sheet</CardTitle>
              <CardDescription>The photograph submitted by the operator.</CardDescription>
            </CardHeader>
            <CardContent>
              <ImageWithFallback
                src={session.data?.image_path ?? ""}
                alt={`Original attendance sheet for session ${id}`}
                className="w-full rounded-md border border-border"
                emptyMessage="No original sheet image is available."
              />
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}