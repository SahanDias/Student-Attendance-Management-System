import type { Metadata } from "next";

import { DashboardPage } from "@/components/pages/dashboard-page";

export const metadata: Metadata = {
  title: "Attendance Dashboard — Sheet Processing Console",
  description:
    "Operator dashboard for the student attendance system: processed sheets, attendance rates per session, per-student trends and flagged signatures.",
  openGraph: {
    title: "Attendance Dashboard — Sheet Processing Console",
    description:
      "Operator dashboard for the student attendance system: processed sheets, attendance rates per session, per-student trends and flagged signatures.",
  },
};

export default function Page() {
  return <DashboardPage />;
}
