"use client";

import { Download } from "lucide-react";

import { InkRatioBar, PresenceBadge } from "@/components/badges";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { SheetResult } from "@/types/api";
import { staticUrl } from "@/services/api";

export function exportResultsCsv(results: SheetResult[], filename: string) {
  const header = ["row", "student_index", "name", "present", "ink_ratio", "confidence"];
  const rows = results.map((r) =>
    [
      r.row,
      r.student_index,
      r.name ?? "",
      r.present ? "present" : "absent",
      r.ink_ratio,
      r.confidence,
    ].join(","),
  );
  const blob = new Blob([[header.join(","), ...rows].join("\n")], {
    type: "text/csv;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function ResultsTable({
  results,
  filename = "attendance.csv",
  showExport = true,
}: {
  results: SheetResult[];
  filename?: string;
  showExport?: boolean;
}) {
  const present = results.filter((r) => r.present).length;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">
          <span className="text-num text-foreground">{present}</span> present ·{" "}
          <span className="text-num text-foreground">{results.length - present}</span> absent ·{" "}
          <span className="text-num">{results.length}</span> rows detected
        </p>
        {showExport && (
          <Button size="sm" variant="outline" onClick={() => exportResultsCsv(results, filename)}>
            <Download className="size-3.5" /> Export as CSV
          </Button>
        )}
      </div>

      <div className="overflow-x-auto rounded-lg border border-border bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-12">#</TableHead>
              <TableHead>Student index</TableHead>
              <TableHead>Name</TableHead>
              <TableHead>Presence</TableHead>
              <TableHead>Ink ratio</TableHead>
              <TableHead className="text-right">Signature crop</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {results.map((r) => (
              <TableRow key={r.student_index}>
                <TableCell className="text-num text-muted-foreground">{r.row}</TableCell>
                <TableCell className="text-num font-medium">{r.student_index}</TableCell>
                <TableCell>{r.name ?? "—"}</TableCell>
                <TableCell>
                  <PresenceBadge present={r.present} />
                </TableCell>
                <TableCell>
                  <InkRatioBar value={r.ink_ratio} />
                </TableCell>
                <TableCell className="text-right">
                  {r.cell_image ? (
                    <img
                      src={staticUrl(r.cell_image)}
                      alt={`Signature cell for ${r.student_index}`}
                      loading="lazy"
                      className="ml-auto h-9 w-28 rounded border border-border bg-background object-cover"
                    />
                  ) : (
                    <span className="text-xs text-muted-foreground">no crop</span>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
