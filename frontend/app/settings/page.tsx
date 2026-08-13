import type { Metadata } from "next";

import { SettingsPage } from "@/components/pages/settings-page";

export const metadata: Metadata = {
  title: "Detection Settings — Attendance Console",
  description:
    "Configure the backend API base URL, ink ratio and minimum component area detection thresholds, and the default header row count.",
  openGraph: {
    title: "Detection Settings — Attendance Console",
    description: "Backend URL and OpenCV detection thresholds for the pipeline.",
  },
};

export default function Page() {
  return <SettingsPage />;
}
