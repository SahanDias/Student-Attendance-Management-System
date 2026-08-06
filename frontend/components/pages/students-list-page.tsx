"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { Search } from "lucide-react";
import { useMemo, useState } from "react";

import { AttendanceBar } from "@/components/badges";
import { PageHeader } from "@/components/page-header";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { getAttendanceSummaries } from "@/services/attendance.service";
import { listStudents } from "@/services/students.service";

export function StudentsPage() {
  const students = useQuery({ queryKey: ["students"], queryFn: listStudents });
  // GET /students returns roster fields only (index, name, batch, subjects,
  // row_no, title) -- no attendance. GET /attendance/summary is the actual
  // source of sessions_attended/sessions_total/percentage per student, so
  // it's fetched separately here and merged by index below, rather than
  // expecting the roster response to carry it.
  const summaries = useQuery({
    queryKey: ["attendance-summaries"],
    queryFn: getAttendanceSummaries,
  });
  const [q, setQ] = useState("");

  const summaryByIndex = useMemo(() => {
    const map = new Map<
      string,
      { sessions_attended: number; sessions_total: number; percentage: number }
    >();
    for (const summary of summaries.data ?? []) {
      if (summary) map.set(summary.index, summary);
    }
    return map;
  }, [summaries.data]);

  const rows = useMemo(
    () =>
      (students.data ?? []).filter(
        (s) =>
          !q ||
          s.name.toLowerCase().includes(q.toLowerCase()) ||
          s.index.toLowerCase().includes(q.toLowerCase()),
      ),
    [students.data, q],
  );

  return (
    <div className="space-y-6">
      <PageHeader
        title="Students"
        description="Roster loaded from info.xml, with attendance aggregated across every processed session."
      />

      <div className="relative max-w-sm">
        <Search className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" aria-hidden />
        <Input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search index or name"
          aria-label="Search students"
          className="pl-8"
        />
      </div>

      <div className="rounded-lg border border-border bg-card">
        {students.isPending ? (
          <TableSkeleton cols={4} rows={8} />
        ) : students.isError ? (
          <ErrorState
            className="m-4 border-0"
            message={(students.error as Error).message}
            onRetry={() => students.refetch()}
          />
        ) : rows.length === 0 ? (
          <EmptyState
            className="m-4 border-0"
            title="No students found"
            description="No roster entry matches that search. Students are created when a sheet's info.xml is processed."
            action={
              <Button variant="outline" size="sm" onClick={() => setQ("")}>
                Clear search
              </Button>
            }
          />
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Index</TableHead>
                  <TableHead>Name</TableHead>
                  <TableHead>Sessions attended</TableHead>
                  <TableHead>Attendance</TableHead>
                  <TableHead className="text-right">Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((s, index) => {
                  // A student with no entry in /attendance/summary (e.g. no
                  // processed sessions yet) must still render "0 / 0", not a
                  // bare "/" from reading undefined fields off a missing entry.
                  const summary = summaryByIndex.get(s.index) ?? {
                    sessions_attended: 0,
                    sessions_total: 0,
                    percentage: 0,
                  };
                  return (
                    <TableRow key={s.index || `student-${index}`}>
                      <TableCell className="text-num font-medium">{s.index}</TableCell>
                      <TableCell>{s.name}</TableCell>
                      <TableCell className="text-num">
                        {summary.sessions_attended} / {summary.sessions_total}
                      </TableCell>
                      <TableCell>
                        <AttendanceBar
                          value={summary.percentage}
                          label={`${s.name}: ${summary.percentage}% attendance`}
                        />
                      </TableCell>
                      <TableCell className="text-right">
                        <Button asChild variant="ghost" size="sm">
                          <Link href={`/students/${s.index}`}>View</Link>
                        </Button>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        )}
      </div>
    </div>
  );
}
