export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  toolsUsed?: string[];
}

export interface ChatResponse {
  response: string;
  toolsUsed?: string[];
  threadId?: string;
  error?: string;
}
