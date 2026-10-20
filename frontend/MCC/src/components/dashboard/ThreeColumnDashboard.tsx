'use client';

import React, { useState, useEffect } from 'react';
import { KPIRibbon } from '@/components/zones/KPIRibbon/KPIRibbon';
import { DistrictLeaderboard } from '@/components/zones/DistrictLeaderboard/DistrictLeaderboard';
import { ScoreDecomposition } from '@/components/zones/ScoreDecomposition/ScoreDecomposition';
import { GISMap } from '@/components/leadership/GISMap/GISMap';
import { BreakingNewsTicker } from '@/components/dashboard/BreakingNewsTicker';
import { KeyMetricsTrends } from '@/components/dashboard/KeyMetricsTrends';
import { TopLowerMatrix } from '@/components/leadership/TopLowerMatrix/TopLowerMatrix';
import { SocialMediaAnalysis } from '@/components/leadership/SocialMediaAnalysis/SocialMediaAnalysis';
import { EmergencyAlert } from '@/components/zones/EmergencyAlert/EmergencyAlert';
import { LiveNewsQueue } from '@/components/dashboard/LiveNewsQueue';
import { LiveStreaming } from '@/components/leadership/LiveStreaming/LiveStreaming';

export const ThreeColumnDashboard: React.FC = () => {
  const [isWide, setIsWide] = useState(true);

  useEffect(() => {
    // 1280px+ (xl) breakpoint for wide desktop & command wall 3-column layout
    const mql = window.matchMedia('(min-width: 1280px)');
    setIsWide(mql.matches);
    const handler = (e: MediaQueryListEvent) => setIsWide(e.matches);
    mql.addEventListener('change', handler);
    return () => mql.removeEventListener('change', handler);
  }, []);

  return (
    <div className="p-4 sm:p-5 lg:p-6 max-w-[1920px] w-full mx-auto flex flex-col gap-5 lg:gap-6 bg-transparent">
      {/* 1. FULL-WIDTH KPI RIBBON AT TOP */}
      <section className="w-full">
        <KPIRibbon layout="ribbon" />
      </section>

      {/* 2. PROGRESSIVE RESPONSIVE WORKSPACE */}
      {!isWide ? (
        /* STAGE 1 (MOBILE: grid-cols-1) & STAGE 2 (TABLET / COMPACT LAPTOP: md/lg 2-COLUMN ASYMMETRIC) */
        <div className="grid grid-cols-1 md:grid-cols-12 gap-5 items-start w-full">
          {/* Primary Column (12 at md, 7 at lg: Map, Ticker & State Leaderboard) */}
          <div className="md:col-span-12 lg:col-span-7 flex flex-col gap-5 min-w-0">
            <GISMap />
            <BreakingNewsTicker />
            <DistrictLeaderboard showChart={false} />
          </div>

          {/* Secondary Column (12 at md, 5 at lg: Live Intelligence, Metrics & Audio-Visual) */}
          <div className="md:col-span-12 lg:col-span-5 flex flex-col gap-5 min-w-0">
            <EmergencyAlert />
            <SocialMediaAnalysis />
            <LiveStreaming />
            <ScoreDecomposition />
            <KeyMetricsTrends />
            <TopLowerMatrix />
            <LiveNewsQueue />
          </div>
        </div>
      ) : (
        /* STAGE 3 (WIDE DESKTOP & COMMAND WALL: 1360px+ 3-COLUMN BALANCED BASELINE) */
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 xl:gap-6 items-start w-full">
          {/* LEFT COLUMN (3/12 on XL, 4/12 on LG) - Analytics & Rankings */}
          <div className="lg:col-span-4 xl:col-span-3 flex flex-col gap-5 min-w-0">
            <ScoreDecomposition />
            <KeyMetricsTrends />
            <TopLowerMatrix />
          </div>

          {/* CENTER COLUMN (5/12 on XL, 4/12 on LG) - Map, Ticker & State Leaderboard */}
          <div className="lg:col-span-4 xl:col-span-5 flex flex-col gap-5 min-w-0">
            <GISMap />
            <BreakingNewsTicker />
            <DistrictLeaderboard showChart={false} />
          </div>

          {/* RIGHT COLUMN (4/12 on XL, 4/12 on LG) - Live Intelligence & Streaming */}
          <div className="lg:col-span-4 xl:col-span-4 flex flex-col gap-5 min-w-0">
            <SocialMediaAnalysis />
            <EmergencyAlert />
            <LiveNewsQueue />
            <LiveStreaming />
          </div>
        </div>
      )}
    </div>
  );
};

export default ThreeColumnDashboard;
