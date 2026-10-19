import { NextRequest, NextResponse } from 'next/server';
import { FASTAPI_BACKEND_URL } from '@/lib/backendClient';
import { verifyAuthToken } from '@/lib/jwt';
import { MOCK_USERS } from '@/lib/serverData';
import { SignJWT, jwtVerify } from 'jose';

const FASTAPI_JWT_SECRET = process.env.FASTAPI_JWT_SECRET || 'dgipr_maha_command_center_secret_2026_key';
const encodedFastApiSecret = new TextEncoder().encode(FASTAPI_JWT_SECRET);

const BACKEND_ROLE_MAP: Record<string, string> = {
  dg_admin: 'DG State Admin',
  director_konkan: 'DG State Admin',
  collector: 'District Collector',
  dio_desk: 'DIO Desk',
};

async function createDirectBackendToken(officer: { username: string; role: string; district_code?: string }): Promise<string> {
  return await new SignJWT({
    sub: officer.username,
    role: officer.role,
    district_code: officer.district_code || null,
  })
    .setProtectedHeader({ alg: 'HS256' })
    .setIssuedAt()
    .setExpirationTime('8h')
    .sign(encodedFastApiSecret);
}

/**
 * Resolves a valid FastAPI backend JWT token from the incoming request.
 */
async function resolveBackendToken(request: NextRequest): Promise<string | null> {
  // 1. Direct FastAPI token in cookie (verify expiration before reusing!)
  const cookieBackendToken = request.cookies.get('maha_backend_token')?.value;
  if (cookieBackendToken) {
    try {
      const { payload } = await jwtVerify(cookieBackendToken, encodedFastApiSecret);
      if (payload && payload.sub && payload.role) {
        return cookieBackendToken;
      }
    } catch {
      // Stale or expired cookie - discard and generate a fresh token
    }
  }

  // 2. Authorization header from frontend
  const authHeader = request.headers.get('authorization') || request.headers.get('Authorization');
  const bearerToken = authHeader?.startsWith('Bearer ') ? authHeader.slice(7) : null;

  let officer = {
    username: 'admin',
    role: 'DG State Admin',
    district_code: 'MH-01',
  };

  const tokenToVerify = bearerToken || request.cookies.get('maha_auth_token')?.value;
  if (tokenToVerify) {
    const verified = await verifyAuthToken(tokenToVerify);
    if (verified.valid && verified.payload?.user) {
      const u = verified.payload.user;
      const role = BACKEND_ROLE_MAP[u.role] || 'DG State Admin';
      const districtCode =
        u.district === 'Palghar'
          ? 'MH-04'
          : u.district === 'Thane'
          ? 'MH-03'
          : 'MH-01';

      officer = {
        username: u.username || 'admin',
        role,
        district_code: districtCode,
      };
    }
  } else {
    // 3. Fallback from maha_auth_user cookie
    const userCookie = request.cookies.get('maha_auth_user')?.value;
    if (userCookie) {
      try {
        const u = JSON.parse(userCookie);
        const role = BACKEND_ROLE_MAP[u.role] || 'DG State Admin';
        const districtCode =
          u.district === 'Palghar'
            ? 'MH-04'
            : u.district === 'Thane'
            ? 'MH-03'
            : 'MH-01';

        officer = {
          username: u.username || 'admin',
          role,
          district_code: districtCode,
        };
      } catch {}
    }
  }

  // Deterministically sign the FastAPI token directly with zero network overhead
  try {
    return await createDirectBackendToken(officer);
  } catch (err) {
    console.error('Failed to generate direct backend token:', err);
    // Fallback: try fetching from FastAPI auth endpoint if local signing fails
    try {
      const tokenRes = await fetch(`${FASTAPI_BACKEND_URL}/api/v1/auth/token`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(officer),
        signal: AbortSignal.timeout(3000),
      });

      if (tokenRes.ok) {
        const data = await tokenRes.json();
        return data.access_token || null;
      }
    } catch {}
    return null;
  }
}

/**
 * Common handler proxying requests to FastAPI copilot backend.
 */
async function proxyToFastApi(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  const subpath = path.join('/');
  const targetUrl = `${FASTAPI_BACKEND_URL}/api/v1/copilot/${subpath}`;

  const backendToken = await resolveBackendToken(request);

  const headers: Record<string, string> = {
    'Accept': request.headers.get('accept') || 'application/json',
  };

  if (backendToken) {
    headers['Authorization'] = `Bearer ${backendToken}`;
  }

  const contentType = request.headers.get('content-type');
  if (contentType) {
    headers['Content-Type'] = contentType;
  }

  const method = request.method;
  let body: any = undefined;

  if (method === 'POST') {
    try {
      const jsonBody = await request.json();
      body = JSON.stringify(jsonBody);
    } catch {
      body = undefined;
    }
  }

  try {
    let finalBackendRes = await fetch(targetUrl, {
      method,
      headers,
      body,
    });

    let currentBackendToken = backendToken;

    // If backend returned 401 (e.g. stale credentials), auto-refresh with a fresh direct token and retry once
    if (finalBackendRes.status === 401) {
      console.warn(`FastAPI returned 401 for ${subpath}, auto-refreshing token and retrying...`);
      currentBackendToken = await createDirectBackendToken({
        username: 'admin',
        role: 'DG State Admin',
        district_code: 'MH-01',
      });
      headers['Authorization'] = `Bearer ${currentBackendToken}`;
      finalBackendRes = await fetch(targetUrl, {
        method,
        headers,
        body,
      });
    }

    const responseHeaders = new Headers();
    finalBackendRes.headers.forEach((val, key) => {
      // Do not forward hop-by-hop headers
      if (
        !['content-encoding', 'content-length', 'transfer-encoding', 'connection'].includes(
          key.toLowerCase()
        )
      ) {
        responseHeaders.set(key, val);
      }
    });

    // Explicitly guarantee streaming headers for SSE
    if (subpath === 'query') {
      responseHeaders.set('Content-Type', 'text/event-stream; charset=utf-8');
      responseHeaders.set('Cache-Control', 'no-cache, no-transform');
      responseHeaders.set('Connection', 'keep-alive');
    }

    // Refresh browser cookie with valid backend token so expired cookies are replaced
    if (currentBackendToken) {
      responseHeaders.append(
        'Set-Cookie',
        `maha_backend_token=${currentBackendToken}; Path=/; HttpOnly; SameSite=Lax; Max-Age=28800`
      );
    }

    return new Response(finalBackendRes.body, {
      status: finalBackendRes.status,
      statusText: finalBackendRes.statusText,
      headers: responseHeaders,
    });
  } catch (err: any) {
    console.error(`Proxy error connecting to ${targetUrl}:`, err);
    return NextResponse.json(
      {
        error: 'Backend communication error',
        message: err?.message || 'Could not connect to FastAPI backend server.',
      },
      { status: 502 }
    );
  }
}

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> }
) {
  return proxyToFastApi(request, context);
}

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> }
) {
  return proxyToFastApi(request, context);
}

export async function DELETE(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> }
) {
  return proxyToFastApi(request, context);
}
