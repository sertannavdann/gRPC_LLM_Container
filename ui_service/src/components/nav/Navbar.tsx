/**
 * Navbar Component
 * 
 * Persistent top navigation bar with page links.
 * Uses Next.js Link for client-side routing.
 */
'use client';

import React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  Bot,
  LayoutDashboard,
  DollarSign,
  Activity,
  Home,
  Plug,
  Settings,
  Zap,
} from 'lucide-react';

const NAV_ITEMS = [
  { href: '/', label: 'Home', icon: Home },
  { href: '/chat', label: 'Chat', icon: Bot },
  { href: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { href: '/finance', label: 'Finance', icon: DollarSign },
  { href: '/integrations', label: 'Integrations', icon: Plug },
  { href: '/pipeline', label: 'Pipeline', icon: Zap },
  { href: '/monitoring', label: 'Monitoring', icon: Activity },
  { href: '/settings', label: 'Settings', icon: Settings },
] as const;

export function Navbar() {
  const pathname = usePathname();

  return (
    <nav className="flex items-center justify-between px-4 py-2 border-b border-border bg-card/80 backdrop-blur-sm flex-shrink-0">
      <div className="flex items-center gap-6">
        {/* Brand */}
        <Link href="/" className="flex items-center gap-2 text-primary font-bold text-lg">
          <Bot className="w-6 h-6" />
          <span className="hidden sm:inline">gRPC LLM</span>
        </Link>

        {/* Nav Links */}
        <div className="flex items-center gap-1">
          {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
            const isActive = href === '/' ? pathname === '/' : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={`flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-md transition-colors ${
                  isActive
                    ? 'bg-primary text-primary-foreground font-medium'
                    : 'text-muted-foreground hover:text-foreground hover:bg-muted'
                }`}
              >
                <Icon className="w-4 h-4" />
                <span className="hidden md:inline">{label}</span>
              </Link>
            );
          })}
        </div>
      </div>

      {/* Right side - status indicator */}
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
          <span className="hidden sm:inline">Connected</span>
        </span>
      </div>
    </nav>
  );
}
