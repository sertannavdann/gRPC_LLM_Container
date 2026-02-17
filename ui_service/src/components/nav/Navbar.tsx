/**
 * Navbar Component
 *
 * Persistent top navigation bar with 6 page routes.
 * Uses Next.js Link for client-side routing with active page highlighting.
 * Framer Motion layout animation on the active indicator.
 * Responsive: hamburger menu on mobile, horizontal nav on desktop.
 *
 * Pages:
 *   Dashboard (/) - home/overview
 *   Modules (/integrations) - module browser with lifecycle panel
 *   Finance (/finance) - financial data + charts
 *   Monitoring (/monitoring) - service health + P99 + agent runs
 *   Pipeline (/pipeline) - build job viewer
 *   Settings (/settings) - provider configuration with lock/unlock
 */
'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { motion } from 'framer-motion';
import {
  Bot,
  LayoutDashboard,
  Boxes,
  DollarSign,
  Activity,
  Zap,
  Settings,
  Menu,
  X,
} from 'lucide-react';

const NAV_ITEMS = [
  { href: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { href: '/integrations', label: 'Modules', icon: Boxes },
  { href: '/finance', label: 'Finance', icon: DollarSign },
  { href: '/monitoring', label: 'Monitoring', icon: Activity },
  { href: '/pipeline', label: 'Pipeline', icon: Zap },
  { href: '/settings', label: 'Settings', icon: Settings },
] as const;

export function Navbar() {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);

  const isActive = (href: string) => {
    if (href === '/dashboard') {
      return pathname === '/' || pathname === '/dashboard' || pathname.startsWith('/dashboard');
    }
    return pathname.startsWith(href);
  };

  return (
    <nav className="flex items-center justify-between px-4 py-2 border-b border-border bg-card/80 backdrop-blur-sm flex-shrink-0 relative">
      <div className="flex items-center gap-6">
        {/* Brand */}
        <Link href="/" className="flex items-center gap-2 text-primary font-bold text-lg">
          <Bot className="w-6 h-6" />
          <span className="hidden sm:inline">NEXUS</span>
        </Link>

        {/* Desktop Nav Links */}
        <div className="hidden md:flex items-center gap-1">
          {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
            const active = isActive(href);
            return (
              <Link
                key={href}
                href={href}
                className="relative flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-md transition-colors"
              >
                {active && (
                  <motion.div
                    layoutId="nav-active"
                    className="absolute inset-0 bg-primary rounded-md"
                    transition={{ type: 'spring', bounce: 0.2, duration: 0.4 }}
                  />
                )}
                <span
                  className={`relative z-10 flex items-center gap-1.5 ${
                    active
                      ? 'text-primary-foreground font-medium'
                      : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  <Icon className="w-4 h-4" />
                  {label}
                </span>
              </Link>
            );
          })}
        </div>
      </div>

      {/* Right side - status + mobile toggle */}
      <div className="flex items-center gap-3">
        <div className="hidden sm:flex items-center gap-2 text-xs text-muted-foreground">
          <span className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
            <span>Connected</span>
          </span>
        </div>

        {/* Mobile hamburger */}
        <button
          onClick={() => setMobileOpen((prev) => !prev)}
          className="md:hidden p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
        >
          {mobileOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
        </button>
      </div>

      {/* Mobile menu dropdown */}
      {mobileOpen && (
        <motion.div
          initial={{ opacity: 0, y: -5 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -5 }}
          className="absolute top-full left-0 right-0 bg-card border-b border-border shadow-lg p-2 md:hidden z-50"
        >
          {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
            const active = isActive(href);
            return (
              <Link
                key={href}
                href={href}
                onClick={() => setMobileOpen(false)}
                className={`flex items-center gap-2 px-3 py-2.5 text-sm rounded-md transition-colors ${
                  active
                    ? 'bg-primary text-primary-foreground font-medium'
                    : 'text-muted-foreground hover:text-foreground hover:bg-muted'
                }`}
              >
                <Icon className="w-4 h-4" />
                {label}
              </Link>
            );
          })}
        </motion.div>
      )}
    </nav>
  );
}
