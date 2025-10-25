'use client';

import React, { useState } from 'react';
import { MessageList } from './MessageList';
import { ChatInput } from './ChatInput';
import { Message, ChatResponse } from '@/types/chat';
import { Bot } from 'lucide-react';

export function ChatContainer() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [threadId, setThreadId] = useState<string | undefined>(undefined);

  const handleSendMessage = async (content: string) => {
    // Add user message
    const userMessage: Message = {
      id: `user-${Date.now()}`,
      role: 'user',
      content,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setIsLoading(true);

    try {
      // Call API
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ message: content, threadId }),
      });

      const data: ChatResponse = await response.json();

      if (!response.ok) {
        throw new Error(data.error || 'Failed to get response');
      }

      // Persist/initialize thread id
      if (data.threadId && data.threadId !== threadId) {
        setThreadId(data.threadId);
      }

      // Add assistant message
      const assistantMessage: Message = {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        content: data.response,
        toolsUsed: data.toolsUsed,
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch (error) {
      console.error('Error sending message:', error);
      
      // Add error message
      const errorMessage: Message = {
        id: `error-${Date.now()}`,
        role: 'assistant',
        content: `Sorry, I encountered an error: ${error instanceof Error ? error.message : 'Unknown error'}`,
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-screen">
      {/* Header */}
      <header className="border-b bg-card p-4">
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center h-10 w-10 rounded-full bg-primary">
            <Bot className="h-6 w-6 text-primary-foreground" />
          </div>
          <div>
            <h1 className="text-lg font-semibold">Locally hosted LLM Orchestrator</h1>
            <p className="text-sm text-muted-foreground">by SAVDAN</p>
          </div>
        </div>
      </header>

      {/* Messages */}
      <MessageList messages={messages} isLoading={isLoading} />

      {/* Input */}
      <ChatInput onSend={handleSendMessage} disabled={isLoading} />
    </div>
  );
}
