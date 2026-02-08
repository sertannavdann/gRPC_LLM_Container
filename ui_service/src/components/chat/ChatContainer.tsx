'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { MessageList } from './MessageList';
import { ChatInput } from './ChatInput';
import { SettingsPanel } from '../settings/SettingsPanel';
import { ConversationHistory } from '../history/ConversationHistory';
import { Dashboard } from '../dashboard';
import { Message, ChatResponse } from '@/types/chat';
import { Bot, Settings, Save, FileText, LayoutDashboard, PanelRightClose, PanelRight, Maximize2 } from 'lucide-react';

// Auto-save debounce delay in ms
const AUTO_SAVE_DELAY = 2000;
// Message threshold for auto-summarization
const SUMMARIZE_THRESHOLD = 20;

export function ChatContainer() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [threadId, setThreadId] = useState<string | undefined>(undefined);
  const [conversationId, setConversationId] = useState<string | undefined>(undefined);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isHistoryOpen, setIsHistoryOpen] = useState(true);
  const [isDashboardOpen, setIsDashboardOpen] = useState(false);
  const [isDashboardFullscreen, setIsDashboardFullscreen] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [lastSaved, setLastSaved] = useState<Date | null>(null);
  const [summary, setSummary] = useState<string | undefined>(undefined);

  // Auto-save conversation when messages change
  useEffect(() => {
    if (messages.length === 0) return;
    
    const timer = setTimeout(() => {
      saveConversation();
    }, AUTO_SAVE_DELAY);
    
    return () => clearTimeout(timer);
  }, [messages]);

  // Check if summarization is needed
  useEffect(() => {
    if (messages.length > 0 && messages.length % SUMMARIZE_THRESHOLD === 0) {
      generateSummary();
    }
  }, [messages.length]);

  const saveConversation = async () => {
    if (messages.length === 0) return;
    
    setIsSaving(true);
    
    try {
      // Serialize messages for storage
      const serializedMessages = messages.map(m => ({
        ...m,
        timestamp: m.timestamp instanceof Date ? m.timestamp.toISOString() : m.timestamp,
      }));
      
      const response = await fetch('/api/conversations', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          id: conversationId,
          messages: serializedMessages,
          summary,
        }),
      });
      
      const data = await response.json();
      
      if (response.ok && data.id) {
        setConversationId(data.id);
        setLastSaved(new Date());
      }
    } catch (error) {
      console.error('Failed to save conversation:', error);
    } finally {
      setIsSaving(false);
    }
  };

  const generateSummary = async () => {
    if (messages.length < SUMMARIZE_THRESHOLD) return;
    
    try {
      const serializedMessages = messages.map(m => ({
        role: m.role,
        content: m.content,
      }));
      
      const response = await fetch('/api/summarize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: serializedMessages }),
      });
      
      const data = await response.json();
      
      if (data.summary) {
        setSummary(data.summary);
        console.log('Generated conversation summary');
      }
    } catch (error) {
      console.error('Failed to generate summary:', error);
    }
  };

  const loadConversation = async (id: string) => {
    try {
      const response = await fetch(`/api/conversations?id=${id}`);
      const data = await response.json();
      
      if (data.conversation) {
        const loadedMessages: Message[] = data.conversation.messages.map((m: any) => ({
          ...m,
          timestamp: new Date(m.timestamp),
        }));
        
        setMessages(loadedMessages);
        setConversationId(data.conversation.id);
        setSummary(data.conversation.summary);
        setThreadId(undefined); // Reset thread for new LLM context
      }
    } catch (error) {
      console.error('Failed to load conversation:', error);
    }
  };

  const startNewConversation = () => {
    setMessages([]);
    setConversationId(undefined);
    setThreadId(undefined);
    setSummary(undefined);
    setLastSaved(null);
  };

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
    <div className="flex h-full">
      {/* Conversation History Sidebar */}
      <ConversationHistory
        currentConversationId={conversationId}
        onSelectConversation={loadConversation}
        onNewConversation={startNewConversation}
        isOpen={isHistoryOpen}
        onToggle={() => setIsHistoryOpen(!isHistoryOpen)}
      />

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <header className="border-b bg-card p-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="flex items-center justify-center h-10 w-10 rounded-full bg-primary">
                <Bot className="h-6 w-6 text-primary-foreground" />
              </div>
              <div>
                <h1 className="text-lg font-semibold">LLM Orchestrator</h1>
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <span>Multi-Provider Agent Framework</span>
                  {isSaving && (
                    <span className="flex items-center gap-1 text-xs">
                      <Save className="h-3 w-3 animate-pulse" />
                      Saving...
                    </span>
                  )}
                  {!isSaving && lastSaved && (
                    <span className="text-xs opacity-60">
                      Saved {lastSaved.toLocaleTimeString()}
                    </span>
                  )}
                </div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {summary && (
                <div className="flex items-center gap-1 px-2 py-1 text-xs bg-muted rounded" title={summary}>
                  <FileText className="h-3 w-3" />
                  <span className="max-w-32 truncate">Summary available</span>
                </div>
              )}
              <button
                onClick={() => setIsDashboardFullscreen(true)}
                className="flex items-center gap-2 px-3 py-2 text-sm rounded-lg border hover:bg-muted transition-colors"
                title="Open Dashboard Fullscreen"
              >
                <Maximize2 className="h-4 w-4" />
              </button>
              <button
                onClick={() => setIsDashboardOpen(!isDashboardOpen)}
                className={`flex items-center gap-2 px-3 py-2 text-sm rounded-lg border transition-colors ${
                  isDashboardOpen ? 'bg-primary text-primary-foreground' : 'hover:bg-muted'
                }`}
                title={isDashboardOpen ? 'Hide Dashboard' : 'Show Dashboard'}
              >
                <LayoutDashboard className="h-4 w-4" />
                {isDashboardOpen ? (
                  <PanelRightClose className="h-4 w-4" />
                ) : (
                  <PanelRight className="h-4 w-4" />
                )}
              </button>
              <button
                onClick={() => setIsSettingsOpen(true)}
                className="flex items-center gap-2 px-3 py-2 text-sm rounded-lg border hover:bg-muted transition-colors"
              >
                <Settings className="h-4 w-4" />
                Settings
              </button>
            </div>
          </div>
        </header>

        {/* Messages */}
        <MessageList messages={messages} isLoading={isLoading} />

        {/* Input */}
        <ChatInput onSend={handleSendMessage} disabled={isLoading} />
      </div>

      {/* Dashboard Panel - Side Panel */}
      {isDashboardOpen && !isDashboardFullscreen && (
        <div className="w-[min(450px,40vw)] min-w-[320px] border-l border-gray-800 flex-shrink-0 overflow-hidden">
          <Dashboard 
            onToggleFullscreen={() => setIsDashboardFullscreen(true)}
            onClose={() => setIsDashboardOpen(false)}
          />
        </div>
      )}

      {/* Dashboard Fullscreen */}
      {isDashboardFullscreen && (
        <Dashboard 
          isFullscreen={true}
          onToggleFullscreen={() => setIsDashboardFullscreen(false)}
          onClose={() => {
            setIsDashboardFullscreen(false);
            setIsDashboardOpen(false);
          }}
        />
      )}

      {/* Settings Panel */}
      <SettingsPanel isOpen={isSettingsOpen} onClose={() => setIsSettingsOpen(false)} />
    </div>
  );
}
