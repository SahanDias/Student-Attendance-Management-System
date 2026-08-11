"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip as RTooltip,
  XAxis,
  YAxis,
} from "recharts";

import { AttendanceBar, PresenceBadge } from "@/components/badges";
import { PageHeader } from "@/components/page-header";
import { CardGridSkeleton, ChartSkeleton, EmptyState, ErrorState } from "@/components/states";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { getAttendanceSummary, getStudentSignatures } from "@/services/attendance.service";
import { getStudent } from "@/services/students.service";
import { staticUrl } from "@/services/api";
import { cn } from "@/lib/utils";

export function StudentDetail({ index }: { index?: string }) {
  const normalizedIndex = index?.trim() ?? "";

  if (!normalizedIndex) {
    return (
      <div className="space-y-6">
        <PageHeader title="Student profile" description="Loading student route…" />
        <EmptyState
          title="Missing student index"
          description="The student detail route did not provide a valid student index."
        />
      </div>
    );
  }

  const student = useQuery({
    queryKey: ["student", normalizedIndex],
    queryFn: () => getStudent(normalizedIndex),
    enabled: Boolean(normalizedIndex),
  });
  const summary = useQuery({
    queryKey: ["summary", normalizedIndex],
    queryFn: () => getAttendanceSummary(normalizedIndex),
    enabled: Boolean(normalizedIndex),
  });
  const signatures = useQuery({
    queryKey: ["signatures", normalizedIndex],
    queryFn: () => getStudentSignatures(normalizedIndex),
    enabled: Boolean(normalizedIndex),
  });

  const donut = summary.data
    ? [
        { name: "Present", value: summary.data.present, fill: "var(--present)" },
        { name: "Absent", value: summary.data.absent, fill: "var(--absent)" },
      ]
    : [];

  const bars = (summary.data?.series ?? []).map((s) => ({
    date: s.date.slice(5),
    value: s.present ? 1 : 0,
    subject: s.subject_code,
  }));

  return (
    <div className="space-y-6">
      <PageHeader
        title={student.data?.name ?? normalizedIndex}
        description={
          student.data
            ? `${student.data.index} · ${student.data.batch}`
            : "Loading student record…"
        }
        actions={
          student.data ? (
            <AttendanceBar
              value={student.data.attendance_percentage}
              label={`${student.data.attendance_percentage}% overall attendance`}
            />
          ) : null
        }
      />

      {student.isError ? (
        <ErrorState message={(student.error as Error).message} onRetry={() => student.refetch()} />
      ) : null}

      <div className="grid gap-4 xl:grid-cols-5">
        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle className="text-base">Present vs absent</CardTitle>
            <CardDescription>Across all processed sessions.</CardDescription>
          </CardHeader>
          <CardContent>
            {summary.isPending ? (
              <ChartSkeleton height={220} />
            ) : summary.isError ? (
              <ErrorState
                message={(summary.error as Error).message}
                onRetry={() => summary.refetch()}
              />
            ) : (
              <div className="flex items-center gap-4">
                <ResponsiveContainer width="55%" height={200}>
                  <PieChart>
                    <Pie
                      data={donut}
                      dataKey="value"
                      innerRadius={52}
                      outerRadius={78}
                      paddingAngle={2}
                    >
                      {donut.map((d) => (
                        <Cell key={d.name} fill={d.fill} stroke="var(--card)" />
                      ))}
                    </Pie>
                    <RTooltip
                      contentStyle={{
                        background: "var(--card)",
                        border: "1px solid var(--border)",
                        borderRadius: 8,
                        fontSize: 12,
                        color: "var(--card-foreground)",
                      }}
                    />
                  </PieChart>
                </ResponsiveContainer>
                <dl className="space-y-2 text-sm">
                  <div>
                    <dt className="text-xs text-muted-foreground">Present</dt>
                    <dd className="text-num text-lg font-semibold text-present">
                      {summary.data?.present}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted-foreground">Absent</dt>
                    <dd className="text-num text-lg font-semibold text-absent">
                      {summary.data?.absent}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted-foreground">Rate</dt>
                    <dd className="text-num text-lg font-semibold">{summary.data?.percentage}%</dd>
                  </div>
                </dl>
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="xl:col-span-3">
          <CardHeader>
            <CardTitle className="text-base">Attendance per session</CardTitle>
            <CardDescription>1 = signed, 0 = no signature detected.</CardDescription>
          </CardHeader>
          <CardContent>
            {summary.isPending ? (
              <ChartSkeleton height={220} />
            ) : bars.length === 0 ? (
              <EmptyState
                title="No sessions recorded"
                description="This student has no processed sessions yet."
              />
            ) : (
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={bars} margin={{ left: -28, right: 8 }}>
                  <CartesianGrid stroke="var(--border)" vertical={false} />
                  <XAxis dataKey="date" stroke="var(--muted-foreground)" fontSize={11} />
                  <YAxis
                    domain={[0, 1]}
                    ticks={[0, 1]}
                    stroke="var(--muted-foreground)"
                    fontSize={11}
                  />
                  <RTooltip
                    contentStyle={{
                      background: "var(--card)",
                      border: "1px solid var(--border)",
                      borderRadius: 8,
                      fontSize: 12,
                      color: "var(--card-foreground)",
                    }}
                  />
                  <Bar dataKey="value" name="Signed" radius={[3, 3, 0, 0]} barSize={18}>
                    {bars.map((b, i) => (
                      <Cell key={i} fill={b.value ? "var(--present)" : "var(--absent)"} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Session heatmap</CardTitle>
          <CardDescription>Every session date, coloured and labelled by outcome.</CardDescription>
        </CardHeader>
        <CardContent>
          {summary.isPending ? (
            <ChartSkeleton height={120} />
          ) : (summary.data?.series ?? []).length === 0 ? (
            <EmptyState
              title="No session dates"
              description="Process a sheet to populate this heatmap."
            />
          ) : (
            <div className="flex flex-wrap gap-2">
              {(summary.data?.series ?? []).map((s, index) => (
                <Tooltip key={s.session_id || `session-${index}`}>
                  <TooltipTrigger asChild>
                    <div
                      className={cn(
                        "flex size-16 flex-col items-center justify-center gap-0.5 rounded-md border text-[11px]",
                        s.present
                          ? "border-present/40 bg-present-soft text-present"
                          : "border-absent/40 bg-absent-soft text-absent",
                      )}
                    >
                      <span className="text-num">{s.date.slice(5)}</span>
                      <span className="font-medium">{s.present ? "P" : "A"}</span>
                    </div>
                  </TooltipTrigger>
                  <TooltipContent>
                    <p className="text-num text-xs">
                      {s.date} · {s.subject_code} · {s.present ? "Present" : "Absent"}
                    </p>
                  </TooltipContent>
                </Tooltip>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Signature crops</CardTitle>
          <CardDescription>Every cell extracted for this student across sessions.</CardDescription>
        </CardHeader>
        <CardContent>
          {signatures.isPending ? (
            <CardGridSkeleton count={6} />
          ) : signatures.isError ? (
            <ErrorState
              message={(signatures.error as Error).message}
              onRetry={() => signatures.refetch()}
            />
          ) : (signatures.data ?? []).length === 0 ? (
            <EmptyState
              title="No signature crops yet"
              description="Crops are stored each time this student's row is extracted from a sheet."
            />
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {(signatures.data ?? []).map((sig) => (
                <figure
                  key={sig.session_id}
                  className="space-y-2 rounded-md border border-border bg-card p-3"
                >
                  <img
                    src={staticUrl(sig.cell_image)}
                    alt={`Signature crop from ${sig.session_date}`}
                    loading="lazy"
                    className="h-16 w-full rounded border border-border bg-background object-cover"
                  />
                  <figcaption className="flex items-center justify-between gap-2">
                    <span className="text-num text-xs text-muted-foreground">
                      {sig.session_date} · {sig.subject_code}
                    </span>
                    <PresenceBadge present={sig.present} />
                  </figcaption>
                </figure>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
