import { NextRequest, NextResponse } from 'next/server';
import { executeAgent } from '@/lib/grpc-client';

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { message } = body;

    if (!message || typeof message !== 'string') {
      return NextResponse.json(
        { error: 'Message is required' },
        { status: 400 }
      );
    }

    console.log(`[API] Received message: ${message}`);

    // Call agent service via gRPC
    const response = await executeAgent(message);

    console.log(`[API] Agent response: ${response.final_answer?.substring(0, 100)}...`);

    return NextResponse.json({
      response: response.final_answer,
    });
  } catch (error: any) {
    console.error('[API] Error:', error);
    return NextResponse.json(
      { error: error.message || 'Failed to process request' },
      { status: 500 }
    );
  }
}
