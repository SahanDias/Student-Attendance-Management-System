"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ChevronRight, Flag } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/page-header";
import { CardGridSkeleton, EmptyState, ErrorState, TableSkeleton } from "@/components/states";
import { Button } from "@/components/ui/button";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  getSignatureSessionItems,
  listSignatureReviews,
  listSignatureSessions,
  submitSignatureReview,
} from "@/services/signatures.service";
import type { SignatureSessionSummary } from "@/types/api";
import { cn } from "@/lib/utils";

function reviewKey(studentIndex: string, sessionId: string): string {
  return `${studentIndex}::${sessionId}`;
}

function SimilarityRing({ value, method }: { value: number; method: string }) {
  const pct = Math.round(value * 100);
  const tone = pct >= 80 ? "var(--present)" : pct >= 65 ? "var(--review)" : "var(--absent)";
  const label = pct >= 80 ? "Strong match" : pct >= 65 ? "Borderline" : "Weak match";
  const methodLabel = method.toLowerCase() === "orb" ? "ORB" : method;
  return (
    <div className="flex items-center gap-2">
      <div
        className="relative flex size-12 items-center justify-center rounded-full"
        style={{ background: `conic-gradient(${tone} ${pct * 3.6}deg, var(--muted) 0deg)` }}
        role="img"
        aria-label={`Similarity ${pct} percent — ${label}, via ${methodLabel} comparison`}
      >
        <span className="text-num flex size-9 items-center justify-center rounded-full bg-card text-xs font-semibold">
          {pct}
        </span>
      </div>
      <div className="flex flex-col">
        <span className="text-xs text-muted-foreground">{label}</span>
        <span className="text-num text-[10px] uppercase tracking-wide text-muted-foreground/70">
          {methodLabel}
        </span>
      </div>
    </div>
  );
}

function SessionListView({ onSelect }: { onSelect: (session: SignatureSessionSummary) => void }) {
  const sessionsQuery = useQuery({
    queryKey: ["signature-sessions"],
    queryFn: listSignatureSessions,
  });
  const sessionList = sessionsQuery.data ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Signature review"
        description="Pick a session to compare its detected signatures against each student's previous signed appearance."
      />

      {sessionsQuery.isPending ? (
        <TableSkeleton rows={8} cols={6} />
      ) : sessionsQuery.isError ? (
        <ErrorState
          message={(sessionsQuery.error as Error).message}
          onRetry={() => sessionsQuery.refetch()}
        />
      ) : sessionList.length === 0 ? (
        <EmptyState
          title="No processed sessions yet"
          description="Signature comparisons appear here once a sheet has been uploaded and processed."
        />
      ) : (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Processed sessions</CardTitle>
            <CardDescription>
              Newest first — select a session to review its signatures.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Date</TableHead>
                  <TableHead>Subject</TableHead>
                  <TableHead>Lecturer</TableHead>
                  <TableHead>Batch</TableHead>
                  <TableHead>Filename</TableHead>
                  <TableHead className="text-right">Items</TableHead>
                  <TableHead className="w-8" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {sessionList.map((session) => (
                  <TableRow
                    key={session.session_id}
                    className="cursor-pointer"
                    onClick={() => onSelect(session)}
                  >
                    <TableCell className="text-num">{session.session_date ?? "—"}</TableCell>
                    <TableCell className="text-num">{session.subject_code ?? "—"}</TableCell>
                    <TableCell>{session.lecturer_name ?? "—"}</TableCell>
                    <TableCell>{session.batch ?? "—"}</TableCell>
                    <TableCell
                      className="max-w-[16rem] truncate text-xs text-muted-foreground"
                      title={session.original_filename ?? undefined}
                    >
                      {session.original_filename ?? "—"}
                    </TableCell>
                    <TableCell className="text-num text-right">
                      <span className={cn(session.item_count === 0 && "text-muted-foreground")}>
                        {session.item_count}
                      </span>
                    </TableCell>
                    <TableCell>
                      <ChevronRight className="size-4 text-muted-foreground" aria-hidden />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

export function SignatureReviewPage() {
  const queryClient = useQueryClient();
  const [selectedSession, setSelectedSession] = useState<SignatureSessionSummary | null>(null);
  const [flaggedOnly, setFlaggedOnly] = useState(false);

  const itemsQuery = useQuery({
    queryKey: ["signature-session-items", selectedSession?.session_id],
    queryFn: () => getSignatureSessionItems(selectedSession!.session_id),
    enabled: selectedSession !== null,
  });
  // Stored decisions from a previous visit -- merged below by
  // (student_index, session_id) so a card an operator already resolved
  // stays resolved after a reload instead of resetting to its buttons.
  const reviews = useQuery({ queryKey: ["signature-reviews"], queryFn: listSignatureReviews });

  const items = useMemo(
    () => (itemsQuery.data ?? []).filter((i) => (flaggedOnly ? i.flagged : true)),
    [itemsQuery.data, flaggedOnly],
  );

  const resolvedByKey = useMemo(() => {
    const map = new Map<string, "confirmed" | "flagged">();
    for (const r of reviews.data ?? []) {
      if (r) map.set(reviewKey(r.student_index, r.session_id), r.decision);
    }
    return map;
  }, [reviews.data]);

  const reviewMutation = useMutation({
    mutationFn: (vars: {
      studentIndex: string;
      sessionId: string;
      decision: "confirmed" | "flagged";
    }) =>
      submitSignatureReview(vars.studentIndex, {
        session_id: vars.sessionId,
        decision: vars.decision,
      }),
    onSuccess: (_record, vars) => {
      // Both queries need refetching: /signatures/sessions/{id} re-derives
      // review_required from the same records, and /signatures/reviews is
      // what resolvedByKey above is built from -- without invalidating that
      // one too, the card wouldn't flip to its resolved state until some
      // unrelated refetch.
      queryClient.invalidateQueries({ queryKey: ["signature-session-items", vars.sessionId] });
      queryClient.invalidateQueries({ queryKey: ["signature-reviews"] });
      if (vars.decision === "confirmed")
        toast.success(`Signature confirmed for ${vars.studentIndex}`);
      else
        toast.warning(`Signature flagged for ${vars.studentIndex}`, {
          description: "Queued for manual verification.",
        });
    },
    onError: (error, vars) => {
      toast.error(`Could not record decision for ${vars.studentIndex}`, {
        description: (error as Error).message,
      });
    },
  });

  if (!selectedSession) {
    return <SessionListView onSelect={setSelectedSession} />;
  }

  return (
    <div className="space-y-6">
      <Breadcrumb>
        <BreadcrumbList>
          <BreadcrumbItem>
            <BreadcrumbLink asChild>
              <button type="button" onClick={() => setSelectedSession(null)}>
                Signature review
              </button>
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbPage>
              {selectedSession.subject_code ?? "Session"} · {selectedSession.session_date ?? "—"}
            </BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      <PageHeader
        title={`${selectedSession.subject_code ?? "Session"} — ${selectedSession.session_date ?? "—"}`}
        description="Compare each detected signature with the student's previous signed session and resolve mismatches."
        actions={
          <div className="flex items-center gap-2">
            <Switch id="flagged-only" checked={flaggedOnly} onCheckedChange={setFlaggedOnly} />
            <Label htmlFor="flagged-only" className="text-sm text-muted-foreground">
              Flagged only
            </Label>
          </div>
        }
      />

      {itemsQuery.isPending ? (
        <CardGridSkeleton count={6} />
      ) : itemsQuery.isError ? (
        <ErrorState
          message={(itemsQuery.error as Error).message}
          onRetry={() => itemsQuery.refetch()}
        />
      ) : items.length === 0 ? (
        <EmptyState
          title={flaggedOnly ? "Nothing flagged" : "No comparisons for this session"}
          description={
            flaggedOnly
              ? "No signature in this session is currently flagged. Turn the filter off to see all comparisons."
              : "Every student present in this session is either new or has no earlier signed session to compare against."
          }
          action={
            flaggedOnly ? (
              <Button variant="outline" size="sm" onClick={() => setFlaggedOnly(false)}>
                Show all
              </Button>
            ) : null
          }
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {items.map((item) => {
            const state = resolvedByKey.get(reviewKey(item.student_index, item.session_id));
            return (
              <Card key={item.id} className={cn(state && "opacity-70")}>
                <CardHeader className="pb-3">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <CardTitle className="text-num text-sm">{item.student_index}</CardTitle>
                      <CardDescription>{item.name}</CardDescription>
                    </div>
                    <SimilarityRing value={item.similarity} method={item.match_method} />
                  </div>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="grid grid-cols-2 gap-2">
                    <figure className="space-y-1">
                      <img
                        src={item.reference_image}
                        alt={`Previous signature for ${item.student_index}`}
                        loading="lazy"
                        className="h-16 w-full rounded border border-border bg-background object-cover"
                      />
                      <figcaption className="text-[11px] text-muted-foreground">
                        Previous · {item.previous_session_date ?? "—"}
                      </figcaption>
                    </figure>
                    <figure className="space-y-1">
                      <img
                        src={item.current_image}
                        alt={`Detected signature for ${item.student_index} on ${item.session_date}`}
                        loading="lazy"
                        className="h-16 w-full rounded border border-border bg-background object-cover"
                      />
                      <figcaption className="text-[11px] text-muted-foreground">
                        Current · {item.session_date ?? "—"}
                      </figcaption>
                    </figure>
                  </div>

                  {state ? (
                    <p
                      className={cn(
                        "flex items-center gap-1.5 rounded-md border px-2 py-1.5 text-xs font-medium",
                        state === "confirmed"
                          ? "border-present/30 bg-present-soft text-present"
                          : "border-review/40 bg-review-soft text-review",
                      )}
                    >
                      {state === "confirmed" ? (
                        <Check className="size-3.5" aria-hidden />
                      ) : (
                        <Flag className="size-3.5" aria-hidden />
                      )}
                      {state === "confirmed" ? "Confirmed by operator" : "Flagged for verification"}
                    </p>
                  ) : (
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        className="flex-1"
                        disabled={reviewMutation.isPending}
                        onClick={() =>
                          reviewMutation.mutate({
                            studentIndex: item.student_index,
                            sessionId: item.session_id,
                            decision: "confirmed",
                          })
                        }
                      >
                        <Check className="size-3.5" /> Confirm
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        className="flex-1"
                        disabled={reviewMutation.isPending}
                        onClick={() =>
                          reviewMutation.mutate({
                            studentIndex: item.student_index,
                            sessionId: item.session_id,
                            decision: "flagged",
                          })
                        }
                      >
                        <Flag className="size-3.5" /> Flag
                      </Button>
                    </div>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
