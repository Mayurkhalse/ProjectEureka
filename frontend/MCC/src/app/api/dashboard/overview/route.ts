import { NextRequest, NextResponse } from 'next/server';
import { getLiveOverviewMetrics } from '@/lib/backendClient';

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams;
  const role = searchParams.get('role') || undefined;
  const district = searchParams.get('district') || undefined;
  const division = searchParams.get('division') || undefined;

  const metrics = await getLiveOverviewMetrics(role, district, division);
  return NextResponse.json({ success: true, data: metrics });
}
