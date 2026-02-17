/**
 * SpendingChart Component
 *
 * Recharts-based financial data visualization:
 * - SpendingChart: LineChart showing spending trend over time
 * - CategoryBreakdown: PieChart (donut) showing category distribution
 *
 * Uses ResponsiveContainer with initialDimension for SSR compatibility.
 * Supports dark mode via CSS variables (hsl(var(--chart-N))).
 */

'use client';

import React from 'react';
import {
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';

// ── Spending Trend (LineChart) ───────────────────────────────────────────────

interface SpendingDataPoint {
  month: string;
  amount: number;
}

interface SpendingChartProps {
  data: SpendingDataPoint[];
}

export function SpendingChart({ data }: SpendingChartProps) {
  if (!data || data.length === 0) {
    return (
      <div className="flex items-center justify-center h-[300px] text-muted-foreground">
        No spending trend data available
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={300} initialDimension={{ width: 400, height: 300 }}>
      <LineChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 10 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
        <XAxis
          dataKey="month"
          stroke="hsl(var(--muted-foreground))"
          fontSize={12}
          tickLine={false}
        />
        <YAxis
          stroke="hsl(var(--muted-foreground))"
          fontSize={12}
          tickLine={false}
          tickFormatter={(value) => `$${value}`}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: 'hsl(var(--card))',
            borderColor: 'hsl(var(--border))',
            borderRadius: '8px',
          }}
          labelStyle={{ color: 'hsl(var(--foreground))' }}
          formatter={(value: number) => [`$${value.toFixed(2)}`, 'Spending']}
        />
        <Line
          type="monotone"
          dataKey="amount"
          stroke="hsl(var(--primary))"
          strokeWidth={2}
          dot={{ fill: 'hsl(var(--primary))', r: 4 }}
          activeDot={{ r: 6 }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

// ── Category Breakdown (PieChart - Donut) ────────────────────────────────────

interface CategoryDataPoint {
  name: string;
  value: number;
}

interface CategoryBreakdownProps {
  data: CategoryDataPoint[];
}

// Chart color palette (dark mode compatible)
const CHART_COLORS = [
  'hsl(var(--chart-1))',
  'hsl(var(--chart-2))',
  'hsl(var(--chart-3))',
  'hsl(var(--chart-4))',
  'hsl(var(--chart-5))',
  'hsl(220, 70%, 50%)', // Fallback blue
  'hsl(280, 70%, 60%)', // Fallback purple
  'hsl(340, 70%, 60%)', // Fallback pink
  'hsl(30, 70%, 55%)',  // Fallback orange
  'hsl(160, 70%, 45%)', // Fallback teal
];

export function CategoryBreakdown({ data }: CategoryBreakdownProps) {
  if (!data || data.length === 0) {
    return (
      <div className="flex items-center justify-center h-[250px] text-muted-foreground">
        No category data available
      </div>
    );
  }

  const total = data.reduce((sum, item) => sum + item.value, 0);

  // Custom label renderer
  const renderLabel = (entry: any) => {
    const percent = ((entry.value / total) * 100).toFixed(1);
    return `${percent}%`;
  };

  return (
    <ResponsiveContainer width="100%" height={250}>
      <PieChart>
        <Pie
          data={data}
          dataKey="value"
          nameKey="name"
          cx="50%"
          cy="50%"
          innerRadius={60}
          outerRadius={100}
          paddingAngle={2}
          label={renderLabel}
        >
          {data.map((entry, index) => (
            <Cell
              key={`cell-${index}`}
              fill={CHART_COLORS[index % CHART_COLORS.length]}
            />
          ))}
        </Pie>
        <Tooltip
          contentStyle={{
            backgroundColor: 'hsl(var(--card))',
            borderColor: 'hsl(var(--border))',
            borderRadius: '8px',
          }}
          formatter={(value: number) => `$${value.toFixed(2)}`}
        />
        <Legend
          verticalAlign="bottom"
          height={36}
          iconType="circle"
          formatter={(value) => (
            <span style={{ color: 'hsl(var(--foreground))', fontSize: '12px' }}>
              {value}
            </span>
          )}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}

// ── Helper: Generate Mock Data for Development ──────────────────────────────

/**
 * Generate mock spending trend data (last 6 months)
 * Used when real data is unavailable.
 */
export function generateMockSpendingData(): SpendingDataPoint[] {
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'];
  return months.map((month) => ({
    month,
    amount: Math.floor(Math.random() * 2000) + 1000,
  }));
}

/**
 * Generate mock category breakdown data
 * Used when real data is unavailable.
 */
export function generateMockCategoryData(): CategoryDataPoint[] {
  return [
    { name: 'Food & Dining', value: 450 },
    { name: 'Transportation', value: 320 },
    { name: 'Shopping', value: 280 },
    { name: 'Entertainment', value: 150 },
    { name: 'Bills & Utilities', value: 600 },
    { name: 'Other', value: 200 },
  ];
}
