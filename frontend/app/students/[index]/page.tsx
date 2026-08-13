import type { Metadata } from "next";

import { StudentDetail } from "@/components/pages/student-detail-page";

export const metadata: Metadata = {
  title: "Student Attendance Profile — Attendance Console",
  description:
    "Per-student attendance profile: present vs absent split, attendance per session date, a session heatmap and every collected signature crop.",
  openGraph: {
    title: "Student Attendance Profile — Attendance Console",
    description: "Attendance breakdown and signature history for one student.",
  },
};

export default async function Page({
  params,
}: {
  params: { index: string } | Promise<{ index: string }>;
}) {
  const { index } = await params;
  return <StudentDetail index={index} />;
}
