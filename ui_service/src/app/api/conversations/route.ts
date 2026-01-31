import { NextRequest, NextResponse } from 'next/server';
import { readFileSync, writeFileSync, existsSync, mkdirSync, readdirSync, unlinkSync } from 'fs';
import { join } from 'path';

// Directory for storing conversations
const CONVERSATIONS_DIR = process.env.CONVERSATIONS_DIR || '/app/data/conversations';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  toolsUsed?: string[];
}

interface Conversation {
  id: string;
  title: string;
  summary?: string;
  messages: Message[];
  createdAt: string;
  updatedAt: string;
  messageCount: number;
}

interface ConversationMeta {
  id: string;
  title: string;
  summary?: string;
  createdAt: string;
  updatedAt: string;
  messageCount: number;
}

// Ensure conversations directory exists
function ensureDir() {
  if (!existsSync(CONVERSATIONS_DIR)) {
    mkdirSync(CONVERSATIONS_DIR, { recursive: true });
  }
}

// Generate a title from the first message
function generateTitle(messages: Message[]): string {
  const firstUserMessage = messages.find(m => m.role === 'user');
  if (!firstUserMessage) return 'New Conversation';
  
  // Truncate to first 50 chars
  const content = firstUserMessage.content;
  return content.length > 50 ? content.substring(0, 47) + '...' : content;
}

// GET - List all conversations or get specific conversation
export async function GET(request: NextRequest) {
  try {
    ensureDir();
    
    const { searchParams } = new URL(request.url);
    const id = searchParams.get('id');
    
    if (id) {
      // Get specific conversation
      const filePath = join(CONVERSATIONS_DIR, `${id}.json`);
      
      if (!existsSync(filePath)) {
        return NextResponse.json(
          { error: 'Conversation not found' },
          { status: 404 }
        );
      }
      
      const content = readFileSync(filePath, 'utf-8');
      const conversation: Conversation = JSON.parse(content);
      
      return NextResponse.json({ conversation });
    }
    
    // List all conversations (metadata only)
    const files = readdirSync(CONVERSATIONS_DIR)
      .filter(f => f.endsWith('.json'))
      .sort((a, b) => {
        // Sort by modification time, newest first
        const statA = readFileSync(join(CONVERSATIONS_DIR, a), 'utf-8');
        const statB = readFileSync(join(CONVERSATIONS_DIR, b), 'utf-8');
        const convA: Conversation = JSON.parse(statA);
        const convB: Conversation = JSON.parse(statB);
        return new Date(convB.updatedAt).getTime() - new Date(convA.updatedAt).getTime();
      });
    
    const conversations: ConversationMeta[] = files.map(file => {
      const content = readFileSync(join(CONVERSATIONS_DIR, file), 'utf-8');
      const conv: Conversation = JSON.parse(content);
      return {
        id: conv.id,
        title: conv.title,
        summary: conv.summary,
        createdAt: conv.createdAt,
        updatedAt: conv.updatedAt,
        messageCount: conv.messageCount,
      };
    });
    
    return NextResponse.json({ conversations });
  } catch (error: any) {
    console.error('[Conversations API] GET error:', error);
    return NextResponse.json(
      { error: error.message || 'Failed to load conversations' },
      { status: 500 }
    );
  }
}

// POST - Save or update conversation
export async function POST(request: NextRequest) {
  try {
    ensureDir();
    
    const body = await request.json();
    const { id, messages, summary } = body;
    
    if (!messages || !Array.isArray(messages)) {
      return NextResponse.json(
        { error: 'Messages array is required' },
        { status: 400 }
      );
    }
    
    const now = new Date().toISOString();
    const conversationId = id || `conv-${Date.now()}`;
    const filePath = join(CONVERSATIONS_DIR, `${conversationId}.json`);
    
    // Load existing or create new
    let conversation: Conversation;
    
    if (existsSync(filePath)) {
      const content = readFileSync(filePath, 'utf-8');
      conversation = JSON.parse(content);
      conversation.messages = messages;
      conversation.updatedAt = now;
      conversation.messageCount = messages.length;
      if (summary) {
        conversation.summary = summary;
      }
    } else {
      conversation = {
        id: conversationId,
        title: generateTitle(messages),
        summary: summary,
        messages: messages,
        createdAt: now,
        updatedAt: now,
        messageCount: messages.length,
      };
    }
    
    // Save to file
    writeFileSync(filePath, JSON.stringify(conversation, null, 2), 'utf-8');
    
    console.log(`[Conversations API] Saved conversation ${conversationId} with ${messages.length} messages`);
    
    return NextResponse.json({
      success: true,
      id: conversationId,
      messageCount: messages.length,
    });
  } catch (error: any) {
    console.error('[Conversations API] POST error:', error);
    return NextResponse.json(
      { error: error.message || 'Failed to save conversation' },
      { status: 500 }
    );
  }
}

// DELETE - Delete a conversation
export async function DELETE(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const id = searchParams.get('id');
    
    if (!id) {
      return NextResponse.json(
        { error: 'Conversation ID is required' },
        { status: 400 }
      );
    }
    
    const filePath = join(CONVERSATIONS_DIR, `${id}.json`);
    
    if (!existsSync(filePath)) {
      return NextResponse.json(
        { error: 'Conversation not found' },
        { status: 404 }
      );
    }
    
    unlinkSync(filePath);
    
    console.log(`[Conversations API] Deleted conversation ${id}`);
    
    return NextResponse.json({ success: true });
  } catch (error: any) {
    console.error('[Conversations API] DELETE error:', error);
    return NextResponse.json(
      { error: error.message || 'Failed to delete conversation' },
      { status: 500 }
    );
  }
}
