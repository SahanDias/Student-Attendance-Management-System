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
