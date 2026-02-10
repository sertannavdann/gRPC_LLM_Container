/**
 * Finance API Route — with filter support
 *
 * Proxies to dashboard_service /bank/* endpoints with optional filters.
 * Used by the FinanceWidget expanded view for filtering transactions.
 */
import { NextRequest, NextResponse } from 'next/server';

const DASHBOARD_SERVICE = process.env.DASHBOARD_SERVICE_URL || 'http://dashboard:8001';

export async function GET(request: NextRequest) {
  try {
    const sp = request.nextUrl.searchParams;

    // Build filter query params for both bank endpoints
    const filterParams = new URLSearchParams();
    if (sp.get('category'))  filterParams.set('category', sp.get('category')!);
    if (sp.get('account'))   filterParams.set('account', sp.get('account')!);
    if (sp.get('date_from')) filterParams.set('date_from', sp.get('date_from')!);
    if (sp.get('date_to'))   filterParams.set('date_to', sp.get('date_to')!);
    if (sp.get('search'))    filterParams.set('search', sp.get('search')!);

    const summaryParams = new URLSearchParams(filterParams);
    summaryParams.set('group_by', sp.get('group_by') || 'category');

    const txnParams = new URLSearchParams(filterParams);
    txnParams.set('per_page', sp.get('per_page') || '50');
    txnParams.set('sort', sp.get('sort') || 'timestamp');
    txnParams.set('sort_dir', sp.get('sort_dir') || 'desc');
    txnParams.set('page', sp.get('page') || '1');

    const [summaryRes, txnRes, catRes] = await Promise.all([
      fetch(`${DASHBOARD_SERVICE}/bank/summary?${summaryParams}`, { cache: 'no-store' }),
      fetch(`${DASHBOARD_SERVICE}/bank/transactions?${txnParams}`, { cache: 'no-store' }),
      fetch(`${DASHBOARD_SERVICE}/bank/categories`, { next: { revalidate: 300 } }),
    ]);

    if (!summaryRes.ok || !txnRes.ok) {
      throw new Error('Bank API unavailable');
    }

    const summary = await summaryRes.json();
    const txnData = await txnRes.json();
    const categories = catRes.ok ? await catRes.json() : { categories: [] };

    const totalExpenses = summary.groups
      .filter((g: any) => g.debits > 0)
      .reduce((s: number, g: any) => s + g.debits, 0);
    const totalIncome = summary.groups.reduce((s: number, g: any) => s + g.credits, 0);

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

    return NextResponse.json({
      transactions,
      recent_count: txnData.total || transactions.length,
      total_expenses_period: totalExpenses,
      total_income_period: totalIncome,
      net_cashflow: totalIncome - totalExpenses,
      platforms: ['cibc'],
      page: txnData.page || 1,
      total_pages: txnData.total_pages || 1,
      available_categories: categories.categories || [],
      filters_applied: {
        category: sp.get('category') || null,
        account: sp.get('account') || null,
        date_from: sp.get('date_from') || null,
        date_to: sp.get('date_to') || null,
        search: sp.get('search') || null,
      },
    });
  } catch (error: any) {
    console.error('[Finance API] Error:', error);
    return NextResponse.json(
      { error: error.message || 'Failed to fetch finance data' },
      { status: 500 }
    );
  }
}
