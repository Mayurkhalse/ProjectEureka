import { NextRequest, NextResponse } from 'next/server';
import { getLiveIncidents } from '@/lib/backendClient';

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams;
  const role = searchParams.get('role') || undefined;
  const district = searchParams.get('district') || undefined;

  const authHeader = request.headers.get('authorization') || undefined;
  const token = authHeader?.startsWith('Bearer ') ? authHeader.substring(7) : undefined;

  const result = await getLiveIncidents(role, district, token);
  return NextResponse.json(result);
}
