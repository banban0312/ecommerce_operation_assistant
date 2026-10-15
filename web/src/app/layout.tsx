import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "运营大盘 · 电商运营助手",
  description: "商品、创意与经营复盘的统一工作台",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
