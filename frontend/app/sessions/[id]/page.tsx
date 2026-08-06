import type { Metadata } from "next";

import { SessionDetail } from "@/components/pages/session-detail-page";

export const metadata: Metadata = {
  title: "Session Detail — Attendance Console",
  description:
    "Read-only view of one processed attendance sheet: pipeline stage gallery, detected results table and the original photograph.",
  openGraph: {
    title: "Session Detail — Attendance Console",
    description: "Pipeline stages, results and source photo for one attendance session.",
  },
};

export default function Page() {
  return <SessionDetail />;
}
