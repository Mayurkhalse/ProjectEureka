import { NextRequest, NextResponse } from 'next/server';
import { MOCK_USERS } from '@/lib/serverData';
import { signAuthToken, JWT_TTL_SECONDS, JWT_TTL_HOURS } from '@/lib/jwt';
import { FASTAPI_BACKEND_URL } from '@/lib/backendClient';

const EMAIL_ALIAS_MAP: Record<string, string> = {
  'director.konkan@maharashtra.gov.in': 'director_konkan',
  'director_konkan@maharashtra.gov.in': 'director_konkan',
  'collector.palghar@maharashtra.gov.in': 'collector_palghar',
  'collector_palghar@maharashtra.gov.in': 'collector_palghar',
  'collector.thane@maharashtra.gov.in': 'collector_thane',
  'collector_thane@maharashtra.gov.in': 'collector_thane',
  'dio.konkan@maharashtra.gov.in': 'operator_konkan',
  'operator_konkan@dgipr.maharashtra.gov.in': 'operator_konkan',
  'operator_konkan@maharashtra.gov.in': 'operator_konkan',
  'dg.gokhale@maharashtra.gov.in': 'admin',
  'admin@maharashtra.gov.in': 'admin',
  'mh-dgipr-konkan-04': 'operator_konkan',
  'mh-dgipr-dir-01': 'director_konkan',
  'mh-dm-palghar-01': 'collector_palghar',
  'mh-dm-thane-01': 'collector_thane',
  'mh-state-dg-01': 'admin',
};

const BACKEND_ROLE_MAP: Record<string, string> = {
  dg_admin: 'DG State Admin',
  director_konkan: 'DG State Admin',
  collector: 'District Collector',
  dio_desk: 'DIO Desk',
};

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { username, pin } = body;

    if (!username || !pin) {
      return NextResponse.json(
        { success: false, message: 'Username and PIN are required.' },
        { status: 400 }
      );
    }

    const normalized = String(username).toLowerCase().trim();
    const resolvedUsername = EMAIL_ALIAS_MAP[normalized] || normalized;

    const matched = MOCK_USERS[resolvedUsername] || MOCK_USERS[username];
    if (!matched || matched.pin !== pin) {
      return NextResponse.json(
        { success: false, message: 'Invalid credentials. Please verify your officer ID and PIN.' },
        { status: 401 }
      );
    }

    // Sign cryptographic HMAC-SHA256 JWT token with 12 hours TTL (43,200s)
    const token = await signAuthToken(matched.user, '12h');

    // Attempt to acquire signed FastAPI backend JWT token
    let backendToken: string | null = null;
    try {
      const backendRole = BACKEND_ROLE_MAP[matched.user.role] || 'DIO Desk';
      const districtCode = matched.user.district === 'Palghar' ? 'MH-04' : (matched.user.district === 'Thane' ? 'MH-03' : 'MH-01');
      const backendRes = await fetch(`${FASTAPI_BACKEND_URL}/api/v1/auth/token`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: matched.user.username,
          role: backendRole,
          district_code: districtCode,
        }),
        signal: AbortSignal.timeout(3000),
      });
      if (backendRes.ok) {
        const tokenJson = await backendRes.json();
        backendToken = tokenJson.access_token || null;
      }
    } catch {
      // Backend not running synchronously - continue gracefully
    }

    const response = NextResponse.json({
      success: true,
      message: 'Authentication successful.',
      token,
      backendToken,
      ttlHours: JWT_TTL_HOURS,
      expiresIn: JWT_TTL_SECONDS,
      user: matched.user,
    });

    // Set HTTP-Only JWT Cookie with 12 hours TTL
    response.cookies.set('maha_auth_token', token, {
      httpOnly: true,
      path: '/',
      maxAge: JWT_TTL_SECONDS, // 12 hours (43,200 seconds)
      sameSite: 'lax',
      secure: process.env.NODE_ENV === 'production',
    });

    if (backendToken) {
      response.cookies.set('maha_backend_token', backendToken, {
        httpOnly: true,
        path: '/',
        maxAge: JWT_TTL_SECONDS,
        sameSite: 'lax',
        secure: process.env.NODE_ENV === 'production',
      });
    }

    // Client-accessible user metadata cookie synchronized with 12 hours TTL
    response.cookies.set('maha_auth_user', JSON.stringify(matched.user), {
      httpOnly: false,
      path: '/',
      maxAge: JWT_TTL_SECONDS, // 12 hours (43,200 seconds)
      sameSite: 'lax',
      secure: process.env.NODE_ENV === 'production',
    });

    return response;
  } catch (error) {
    return NextResponse.json(
      { success: false, message: 'Server error during authentication.', error: String(error) },
      { status: 500 }
    );
  }
}
