/**
 * Finance Widget
 * 
 * Displays financial overview and recent transactions.
 * Shows net cashflow and spending categories.
 */
'use client';

import React from 'react';
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
  Clock
} from 'lucide-react';

interface FinanceWidgetProps {
  data: FinanceContext | null;
  expanded?: boolean;
  onFocus?: () => void;
  onCollapse?: () => void;
}

export function FinanceWidget({ data, expanded, onFocus, onCollapse }: FinanceWidgetProps) {
  if (!data) {
    return (
      <div className="bg-gray-800 rounded-xl p-4 animate-pulse">
        <div className="h-6 bg-gray-700 rounded w-1/3 mb-4"></div>
        <div className="grid grid-cols-3 gap-3 mb-4">
          <div className="h-16 bg-gray-700 rounded"></div>
          <div className="h-16 bg-gray-700 rounded"></div>
          <div className="h-16 bg-gray-700 rounded"></div>
        </div>
        <div className="space-y-2">
          <div className="h-10 bg-gray-700 rounded"></div>
          <div className="h-10 bg-gray-700 rounded"></div>
        </div>
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
  
  const getCategoryIcon = (category: string, amount: number) => {
    if (amount > 0) {
      return <ArrowDownRight className="w-4 h-4 text-green-400" />;
    }
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
            {txn.pending && (
              <span className="flex items-center gap-1 text-yellow-400">
                <Clock className="w-3 h-3" />
                Pending
              </span>
            )}
          </div>
        </div>
      </div>
      <span className={`font-medium text-sm ${txn.amount > 0 ? 'text-green-400' : 'text-white'}`}>
        {txn.amount > 0 ? '+' : ''}{formatCurrency(txn.amount, txn.currency)}
      </span>
    </div>
  );
  
  const isPositiveCashflow = data.net_cashflow >= 0;
  
  return (
    <div className={`bg-gray-800 rounded-xl p-4 ${expanded ? 'h-full' : ''}`}>
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <DollarSign className="w-5 h-5 text-green-400" />
          <h3 className="font-semibold">Finance</h3>
        </div>
        
        <div className="flex items-center gap-2">
          {expanded ? (
            <button 
              onClick={onCollapse}
              className="p-1 hover:bg-gray-700 rounded transition-colors"
            >
              <Minimize2 className="w-4 h-4 text-gray-400" />
            </button>
          ) : (
            <button 
              onClick={onFocus}
              className="p-1 hover:bg-gray-700 rounded transition-colors"
            >
              <Maximize2 className="w-4 h-4 text-gray-400" />
            </button>
          )}
        </div>
      </div>
      
      {/* Summary Cards */}
      <div className="grid grid-cols-3 gap-3 mb-4">
        <div className="bg-gray-700/50 rounded-lg p-3">
          <div className="flex items-center gap-1 text-xs text-gray-400 mb-1">
            <TrendingUp className="w-3 h-3" />
            Income
          </div>
          <p className="font-semibold text-green-400">
            {formatCurrency(data.total_income_period)}
          </p>
        </div>
        
        <div className="bg-gray-700/50 rounded-lg p-3">
          <div className="flex items-center gap-1 text-xs text-gray-400 mb-1">
            <TrendingDown className="w-3 h-3" />
            Expenses
          </div>
          <p className="font-semibold text-red-400">
            {formatCurrency(data.total_expenses_period)}
          </p>
        </div>
        
        <div className={`rounded-lg p-3 ${isPositiveCashflow ? 'bg-green-500/10' : 'bg-red-500/10'}`}>
          <div className="flex items-center gap-1 text-xs text-gray-400 mb-1">
            <CreditCard className="w-3 h-3" />
            Net
          </div>
          <p className={`font-semibold ${isPositiveCashflow ? 'text-green-400' : 'text-red-400'}`}>
            {isPositiveCashflow ? '+' : ''}{formatCurrency(data.net_cashflow)}
          </p>
        </div>
      </div>
      
      {/* Transactions List */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <h4 className="text-sm text-gray-400">Recent Transactions</h4>
          <span className="text-xs text-gray-500">{data.recent_count} total</span>
        </div>
        
        <div className={`${expanded ? 'overflow-auto max-h-[calc(100vh-320px)]' : ''}`}>
          {data.transactions.slice(0, expanded ? undefined : 4).map(txn => (
            <TransactionRow key={txn.id} txn={txn} />
          ))}
        </div>
      </div>
      
      {/* Footer - show more link */}
      {!expanded && data.transactions.length > 4 && (
        <button 
          onClick={onFocus}
          className="flex items-center justify-center gap-1 w-full mt-3 py-2 text-xs text-gray-400 hover:text-white transition-colors"
        >
          <span>View all transactions</span>
          <ChevronRight className="w-3 h-3" />
        </button>
      )}
    </div>
  );
}
