/**
 * Dashboard Types
 * 
 * TypeScript types for the dashboard data structure.
 */

// Canonical schema types
export interface FinancialTransaction {
  id: string;
  timestamp: string;
  amount: number;
  currency: string;
  category: string;
  merchant: string;
  account_id: string;
  pending: boolean;
  platform: string;
}

export interface FinanceContext {
  transactions: FinancialTransaction[];
  recent_count: number;
  total_expenses_period: number;
  total_income_period: number;
  net_cashflow: number;
  platforms: string[];
}

export interface CalendarEvent {
  id: string;
  start_time: string;
  end_time: string;
  title: string;
  description: string | null;
  location: { latitude: number; longitude: number; address: string } | null;
  attendees: { name: string; email: string }[];
  status: string;
  event_type: string;
  urgency: 'HIGH' | 'MEDIUM' | 'LOW';
  platform: string;
}

export interface CalendarContext {
  events: CalendarEvent[];
  next_3: CalendarEvent[];
  imminent: CalendarEvent[];
  today_count: number;
  platforms: string[];
}

export interface HealthToday {
  steps: number;
  goal_steps: number;
  steps_progress: number;
  calories_burned: number;
  active_minutes: number;
  current_heart_rate: number;
  hrv: number;
  sleep_last_night: number;
  sleep_score: number;
  readiness: number;
}

export interface HealthContext {
  today: HealthToday;
  steps: number;
  steps_goal: number;
  steps_progress: number;
  heart_rate: number;
  hrv: number;
  sleep_hours: number;
  sleep_score: number;
  readiness: number;
  platforms: string[];
}

export interface NavigationRoute {
  id: string;
  origin: { latitude: number; longitude: number; address: string };
  destination: { latitude: number; longitude: number; address: string };
  distance_meters: number;
  distance_km: number;
  duration_seconds: number;
  duration_minutes: number;
  traffic_level: 'light' | 'moderate' | 'heavy';
  estimated_arrival: string;
  transport_mode: string;
  platform: string;
}

export interface NavigationContext {
  routes: NavigationRoute[];
  primary_route: NavigationRoute | null;
  commute: Record<string, unknown>;
  platforms: string[];
}

export interface RelevanceItem {
  type: string;
  subtype: string;
  title: string;
  alert?: string;
  priority: number;
  data?: unknown;
}

export interface RelevanceClassification {
  high: RelevanceItem[];
  medium: RelevanceItem[];
  low: RelevanceItem[];
}

export interface DashboardContext {
  user_id: string;
  context: {
    finance: FinanceContext;
    calendar: CalendarContext;
    health: HealthContext;
    navigation: NavigationContext;
  };
  relevance: RelevanceClassification;
  last_updated: {
    finance: string;
    calendar: string;
    health: string;
    navigation: string;
  };
}

// Adapter types
export interface Adapter {
  platform: string;
  name: string;
  icon: string;
  connected: boolean;
  status: 'active' | 'available' | 'error';
}

export interface AdapterCategory {
  category: string;
  icon: string;
  adapters: Adapter[];
  connected_count: number;
}

export interface AdaptersResponse {
  categories: AdapterCategory[];
  total_connected: number;
  total_available: number;
}
