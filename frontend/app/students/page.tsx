import type { Metadata } from "next";

import { StudentsPage } from "@/components/pages/students-list-page";

export const metadata: Metadata = {
  title: "Students Roster — Attendance Console",
  description:
    "Searchable roster of every student with batch, sessions attended and attendance percentage detected from signing sheets.",
  openGraph: {
    title: "Students Roster — Attendance Console",
    description: "Attendance percentages for every student in the roster.",
  },
};

export default function Page() {
  return <StudentsPage />;
}
