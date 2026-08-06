"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { Search } from "lucide-react";
import { useMemo, useState } from "react";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/badges";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { listSessions } from "@/services/sessions.service";

export function SessionsPage() {
  const sessions = useQuery({ queryKey: ["sessions"], queryFn: listSessions });
  const [q, setQ] = useState("");
  const [subject, setSubject] = useState("all");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");

  const subjects = useMemo(
    () => Array.from(new Set((sessions.data ?? []).map((s) => s.subject_code))),
    [sessions.data],
  );

  const rows = useMemo(() => {
    return (sessions.data ?? []).filter((s) => {
      const matchesQ =
        !q ||
        s.subject_code.toLowerCase().includes(q.toLowerCase()) ||
        s.session_id.toLowerCase().includes(q.toLowerCase()) ||
        s.session_date.includes(q);
      const matchesSubject = subject === "all" || s.subject_code === subject;
      const matchesFrom = !from || s.session_date >= from;
      const matchesTo = !to || s.session_date <= to;
      return matchesQ && matchesSubject && matchesFrom && matchesTo;
    });
  }, [sessions.data, q, subject, from, to]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Sessions"
        description="Every signing sheet the pipeline has read, with detection counts and review status."
        actions={
          <Button asChild size="sm">
            <Link href="/upload">Upload sheet</Link>
          </Button>
        }
      />

      <div className="grid gap-3 rounded-lg border border-border bg-card p-4 sm:grid-cols-2 xl:grid-cols-4">
        <div className="space-y-1.5">
          <Label htmlFor="q">Search</Label>
          <div className="relative">
            <Search
              className="absolute left-2.5 top-2.5 size-4 text-muted-foreground"
              aria-hidden
            />
            <Input
              id="q"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Subject, date or session id"
              className="pl-8"
            />
          </div>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="subject-filter">Subject</Label>
          <Select value={subject} onValueChange={setSubject}>
            <SelectTrigger id="subject-filter">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All subjects</SelectItem>
              {subjects.map((s) => (
                <SelectItem key={s} value={s}>
                  {s}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="from">From</Label>
          <Input
            id="from"
            type="date"
            value={from}
            onChange={(e) => setFrom(e.target.value)}
            className="text-num"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="to">To</Label>
          <Input
            id="to"
            type="date"
            value={to}
            onChange={(e) => setTo(e.target.value)}
            className="text-num"
          />
        </div>
      </div>

      <div className="rounded-lg border border-border bg-card">
        {sessions.isPending ? (
          <TableSkeleton cols={7} />
        ) : sessions.isError ? (
          <ErrorState
            className="m-4 border-0"
            message={(sessions.error as Error).message}
            onRetry={() => sessions.refetch()}
          />
        ) : rows.length === 0 ? (
          <EmptyState
            className="m-4 border-0"
            title="No sessions match these filters"
            description="Try clearing the search or widening the date range, or process a new sheet."
            action={
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setQ("");
                  setSubject("all");
                  setFrom("");
                  setTo("");
                }}
              >
                Clear filters
              </Button>
            }
          />
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Date</TableHead>
                  <TableHead>Subject</TableHead>
                  <TableHead>Session id</TableHead>
                  <TableHead>Detected</TableHead>
                  <TableHead>Present</TableHead>
                  <TableHead>Absent</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((s, index) => (
                  <TableRow
                    key={s.session_id ?? `${s.session_date}-${s.subject_code}-${s.students_detected}-${index}`}
                  >
                    <TableCell className="text-num">{s.session_date}</TableCell>
                    <TableCell className="text-num font-medium">{s.subject_code}</TableCell>
                    <TableCell className="text-num text-xs text-muted-foreground">
                      {s.session_id}
                    </TableCell>
                    <TableCell className="text-num">{s.students_detected}</TableCell>
                    <TableCell className="text-num text-present">{s.present_count}</TableCell>
                    <TableCell className="text-num text-absent">{s.absent_count}</TableCell>
                    <TableCell>
                      <StatusBadge status={s.status} />
                    </TableCell>
                    <TableCell className="text-right">
                      <Button asChild variant="ghost" size="sm">
                        <Link href={`/sessions/${s.session_id}`}>View</Link>
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </div>
    </div>
  );
}