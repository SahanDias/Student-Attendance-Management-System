
"use client";

import { PageHeader } from "@/components/page-header";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export function SessionDetail() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Session"
        description="Session detail page"
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Card>
          <CardHeader>
            <CardDescription>Students detected</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-num text-2xl font-semibold">—</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardDescription>Present</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-num text-2xl font-semibold">—</p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Pipeline stages</CardTitle>
          <CardDescription>Read-only record of the run.</CardDescription>
        </CardHeader>
        <CardContent>
          <p>Stage list will appear here.</p>
        </CardContent>
      </Card>
    </div>
  );
}