"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { ArrowUpRight, FileStack, Flag, Percent, Users } from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip as RTooltip,
  XAxis,
  YAxis,
} from "recharts";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/badges";
import { ChartSkeleton, EmptyState, ErrorState, TableSkeleton } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { getAttendanceSummaries, getAttendanceTrend } from "@/services/attendance.service";
import { listSessions } from "@/services/sessions.service";
import { listStudents } from "@/services/students.service";

function StatCard({
  label,
  value,
  hint,
  icon: Icon,
}: {
  label: string;
  value: string;
  hint: string;
  icon: typeof Users;
}) {
  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-2 space-y-0 pb-2">
        <CardDescription>{label}</CardDescription>
        <Icon className="size-4 text-muted-foreground" aria-hidden />
      </CardHeader>
      <CardContent>
        <p className="text-num text-3xl font-semibold tracking-tight text-foreground">{value}</p>
        <p className="mt-1 text-xs text-muted-foreground">{hint}</p>
      </CardContent>
    </Card>
  );
}

const axis = {
  stroke: "var(--muted-foreground)",
  fontSize: 11,
};

function formatUploadedAt(value: string | undefined): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "—";
  return parsed.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function DashboardPage() {
  const sessions = useQuery({ queryKey: ["sessions"], queryFn: listSessions });
  const students = useQuery({ queryKey: ["students"], queryFn: listStudents });
  const trend = useQuery({ queryKey: ["trend"], queryFn: getAttendanceTrend });
  const attendanceSummaries = useQuery({
    queryKey: ["attendance-summaries"],
    queryFn: getAttendanceSummaries,
  });

  const safeStudents = Array.isArray(students.data)
    ? students.data.filter((student): student is NonNullable<typeof student> => Boolean(student))
    : [];
  const safeSessions = Array.isArray(sessions.data)
    ? sessions.data.filter((session): session is NonNullable<typeof session> => Boolean(session))
    : [];

  const totalPresent = safeSessions.reduce((a, s) => a + (s?.present_count ?? 0), 0);
  const totalDetected = safeSessions.reduce((a, s) => a + (s?.students_detected ?? 0), 0);
  const rate = totalDetected ? (totalPresent / totalDetected) * 100 : 0;
  const flagged = safeSessions.reduce((a, s) => a + (s?.flagged_count ?? 0), 0);

  const safeSummaries = Array.isArray(attendanceSummaries.data)
    ? attendanceSummaries.data.filter((summary): summary is NonNullable<typeof summary> =>
        Boolean(summary),
      )
    : [];

  const lowest = safeSummaries
    .slice()
    .sort((a, b) => (a?.percentage ?? 0) - (b?.percentage ?? 0))
    .slice(0, 10)
    .map((summary) => ({
      name: summary?.index?.replace("2022-CS-", "") ?? "Unknown",
      value: summary?.percentage ?? 0,
    }));

  // processed_at carries the backend's uploaded_at (see mapSessionSummary in
  // sessions.service.ts -- GET /sheets never sends a processed_at field, so
  // the mapper's fallback chain resolves it to uploaded_at). Sorting on it
  // here, rather than session_date, means a freshly processed sheet always
  // surfaces first even if its class met long ago.
  const recent = safeSessions
    .filter((session) => Boolean(session?.processed_at))
    .sort((a, b) => (b?.processed_at ?? "").localeCompare(a?.processed_at ?? ""))
    .slice(0, 6);

  if (process.env.NODE_ENV === "development") {
    // The true raw (pre-mapping) GET /sheets body is logged in
    // listSessions() itself -- sessions.data here is already mapped to
    // SessionSummary, so only the post-filter count is logged from here.
    console.log("[dashboard] recent sessions post-filter length:", recent.length);
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Dashboard"
        description="Processing throughput and attendance health across every sheet read by the OpenCV pipeline."
        actions={
          <Button asChild size="sm">
            <Link href="/upload">Upload a sheet</Link>
          </Button>
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Total sheets processed"
          value={sessions.isPending ? "—" : String(sessions.data?.length ?? 0)}
          hint="Sessions stored in MongoDB"
          icon={FileStack}
        />
        <StatCard
          label="Total students"
          value={students.isPending ? "—" : String(students.data?.length ?? 0)}
          hint="Enrolled across all batches"
          icon={Users}
        />
        <StatCard
          label="Overall attendance rate"
          value={sessions.isPending ? "—" : `${rate.toFixed(1)}%`}
          hint={`${totalPresent} of ${totalDetected} detected rows`}
          icon={Percent}
        />
        <StatCard
          label="Flagged signatures"
          value={sessions.isPending ? "—" : String(flagged)}
          hint="Awaiting operator verification"
          icon={Flag}
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-5">
        <Card className="xl:col-span-3">
          <CardHeader>
            <CardTitle className="text-base">Attendance rate over time</CardTitle>
            <CardDescription>One point per processed session date.</CardDescription>
          </CardHeader>
          <CardContent>
            {trend.isPending ? (
              <ChartSkeleton />
            ) : trend.isError ? (
              <ErrorState
                message={(trend.error as Error).message}
                onRetry={() => trend.refetch()}
              />
            ) : (trend.data ?? []).length === 0 ? (
              <EmptyState
                title="No sessions processed yet"
                description="Attendance trends appear once at least one signing sheet has been read."
                action={
                  <Button asChild size="sm">
                    <Link href="/upload">Upload first sheet</Link>
                  </Button>
                }
              />
            ) : (
              <ResponsiveContainer width="100%" height={260}>
                <LineChart data={trend.data} margin={{ left: -18, right: 8, top: 8 }}>
                  <CartesianGrid stroke="var(--border)" vertical={false} />
                  <XAxis dataKey="date" tickFormatter={(d: string) => d.slice(5)} {...axis} />
                  <YAxis domain={[0, 100]} unit="%" {...axis} />
                  <RTooltip
                    contentStyle={{
                      background: "var(--card)",
                      border: "1px solid var(--border)",
                      borderRadius: 8,
                      fontSize: 12,
                      color: "var(--card-foreground)",
                    }}
                  />
                  <Line
                    type="monotone"
                    dataKey="rate"
                    name="Attendance rate"
                    stroke="var(--chart-1)"
                    strokeWidth={2}
                    dot={{ r: 3, fill: "var(--chart-1)" }}
                  />
                </LineChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        <Card className="xl:col-span-2">
          <CardHeader className="flex-row items-start justify-between space-y-0">
            <div>
              <CardTitle className="text-base">Lowest attendance</CardTitle>
              <CardDescription>Bottom 10 students by percentage.</CardDescription>
            </div>
            <Link
              href="/students"
              className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline"
            >
              View all <ArrowUpRight className="size-3" aria-hidden />
            </Link>
          </CardHeader>
          <CardContent>
            {attendanceSummaries.isPending ? (
              <ChartSkeleton />
            ) : attendanceSummaries.isError ? (
              <ErrorState
                message={(attendanceSummaries.error as Error).message}
                onRetry={() => attendanceSummaries.refetch()}
              />
            ) : lowest.length === 0 ? (
              <EmptyState
                title="No students yet"
                description="Student records are created from the info.xml roster."
              />
            ) : (
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={lowest} layout="vertical" margin={{ left: 4, right: 16 }}>
                  <CartesianGrid stroke="var(--border)" horizontal={false} />
                  <XAxis type="number" domain={[0, 100]} unit="%" {...axis} />
                  <YAxis type="category" dataKey="name" width={44} {...axis} />
                  <RTooltip
                    contentStyle={{
                      background: "var(--card)",
                      border: "1px solid var(--border)",
                      borderRadius: 8,
                      fontSize: 12,
                      color: "var(--card-foreground)",
                    }}
                  />
                  <Bar
                    dataKey="value"
                    name="Attendance %"
                    fill="var(--chart-1)"
                    radius={[0, 3, 3, 0]}
                    barSize={12}
                  />
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Recent sessions</CardTitle>
          <CardDescription>Latest sheets read by the pipeline.</CardDescription>
        </CardHeader>
        <CardContent className="px-0">
          {sessions.isPending ? (
            <TableSkeleton cols={6} />
          ) : sessions.isError ? (
            <ErrorState
              className="mx-6"
              message={(sessions.error as Error).message}
              onRetry={() => sessions.refetch()}
            />
          ) : recent.length === 0 ? (
            <EmptyState
              className="mx-6"
              title="No sessions yet"
              description="Upload a photographed signing sheet with its info.xml to create the first session."
              action={
                <Button asChild size="sm">
                  <Link href="/upload">Upload sheet</Link>
                </Button>
              }
            />
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Date</TableHead>
                    <TableHead>Uploaded</TableHead>
                    <TableHead>Subject</TableHead>
                    <TableHead>Detected</TableHead>
                    <TableHead>Present</TableHead>
                    <TableHead>Absent</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right">Action</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {recent.map((s) => (
                    <TableRow key={s.session_id}>
                      <TableCell className="text-num">{s.session_date}</TableCell>
                      <TableCell className="text-num">{formatUploadedAt(s.processed_at)}</TableCell>
                      <TableCell className="text-num font-medium">{s.subject_code}</TableCell>
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
        </CardContent>
      </Card>
    </div>
  );
}
