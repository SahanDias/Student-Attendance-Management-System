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
