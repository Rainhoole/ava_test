'use client';

import Image from 'next/image';
import { useState } from 'react';
import { Plus, Search, MessageSquare, Loader2, CheckCircle, XCircle, Clock, X } from 'lucide-react';
import { Task, TaskStatus } from '@/types';
import { formatRelativeTime, truncateHandle, cn } from '@/lib/utils';

interface SidebarProps {
  tasks: Task[];
  selectedTaskId: string | null;
  onSelectTask: (task: Task | null) => void;
  onNewResearch: () => void;
  isLoading: boolean;
}

function StatusIcon({ status }: { status: TaskStatus }) {
  switch (status) {
    case 'pending':
      return <Clock className="w-3 h-3" />;
    case 'running':
      return <Loader2 className="w-3 h-3 animate-spin" />;
    case 'completed':
      return <CheckCircle className="w-3 h-3" />;
    case 'failed':
      return <XCircle className="w-3 h-3" />;
    case 'cancelled':
      return <X className="w-3 h-3" />;
    default:
      return null;
  }
}

function getStatusStyles(status: TaskStatus): string {
  switch (status) {
    case 'pending':
      return 'bg-amber-500/10 text-amber-400 border border-amber-500/20';
    case 'running':
      return 'bg-sky-500/10 text-sky-400 border border-sky-500/20';
    case 'completed':
      return 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20';
    case 'failed':
      return 'bg-red-500/10 text-red-400 border border-red-500/20';
    case 'cancelled':
      return 'bg-white/5 text-gray-400 border border-white/10';
    default:
      return 'bg-white/5 text-gray-400 border border-white/10';
  }
}

export default function Sidebar({
  tasks,
  selectedTaskId,
  onSelectTask,
  onNewResearch,
  isLoading,
}: SidebarProps) {
  const [searchQuery, setSearchQuery] = useState('');

  const filteredTasks = tasks.filter((task) =>
    task.handle.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="hidden md:flex w-72 h-full flex-col workspace-sidebar">
      {/* Header with Logo */}
      <div className="p-4 border-b border-white/10">
        <div className="flex items-center gap-2 mb-4">
          <Image src="/reforge-logo.png" alt="Reforge" width={90} height={20} className="h-5 w-auto" />
        </div>
        <button
          onClick={onNewResearch}
          className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-brand-blue text-black hover:bg-brand-blue-hover transition-colors text-sm font-semibold"
        >
          <Plus className="w-4 h-4" />
          <span>New Research</span>
        </button>
      </div>

      {/* Search */}
      <div className="p-4">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
          <input
            type="text"
            placeholder="Search tasks..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2.5 bg-white/[0.04] rounded-xl text-sm text-white placeholder-gray-500 border border-white/10 focus:outline-none focus:ring-2 focus:ring-brand-blue/20 focus:border-brand-blue/30 transition-all"
          />
        </div>
      </div>

      {/* Task List */}
      <div className="flex-1 overflow-y-auto px-3">
        {isLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="w-5 h-5 animate-spin text-gray-500" />
          </div>
        ) : filteredTasks.length === 0 ? (
          <div className="text-center py-8 text-gray-500 text-sm">
            {searchQuery ? 'No matching tasks' : 'No research tasks yet'}
          </div>
        ) : (
          <div className="space-y-2 pb-4">
            {filteredTasks.map((task) => (
              <button
                key={task.task_id}
                onClick={() => onSelectTask(task)}
                className={cn(
                  'w-full text-left p-3 rounded-2xl transition-all group',
                  selectedTaskId === task.task_id
                    ? 'bg-white/[0.07] border border-brand-blue/30 shadow-[0_0_0_1px_rgba(69,191,255,0.12)_inset]'
                    : 'hover:bg-white/[0.03] border border-transparent'
                )}
              >
                <div className="flex items-start gap-3">
                  <div className="w-8 h-8 rounded-lg bg-white/[0.06] flex items-center justify-center flex-shrink-0 mt-0.5">
                    <MessageSquare className="w-4 h-4 text-gray-500" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="font-medium text-white text-sm truncate">
                      {truncateHandle(task.handle, 20)}
                    </div>
                    <div className="flex items-center gap-1.5 mt-1.5">
                      <span
                        className={cn(
                          'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium',
                          getStatusStyles(task.status)
                        )}
                      >
                        <StatusIcon status={task.status} />
                        <span className="capitalize">{task.status}</span>
                      </span>
                      {task.engine && (
                        <span className={cn(
                          'px-1.5 py-0.5 rounded text-[10px] font-medium',
                          task.engine === 'openai'
                            ? 'bg-emerald-500/10 text-emerald-400'
                            : 'bg-orange-500/10 text-orange-400'
                        )}>
                          {task.engine === 'openai' ? 'OAI' : 'CLD'}
                        </span>
                      )}
                    </div>
                    <div className="text-xs text-gray-500 mt-1">
                      {formatRelativeTime(task.created_at)}
                    </div>
                  </div>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="p-4 border-t border-white/10">
        <div className="text-xs text-gray-500 text-center font-mono tracking-widest">
          {tasks.length} TASK{tasks.length !== 1 ? 'S' : ''}
        </div>
      </div>
    </div>
  );
}
