'use client';

import React, { useState, useEffect } from 'react';
import { 
  History, 
  MessageSquare, 
  Trash2, 
  Plus, 
  ChevronLeft,
  ChevronRight,
  Loader2,
  FileText
} from 'lucide-react';

interface ConversationMeta {
  id: string;
  title: string;
  summary?: string;
  createdAt: string;
  updatedAt: string;
  messageCount: number;
}

interface ConversationHistoryProps {
  currentConversationId?: string;
  onSelectConversation: (id: string) => void;
  onNewConversation: () => void;
  isOpen: boolean;
  onToggle: () => void;
}

export function ConversationHistory({
  currentConversationId,
  onSelectConversation,
  onNewConversation,
  isOpen,
  onToggle,
}: ConversationHistoryProps) {
  const [conversations, setConversations] = useState<ConversationMeta[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load conversations on mount and when panel opens
  useEffect(() => {
    if (isOpen) {
      loadConversations();
    }
  }, [isOpen]);

  const loadConversations = async () => {
    setLoading(true);
    setError(null);
    
    try {
      const response = await fetch('/api/conversations');
      const data = await response.json();
      
      if (!response.ok) {
        throw new Error(data.error || 'Failed to load conversations');
      }
      
      setConversations(data.conversations || []);
    } catch (err: any) {
      setError(err.message);
      console.error('Error loading conversations:', err);
    } finally {
      setLoading(false);
    }
  };

  const deleteConversation = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    
    if (!confirm('Delete this conversation?')) return;
    
    try {
      const response = await fetch(`/api/conversations?id=${id}`, {
        method: 'DELETE',
      });
      
      if (!response.ok) {
        throw new Error('Failed to delete conversation');
      }
      
      // Remove from list
      setConversations(prev => prev.filter(c => c.id !== id));
      
      // If deleted current conversation, start new one
      if (id === currentConversationId) {
        onNewConversation();
      }
    } catch (err: any) {
      console.error('Error deleting conversation:', err);
    }
  };

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
    
    if (diffDays === 0) {
      return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } else if (diffDays === 1) {
      return 'Yesterday';
    } else if (diffDays < 7) {
      return date.toLocaleDateString([], { weekday: 'short' });
    } else {
      return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
    }
  };

  // Collapsed state - just show toggle button
  if (!isOpen) {
    return (
      <div className="border-r bg-card h-full flex flex-col items-center py-4">
        <button
          onClick={onToggle}
          className="p-2 hover:bg-muted rounded-lg transition-colors"
          title="Show conversation history"
        >
          <ChevronRight className="h-5 w-5" />
        </button>
        <button
          onClick={onNewConversation}
          className="p-2 hover:bg-muted rounded-lg transition-colors mt-2"
          title="New conversation"
        >
          <Plus className="h-5 w-5" />
        </button>
      </div>
    );
  }

  return (
    <div className="w-64 border-r bg-card h-full flex flex-col">
      {/* Header */}
      <div className="p-3 border-b flex items-center justify-between">
        <div className="flex items-center gap-2">
          <History className="h-4 w-4" />
          <span className="font-medium text-sm">History</span>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={onNewConversation}
            className="p-1.5 hover:bg-muted rounded transition-colors"
            title="New conversation"
          >
            <Plus className="h-4 w-4" />
          </button>
          <button
            onClick={onToggle}
            className="p-1.5 hover:bg-muted rounded transition-colors"
            title="Hide history"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Conversation List */}
      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : error ? (
          <div className="p-3 text-sm text-destructive">{error}</div>
        ) : conversations.length === 0 ? (
          <div className="p-4 text-center text-sm text-muted-foreground">
            <MessageSquare className="h-8 w-8 mx-auto mb-2 opacity-50" />
            <p>No conversations yet</p>
            <p className="text-xs mt-1">Start chatting to save history</p>
          </div>
        ) : (
          <div className="py-2">
            {conversations.map((conv) => (
              <button
                key={conv.id}
                onClick={() => onSelectConversation(conv.id)}
                className={`w-full text-left px-3 py-2 hover:bg-muted transition-colors group ${
                  conv.id === currentConversationId ? 'bg-muted' : ''
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium truncate">
                      {conv.title}
                    </div>
                    {conv.summary && (
                      <div className="text-xs text-muted-foreground truncate mt-0.5 flex items-center gap-1">
                        <FileText className="h-3 w-3 flex-shrink-0" />
                        <span className="truncate">{conv.summary}</span>
                      </div>
                    )}
                    <div className="text-xs text-muted-foreground mt-1">
                      {conv.messageCount} messages • {formatDate(conv.updatedAt)}
                    </div>
                  </div>
                  <button
                    onClick={(e) => deleteConversation(conv.id, e)}
                    className="p-1 opacity-0 group-hover:opacity-100 hover:bg-destructive/10 hover:text-destructive rounded transition-all"
                    title="Delete conversation"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Footer with stats */}
      {conversations.length > 0 && (
        <div className="p-2 border-t text-xs text-muted-foreground text-center">
          {conversations.length} conversation{conversations.length !== 1 ? 's' : ''}
        </div>
      )}
    </div>
  );
}
