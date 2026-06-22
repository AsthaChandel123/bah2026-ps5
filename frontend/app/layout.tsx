import type { Metadata } from "next";
import "./globals.css";
import "maplibre-gl/dist/maplibre-gl.css";
import "uplot/dist/uPlot.min.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "Bharat Climate Twin — AI-Powered Digital Twin of India's Climate",
  description:
    "Interactive, uncertainty-aware digital twin of India's climate (rainfall + temperature) with a real-time what-if scenario engine. ISRO BAH 2026 · PS5.",
};

export const viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#05080f",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
