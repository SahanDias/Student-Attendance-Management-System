import type { Metadata } from "next";

import { SignatureReviewPage } from "@/components/pages/signature-review-page";

export const metadata: Metadata = {
  title: "Signature Review Queue — Attendance Console",
  description:
    "Pick a processed session, then compare each detected signature against the student's previous signed appearance, with similarity scores and confirm or flag actions.",
  openGraph: {
    title: "Signature Review Queue — Attendance Console",
    description: "Confirm or flag detected signatures against each student's previous session.",
  },
};

export default function Page() {
  return <SignatureReviewPage />;
}
