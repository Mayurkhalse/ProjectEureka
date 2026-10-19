import { NextRequest, NextResponse } from 'next/server';
import { MOCK_USERS } from '@/lib/serverData';
import { executeLiveIncidentAction } from '@/lib/backendClient';

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const body = await request.json();
    const { action, username } = body;

    const matchedUser = username ? MOCK_USERS[username]?.user : null;
    const role = matchedUser?.role || body.role;

    // Enforce role authorization: DIO desk cannot authorize official rebuttals
    if (role === 'dio_desk') {
      return NextResponse.json(
        {
          success: false,
          message: 'Permission Denied: District Collector or DG State Admin clearance required to authorize official government rebuttals.',
        },
        { status: 403 }
      );
    }

    if (!['authorize', 'issue_advisory', 'request_edits'].includes(action)) {
      return NextResponse.json(
        { success: false, message: 'Invalid action type.' },
        { status: 400 }
      );
    }

    const authUser = matchedUser || {
      id: 'collector',
      username: username || 'collector_palghar',
      name: 'Vikram S. Mahajan, IAS',
      marathiName: 'विक्रम एस. महाजन',
      role: 'collector',
      designation: 'Collector',
      division: 'Konkan',
      district: 'Palghar',
      avatarInitials: 'VM',
      permittedDivisions: ['Konkan'],
      permittedDistricts: ['Palghar'],
      canAuthorizeRebuttals: true,
    };

    const authHeader = request.headers.get('authorization') || undefined;
    const token = authHeader?.startsWith('Bearer ') ? authHeader.substring(7) : undefined;

    const updated = await executeLiveIncidentAction(
      id,
      action as 'authorize' | 'issue_advisory' | 'request_edits',
      authUser,
      token
    );

    if (!updated) {
      return NextResponse.json(
        { success: false, message: 'Incident not found.' },
        { status: 404 }
      );
    }

    return NextResponse.json({
      success: true,
      message:
        action === 'authorize'
          ? 'Rebuttal authorized and dispatched successfully.'
          : action === 'issue_advisory'
          ? 'Press advisory issued to media houses.'
          : 'Returned to DIO for field edits.',
      data: updated,
    });
  } catch (error) {
    return NextResponse.json(
      { success: false, message: 'Server error updating incident.', error: String(error) },
      { status: 500 }
    );
  }
}
