import Link from 'next/link';
import {
  Bot,
  LayoutDashboard,
  DollarSign,
  Activity,
  ArrowRight,
  Sparkles,
  Brain,
  Zap,
} from 'lucide-react';

const PAGES = [
  {
    href: '/chat',
    label: 'AI Chat',
    desc: 'Multi-provider LLM orchestrator with tool use, conversation history, and smart summarization.',
    icon: Bot,
    color: 'from-blue-600 to-cyan-500',
    badge: 'gRPC',
  },
  {
    href: '/dashboard',
    label: 'Dashboard',
    desc: 'Unified dashboard with finance, calendar, health, and navigation widgets. Supports grid, row, and column layouts.',
    icon: LayoutDashboard,
    color: 'from-purple-600 to-pink-500',
    badge: 'Live',
  },
  {
    href: '/finance',
    label: 'Finance',
    desc: 'Interactive finance dashboard with category charts, monthly trends, top merchants, and full transaction explorer.',
    icon: DollarSign,
    color: 'from-green-600 to-emerald-500',
    badge: 'Bank Data',
  },
  {
    href: '/monitoring',
    label: 'Monitoring',
    desc: 'Grafana dashboards with Prometheus metrics, OpenTelemetry traces, and service health overview.',
    icon: Activity,
    color: 'from-orange-600 to-amber-500',
    badge: 'OTel',
  },
] as const;

export default function Home() {
  return (
    <div className="h-full overflow-auto bg-background">
      {/* Hero */}
      <section className="relative flex flex-col items-center justify-center px-6 pt-16 pb-12 text-center">
        <div className="flex items-center gap-2 mb-4 text-primary">
          <Brain className="w-10 h-10" />
          <Zap className="w-6 h-6 text-amber-400" />
          <Sparkles className="w-8 h-8 text-purple-400" />
        </div>
        <h1 className="text-4xl sm:text-5xl font-bold tracking-tight mb-4 bg-gradient-to-r from-blue-400 via-purple-400 to-green-400 bg-clip-text text-transparent">
          gRPC LLM Agent
        </h1>
        <p className="max-w-2xl text-lg text-muted-foreground leading-relaxed">
          A multi-provider AI orchestration platform with real-time finance analytics,
          health metrics, and full observability — powered by gRPC microservices.
        </p>
      </section>

      {/* Page Cards */}
      <section className="max-w-5xl mx-auto px-6 pb-16 grid grid-cols-1 sm:grid-cols-2 gap-6">
        {PAGES.map(({ href, label, desc, icon: Icon, color, badge }) => (
          <Link
            key={href}
            href={href}
            className="group relative flex flex-col p-6 rounded-2xl border border-border bg-card hover:border-primary/40 transition-all duration-300 hover:shadow-lg hover:shadow-primary/5"
          >
            {/* Badge */}
            <span className="absolute top-4 right-4 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider rounded-full bg-muted text-muted-foreground">
              {badge}
            </span>

            {/* Icon */}
            <div className={`flex items-center justify-center w-12 h-12 rounded-xl bg-gradient-to-br ${color} mb-4`}>
              <Icon className="w-6 h-6 text-white" />
            </div>

            {/* Text */}
            <h2 className="text-xl font-semibold mb-2 group-hover:text-primary transition-colors">
              {label}
            </h2>
            <p className="text-sm text-muted-foreground leading-relaxed flex-1">
              {desc}
            </p>

            {/* Arrow */}
            <div className="flex items-center gap-1 mt-4 text-sm font-medium text-primary opacity-0 group-hover:opacity-100 transition-opacity">
              Open <ArrowRight className="w-4 h-4" />
            </div>
          </Link>
        ))}
      </section>
    </div>
  );
}
