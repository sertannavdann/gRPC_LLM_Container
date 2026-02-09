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

// Weather types
export interface WeatherData {
  id: string;
  timestamp: string;
  temperature_celsius: number;
  feels_like_celsius: number;
  temperature_fahrenheit: number;
  humidity: number;
  pressure_hpa: number;
  wind_speed_ms: number;
  wind_speed_kmh: number;
  wind_direction_deg: number;
  condition: string;
  description: string;
  icon_code: string;
  visibility_meters: number;
  clouds_percent: number;
  uv_index: number | null;
  precipitation_mm: number | null;
  platform: string;
  metadata: Record<string, unknown>;
}

export interface WeatherForecast {
  id: string;
  forecast_time: string;
  temperature_celsius: number;
  feels_like_celsius: number;
  condition: string;
  description: string;
  precipitation_probability: number;
  precipitation_mm: number;
  humidity: number;
  wind_speed_ms: number;
  platform: string;
}

export interface WeatherContext {
  current: WeatherData | null;
  forecasts: WeatherForecast[];
  platforms: string[];
}

// Gaming types
export interface GamingProfile {
  id: string;
  username: string;
  platform_tag: string;
  level: number;
  trophies: number;
  wins: number;
  losses: number;
  games_played: number;
  win_rate: number;
  clan_name: string | null;
  clan_tag: string | null;
  arena: string | null;
  platform: string;
  metadata: Record<string, unknown>;
}

export interface GamingMatch {
  id: string;
  timestamp: string;
  game_type: string;
  result: string;
  trophies_change: number;
  opponent_tag: string | null;
  opponent_name: string | null;
  duration_seconds: number | null;
  platform: string;
}

export interface GamingContext {
  profiles: GamingProfile[];
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
    weather: WeatherContext;
    gaming: GamingContext;
  };
  relevance: RelevanceClassification;
  last_updated: {
    finance: string;
    calendar: string;
    health: string;
    navigation: string;
    weather?: string;
    gaming?: string;
  };
}

// Adapter types
export interface AdapterAuthField {
  key: string;
  label: string;
  placeholder: string;
  type: 'api_key' | 'oauth_token' | 'text';
  envVar: string;
}

export interface Adapter {
  platform: string;
  name: string;
  icon: string;
  connected: boolean;
  status: 'active' | 'available' | 'error';
  auth_type?: 'api_key' | 'oauth2' | 'none';
  auth_fields?: AdapterAuthField[];
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
