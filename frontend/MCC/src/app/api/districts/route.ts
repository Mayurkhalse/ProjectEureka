import { NextRequest, NextResponse } from 'next/server';
import { getLiveDistricts } from '@/lib/backendClient';

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams;
  const role = searchParams.get('role') || undefined;
  const district = searchParams.get('district') || undefined;
  const division = searchParams.get('division') || undefined;

  const authHeader = request.headers.get('authorization') || undefined;
  const token = authHeader?.startsWith('Bearer ') ? authHeader.substring(7) : undefined;

  const result = await getLiveDistricts(role, district, division, token);
  return NextResponse.json(result);
}
