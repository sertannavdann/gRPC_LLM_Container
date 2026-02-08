/**
 * Dashboard Context API
 * 
 * Fetches aggregated user data from the dashboard service.
 * Returns unified context with finance, calendar, health, and navigation data.
 * Finance data is fetched live from the dashboard_service bank endpoints.
 */
import { NextRequest, NextResponse } from 'next/server';

const DASHBOARD_SERVICE = process.env.DASHBOARD_SERVICE_URL || 'http://dashboard_service:8001';

// ---------- Real finance data fetcher ----------
async function fetchRealFinance(): Promise<any> {
  try {
    const [summaryRes, txnRes] = await Promise.all([
      fetch(`${DASHBOARD_SERVICE}/bank/summary?group_by=category`, { next: { revalidate: 60 } }),
      fetch(`${DASHBOARD_SERVICE}/bank/transactions?per_page=20&sort=timestamp&sort_dir=desc`, { next: { revalidate: 60 } }),
    ]);

    if (!summaryRes.ok || !txnRes.ok) throw new Error('Bank API unavailable');

    const summary = await summaryRes.json();
    const txnData = await txnRes.json();

    const totalExpenses = summary.groups
      .filter((g: any) => g.debits > 0)
      .reduce((s: number, g: any) => s + g.debits, 0);
    const totalIncome = summary.groups.reduce((s: number, g: any) => s + g.credits, 0);

    // Map transactions to canonical FinancialTransaction schema
    const transactions = txnData.transactions.map((t: any) => ({
      id: t.id || `bank:${t.timestamp}:${t.merchant}`,
      timestamp: t.timestamp,
      amount: t.metadata?.is_debit === false ? t.amount : -t.amount,
      currency: 'CAD',
      category: t.metadata?.spending_category || t.category || 'Other',
      merchant: t.merchant || 'Unknown',
      account_id: t.metadata?.account_type || 'unknown',
      pending: false,
      platform: 'cibc',
    }));

    return {
      transactions,
      recent_count: txnData.total || transactions.length,
      total_expenses_period: totalExpenses,
      total_income_period: totalIncome,
      net_cashflow: totalIncome - totalExpenses,
      platforms: ['cibc'],
    };
  } catch (err) {
    console.warn('[Dashboard API] Bank fetch failed, using fallback:', (err as Error).message);
    return null;
  }
}

// ---------- Mock fallback data ----------
const mockFinanceData = {
  transactions: Array.from({ length: 20 }, (_, i) => ({
    id: `mock:txn_${i}`,
    timestamp: new Date(Date.now() - i * 3600000 * 24).toISOString(),
    amount: Math.random() > 0.3 ? -(Math.random() * 100 + 10) : (Math.random() * 500 + 100),
    currency: 'CAD',
    category: Math.random() > 0.3 ? 'expense' : 'income',
    merchant: ['Starbucks', 'Amazon', 'Uber Eats', 'Costco', 'Netflix', 'Payroll'][Math.floor(Math.random() * 6)],
    account_id: 'mock_checking_001',
    pending: i === 0 && Math.random() > 0.7,
    platform: 'mock',
  })),
  recent_count: 20,
  total_expenses_period: 1543.21,
  total_income_period: 2500.00,
  net_cashflow: 956.79,
  platforms: ['mock'],
};

// Define event type for reuse
type CalendarEvent = {
  id: string;
  start_time: string;
  end_time: string;
  title: string;
  description: string | null;
  location: { latitude: number; longitude: number; address: string } | null;
  attendees: { name: string; email: string }[];
  status: string;
  event_type: string;
  urgency: string;
  platform: string;
};

type NavigationRoute = {
  id: string;
  origin: { latitude: number; longitude: number; address: string };
  destination: { latitude: number; longitude: number; address: string };
  distance_meters: number;
  distance_km: number;
  duration_seconds: number;
  duration_minutes: number;
  traffic_level: string;
  estimated_arrival: string;
  transport_mode: string;
  platform: string;
};

const mockCalendarData: {
  events: CalendarEvent[];
  next_3: CalendarEvent[];
  imminent: CalendarEvent[];
  today_count: number;
  platforms: string[];
} = {
  events: Array.from({ length: 10 }, (_, i) => {
    const startDate = new Date(Date.now() + i * 3600000 * (3 + Math.random() * 5));
    const endDate = new Date(startDate.getTime() + 3600000);
    return {
      id: `mock:event_${i}`,
      start_time: startDate.toISOString(),
      end_time: endDate.toISOString(),
      title: ['Team Standup', '1:1 with Manager', 'Sprint Planning', 'Deep Work', 'Lunch'][i % 5],
      description: null,
      location: i % 3 === 0 ? { latitude: 43.6532, longitude: -79.3832, address: 'Office' } : null,
      attendees: i % 2 === 0 ? [{ name: 'Alice', email: 'alice@example.com' }] : [],
      status: 'confirmed',
      event_type: i % 4 === 0 ? 'focus_time' : 'meeting',
      urgency: i === 0 ? 'HIGH' : i < 3 ? 'MEDIUM' : 'LOW',
      platform: 'mock',
    };
  }),
  next_3: [],
  imminent: [],
  today_count: 4,
  platforms: ['mock'],
};

const mockHealthData = {
  today: {
    steps: 6234,
    goal_steps: 10000,
    steps_progress: 0.6234,
    calories_burned: 1876,
    active_minutes: 32,
    current_heart_rate: 72,
    hrv: 48,
    sleep_last_night: 7.2,
    sleep_score: 78,
    readiness: 72,
  },
  steps: 6234,
  steps_goal: 10000,
  steps_progress: 0.6234,
  heart_rate: 72,
  hrv: 48,
  sleep_hours: 7.2,
  sleep_score: 78,
  readiness: 72,
  platforms: ['mock'],
};

const mockNavigationData: {
  routes: NavigationRoute[];
  primary_route: NavigationRoute | null;
  commute: Record<string, unknown>;
  platforms: string[];
} = {
  routes: [{
    id: 'mock:route_1',
    origin: { latitude: 43.6532, longitude: -79.3832, address: '123 Home St, Toronto' },
    destination: { latitude: 43.6510, longitude: -79.3470, address: '456 King St W, Toronto' },
    distance_meters: 4500,
    distance_km: 4.5,
    duration_seconds: 1200,
    duration_minutes: 20,
    traffic_level: 'moderate',
    estimated_arrival: new Date(Date.now() + 1200000).toISOString(),
    transport_mode: 'driving',
    platform: 'mock',
  }],
  primary_route: null,
  commute: {},
  platforms: ['mock'],
};

// GET - Fetch unified context
export async function GET(request: NextRequest) {
  try {
    const searchParams = request.nextUrl.searchParams;
    const category = searchParams.get('category');
    
    // Fetch real finance data, fall back to mock if service is unavailable
    const financeData = await fetchRealFinance() || mockFinanceData;
    
    // Set next_3 from events
    mockCalendarData.next_3 = mockCalendarData.events.slice(0, 3);
    mockCalendarData.imminent = mockCalendarData.events.filter(e => e.urgency === 'HIGH');
    mockNavigationData.primary_route = mockNavigationData.routes[0];
    
    // Build relevance classification
    const relevance = {
      high: [] as any[],
      medium: [] as any[],
      low: [] as any[],
    };
    
    // Calendar high priority (imminent events)
    mockCalendarData.imminent.forEach(event => {
      relevance.high.push({
        type: 'calendar',
        subtype: 'event',
        title: event.title,
        alert: 'Starting soon',
        priority: 100,
        data: event,
      });
    });
    
    // Health alerts
    if (mockHealthData.hrv && mockHealthData.hrv < 40) {
      relevance.high.push({
        type: 'health',
        subtype: 'hrv_alert',
        title: 'Low HRV',
        alert: `HRV is ${mockHealthData.hrv}ms`,
        priority: 75,
      });
    }
    
    // Traffic alerts
    if (mockNavigationData.primary_route?.traffic_level === 'heavy') {
      relevance.high.push({
        type: 'navigation',
        subtype: 'traffic',
        title: 'Heavy Traffic',
        alert: `${mockNavigationData.primary_route.duration_minutes} min to work`,
        priority: 65,
      });
    }
    
    // Medium priority items
    relevance.medium.push({
      type: 'health',
      subtype: 'steps',
      title: `Steps: ${Math.round(mockHealthData.steps_progress * 100)}% of goal`,
      priority: 35,
    });
    
    // If specific category requested
    if (category) {
      const categoryData: Record<string, any> = {
        finance: financeData,
        calendar: mockCalendarData,
        health: mockHealthData,
        navigation: mockNavigationData,
      };
      
      return NextResponse.json({
        [category]: categoryData[category] || {},
        last_updated: new Date().toISOString(),
      });
    }
    
    // Return full unified context
    const context = {
      user_id: 'demo_user',
      context: {
        finance: financeData,
        calendar: mockCalendarData,
        health: mockHealthData,
        navigation: mockNavigationData,
      },
      relevance,
      last_updated: {
        finance: new Date().toISOString(),
        calendar: new Date().toISOString(),
        health: new Date().toISOString(),
        navigation: new Date().toISOString(),
      },
    };
    
    return NextResponse.json(context);
    
  } catch (error: any) {
    console.error('[Dashboard API] Error:', error);
    return NextResponse.json(
      { error: error.message || 'Failed to fetch dashboard context' },
      { status: 500 }
    );
  }
}

// POST - Update user configuration
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    
    // In production, this would update user preferences
    // For now, just acknowledge
    
    return NextResponse.json({
      success: true,
      message: 'Configuration updated',
      config: body,
    });
    
  } catch (error: any) {
    console.error('[Dashboard API] Error:', error);
    return NextResponse.json(
      { error: error.message || 'Failed to update configuration' },
      { status: 500 }
    );
  }
}
