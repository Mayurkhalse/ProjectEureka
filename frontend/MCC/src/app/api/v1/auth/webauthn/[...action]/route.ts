import { NextRequest, NextResponse } from 'next/server';
import { getBackendEndpoint } from '@/lib/backendClient';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

async function proxyRequest(request: NextRequest, { params }: { params: Promise<{ action: string[] }> | { action: string[] } }) {
  const resolvedParams = 'then' in params ? await params : params;
  const actionPath = (resolvedParams.action || []).join('/');

  const search = request.nextUrl.search;
  const targetUrl = getBackendEndpoint(`/api/v1/auth/webauthn/${actionPath}${search}`);

  const headers: Record<string, string> = {
    Accept: 'application/json',
  };

  const authHeader = request.headers.get('authorization');
  if (authHeader) headers['Authorization'] = authHeader;

  let body: any = undefined;
  if (request.method !== 'GET' && request.method !== 'HEAD') {
    headers['Content-Type'] = 'application/json';
    try {
      body = await request.text();
    } catch {}
  }

  try {
    const res = await fetch(targetUrl.toString(), {
      method: request.method,
      headers,
      body,
    });

    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch (err: any) {
    return NextResponse.json(
      { status: 'error', detail: err?.message || 'Failed to proxy WebAuthn request to backend.' },
      { status: 502 }
    );
  }
}

export async function GET(request: NextRequest, context: any) {
  return proxyRequest(request, context);
}

export async function POST(request: NextRequest, context: any) {
  return proxyRequest(request, context);
}

export async function DELETE(request: NextRequest, context: any) {
  return proxyRequest(request, context);
}
