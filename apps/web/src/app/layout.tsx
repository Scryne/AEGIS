import type { Metadata } from "next";
import { JetBrains_Mono, Public_Sans } from "next/font/google";
import type { ReactNode } from "react";

import "./globals.css";

// Türkçe karakterler için latin-ext şart; yoksa ş/ğ/ı yedek fonttan gelir.
const publicSans = Public_Sans({
  subsets: ["latin", "latin-ext"],
  variable: "--font-public-sans",
  display: "swap",
});
const jetbrains = JetBrains_Mono({
  subsets: ["latin", "latin-ext"],
  variable: "--font-jetbrains",
  display: "swap",
});

export const metadata: Metadata = {
  title: { default: "AEGIS", template: "%s · AEGIS" },
  description: "KYB / kurumsal due diligence — yaptırım/PEP taraması ve denetime dayanıklı dosya.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="tr" className={`${publicSans.variable} ${jetbrains.variable}`}>
      <body>{children}</body>
    </html>
  );
}
