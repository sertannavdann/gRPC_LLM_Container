/**
 * TransactionTable Component
 *
 * Sortable transaction table with color-coded amounts and client-side pagination.
 * Columns: Date, Description, Amount, Category
 * - Green for positive amounts (credits)
 * - Red for negative amounts (debits)
 * - Pagination: 20 rows per page
 */

'use client';

import React, { useState, useMemo } from 'react';
import { ArrowUpDown, ArrowUp, ArrowDown, ChevronLeft, ChevronRight } from 'lucide-react';
import type { Transaction } from '@/machines/financePage';

interface TransactionTableProps {
  transactions: Transaction[];
}

type SortColumn = 'timestamp' | 'merchant' | 'amount' | 'category';
type SortDirection = 'asc' | 'desc';

const ROWS_PER_PAGE = 20;

export function TransactionTable({ transactions }: TransactionTableProps) {
  const [sortColumn, setSortColumn] = useState<SortColumn>('timestamp');
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc');
  const [currentPage, setCurrentPage] = useState(1);

  // Sort transactions
  const sortedTransactions = useMemo(() => {
    const sorted = [...transactions].sort((a, b) => {
      let aVal: any = a[sortColumn];
      let bVal: any = b[sortColumn];

      // Handle timestamp conversion
      if (sortColumn === 'timestamp') {
        aVal = new Date(a.timestamp).getTime();
        bVal = new Date(b.timestamp).getTime();
      }

      if (sortDirection === 'asc') {
        return aVal > bVal ? 1 : aVal < bVal ? -1 : 0;
      } else {
        return aVal < bVal ? 1 : aVal > bVal ? -1 : 0;
      }
    });

    return sorted;
  }, [transactions, sortColumn, sortDirection]);

  // Paginate
  const totalPages = Math.ceil(sortedTransactions.length / ROWS_PER_PAGE);
  const paginatedTransactions = useMemo(() => {
    const start = (currentPage - 1) * ROWS_PER_PAGE;
    const end = start + ROWS_PER_PAGE;
    return sortedTransactions.slice(start, end);
  }, [sortedTransactions, currentPage]);

  const handleSort = (column: SortColumn) => {
    if (sortColumn === column) {
      setSortDirection((prev) => (prev === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortColumn(column);
      setSortDirection('desc');
    }
  };

  const handlePageChange = (newPage: number) => {
    if (newPage >= 1 && newPage <= totalPages) {
      setCurrentPage(newPage);
    }
  };

  const SortIcon = ({ column }: { column: SortColumn }) => {
    if (sortColumn !== column) {
      return <ArrowUpDown className="h-4 w-4 opacity-40" />;
    }
    return sortDirection === 'asc' ? (
      <ArrowUp className="h-4 w-4" />
    ) : (
      <ArrowDown className="h-4 w-4" />
    );
  };

  if (transactions.length === 0) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        No transactions available
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {/* Table */}
      <div className="rounded-lg border border-border overflow-hidden">
        <table className="w-full">
          <thead className="bg-muted/50">
            <tr>
              <th className="text-left p-3 font-medium">
                <button
                  onClick={() => handleSort('timestamp')}
                  className="flex items-center gap-2 hover:text-foreground transition-colors"
                >
                  Date
                  <SortIcon column="timestamp" />
                </button>
              </th>
              <th className="text-left p-3 font-medium">
                <button
                  onClick={() => handleSort('merchant')}
                  className="flex items-center gap-2 hover:text-foreground transition-colors"
                >
                  Description
                  <SortIcon column="merchant" />
                </button>
              </th>
              <th className="text-right p-3 font-medium">
                <button
                  onClick={() => handleSort('amount')}
                  className="flex items-center justify-end gap-2 hover:text-foreground transition-colors ml-auto"
                >
                  Amount
                  <SortIcon column="amount" />
                </button>
              </th>
              <th className="text-left p-3 font-medium">
                <button
                  onClick={() => handleSort('category')}
                  className="flex items-center gap-2 hover:text-foreground transition-colors"
                >
                  Category
                  <SortIcon column="category" />
                </button>
              </th>
            </tr>
          </thead>
          <tbody>
            {paginatedTransactions.map((txn, idx) => (
              <tr
                key={txn.id}
                className={`border-t border-border hover:bg-muted/30 transition-colors ${
                  idx % 2 === 0 ? 'bg-card' : 'bg-muted/10'
                }`}
              >
                <td className="p-3 text-sm">
                  {new Date(txn.timestamp).toLocaleDateString('en-US', {
                    year: 'numeric',
                    month: 'short',
                    day: 'numeric',
                  })}
                </td>
                <td className="p-3 text-sm">{txn.merchant}</td>
                <td
                  className={`p-3 text-sm text-right font-semibold ${
                    txn.amount >= 0 ? 'text-green-500' : 'text-red-500'
                  }`}
                >
                  {txn.amount >= 0 ? '+' : ''}
                  {txn.currency} ${Math.abs(txn.amount).toFixed(2)}
                </td>
                <td className="p-3 text-sm">
                  <span className="px-2 py-1 rounded-md bg-muted text-xs font-medium">
                    {txn.category}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <div>
            Showing {(currentPage - 1) * ROWS_PER_PAGE + 1} to{' '}
            {Math.min(currentPage * ROWS_PER_PAGE, sortedTransactions.length)} of{' '}
            {sortedTransactions.length} transactions
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => handlePageChange(currentPage - 1)}
              disabled={currentPage === 1}
              className="p-2 rounded-md border border-border hover:bg-muted disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <div className="px-3 py-1">
              Page {currentPage} of {totalPages}
            </div>
            <button
              onClick={() => handlePageChange(currentPage + 1)}
              disabled={currentPage === totalPages}
              className="p-2 rounded-md border border-border hover:bg-muted disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
