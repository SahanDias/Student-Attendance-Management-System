import type { Metadata } from "next";
import type { ReactNode } from "react";

import { Providers } from "./providers";
import "./globals.css";

const title = "Attendance Dashboard — Sheet Processing Console";
const description =
  "Operator dashboard for the student attendance system: processed sheets, attendance rates per session, per-student trends and flagged signatures.";
const ogImage =
  "https://pub-bb2e103a32db4e198524a2e9ed8f35b4.r2.dev/c8ee8685-a9a2-4943-b036-1fdb6b4282c1/id-preview-ccbd0a46--ec0e5141-d1de-4368-9d7a-c7abb2778437.lovable.app-1785679798082.png";

export const metadata: Metadata = {
  title,
  description,
  openGraph: {
    type: "website",
    title,
    description,
    images: [ogImage],
  },
  twitter: {
    card: "summary_large_image",
    title,
    description,
    images: [ogImage],
  },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap"
        />
      </head>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
