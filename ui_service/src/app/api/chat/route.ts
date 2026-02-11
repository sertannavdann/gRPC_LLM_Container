import { NextRequest, NextResponse } from 'next/server';
import { executeAgent } from '@/lib/grpc-client';

export async function POST(request: NextRequest) {
  try {
  const body = await request.json();
  const { message, threadId } = body;

    if (!message || typeof message !== 'string') {
      return NextResponse.json(
        { error: 'Message is required' },
        { status: 400 }
      );
    }

    console.log(`[API] Received message: ${message}`);

    // Call agent service via gRPC
    const response = await executeAgent(message, threadId);

    console.log(`[API] Agent response: ${response.final_answer?.substring(0, 100)}...`);

    // Extract tools used and thread id from sources if available
    let toolsUsed: string[] | undefined = undefined;
    let nextThreadId: string | undefined = threadId;
    try {
      if (response.sources) {
        const sources = JSON.parse(response.sources);
        if (Array.isArray(sources?.tools_used)) {
          // tools_used can be array of strings or objects {tool, status}
          // Normalize to array of tool name strings
          toolsUsed = sources.tools_used.map((t: string | { tool: string }) =>
            typeof t === 'string' ? t : t.tool || 'unknown'
          );
        }
        if (typeof sources?.thread_id === 'string') {
          nextThreadId = sources.thread_id;
        }
      }
    } catch {
      // Ignore parsing errors; return basic response
    }

    return NextResponse.json({
      response: response.final_answer,
      toolsUsed,
      threadId: nextThreadId,
    });
  } catch (error: any) {
    console.error('[API] Error:', error);
    return NextResponse.json(
      { error: error.message || 'Failed to process request' },
      { status: 500 }
    );
  }
}
