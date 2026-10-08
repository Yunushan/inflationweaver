import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "InflationWeaver | Real return workspace",
  description: "Analyze purchasing power, inflation-adjusted returns and drawdowns from your own financial series.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
