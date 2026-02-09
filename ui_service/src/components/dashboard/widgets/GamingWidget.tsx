/**
 * Gaming Widget
 *
 * Displays gaming profile stats and recent battle history.
 * Currently supports Clash Royale.
 */
'use client';

import React from 'react';
import { GamingContext, GamingProfile, GamingMatch } from '@/types/dashboard';
import {
  Gamepad2,
  Trophy,
  Swords,
  TrendingUp,
  TrendingDown,
  Maximize2,
  Minimize2,
  Crown,
  Shield,
} from 'lucide-react';

interface GamingWidgetProps {
  data: GamingContext | null;
  expanded?: boolean;
  onFocus?: () => void;
  onCollapse?: () => void;
}

export function GamingWidget({ data, expanded, onFocus, onCollapse }: GamingWidgetProps) {
  if (!data || data.profiles.length === 0) {
    return (
      <div className="bg-gray-800 rounded-xl p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Gamepad2 className="w-4 h-4 text-purple-400" />
            <span className="font-medium text-sm">Gaming</span>
          </div>
          {onFocus && (
            <button onClick={onFocus} className="p-1 hover:bg-gray-700 rounded transition-colors">
              <Maximize2 className="w-3.5 h-3.5 text-gray-500" />
            </button>
          )}
        </div>
        <p className="text-sm text-gray-500 text-center py-6">
          No gaming data. Connect Clash Royale in Integrations.
        </p>
      </div>
    );
  }

  const profile = data.profiles[0];
  const recentBattles: GamingMatch[] = (profile.metadata?.recent_battles as GamingMatch[]) || [];

  return (
    <div className={`bg-gray-800 rounded-xl p-4 ${expanded ? 'min-h-[400px]' : ''}`}>
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Gamepad2 className="w-4 h-4 text-purple-400" />
          <span className="font-medium text-sm">Gaming</span>
        </div>
        {expanded && onCollapse ? (
          <button onClick={onCollapse} className="p-1 hover:bg-gray-700 rounded transition-colors">
            <Minimize2 className="w-3.5 h-3.5 text-gray-500" />
          </button>
        ) : onFocus ? (
          <button onClick={onFocus} className="p-1 hover:bg-gray-700 rounded transition-colors">
            <Maximize2 className="w-3.5 h-3.5 text-gray-500" />
          </button>
        ) : null}
      </div>

      {/* Player info */}
      <div className="flex items-center gap-3 mb-4">
        <div className="w-10 h-10 rounded-full bg-purple-500/20 flex items-center justify-center">
          <Crown className="w-5 h-5 text-purple-400" />
        </div>
        <div>
          <div className="font-semibold">{profile.username}</div>
          <div className="text-xs text-gray-500">
            {profile.arena || `Level ${profile.level}`}
            {profile.clan_name && ` · ${profile.clan_name}`}
          </div>
        </div>
        <div className="ml-auto text-right">
          <div className="flex items-center gap-1 text-yellow-400">
            <Trophy className="w-4 h-4" />
            <span className="font-bold">{profile.trophies.toLocaleString()}</span>
          </div>
        </div>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-3 gap-3 mb-4">
        <div className="bg-gray-700/50 rounded-lg px-3 py-2 text-center">
          <div className="text-sm font-medium text-green-400">{profile.wins.toLocaleString()}</div>
          <div className="text-xs text-gray-500">Wins</div>
        </div>
        <div className="bg-gray-700/50 rounded-lg px-3 py-2 text-center">
          <div className="text-sm font-medium text-red-400">{profile.losses.toLocaleString()}</div>
          <div className="text-xs text-gray-500">Losses</div>
        </div>
        <div className="bg-gray-700/50 rounded-lg px-3 py-2 text-center">
          <div className="text-sm font-medium">{(profile.win_rate * 100).toFixed(1)}%</div>
          <div className="text-xs text-gray-500">Win Rate</div>
        </div>
      </div>

      {/* Recent battles */}
      {recentBattles.length > 0 && (
        <div>
          <div className="text-xs font-medium text-gray-500 mb-2 uppercase tracking-wider">Recent Battles</div>
          <div className="space-y-1.5">
            {recentBattles.slice(0, expanded ? 10 : 5).map((battle, i) => (
              <BattleRow key={battle.id || i} battle={battle} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function BattleRow({ battle }: { battle: GamingMatch }) {
  const isWin = battle.result === 'win';
  const time = new Date(battle.timestamp);
  const timeStr = time.toLocaleDateString('en-CA', { month: 'short', day: 'numeric' });

  return (
    <div className="flex items-center gap-2 px-2 py-1.5 bg-gray-700/30 rounded-lg">
      <div className={`w-1.5 h-1.5 rounded-full ${isWin ? 'bg-green-500' : 'bg-red-500'}`} />
      <div className="flex-1 min-w-0">
        <span className="text-xs">
          {battle.opponent_name || 'Opponent'}
        </span>
      </div>
      <div className={`flex items-center gap-1 text-xs ${
        battle.trophies_change > 0 ? 'text-green-400' : battle.trophies_change < 0 ? 'text-red-400' : 'text-gray-500'
      }`}>
        {battle.trophies_change > 0 ? (
          <TrendingUp className="w-3 h-3" />
        ) : battle.trophies_change < 0 ? (
          <TrendingDown className="w-3 h-3" />
        ) : null}
        {battle.trophies_change > 0 ? '+' : ''}{battle.trophies_change}
      </div>
      <span className="text-xs text-gray-600">{timeStr}</span>
    </div>
  );
}
