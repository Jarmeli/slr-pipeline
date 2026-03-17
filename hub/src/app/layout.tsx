import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SLR Pipeline: Orchestration Hub",
  description: "Premium Control Plane for Multi-Agent Simulation",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        {children}
      </body>
    </html>
  );
}
