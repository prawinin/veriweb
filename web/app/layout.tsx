import type { Metadata } from "next";
import "./globals.css";
import "./readability.css";

export const metadata: Metadata = {
  title: "Veriweb — Research with a paper trail",
  description:
    "Follow the evidence, inspect every citation, and compare conflicting sources. An open-model research workbench built for AMD compute.",
};
export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
