'use client';

import { useEffect, useState } from 'react';
import { Layers } from 'lucide-react';
import type { Engine, Task } from '@/types';
import { cancelTask } from '@/lib/api';
import { useBudgetFlow } from '@/hooks/useBudgetFlow';
import ResearchInput from './ResearchInput';
import TaskActions from './TaskActions';
import LogViewer from './LogViewer';
import ReportViewer from './ReportViewer';

interface MainPanelProps {
  selectedTask: Task | null;
  onSubmitResearch: (
    handle: string,
    engine: Engine,
    mandateId?: string,
    budgetUsd?: number,
    fluxaJwt?: string
  ) => Promise<void>;
  isSubmitting: boolean;
  onTaskUpdate: () => void;
}

export default function MainPanel({
  selectedTask,
  onSubmitResearch,
  isSubmitting,
  onTaskUpdate,
}: MainPanelProps) {
  const [activeView, setActiveView] = useState<'log' | 'report'>('report');
  const [isCancelling, setIsCancelling] = useState(false);
  const { pendingHandle, displayHandle, logExtraEntries, beginBudgetedResearch } = useBudgetFlow({
    selectedTask,
    onAuthorizedResearch: onSubmitResearch,
  });

  useEffect(() => {
    if (!selectedTask) {
      return;
    }

    const isRunning = selectedTask.status === 'running' || selectedTask.status === 'pending';
    setActiveView(isRunning ? 'log' : 'report');
  }, [selectedTask]);

  const handleCancel = async () => {
    if (!selectedTask || isCancelling) {
      return;
    }

    setIsCancelling(true);
    try {
      await cancelTask(selectedTask.task_id);
      onTaskUpdate();
    } catch (err) {
      console.error('Failed to cancel task:', err);
    } finally {
      setIsCancelling(false);
    }
  };

  const effectiveView = selectedTask ? activeView : 'log';
  const isRunningTask = selectedTask?.status === 'running' || selectedTask?.status === 'pending';

  return (
    <div className="workspace-main flex h-full min-w-0 flex-1 flex-col">
      {selectedTask || pendingHandle ? (
        <>
          <div className="border-b border-white/10 bg-black/50 px-6 py-5 backdrop-blur-sm md:px-8">
            <div className="mx-auto max-w-4xl">
              <div className="workspace-task-header flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-blue shadow-[0_10px_24px_rgba(69,191,255,0.25)]">
                  <span className="text-lg font-semibold text-black">
                    {displayHandle.replace('@', '').charAt(0).toUpperCase()}
                  </span>
                </div>
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <h2 className="truncate font-serif text-lg font-semibold text-white">{displayHandle}</h2>
                    {selectedTask?.engine ? (
                      <span
                        className={`inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium tracking-wide ${
                          selectedTask.engine === 'openai'
                            ? 'border border-emerald-500/20 bg-emerald-500/10 text-emerald-400'
                            : 'border border-orange-500/20 bg-orange-500/10 text-orange-400'
                        }`}
                      >
                        {selectedTask.engine === 'openai' ? 'OpenAI' : 'Claude'}
                      </span>
                    ) : (
                      <span className="inline-flex items-center rounded border border-white/10 bg-white/5 px-1.5 py-0.5 text-[10px] font-medium tracking-wide text-gray-400">
                        OpenAI
                      </span>
                    )}
                  </div>
                  {selectedTask ? (
                    <p className="mt-0.5 font-mono text-xs text-gray-500">ID: {selectedTask.task_id.slice(0, 8)}</p>
                  ) : (
                    <p className="mt-0.5 font-mono text-xs text-gray-500">Awaiting budget authorization</p>
                  )}
                </div>
              </div>
            </div>
          </div>

          <div className="flex min-h-0 flex-1 flex-col bg-black">
            {effectiveView === 'log' ? (
              <LogViewer
                taskId={selectedTask?.task_id}
                isRunning={Boolean(pendingHandle) || Boolean(isRunningTask)}
                extraEntries={logExtraEntries}
              />
            ) : (
              selectedTask && <ReportViewer taskId={selectedTask.task_id} />
            )}
          </div>

          {selectedTask && (
            <div className="border-t border-white/10 bg-black/70 p-4 backdrop-blur-sm">
              <div className="mx-auto max-w-4xl">
                <TaskActions
                  task={selectedTask}
                  activeView={activeView}
                  onViewChange={setActiveView}
                  onCancel={selectedTask.status === 'running' ? handleCancel : undefined}
                  isCancelling={isCancelling}
                />
              </div>
            </div>
          )}
        </>
      ) : (
        <div className="workspace-empty corner-frame flex flex-1 flex-col items-center justify-center p-8">
          <div className="mb-10 text-center">
            <div className="mb-6 inline-flex h-20 w-20 items-center justify-center rounded-2xl bg-brand-blue shadow-[0_18px_42px_rgba(69,191,255,0.2)]">
              <Layers className="h-10 w-10 text-black" />
            </div>
            <h1 className="mb-3 font-serif text-3xl font-semibold tracking-tight text-white">
              AVA Frontend
            </h1>
            <p className="max-w-md leading-relaxed text-gray-400">
              Enter a Twitter handle to generate a research brief with live logs, structured report output,
              and budget-aware task tracking.
            </p>
          </div>

          <ResearchInput onSubmit={beginBudgetedResearch} isSubmitting={isSubmitting} />

          <div className="mt-16 text-center">
            <p className="font-mono text-xs tracking-wider text-gray-600">DEMO-FIRST, LIVE-READY</p>
          </div>
        </div>
      )}
    </div>
  );
}
