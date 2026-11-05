import type { Metadata } from "next";
import { Figtree, Inter } from "next/font/google";
import { MENU_BOOT } from "@/lib/menu-state";
import "./globals.css";

// Two fonts, as in the approved designs: Figtree on the sign-in pages, Inter inside the CRM.
const figtree = Figtree({ variable: "--font-figtree", subsets: ["latin"], weight: ["400", "500", "600", "700"] });
const inter = Inter({ variable: "--font-inter", subsets: ["latin"] }); // variable: every weight, including 450

export const metadata: Metadata = {
  title: "NEO CRM",
  description: "Leads, bookings and patients for the NEO clinics.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    // MENU_BOOT adds an attribute to <html> before React starts, which React would otherwise report.
    <html lang="en" className={`${figtree.variable} ${inter.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: MENU_BOOT }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
