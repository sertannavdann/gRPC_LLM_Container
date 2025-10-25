import type { Metadata } from 'next';
import './globals.css';
import './highlight.css';

export const metadata: Metadata = {
  title: 'gRPC LLM Agent',
  description: 'Chat interface for gRPC-based LLM agent',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
