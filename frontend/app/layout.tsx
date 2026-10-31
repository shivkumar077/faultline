import type { Metadata } from "next";
import { Shell } from "@/components/shell";
import "./globals.css";
import "./workspace.css";

export const metadata: Metadata = {
  title: "Faultline — Reliability workspace",
  description: "Evidence-led mutation analysis, failure diagnosis, and repair evaluation.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
