'use client';

import React, { useEffect, useState } from 'react';
import { useDashboardStore } from '@/stores/dashboardStore';
import { DistrictPositionData } from '@/types/dashboard';
import { MAHARASHTRA_DISTRICT_META } from '@/lib/backendClient';
import { MaterialIcon } from '@/components/shared/MaterialIcon';
import { SampleDataBadge } from '@/components/shared/SampleDataBadge';

export const GovernmentPositionsSection: React.FC = () => {
  const { selectedDistrictId, language } = useDashboardStore();
  const [positions, setPositions] = useState<DistrictPositionData[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  // Map selectedDistrictId (slug) to standard MH-XX code
  const meta = MAHARASHTRA_DISTRICT_META[selectedDistrictId.toLowerCase()] ||
    MAHARASHTRA_DISTRICT_META['thane'] || { code: 'MH-04', nameMr: 'ठाणे', division: 'Konkan', id: 'thane' };

  const districtCode = meta.code;

  useEffect(() => {
    let isMounted = true;
    setLoading(true);
    setError(null);

    async function fetchPositions() {
      try {
        const res = await fetch(`/api/v1/districts/${districtCode}/positions`);
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}: Failed to load positions`);
        }
        const data = await res.json();
        if (isMounted) {
          setPositions(data.positions || []);
          setLoading(false);
        }
      } catch (err: any) {
        if (isMounted) {
          setError(err.message || 'Could not load government positions');
          setLoading(false);
        }
      }
    }

    fetchPositions();
    return () => {
      isMounted = false;
    };
  }, [districtCode]);

  // Group positions into Political Leadership and Executive Administration
  const politicalCategories = ['MINISTER', 'MP', 'MLA', 'MLC'];
  const politicalPositions = positions.filter((p) => politicalCategories.includes(p.category));
  const executivePositions = positions.filter((p) => !politicalCategories.includes(p.category));

  return (
    <div className="bg-surface-secondary border border-borderLine-subtle rounded-md p-3.5 space-y-3.5">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-borderLine-subtle pb-2.5">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-full bg-surface border border-borderLine-standard flex items-center justify-center text-content-primary">
            <MaterialIcon name="domain" size="xs" />
          </div>
          <div>
            <h4 className="text-xs font-bold text-content-primary flex items-center gap-2">
              <span>
                {language === 'mr'
                  ? 'शासकीय व लोकप्रतिनिधी पदे'
                  : 'Key Government & Elected Positions'}
              </span>
              <span className="text-[10px] font-mono text-content-muted">({districtCode})</span>
            </h4>
            <p className="text-[10px] text-content-muted">
              {language === 'mr'
                ? 'जिल्हा प्रशासन, लोकप्रतिनिधी व प्रमुख संपर्क यंत्रणा'
                : 'District Executive Administration & Elected Representative Directory'}
            </p>
          </div>
        </div>
        <SampleDataBadge />
      </div>

      {/* Loading State */}
      {loading && (
        <div className="space-y-2 py-3">
          <div className="h-4 bg-surface rounded animate-pulse w-1/3" />
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <div className="h-16 bg-surface rounded animate-pulse" />
            <div className="h-16 bg-surface rounded animate-pulse" />
          </div>
        </div>
      )}

      {/* Error State */}
      {!loading && error && (
        <div className="p-3 bg-red-500/10 border border-red-500/20 rounded text-xs text-red-500 flex items-center gap-2">
          <MaterialIcon name="error" size="sm" />
          <span>{error}</span>
        </div>
      )}

      {/* Empty State */}
      {!loading && !error && positions.length === 0 && (
        <div className="p-4 text-center text-xs text-content-muted">
          <MaterialIcon name="warning" size="md" className="mx-auto mb-1 text-content-muted" />
          <p>{language === 'mr' ? 'कोणतीही पदे आढळली नाहीत.' : 'No government positions found for this district.'}</p>
        </div>
      )}

      {/* Content: Grouped Categories */}
      {!loading && !error && positions.length > 0 && (
        <div className="space-y-4">
          {/* 1. Elected Leadership */}
          {politicalPositions.length > 0 && (
            <div className="space-y-2">
              <div className="flex items-center gap-1.5 text-[11px] font-semibold text-content-secondary uppercase tracking-wider">
                <MaterialIcon name="how_to_reg" size="xs" className="text-content-muted" />
                <span>{language === 'mr' ? 'लोकप्रतिनिधी' : 'Elected Leadership'}</span>
                <span className="text-[10px] font-mono text-content-muted">({politicalPositions.length})</span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                {politicalPositions.map((pos) => {
                  const isExpanded = expandedId === pos.id;
                  const designation = language === 'mr' ? pos.designation_mr : pos.designation_en;
                  const responsibilities = language === 'mr' ? pos.responsibilities_mr : pos.responsibilities_en;

                  return (
                    <div
                      key={pos.id}
                      className="bg-surface border border-borderLine-subtle hover:border-borderLine-standard rounded p-2.5 transition-colors space-y-1.5"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <div className="text-[11px] font-bold text-content-primary truncate">
                            {pos.person_name}
                          </div>
                          <div className="text-[10px] text-content-secondary line-clamp-1">
                            {designation}
                          </div>
                        </div>
                        <span className="shrink-0 px-1.5 py-0.5 rounded text-[9px] font-mono uppercase bg-surface-secondary text-content-muted border border-borderLine-subtle">
                          {pos.category}
                        </span>
                      </div>

                      {/* Contact row */}
                      <div className="flex items-center gap-3 text-[10px] font-mono text-content-muted pt-1 border-t border-borderLine-subtle/60">
                        {pos.phone && (
                          <a
                            href={`tel:${pos.phone}`}
                            className="flex items-center gap-1 hover:text-content-primary transition-colors"
                            title="Call Office"
                          >
                            <MaterialIcon name="call" size="xs" />
                            <span>{pos.phone}</span>
                          </a>
                        )}
                        {pos.email && (
                          <a
                            href={`mailto:${pos.email}`}
                            className="flex items-center gap-1 hover:text-content-primary transition-colors truncate max-w-[150px]"
                            title={pos.email}
                          >
                            <MaterialIcon name="mail" size="xs" />
                            <span className="truncate">{pos.email}</span>
                          </a>
                        )}
                      </div>

                      {/* Expandable Responsibilities */}
                      {responsibilities && (
                        <div className="pt-1">
                          <button
                            type="button"
                            onClick={() => setExpandedId(isExpanded ? null : pos.id)}
                            className="text-[10px] text-content-secondary hover:text-content-primary flex items-center gap-0.5 cursor-pointer"
                          >
                            <MaterialIcon
                              name={isExpanded ? 'expand_less' : 'expand_more'}
                              size="xs"
                            />
                            <span>{language === 'mr' ? 'जबाबदाऱ्या' : 'Responsibilities'}</span>
                          </button>
                          {isExpanded && (
                            <p className="text-[10px] text-content-muted bg-surface-secondary p-1.5 rounded mt-1 leading-relaxed">
                              {responsibilities}
                            </p>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* 2. Executive Administration */}
          {executivePositions.length > 0 && (
            <div className="space-y-2">
              <div className="flex items-center gap-1.5 text-[11px] font-semibold text-content-secondary uppercase tracking-wider">
                <MaterialIcon name="shield" size="xs" className="text-content-muted" />
                <span>{language === 'mr' ? 'प्रशासकीय प्रमुख' : 'Executive Administration'}</span>
                <span className="text-[10px] font-mono text-content-muted">({executivePositions.length})</span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                {executivePositions.map((pos) => {
                  const isExpanded = expandedId === pos.id;
                  const designation = language === 'mr' ? pos.designation_mr : pos.designation_en;
                  const responsibilities = language === 'mr' ? pos.responsibilities_mr : pos.responsibilities_en;

                  return (
                    <div
                      key={pos.id}
                      className="bg-surface border border-borderLine-subtle hover:border-borderLine-standard rounded p-2.5 transition-colors space-y-1.5"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <div className="text-[11px] font-bold text-content-primary truncate">
                            {pos.person_name}
                          </div>
                          <div className="text-[10px] text-content-secondary line-clamp-1">
                            {designation}
                          </div>
                        </div>
                        <span className="shrink-0 px-1.5 py-0.5 rounded text-[9px] font-mono uppercase bg-surface-secondary text-content-muted border border-borderLine-subtle">
                          {pos.category}
                        </span>
                      </div>

                      {/* Contact row */}
                      <div className="flex items-center gap-3 text-[10px] font-mono text-content-muted pt-1 border-t border-borderLine-subtle/60">
                        {pos.phone && (
                          <a
                            href={`tel:${pos.phone}`}
                            className="flex items-center gap-1 hover:text-content-primary transition-colors"
                            title="Call Office"
                          >
                            <MaterialIcon name="call" size="xs" />
                            <span>{pos.phone}</span>
                          </a>
                        )}
                        {pos.email && (
                          <a
                            href={`mailto:${pos.email}`}
                            className="flex items-center gap-1 hover:text-content-primary transition-colors truncate max-w-[150px]"
                            title={pos.email}
                          >
                            <MaterialIcon name="mail" size="xs" />
                            <span className="truncate">{pos.email}</span>
                          </a>
                        )}
                      </div>

                      {/* Expandable Responsibilities */}
                      {responsibilities && (
                        <div className="pt-1">
                          <button
                            type="button"
                            onClick={() => setExpandedId(isExpanded ? null : pos.id)}
                            className="text-[10px] text-content-secondary hover:text-content-primary flex items-center gap-0.5 cursor-pointer"
                          >
                            <MaterialIcon
                              name={isExpanded ? 'expand_less' : 'expand_more'}
                              size="xs"
                            />
                            <span>{language === 'mr' ? 'जबाबदाऱ्या' : 'Responsibilities'}</span>
                          </button>
                          {isExpanded && (
                            <p className="text-[10px] text-content-muted bg-surface-secondary p-1.5 rounded mt-1 leading-relaxed">
                              {responsibilities}
                            </p>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
