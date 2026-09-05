import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Voice Verse Bot",
  description: "Adaptive multi-agent AI interview panel over Agora RTC",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
