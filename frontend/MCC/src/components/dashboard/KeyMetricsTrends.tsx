'use client';

import React from 'react';
import { useDashboardStore } from '@/stores/dashboardStore';
import { useTranslation } from '@/lib/translations';
import { DistrictPerformanceChart } from '@/components/zones/DistrictLeaderboard/DistrictPerformanceChart';
import { Skeleton } from '@/components/shared/Skeleton';
import { MaterialIcon } from '@/components/shared/MaterialIcon';

export const KeyMetricsTrends: React.FC = () => {
  const {
    districts,
    selectedDistrictId,
    setSelectedDistrictId,
    selectedDivision,
    language,
    isLoadingData,
  } = useDashboardStore();
  const t = useTranslation(language);

  if (isLoadingData) {
    return (
      <div className="bg-white border border-slate-200/90 rounded-xl p-4 shadow-sm space-y-3 min-h-[220px]">
        <div className="flex justify-between items-center pb-2 border-b border-slate-100">
          <Skeleton className="h-4 w-48 rounded" />
          <Skeleton variant="subtle" className="h-3 w-28 rounded" />
        </div>
        <div className="h-40 flex items-end justify-between gap-4 px-6 pt-4">
          <Skeleton className="h-28 w-14 rounded-t" />
          <Skeleton className="h-36 w-14 rounded-t" />
          <Skeleton className="h-24 w-14 rounded-t" />
          <Skeleton className="h-32 w-14 rounded-t" />
          <Skeleton className="h-20 w-14 rounded-t" />
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl shadow-sm border border-slate-200/80 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="p-4 sm:p-5 border-b border-slate-100 bg-white flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded bg-blue-50 text-gov-blue">
            <MaterialIcon name="bar_chart" size="sm" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-gov-primary tracking-tight">
              {language === 'mr' ? 'प्रमुख निर्देशक व कल विश्लेषण' : 'Key Metrics & Trends'}
            </h3>
            <p className="text-[11px] text-slate-500 font-medium">
              {language === 'mr'
                ? 'शीर्ष ५ जिल्ह्यांचे ४ सीपीआय घटकांनुसार तुलनात्मक विश्लेषण'
                : 'Top 5 District Comparative Breakdown (Volume, TAT, Sentiment, SLA)'}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-[11px] font-mono font-semibold text-slate-600 bg-slate-100 border border-slate-200 px-2 py-0.5 rounded">
            {selectedDivision}
          </span>
        </div>
      </div>

      {/* Chart Canvas */}
      <div className="p-4 sm:p-5">
        <DistrictPerformanceChart
          districts={districts}
          selectedDistrictId={selectedDistrictId}
          onSelectDistrict={setSelectedDistrictId}
        />
      </div>
    </div>
  );
};
