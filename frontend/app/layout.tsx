import type { Metadata } from "next";
import { Cinzel, IBM_Plex_Mono, Space_Grotesk } from "next/font/google";

import { Providers } from "@/app/providers";
import "./globals.css";

const displayFont = Cinzel({
  subsets: ["latin"],
  variable: "--font-display",
});

const uiFont = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-ui",
});

const monoFont = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-mono",
});

export const metadata: Metadata = {
  title: "DAQS Game Client",
  description: "Game-like React frontend for the DAQS neuro-symbolic RPG prototype.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body
        className={`${displayFont.variable} ${uiFont.variable} ${monoFont.variable} min-h-screen bg-[var(--bg)] font-[family:var(--font-ui)] text-[var(--ink)]`}
      >
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
