"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { ArrowUpRight, FileStack, Flag, Percent, Users } from "lucide-react";

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

<PageHeader
  title="Dashboard"
  description="Processing throughput and attendance health across every sheet read by the OpenCV pipeline."
  actions={
    <Button asChild size="sm">
      <Link href="/upload">Upload a sheet</Link>
    </Button>
  }
/>;

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
</div>;

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
</Card>;

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
</div>;
