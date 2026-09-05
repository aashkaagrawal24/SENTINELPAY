import "./globals.css";
import "./judge.css";
import "./advanced.css";
import { Inter } from "next/font/google";
import Script from "next/script";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata = {
  title: "SentinelPay v4.2 — Agentic Commerce Gateway",
  description: "Make your merchant sellable to AI buyers. Bounded negotiation, formal Z3 verification, and Razorpay Test Mode execution.",
};

import { CommandPalette } from "@/components/common/command-palette";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`dark ${inter.variable}`}>
      <body className="min-h-screen bg-background text-foreground antialiased selection:bg-blue-500/30 selection:text-blue-200">
        <Script src="https://checkout.razorpay.com/v1/checkout.js" strategy="lazyOnload" />
        <CommandPalette />
        {children}
      </body>
    </html>
  );
}
