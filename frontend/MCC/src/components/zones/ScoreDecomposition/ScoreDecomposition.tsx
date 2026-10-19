'use client';

import React, { useMemo } from 'react';
import { useDashboardStore } from '@/stores/dashboardStore';
import { useTranslation } from '@/lib/translations';
import { ScoreMetricBar } from './ScoreMetricBar';
import { ScoreDecompositionSkeleton } from '@/components/skeletons/ScoreDecompositionSkeleton';
import { getDistrictName } from '@/lib/dataLocalization';
import { getDistrictSentiment } from '@/lib/sentimentEngine';
import { MaterialIcon } from '@/components/shared/MaterialIcon';

export const ScoreDecomposition: React.FC = () => {
  const { districts, selectedDistrictId, selectedPeriod, language, isLoadingData } = useDashboardStore();
  const t = useTranslation(language);

  const selected =
    districts.find((d) => d.id === selectedDistrictId?.toLowerCase()) ||
    districts[0];

  const sentimentBreakdown = useMemo(() => {
    return getDistrictSentiment(selected.id, selectedPeriod);
  }, [selected.id, selectedPeriod]);

  // Safeguard #1: Return skeleton directly at root level to prevent double card wrappers
  if (isLoadingData) {
    return <ScoreDecompositionSkeleton />;
  }

  return (
    <div className="bg-white rounded-xl shadow-sm border border-slate-200/80 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="p-5 border-b border-slate-200/80 bg-white flex items-center justify-between flex-wrap gap-2">
        <div>
          <h3 className="text-sm font-bold text-gov-primary tracking-tight mb-1">
            {t.zone3.title} — {language === 'mr' ? (selected.nameMr || getDistrictName(selected.name, 'mr')) : selected.name}
          </h3>
          <p className="text-[11px] text-slate-500 font-medium">
            {t.zone3.subtitle}
          </p>
        </div>

        <div className="flex items-center gap-2 text-xs font-semibold text-slate-700">
          <span className="text-gov-primary font-bold">
            {t.zone3.rankPrefix} #{selected.rank}
          </span>
          <span className="text-slate-300 select-none font-mono">|</span>
          <span className="font-mono font-bold text-gov-primary">
            {selected.cpi} <span className="font-sans font-medium text-slate-500">/ 100 {t.zone3.cpiPrefix}</span>
          </span>
        </div>
      </div>

      {/* 4 Constituent Scores */}
      <div className="p-5 space-y-4 bg-white">
        {/* 1. Volume Score */}
        <ScoreMetricBar
          icon="newspaper"
          title={t.zone3.volumeTitle}
          subtitle={t.zone3.volumeSub}
          score={selected.volumeScore}
          valueLabel={`${selected.releases} ${language === 'mr' ? 'पत्रके' : 'releases'}`}
          gapLabel={`${25 - selected.volumeScore} ${t.zone3.gapSuffix}`}
        />

        {/* 2. TAT / Dispatch Speed */}
        <ScoreMetricBar
          icon="send"
          title={t.zone3.tatTitle}
          subtitle={t.zone3.tatSub}
          score={selected.tatScore}
          valueLabel={`${selected.avgTAT} ${language === 'mr' ? 'मिनिटे' : 'min'}`}
          gapLabel={`${25 - selected.tatScore} ${t.zone3.gapSuffix}`}
        />

        {/* 3. Media Sentiment Score (Multi-Channel 4-Stream Composite) */}
        <div className="space-y-1.5 p-2 rounded-md hover:bg-slate-50 transition-colors">
          <ScoreMetricBar
            icon="chat_bubble"
            title={t.zone3.sentimentTitle}
            subtitle={t.zone3.sentimentSub}
            score={selected.sentimentScore}
            valueLabel={`${selected.sentiment}%`}
            gapLabel={`${25 - selected.sentimentScore} ${t.zone3.gapSuffix}`}
          />

          {/* 4-Channel Weighted Breakdown Badges */}
          <div className="mt-2 pt-2 border-t border-slate-100">
            <div className="text-[10px] font-semibold text-slate-500 flex items-center gap-1 mb-1.5">
              <MaterialIcon name="bar_chart" size="xs" className="text-slate-400" />
              <span>{language === 'mr' ? '४-प्रवाह घटक:' : '4-Channel Mix:'}</span>
            </div>
            <div className="grid grid-cols-2 gap-2 p-3 bg-slate-50/80 rounded-lg border border-slate-100">
              <div
                className="flex items-center justify-between gap-1 pl-2 border-l-2 border-blue-500 text-[11px]"
                title="Print Media OCR (35% weight in composite tone score)"
              >
                <span className="text-slate-700 font-medium truncate">{language === 'mr' ? 'प्रिंट ओसीआर' : 'Print OCR'}</span>
                <div className="flex items-center gap-1 shrink-0 font-mono text-[11px]">
                  <strong className="text-slate-900">{sentimentBreakdown.printOcr}%</strong>
                  <span className="text-slate-400 text-[10px]">(35%)</span>
                </div>
              </div>
              <div
                className="flex items-center justify-between gap-1 pl-2 border-l-2 border-purple-500 text-[11px]"
                title="Broadcast TV Telemetry - DD Sahyadri & Regional News (25% weight)"
              >
                <span className="text-slate-700 font-medium truncate">{language === 'mr' ? 'टीव्ही प्रसारण' : 'Broadcast TV'}</span>
                <div className="flex items-center gap-1 shrink-0 font-mono text-[11px]">
                  <strong className="text-slate-900">{sentimentBreakdown.broadcastTv}%</strong>
                  <span className="text-slate-400 text-[10px]">(25%)</span>
                </div>
              </div>
              <div
                className="flex items-center justify-between gap-1 pl-2 border-l-2 border-emerald-500 text-[11px]"
                title="Social Listening - X/Twitter, FB, Insta, YouTube (25% weight)"
              >
                <span className="text-slate-700 font-medium truncate">{language === 'mr' ? 'सोशल ऐकणे' : 'Social'}</span>
                <div className="flex items-center gap-1 shrink-0 font-mono text-[11px]">
                  <strong className="text-slate-900">{sentimentBreakdown.socialListening}%</strong>
                  <span className="text-slate-400 text-[10px]">(25%)</span>
                </div>
              </div>
              <div
                className="flex items-center justify-between gap-1 pl-2 border-l-2 border-amber-500 text-[11px]"
                title="Citizen/User Comments & Public Feedback (15% weight)"
              >
                <span className="text-slate-700 font-medium truncate">{language === 'mr' ? 'नागरिक टिप्पण्या' : 'Comments'}</span>
                <div className="flex items-center gap-1 shrink-0 font-mono text-[11px]">
                  <strong className="text-slate-900">{sentimentBreakdown.userComments}%</strong>
                  <span className="text-slate-400 text-[10px]">(15%)</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* 4. Crisis SLA */}
        <ScoreMetricBar
          icon="warning"
          title={t.zone3.crisisTitle}
          subtitle={t.zone3.crisisSub}
          score={selected.crisisScore}
          valueLabel={`${selected.crisisSLA}% SLA`}
          gapLabel={`${25 - selected.crisisScore} ${t.zone3.gapSuffix}`}
        />
      </div>

      <div className="px-4 py-2 bg-slate-50 border-t border-slate-200 text-[11px] text-slate-500 flex justify-between items-center">
        <span>{t.zone3.footerLeft}</span>
        <span className="font-semibold text-gov-primary">{t.zone3.footerRight}</span>
      </div>
    </div>
  );
};
