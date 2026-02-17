import type { Metadata } from 'next';
import { Navbar } from '@/components/nav/Navbar';
import './globals.css';
import './highlight.css';

export const metadata: Metadata = {
  title: 'NEXUS | gRPC LLM Agent',
  description: 'Multi-provider AI agent with finance, health & navigation dashboards',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="flex flex-col h-screen overflow-hidden">
        <Navbar />
        <main className="flex-1 overflow-hidden">{children}</main>
      </body>
    </html>
  );
}
