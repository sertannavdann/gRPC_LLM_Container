import { NextRequest, NextResponse } from 'next/server';
import { executeAgent } from '@/lib/grpc-client';

interface Message {
  role: 'user' | 'assistant';
  content: string;
}

// Maximum messages before auto-summarization triggers
const AUTO_SUMMARIZE_THRESHOLD = 20;

// Summarization prompt template
const SUMMARIZE_PROMPT = `You are a conversation summarizer. Summarize the following conversation into a concise summary that captures:
1. Main topics discussed
2. Key decisions or conclusions reached
3. Important information shared
4. Any action items or follow-ups mentioned

Keep the summary under 200 words. Be factual and concise.

CONVERSATION:
{conversation}

SUMMARY:`;

// Format messages for summarization
function formatConversationForSummary(messages: Message[]): string {
  return messages
    .map(m => `${m.role.toUpperCase()}: ${m.content}`)
    .join('\n\n');
}

// POST - Generate summary for conversation
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { messages, force } = body;
    
    if (!messages || !Array.isArray(messages)) {
      return NextResponse.json(
        { error: 'Messages array is required' },
        { status: 400 }
      );
    }
    
    // Check if summarization is needed (unless forced)
    if (!force && messages.length < AUTO_SUMMARIZE_THRESHOLD) {
      return NextResponse.json({
        needed: false,
        message: `Summarization not needed yet (${messages.length}/${AUTO_SUMMARIZE_THRESHOLD} messages)`,
      });
    }
    
    console.log(`[Summarize API] Generating summary for ${messages.length} messages`);
    
    // Format conversation
    const conversationText = formatConversationForSummary(messages);
    const prompt = SUMMARIZE_PROMPT.replace('{conversation}', conversationText);
    
    // Call the local LLM via orchestrator
    // Note: This will use whatever provider is currently configured
    // For summarization, we want to use local to avoid API costs
    const response = await executeAgent(prompt);
    
    const summary = response.final_answer || 'Unable to generate summary';
    
    console.log(`[Summarize API] Generated summary: ${summary.substring(0, 100)}...`);
    
    return NextResponse.json({
      needed: true,
      summary: summary.trim(),
      messageCount: messages.length,
    });
  } catch (error: any) {
    console.error('[Summarize API] Error:', error);
    return NextResponse.json(
      { error: error.message || 'Failed to generate summary' },
      { status: 500 }
    );
  }
}

// GET - Check if summarization is needed
export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const countStr = searchParams.get('messageCount');
  
  if (!countStr) {
    return NextResponse.json(
      { error: 'messageCount parameter is required' },
      { status: 400 }
    );
  }
  
  const count = parseInt(countStr, 10);
  const needed = count >= AUTO_SUMMARIZE_THRESHOLD;
  
  return NextResponse.json({
    needed,
    threshold: AUTO_SUMMARIZE_THRESHOLD,
    current: count,
  });
}
