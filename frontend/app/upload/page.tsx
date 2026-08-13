import type { Metadata } from "next";

import { UploadPage } from "@/components/pages/upload-page";

export const metadata: Metadata = {
  title: "Upload Signing Sheet — Attendance Console",
  description:
    "Drop a photographed attendance sheet and its info.xml, then watch the OpenCV pipeline run stage by stage with live step previews.",
  openGraph: {
    title: "Upload Signing Sheet — Attendance Console",
    description: "Upload a sheet photo and info.xml and follow every OpenCV processing stage live.",
  },
};

export default function Page() {
  return <UploadPage />;
}
