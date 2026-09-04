import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Chamados — Suporte Técnico",
  description: "Central inteligente de chamados para suporte técnico",
  other: {
    "codex-preview": "development",
  },
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="pt-BR">
      <body className="antialiased">{children}</body>
    </html>
  );
}
