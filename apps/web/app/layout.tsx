import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Mobius | Online Threat Alert",
  description: "공개·허가 데이터 기반의 온라인 공격 조기경보 서비스",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="ko"><body>{children}</body></html>;
}
