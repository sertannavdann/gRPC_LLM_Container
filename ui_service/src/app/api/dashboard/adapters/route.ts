/**
 * Dashboard Adapters API
 * 
 * Lists available adapters and manages adapter connections.
 */
import { NextRequest, NextResponse } from 'next/server';

// Available adapters registry
const AVAILABLE_ADAPTERS = {
  finance: [
    { platform: 'cibc', name: 'CIBC', icon: '🏛️', connected: true, status: 'active' },
    { platform: 'wealthsimple', name: 'Wealthsimple', icon: '💹', connected: false, status: 'available' },
    { platform: 'affirm', name: 'Affirm', icon: '💳', connected: false, status: 'available' },
    { platform: 'plaid', name: 'Plaid', icon: '🔗', connected: false, status: 'available' },
  ],
  calendar: [
    { platform: 'mock', name: 'Mock Calendar', icon: '📅', connected: true, status: 'active' },
    { platform: 'google', name: 'Google Calendar', icon: '📆', connected: false, status: 'available' },
    { platform: 'apple', name: 'Apple Calendar', icon: '🍎', connected: false, status: 'available' },
    { platform: 'outlook', name: 'Outlook', icon: '📧', connected: false, status: 'available' },
  ],
  health: [
    { platform: 'mock', name: 'Mock Health', icon: '❤️', connected: true, status: 'active' },
    { platform: 'apple_health', name: 'Apple Health', icon: '🍎', connected: false, status: 'available' },
    { platform: 'oura', name: 'Oura Ring', icon: '💍', connected: false, status: 'available' },
    { platform: 'whoop', name: 'Whoop', icon: '⌚', connected: false, status: 'available' },
    { platform: 'fitbit', name: 'Fitbit', icon: '🏃', connected: false, status: 'available' },
    { platform: 'garmin', name: 'Garmin', icon: '⌚', connected: false, status: 'available' },
  ],
  navigation: [
    { platform: 'mock', name: 'Mock Navigation', icon: '🗺️', connected: true, status: 'active' },
    { platform: 'google_maps', name: 'Google Maps', icon: '📍', connected: false, status: 'available' },
    { platform: 'apple_maps', name: 'Apple Maps', icon: '🍎', connected: false, status: 'available' },
    { platform: 'waze', name: 'Waze', icon: '🚗', connected: false, status: 'available' },
  ],
};

// GET - List available adapters
export async function GET(request: NextRequest) {
  try {
    const searchParams = request.nextUrl.searchParams;
    const category = searchParams.get('category');
    
    if (category && category in AVAILABLE_ADAPTERS) {
      return NextResponse.json({
        category,
        adapters: AVAILABLE_ADAPTERS[category as keyof typeof AVAILABLE_ADAPTERS],
      });
    }
    
    // Return all adapters
    const allAdapters = Object.entries(AVAILABLE_ADAPTERS).map(([category, adapters]) => ({
      category,
      icon: { finance: '💰', calendar: '📅', health: '❤️', navigation: '🗺️' }[category] || '📦',
      adapters,
      connected_count: adapters.filter(a => a.connected).length,
    }));
    
    return NextResponse.json({
      categories: allAdapters,
      total_connected: allAdapters.reduce((sum, cat) => sum + cat.connected_count, 0),
      total_available: Object.values(AVAILABLE_ADAPTERS).flat().length,
    });
    
  } catch (error: any) {
    console.error('[Adapters API] Error:', error);
    return NextResponse.json(
      { error: error.message || 'Failed to list adapters' },
      { status: 500 }
    );
  }
}

// POST - Connect/disconnect adapter
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { category, platform, action, credentials } = body;
    
    if (!category || !platform || !action) {
      return NextResponse.json(
        { error: 'Missing required fields: category, platform, action' },
        { status: 400 }
      );
    }
    
    if (!['connect', 'disconnect'].includes(action)) {
      return NextResponse.json(
        { error: 'Invalid action. Must be "connect" or "disconnect"' },
        { status: 400 }
      );
    }
    
    // In production, this would:
    // 1. Validate credentials if connecting
    // 2. Store in secure credential store
    // 3. Test connection to platform
    // 4. Update user's adapter configuration
    
    // For now, simulate the action
    const response = {
      success: true,
      action,
      category,
      platform,
      message: action === 'connect' 
        ? `Successfully connected ${platform} adapter`
        : `Disconnected ${platform} adapter`,
      // Would return OAuth URL for real integrations
      oauth_url: action === 'connect' && !credentials 
        ? `https://oauth.example.com/${platform}/authorize?redirect_uri=...`
        : null,
    };
    
    return NextResponse.json(response);
    
  } catch (error: any) {
    console.error('[Adapters API] Error:', error);
    return NextResponse.json(
      { error: error.message || 'Failed to update adapter' },
      { status: 500 }
    );
  }
}
