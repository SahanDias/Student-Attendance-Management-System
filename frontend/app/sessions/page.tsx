import type { Metadata } from "next";

import { SessionsPage } from "@/components/pages/sessions-list-page";

export const metadata: Metadata = {
  title: "Processed Sessions — Attendance Console",
  description:
    "Search and filter every processed attendance sheet by subject code and date range, with per-session present and absent counts.",
  openGraph: {
    title: "Processed Sessions — Attendance Console",
    description: "Every processed signing sheet, searchable by subject and date range.",
  },
};

export default function Page() {
  return <SessionsPage />;
}
