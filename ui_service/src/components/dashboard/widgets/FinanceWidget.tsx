/**
 * Finance Widget
 * 
 * Displays financial overview and recent transactions.
 * When expanded, shows filter controls (category, date range, search)
 * and a link to the full interactive finance dashboard.
 */
'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { FinanceContext, FinancialTransaction } from '@/types/dashboard';
import { 
  DollarSign, 
  TrendingUp, 
  TrendingDown, 
  ArrowUpRight,
  ArrowDownRight,
  CreditCard,
  Maximize2,
  Minimize2,
  ChevronRight,
  Clock,
  Search,
  Filter,
  ExternalLink,
  X,
  Loader2,
} from 'lucide-react';

interface FinanceWidgetProps {
  data: FinanceContext | null;
  expanded?: boolean;
  onFocus?: () => void;
  onCollapse?: () => void;
}

interface FinanceFilters {
  category: string;
  date_from: string;
  date_to: string;
  search: string;
}

const FINANCE_URL = typeof window !== 'undefined'
  ? `${window.location.protocol}//${window.location.hostname}:8001`
  : 'http://localhost:8001';

export function FinanceWidget({ data, expanded, onFocus, onCollapse }: FinanceWidgetProps) {
  const [filters, setFilters] = useState<FinanceFilters>({ category: '', date_from: '', date_to: '', search: '' });
  const [filteredData, setFilteredData] = useState<any>(null);
  const [filterLoading, setFilterLoading] = useState(false);
  const [categories, setCategories] = useState<string[]>([]);
  const [showFilters, setShowFilters] = useState(false);

  // Fetch filtered data when filters change (only in expanded mode)
  const fetchFiltered = useCallback(async () => {
    const hasFilters = filters.category || filters.date_from || filters.date_to || filters.search;
    if (!expanded || !hasFilters) {
      setFilteredData(null);
      return;
    }
    setFilterLoading(true);
    try {
      const params = new URLSearchParams();
      if (filters.category)  params.set('category', filters.category);
      if (filters.date_from) params.set('date_from', filters.date_from);
      if (filters.date_to)   params.set('date_to', filters.date_to);
      if (filters.search)    params.set('search', filters.search);
      const res = await fetch(`/api/dashboard/finance?${params}`);
      if (res.ok) {
        const json = await res.json();
        setFilteredData(json);
        if (json.available_categories?.length) {
          setCategories(json.available_categories.map((c: any) => c.category || c.name || c));
        }
      }
    } catch (err) {
      console.error('[FinanceWidget] Filter fetch failed:', err);
    } finally {
      setFilterLoading(false);
    }
  }, [filters, expanded]);

  // Fetch categories on mount when expanded
  useEffect(() => {
    if (expanded && categories.length === 0) {
      fetch('/api/dashboard/finance')
        .then(r => r.ok ? r.json() : null)
        .then(d => {
          if (d?.available_categories?.length) {
            setCategories(d.available_categories.map((c: any) => c.category || c.name || c));
          }
        })
        .catch(() => {});
    }
  }, [expanded, categories.length]);

  // Debounced filter fetch
  useEffect(() => {
    const timer = setTimeout(fetchFiltered, 400);
    return () => clearTimeout(timer);
  }, [fetchFiltered]);

  // Reset filters when collapsing
  useEffect(() => {
    if (!expanded) {
      setFilters({ category: '', date_from: '', date_to: '', search: '' });
      setFilteredData(null);
      setShowFilters(false);
    }
  }, [expanded]);

  const displayData = filteredData || data;

  if (!displayData) {
    return (
      <div className="bg-gray-800 rounded-xl p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <DollarSign className="w-4 h-4 text-green-400" />
            <span className="font-medium text-sm">Finance</span>
          </div>
        </div>
        <p className="text-sm text-gray-500 text-center py-6">
          No finance data available. CIBC bank data loads automatically.
        </p>
      </div>
    );
  }
  
  const formatCurrency = (amount: number, currency = 'CAD') => {
    return new Intl.NumberFormat('en-CA', {
      style: 'currency',
      currency,
      minimumFractionDigits: 0,
      maximumFractionDigits: 2,
    }).format(amount);
  };
  
  const formatDate = (isoString: string) => {
    const date = new Date(isoString);
    const today = new Date();
    if (date.toDateString() === today.toDateString()) return 'Today';
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);
    if (date.toDateString() === yesterday.toDateString()) return 'Yesterday';
    return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
  };
  
  const getCategoryIcon = (_category: string, amount: number) => {
    if (amount > 0) return <ArrowDownRight className="w-4 h-4 text-green-400" />;
    return <ArrowUpRight className="w-4 h-4 text-red-400" />;
  };
  
  const TransactionRow = ({ txn }: { txn: FinancialTransaction }) => (
    <div className="flex items-center justify-between py-2 border-b border-gray-700/50 last:border-0">
      <div className="flex items-center gap-3 min-w-0">
        <div className={`p-2 rounded-lg ${txn.amount > 0 ? 'bg-green-500/10' : 'bg-gray-700'}`}>
          {getCategoryIcon(txn.category, txn.amount)}
        </div>
        <div className="min-w-0">
          <p className="font-medium text-sm truncate">{txn.merchant}</p>
          <div className="flex items-center gap-2 text-xs text-gray-500">
            <span>{formatDate(txn.timestamp)}</span>
            <span className="px-1.5 py-0.5 bg-gray-700 rounded text-[10px]">{txn.category}</span>
            {txn.pending && (
              <span className="flex items-center gap-1 text-yellow-400">
                <Clock className="w-3 h-3" />
                Pending
              </span>
            )}
          </div>
        </div>
      </div>
      <span className={`font-medium text-sm whitespace-nowrap ${txn.amount > 0 ? 'text-green-400' : 'text-white'}`}>
        {txn.amount > 0 ? '+' : ''}{formatCurrency(txn.amount, txn.currency)}
      </span>
    </div>
  );

  const hasActiveFilters = filters.category || filters.date_from || filters.date_to || filters.search;
  const isPositiveCashflow = displayData.net_cashflow >= 0;
  
  return (
    <div className={`bg-gray-800 rounded-xl p-4 ${expanded ? 'h-full flex flex-col' : ''}`}>
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <DollarSign className="w-5 h-5 text-green-400" />
          <h3 className="font-semibold">Finance</h3>
          {filterLoading && <Loader2 className="w-3.5 h-3.5 animate-spin text-gray-400" />}
        </div>
        
        <div className="flex items-center gap-2">
          {/* Full Finance Dashboard link */}
          <a
            href={FINANCE_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 px-2 py-1 text-xs text-gray-400 hover:text-white hover:bg-gray-700 rounded-lg transition-colors"
            title="Open full Finance Dashboard"
          >
            <ExternalLink className="w-3.5 h-3.5" />
            {expanded && <span>Full Dashboard</span>}
          </a>

          {/* Filter toggle (expanded only) */}
          {expanded && (
            <button
              onClick={() => setShowFilters(v => !v)}
              className={`p-1.5 rounded-lg transition-colors ${
                showFilters || hasActiveFilters
                  ? 'bg-green-600 text-white'
                  : 'hover:bg-gray-700 text-gray-400'
              }`}
              title="Toggle Filters"
            >
              <Filter className="w-4 h-4" />
            </button>
          )}

          {expanded ? (
            <button onClick={onCollapse} className="p-1 hover:bg-gray-700 rounded transition-colors">
              <Minimize2 className="w-4 h-4 text-gray-400" />
            </button>
          ) : (
            <button onClick={onFocus} className="p-1 hover:bg-gray-700 rounded transition-colors">
              <Maximize2 className="w-4 h-4 text-gray-400" />
            </button>
          )}
        </div>
      </div>

      {/* Filter Bar (expanded only) */}
      {expanded && showFilters && (
        <div className="mb-4 p-3 bg-gray-700/50 rounded-lg space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-gray-400 uppercase tracking-wider">Filters</span>
            {hasActiveFilters && (
              <button
                onClick={() => setFilters({ category: '', date_from: '', date_to: '', search: '' })}
                className="flex items-center gap-1 text-xs text-gray-400 hover:text-white transition-colors"
              >
                <X className="w-3 h-3" /> Clear all
              </button>
            )}
          </div>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            {/* Category dropdown */}
            <div>
              <label className="block text-[10px] text-gray-500 mb-1 uppercase">Category</label>
              <select
                value={filters.category}
                onChange={(e) => setFilters(f => ({ ...f, category: e.target.value }))}
                className="w-full px-2 py-1.5 text-xs bg-gray-800 border border-gray-600 rounded-md text-white focus:ring-1 focus:ring-green-500 outline-none"
              >
                <option value="">All Categories</option>
                {categories.map(cat => (
                  <option key={cat} value={cat}>{cat}</option>
                ))}
              </select>
            </div>
            {/* Date from */}
            <div>
              <label className="block text-[10px] text-gray-500 mb-1 uppercase">From Date</label>
              <input
                type="date"
                value={filters.date_from}
                onChange={(e) => setFilters(f => ({ ...f, date_from: e.target.value }))}
                className="w-full px-2 py-1.5 text-xs bg-gray-800 border border-gray-600 rounded-md text-white focus:ring-1 focus:ring-green-500 outline-none"
              />
            </div>
            {/* Date to */}
            <div>
              <label className="block text-[10px] text-gray-500 mb-1 uppercase">To Date</label>
              <input
                type="date"
                value={filters.date_to}
                onChange={(e) => setFilters(f => ({ ...f, date_to: e.target.value }))}
                className="w-full px-2 py-1.5 text-xs bg-gray-800 border border-gray-600 rounded-md text-white focus:ring-1 focus:ring-green-500 outline-none"
              />
            </div>
            {/* Search */}
            <div>
              <label className="block text-[10px] text-gray-500 mb-1 uppercase">Search</label>
              <div className="relative">
                <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3 text-gray-500" />
                <input
                  type="text"
                  value={filters.search}
                  onChange={(e) => setFilters(f => ({ ...f, search: e.target.value }))}
                  placeholder="Merchant, description..."
                  className="w-full pl-7 pr-2 py-1.5 text-xs bg-gray-800 border border-gray-600 rounded-md text-white focus:ring-1 focus:ring-green-500 outline-none placeholder:text-gray-600"
                />
              </div>
            </div>
          </div>
          {hasActiveFilters && (
            <div className="flex items-center gap-1 text-[10px] text-gray-500">
              <Filter className="w-3 h-3" />
              Showing filtered results • {displayData.recent_count || 0} transactions
            </div>
          )}
        </div>
      )}
      
      {/* Summary Cards */}
      <div className="grid grid-cols-3 gap-3 mb-4">
        <div className="bg-gray-700/50 rounded-lg p-3">
          <div className="flex items-center gap-1 text-xs text-gray-400 mb-1">
            <TrendingUp className="w-3 h-3" />
            Income
          </div>
          <p className="font-semibold text-green-400">
            {formatCurrency(displayData.total_income_period)}
          </p>
        </div>
        
        <div className="bg-gray-700/50 rounded-lg p-3">
          <div className="flex items-center gap-1 text-xs text-gray-400 mb-1">
            <TrendingDown className="w-3 h-3" />
            Expenses
          </div>
          <p className="font-semibold text-red-400">
            {formatCurrency(displayData.total_expenses_period)}
          </p>
        </div>
        
        <div className={`rounded-lg p-3 ${isPositiveCashflow ? 'bg-green-500/10' : 'bg-red-500/10'}`}>
          <div className="flex items-center gap-1 text-xs text-gray-400 mb-1">
            <CreditCard className="w-3 h-3" />
            Net
          </div>
          <p className={`font-semibold ${isPositiveCashflow ? 'text-green-400' : 'text-red-400'}`}>
            {isPositiveCashflow ? '+' : ''}{formatCurrency(displayData.net_cashflow)}
          </p>
        </div>
      </div>
      
      {/* Transactions List */}
      <div className={expanded ? 'flex-1 flex flex-col min-h-0' : ''}>
        <div className="flex items-center justify-between mb-2">
          <h4 className="text-sm text-gray-400">Recent Transactions</h4>
          <span className="text-xs text-gray-500">{displayData.recent_count} total</span>
        </div>
        
        <div className={`${expanded ? 'overflow-auto flex-1' : ''}`}>
          {(displayData.transactions || []).slice(0, expanded ? undefined : 4).map((txn: FinancialTransaction) => (
            <TransactionRow key={txn.id} txn={txn} />
          ))}
          {(displayData.transactions || []).length === 0 && (
            <p className="text-sm text-gray-500 text-center py-4">No transactions match your filters.</p>
          )}
        </div>
      </div>
      
      {/* Footer */}
      {!expanded && (
        <div className="flex items-center justify-between mt-3 pt-3 border-t border-gray-700/50">
          {(data?.transactions || []).length > 4 && (
            <button 
              onClick={onFocus}
              className="flex items-center gap-1 text-xs text-gray-400 hover:text-white transition-colors"
            >
              <span>View all & filter</span>
              <ChevronRight className="w-3 h-3" />
            </button>
          )}
          <a
            href={FINANCE_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 text-xs text-gray-400 hover:text-green-400 transition-colors ml-auto"
          >
            <ExternalLink className="w-3 h-3" />
            Full Dashboard
          </a>
        </div>
      )}
    </div>
  );
}
