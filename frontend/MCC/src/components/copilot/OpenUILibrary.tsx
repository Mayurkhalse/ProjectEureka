'use client';

import React, { useState } from 'react';
import { MaterialIcon } from '@/components/shared/MaterialIcon';

export interface ComponentProps {
  [key: string]: any;
}

// 1. Stack Component
export const Stack: React.FC<{
  direction?: 'vertical' | 'horizontal';
  children: React.ReactNode;
  className?: string;
}> = ({ direction = 'vertical', children, className = '' }) => {
  return (
    <div
      className={`flex ${
        direction === 'horizontal' ? 'flex-row gap-3 flex-wrap' : 'flex-col gap-3'
      } ${className}`}
    >
      {children}
    </div>
  );
};

// 2. KpiCard Component with "Explain this number"
export const KpiCard: React.FC<{
  title: string;
  value: string | number;
  unit?: string;
  delta?: number;
  status?: 'positive' | 'negative' | 'neutral' | 'critical';
  caption?: string;
  onExplain?: () => void;
}> = ({ title, value, unit, delta, status = 'neutral', caption, onExplain }) => {
  const statusStyles = {
    positive: 'border-emerald-200 bg-emerald-50/50 text-emerald-900',
    negative: 'border-rose-200 bg-rose-50/50 text-rose-900',
    critical: 'border-red-300 bg-red-100/60 text-red-950 font-bold',
    neutral: 'border-slate-200 bg-white text-slate-800',
  }[status];

  return (
    <div className={`p-4 rounded-xl border shadow-sm transition-all flex flex-col justify-between ${statusStyles}`}>
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-slate-600 uppercase tracking-wider">{title}</span>
        {onExplain && (
          <button
            onClick={onExplain}
            title="Explain this number"
            className="text-slate-400 hover:text-amber-600 p-1 rounded transition-colors text-xs flex items-center gap-0.5"
            aria-label={`Explain value for ${title}`}
          >
            <MaterialIcon name="description" size="xs" />
          </button>
        )}
      </div>

      <div className="my-2 flex items-baseline gap-1.5">
        <span className="text-2xl font-black tracking-tight">{value}</span>
        {unit && <span className="text-xs font-medium text-slate-500">{unit}</span>}
      </div>

      <div className="flex items-center justify-between text-[11px] text-slate-500">
        {caption && <span>{caption}</span>}
        {delta !== undefined && (
          <span className={`font-semibold flex items-center gap-0.5 ${delta >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>
            <MaterialIcon name={delta >= 0 ? 'trending_up' : 'trending_down'} size="xs" />
            {delta > 0 ? `+${delta}` : delta}
          </span>
        )}
      </div>
    </div>
  );
};

// 3. DataTable Component
export const DataTable: React.FC<{
  columns: string | string[];
  rows: string | Array<Record<string, any>>;
  caption?: string;
}> = ({ columns, rows, caption }) => {
  const colList = Array.isArray(columns) ? columns : typeof columns === 'string' ? columns.split(',').map((c) => c.trim()) : [];
  let rowList: Array<Record<string, any>> = [];
  if (Array.isArray(rows)) {
    rowList = rows;
  } else if (typeof rows === 'string') {
    try {
      rowList = JSON.parse(rows);
    } catch {
      rowList = [];
    }
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white shadow-sm my-2">
      {caption && (
        <div className="px-4 py-2 bg-slate-50 border-b border-slate-200 text-xs font-bold text-slate-700">
          {caption}
        </div>
      )}
      <table className="min-w-full divide-y divide-slate-200 text-left text-xs">
        <thead className="bg-slate-100/75 text-slate-700 font-semibold uppercase tracking-wider">
          <tr>
            {colList.map((col, idx) => (
              <th key={idx} scope="col" className="px-3 py-2.5">
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 font-medium text-slate-700">
          {rowList.map((row, rIdx) => (
            <tr key={rIdx} className={rIdx % 2 === 0 ? 'bg-white' : 'bg-slate-50/50 hover:bg-slate-50'}>
              {colList.map((col, cIdx) => (
                <td key={cIdx} className="px-3 py-2 whitespace-nowrap">
                  {row[col] !== undefined ? String(row[col]) : row[Object.keys(row)[cIdx]] !== undefined ? String(row[Object.keys(row)[cIdx]]) : '-'}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

// 4. BarChart Component with "View as Table" toggle
export const BarChart: React.FC<{
  title: string;
  xKey?: string;
  yKey?: string;
  data?: string | Array<Record<string, any>>;
  children?: React.ReactNode;
  onExplain?: () => void;
}> = ({ title, xKey = 'x', yKey = 'y', data, children, onExplain }) => {
  const [viewAsTable, setViewAsTable] = useState(false);

  let chartData: Array<Record<string, any>> = [];
  if (Array.isArray(data)) {
    chartData = data;
  } else if (typeof data === 'string') {
    try {
      chartData = JSON.parse(data);
    } catch {
      chartData = [];
    }
  }

  const maxVal = Math.max(...chartData.map((d) => Number(d[yKey]) || 0), 100);

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm my-2">
      <div className="flex items-center justify-between border-b border-slate-100 pb-2 mb-3">
        <div className="flex items-center gap-2">
          <MaterialIcon name="bar_chart" size="sm" className="text-amber-600" />
          <h4 className="text-xs font-bold text-slate-800">{title}</h4>
        </div>
        <div className="flex items-center gap-2">
          {onExplain && (
            <button
              onClick={onExplain}
              className="text-xs text-slate-500 hover:text-amber-600 flex items-center gap-1 border rounded px-2 py-0.5"
            >
              <MaterialIcon name="description" size="xs" /> Explain
            </button>
          )}
          <button
            onClick={() => setViewAsTable(!viewAsTable)}
            className="text-xs font-semibold px-2.5 py-1 rounded-md border border-slate-200 bg-slate-50 text-slate-700 hover:bg-slate-100 transition-colors flex items-center gap-1"
          >
            <MaterialIcon name={viewAsTable ? 'bar_chart' : 'checklist'} size="xs" />
            {viewAsTable ? 'View Chart' : 'View as Table'}
          </button>
        </div>
      </div>

      {viewAsTable ? (
        <DataTable
          columns={[xKey, yKey]}
          rows={chartData}
          caption={`${title} (Table View)`}
        />
      ) : (
        <div className="space-y-2 py-2">
          {chartData.map((d, idx) => {
            const val = Number(d[yKey]) || 0;
            const pct = Math.min(100, Math.round((val / maxVal) * 100));
            return (
              <div key={idx} className="space-y-0.5 text-xs">
                <div className="flex justify-between font-medium text-slate-700">
                  <span>{String(d[xKey] || '')}</span>
                  <span className="font-bold text-slate-900">{val}</span>
                </div>
                <div className="h-2.5 w-full bg-slate-100 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-amber-500 to-amber-600 rounded-full transition-all duration-500"
                    style={{ width: `${pct}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      )}

      {children && <div className="mt-2 text-xs text-slate-600 border-t border-slate-50 pt-2">{children}</div>}
    </div>
  );
};

// 5. LineChart Component with "View as Table" toggle
export const LineChart: React.FC<{
  title: string;
  xKey?: string;
  yKey?: string;
  data?: string | Array<Record<string, any>>;
  children?: React.ReactNode;
}> = ({ title, xKey = 'day', yKey = 'value', data, children }) => {
  const [viewAsTable, setViewAsTable] = useState(false);

  let chartData: Array<Record<string, any>> = [];
  if (Array.isArray(data)) {
    chartData = data;
  } else if (typeof data === 'string') {
    try {
      chartData = JSON.parse(data);
    } catch {
      chartData = [];
    }
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm my-2">
      <div className="flex items-center justify-between border-b border-slate-100 pb-2 mb-3">
        <div className="flex items-center gap-2">
          <MaterialIcon name="trending_up" size="sm" className="text-blue-600" />
          <h4 className="text-xs font-bold text-slate-800">{title}</h4>
        </div>
        <button
          onClick={() => setViewAsTable(!viewAsTable)}
          className="text-xs font-semibold px-2.5 py-1 rounded-md border border-slate-200 bg-slate-50 text-slate-700 hover:bg-slate-100 transition-colors flex items-center gap-1"
        >
          <MaterialIcon name={viewAsTable ? 'trending_up' : 'checklist'} size="xs" />
          {viewAsTable ? 'View Trend Line' : 'View as Table'}
        </button>
      </div>

      {viewAsTable ? (
        <DataTable columns={[xKey, yKey]} rows={chartData} caption={`${title} (Historical Data)`} />
      ) : (
        <div className="py-2">
          <div className="h-28 flex items-end gap-1.5 pt-4 px-2 border-b border-slate-200">
            {chartData.map((d, idx) => {
              const val = Number(d[yKey]) || 0;
              const h = Math.min(100, Math.max(10, Math.round(val)));
              return (
                <div key={idx} className="flex-1 flex flex-col items-center gap-1 group relative">
                  <div
                    className="w-full bg-blue-500 rounded-t hover:bg-blue-600 transition-all cursor-pointer"
                    style={{ height: `${h}%` }}
                    title={`${d[xKey]}: ${val}`}
                  />
                  <span className="text-[9px] text-slate-400 font-mono scale-90">{d[xKey]}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {children && <div className="mt-2 text-xs text-slate-600">{children}</div>}
    </div>
  );
};

// 6. GraphView Component (Capped at 200 nodes) with "View as Table"
export const GraphView: React.FC<{
  title: string;
  nodes?: string | Array<Record<string, any>>;
  edges?: string | Array<Record<string, any>>;
  children?: React.ReactNode;
}> = ({ title, nodes, edges, children }) => {
  const [viewAsTable, setViewAsTable] = useState(false);

  let nodeList: Array<Record<string, any>> = [];
  if (Array.isArray(nodes)) nodeList = nodes.slice(0, 200);
  else if (typeof nodes === 'string') {
    try {
      nodeList = JSON.parse(nodes).slice(0, 200);
    } catch {
      nodeList = [];
    }
  }

  let edgeList: Array<Record<string, any>> = [];
  if (Array.isArray(edges)) edgeList = edges.slice(0, 300);
  else if (typeof edges === 'string') {
    try {
      edgeList = JSON.parse(edges).slice(0, 300);
    } catch {
      edgeList = [];
    }
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm my-2">
      <div className="flex items-center justify-between border-b border-slate-100 pb-2 mb-3">
        <div className="flex items-center gap-2">
          <MaterialIcon name="alt_route" size="sm" className="text-purple-600" />
          <h4 className="text-xs font-bold text-slate-800">{title}</h4>
        </div>
        <button
          onClick={() => setViewAsTable(!viewAsTable)}
          className="text-xs font-semibold px-2.5 py-1 rounded-md border border-slate-200 bg-slate-50 text-slate-700 hover:bg-slate-100 transition-colors flex items-center gap-1"
        >
          <MaterialIcon name={viewAsTable ? 'alt_route' : 'checklist'} size="xs" />
          {viewAsTable ? 'View Network' : 'View as Table'}
        </button>
      </div>

      {viewAsTable ? (
        <DataTable
          columns={['From', 'Relation', 'To']}
          rows={edgeList.map((e) => ({
            From: e.from,
            Relation: e.relation || 'CONNECTED',
            To: e.to,
          }))}
          caption={`${title} (Edge List)`}
        />
      ) : (
        <div className="p-3 bg-slate-50/50 rounded-lg border border-slate-100">
          <div className="text-[11px] font-semibold text-slate-500 mb-2">
            Network Topology ({nodeList.length} Nodes, {edgeList.length} Adjacencies):
          </div>
          <div className="flex flex-wrap gap-1.5">
            {nodeList.map((n, idx) => (
              <span
                key={idx}
                className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold border bg-purple-50 text-purple-900 border-purple-200"
              >
                <span className="w-1.5 h-1.5 rounded-full bg-purple-600" />
                {n.label || n.id}
              </span>
            ))}
          </div>
        </div>
      )}

      {children && <div className="mt-2 text-xs text-slate-600">{children}</div>}
    </div>
  );
};

// 7. Callout Component
export const Callout: React.FC<{
  type?: 'info' | 'warning' | 'success' | 'critical';
  message: string;
}> = ({ type = 'info', message }) => {
  const styles = {
    info: 'bg-blue-50 border-blue-200 text-blue-900',
    warning: 'bg-amber-50 border-amber-200 text-amber-900',
    success: 'bg-emerald-50 border-emerald-200 text-emerald-900',
    critical: 'bg-rose-50 border-rose-300 text-rose-950 font-medium',
  }[type];

  const iconName: any = {
    info: 'description',
    warning: 'warning',
    success: 'check_circle',
    critical: 'error',
  }[type];

  return (
    <div className={`p-3 rounded-lg border flex items-start gap-2.5 text-xs ${styles} my-2`}>
      <MaterialIcon name={iconName} size="sm" className="shrink-0 mt-0.5" />
      <span className="leading-relaxed">{message}</span>
    </div>
  );
};

// 8. Heading Component
export const Heading: React.FC<{
  level?: number;
  text: string;
}> = ({ level = 2, text }) => {
  const sizeClasses = {
    1: 'text-lg font-black tracking-tight text-slate-900',
    2: 'text-sm font-bold text-slate-800',
    3: 'text-xs font-bold text-slate-700 uppercase tracking-wider',
    4: 'text-xs font-semibold text-slate-600',
  }[level] || 'text-sm font-bold';

  if (level === 1) return <h1 className={`${sizeClasses} my-1.5`}>{text}</h1>;
  if (level === 3) return <h3 className={`${sizeClasses} my-1.5`}>{text}</h3>;
  if (level === 4) return <h4 className={`${sizeClasses} my-1.5`}>{text}</h4>;
  return <h2 className={`${sizeClasses} my-1.5`}>{text}</h2>;
};

// 9. Text Component
export const Text: React.FC<{ content: string }> = ({ content }) => {
  return <p className="text-xs text-slate-700 leading-relaxed my-1">{content}</p>;
};
