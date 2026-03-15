'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { Layers } from 'lucide-react';
import { Task, Engine, BudgetEntry } from '@/types';
import { cancelTask, retryResearch } from '@/lib/api';
import {
  createIntentMandate,
  DEFAULT_BUDGET_USD,
  formatUSD,
  ensureAuthenticated,
  fetchMandateById,
} from '@/lib/fluxa';
import ResearchInput from './ResearchInput';
import TaskActions from './TaskActions';
import LogViewer from './LogViewer';
import ReportViewer from './ReportViewer';

const MANDATE_POLL_INTERVAL_MS = 5000;
const MANDATE_POLL_TIMEOUT_MS = 30 * 60 * 1000;

interface MainPanelProps {
  selectedTask: Task | null;
  onSubmitResearch: (handle: string, engine: Engine, mandateId?: string, budgetUsd?: number, fluxaJwt?: string, file?: File) => Promise<void>;
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
  const [isRetryingResearch, setIsRetryingResearch] = useState(false);
  const [pendingHandle, setPendingHandle] = useState<string | null>(null);
  const [pendingEngine, setPendingEngine] = useState<Engine>('openai');
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [budgetEntries, setBudgetEntries] = useState<BudgetEntry[]>([]);
  const [budgetHandle, setBudgetHandle] = useState<string | null>(null);
  const [budgetStep, setBudgetStep] = useState<'idle' | 'ask' | 'creating' | 'authorize' | 'waiting' | 'done'>('idle');
  const [mandateId, setMandateId] = useState<string | null>(null);
  const [authUrl, setAuthUrl] = useState<string | null>(null);
  const budgetSeqRef = useRef(1);
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollStartedAtRef = useRef<number | null>(null);
  const pendingHandleRef = useRef<string | null>(null);
  const pendingEngineRef = useRef<Engine>('openai');
  const pendingFileRef = useRef<File | null>(null);
  const isCreatingRef = useRef(false);

  const formatBudgetTimestamp = () =>
    new Date().toLocaleTimeString('en-GB', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    });

  const addBudgetEntry = (entry: Omit<BudgetEntry, 'type' | 'seq' | 'ts'>) => {
    setBudgetEntries((prev) => [
      ...prev,
      {
        type: 'budget',
        seq: 900000 + budgetSeqRef.current++,
        ts: formatBudgetTimestamp(),
        ...entry,
      },
    ]);
  };

  const clearBudgetActions = () => {
    setBudgetEntries((prev) =>
      prev.map((entry) => ({ ...entry, actions: undefined }))
    );
  };

  const stopPolling = useCallback(() => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
    pollStartedAtRef.current = null;
  }, []);

  const resetBudgetFlow = () => {
    stopPolling();
    setBudgetEntries([]);
    setBudgetHandle(null);
    setBudgetStep('idle');
    setMandateId(null);
    setAuthUrl(null);
    budgetSeqRef.current = 1;
  };

  // Auto-switch view based on task status
  useEffect(() => {
    if (selectedTask) {
      const isRunning = selectedTask.status === 'running' || selectedTask.status === 'pending';
      const isFailed = selectedTask.status === 'failed' || selectedTask.status === 'cancelled';
      const isPaymentFailed = selectedTask.payment_status === 'failed';
      // Show log for running/failed/cancelled tasks, or when payment failed (report is locked)
      setActiveView(isRunning || isFailed || isPaymentFailed ? 'log' : 'report');
    }
  }, [selectedTask?.task_id, selectedTask?.status, selectedTask?.payment_status]);

  useEffect(() => {
    pendingHandleRef.current = pendingHandle;
  }, [pendingHandle]);

  useEffect(() => {
    pendingEngineRef.current = pendingEngine;
  }, [pendingEngine]);

  useEffect(() => {
    if (selectedTask && pendingHandle && selectedTask.handle === pendingHandle) {
      setPendingHandle(null);
    }
  }, [selectedTask?.task_id, selectedTask?.handle, pendingHandle]);

  useEffect(() => {
    if (selectedTask && budgetHandle && selectedTask.handle !== budgetHandle) {
      setBudgetEntries([]);
      setBudgetHandle(null);
    }
  }, [selectedTask?.task_id, selectedTask?.handle, budgetHandle]);

  useEffect(() => {
    return () => {
      stopPolling();
    };
  }, [stopPolling]);

  const handleCancel = async () => {
    if (!selectedTask || isCancelling) return;
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

  const handleRetryResearch = async () => {
    if (!selectedTask || isRetryingResearch) return;
    setIsRetryingResearch(true);
    try {
      await retryResearch(selectedTask.task_id);
      onTaskUpdate();
    } catch (err) {
      console.error('Failed to retry research:', err);
    } finally {
      setIsRetryingResearch(false);
    }
  };

  const handleBudgetCancel = () => {
    resetBudgetFlow();
    setPendingHandle(null);
    setPendingFile(null);
    pendingHandleRef.current = null;
    pendingFileRef.current = null;
  };

  const handleApproveBudget = async () => {
    const currentHandle = pendingHandleRef.current ?? pendingHandle;
    if (!currentHandle || isCreatingRef.current) return;

    isCreatingRef.current = true;
    setBudgetStep('creating');
    clearBudgetActions();
    addBudgetEntry({
      role: 'assistant',
      content: 'Creating budget request...',
    });

    try {
      const result = await createIntentMandate(
        DEFAULT_BUDGET_USD,
        1,
        `Research budget for ${currentHandle}: ${formatUSD(DEFAULT_BUDGET_USD)} USDC`
      );

      if (!pendingHandleRef.current) {
        return;
      }

      if (result.success && result.mandateId && result.authorizationUrl) {
        setMandateId(result.mandateId);
        setAuthUrl(result.authorizationUrl);
        setBudgetStep('authorize');

        addBudgetEntry({
          role: 'assistant',
          content: 'Budget request created. Go to wallet to approve — I will check automatically.',
          actions: [
            {
              id: 'open-wallet',
              label: 'Go to wallet',
              variant: 'primary',
              onClick: () => handleOpenWallet(result.authorizationUrl, result.mandateId),
            },
            {
              id: 'cancel-authorization',
              label: 'Cancel',
              variant: 'secondary',
              onClick: handleBudgetCancel,
            },
          ],
        });
      } else {
        setBudgetStep('idle');
        addBudgetEntry({
          role: 'system',
          content: `Failed to create budget: ${result.error || 'Unknown error'}`,
        });
        addBudgetEntry({
          role: 'assistant',
          content: 'Try again when you are ready.',
          actions: [
            {
              id: 'retry-budget',
              label: 'Retry',
              variant: 'primary',
              onClick: handleApproveBudget,
            },
            {
              id: 'cancel-budget',
              label: 'Cancel',
              variant: 'secondary',
              onClick: handleBudgetCancel,
            },
          ],
        });
      }
    } finally {
      isCreatingRef.current = false;
    }
  };

  const startPolling = (currentMandateId: string) => {
    stopPolling();
    pollStartedAtRef.current = Date.now();
    let inFlight = false;

    pollTimerRef.current = setInterval(async () => {
      if (inFlight) return;
      inFlight = true;

      try {
        const elapsed = Date.now() - (pollStartedAtRef.current ?? Date.now());
        if (elapsed > MANDATE_POLL_TIMEOUT_MS) {
          stopPolling();
          setBudgetStep('waiting');
          clearBudgetActions();
          addBudgetEntry({
            role: 'assistant',
            content: 'Still waiting for approval. Go to wallet to approve — I will keep checking automatically.',
            actions: [
              {
                id: 'open-wallet-timeout',
                label: 'Go to wallet',
                variant: 'primary',
                onClick: handleOpenWallet,
              },
              {
                id: 'cancel-timeout',
                label: 'Cancel',
                variant: 'secondary',
                onClick: handleBudgetCancel,
              },
            ],
          });
          return;
        }

        const result = await fetchMandateById(currentMandateId);
        if (!result.success || !result.mandate) return;

        const status = result.mandate.status?.toLowerCase?.() ?? '';
        const isSigned = ['signed', 'active', 'authorized', 'enabled'].includes(status);
        const isAuthorized = isSigned || Boolean(result.mandate.signedAt) || Boolean(result.mandate.isEnabled);

        if (!isAuthorized) return;

        stopPolling();
        clearBudgetActions();
        addBudgetEntry({
          role: 'assistant',
          content: 'Budget confirmed! Starting research...',
        });

        const authResult = await ensureAuthenticated();
        if (!authResult.success || !authResult.jwt) {
          addBudgetEntry({
            role: 'system',
            content: `Authentication error: ${authResult.error || 'JWT not found'}`,
          });
          setBudgetStep('idle');
          addBudgetEntry({
            role: 'assistant',
            content: 'Unable to continue without authorization. Please retry.',
            actions: [
              {
                id: 'retry-auth',
                label: 'Retry',
                variant: 'primary',
                onClick: handleApproveBudget,
              },
              {
                id: 'cancel-auth',
                label: 'Cancel',
                variant: 'secondary',
                onClick: handleBudgetCancel,
              },
            ],
          });
          return;
        }

        setBudgetStep('done');

        const currentHandle = pendingHandleRef.current;
        const currentEngine = pendingEngineRef.current;
        const currentFile = pendingFileRef.current;
        if (currentHandle) {
          onSubmitResearch(
            currentHandle,
            currentEngine,
            currentMandateId,
            DEFAULT_BUDGET_USD,
            authResult.jwt,
            currentFile ?? undefined
          );
          pendingFileRef.current = null;
          setPendingFile(null);
        }
      } finally {
        inFlight = false;
      }
    }, MANDATE_POLL_INTERVAL_MS);
  };

  const handleOpenWallet = (overrideAuthUrl?: string, overrideMandateId?: string) => {
    const url = overrideAuthUrl ?? authUrl;
    const id = overrideMandateId ?? mandateId;
    if (!url || !id) return;

    window.open(url, '_blank', 'noopener,noreferrer');
    setBudgetStep('waiting');
    clearBudgetActions();
    addBudgetEntry({
      role: 'assistant',
      content: 'Waiting for approval... I will check automatically.',
      actions: [
        {
          id: 'open-wallet-again',
          label: 'Go to wallet',
          variant: 'secondary',
          onClick: () => handleOpenWallet(url, id),
        },
        {
          id: 'cancel-waiting',
          label: 'Cancel',
          variant: 'ghost',
          onClick: handleBudgetCancel,
        },
      ],
    });
    startPolling(id);
  };

  const viewToShow = activeView;
  const effectiveView = selectedTask ? viewToShow : 'log';
  const displayHandle = selectedTask?.handle ?? pendingHandle ?? '';
  const showBudgetEntries = Boolean(
    budgetEntries.length &&
      (pendingHandle || (selectedTask && budgetHandle && selectedTask.handle === budgetHandle))
  );
  const logExtraEntries = showBudgetEntries ? budgetEntries : [];

  const handleResearchInput = (handle: string, engine: Engine, file?: File) => {
    resetBudgetFlow();
    setPendingHandle(handle);
    setPendingEngine(engine);
    setPendingFile(file ?? null);
    pendingHandleRef.current = handle;
    pendingEngineRef.current = engine;
    pendingFileRef.current = file ?? null;
    setBudgetHandle(handle);
    setBudgetStep('creating');

    const label = file ? `**${file.name}**` : `**${handle}**`;
    addBudgetEntry({
      role: 'assistant',
      content: `To research ${label}, I need a ${formatUSD(DEFAULT_BUDGET_USD)} budget from your Fluxa Wallet.\n\nTypical cost: $0.50 - $2.00 per research.`,
      actions: [
        {
          id: 'cancel-budget',
          label: 'Cancel',
          variant: 'secondary',
          onClick: handleBudgetCancel,
        },
      ],
    });

    handleApproveBudget();
  };

  return (
    <div className="flex-1 flex flex-col h-full bg-black">
      {selectedTask || pendingHandle ? (
        <>
          {/* Task header */}
          <div className="px-8 py-5 border-b border-white/[0.06] bg-black">
            <div className="max-w-4xl mx-auto">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-brand-blue flex items-center justify-center">
                  <span className="text-black text-lg font-semibold">
                    {displayHandle.replace(/^[@https?:\/\/]+/, '').charAt(0).toUpperCase()}
                  </span>
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-lg font-semibold text-white font-serif">{displayHandle}</h2>
                    {selectedTask?.engine && (
                      <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium tracking-wide ${
                        selectedTask.engine === 'openai'
                          ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                          : 'bg-orange-500/10 text-orange-400 border border-orange-500/20'
                      }`}>
                        {selectedTask.engine === 'openai' ? 'OpenAI' : 'Claude'}
                      </span>
                    )}
                    {!selectedTask?.engine && (
                      <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium tracking-wide bg-white/5 text-gray-400 border border-white/10">
                        OpenAI
                      </span>
                    )}
                  </div>
                  {selectedTask ? (
                    <p className="text-xs text-gray-500 font-mono mt-0.5">
                      ID: {selectedTask.task_id.slice(0, 8)}
                    </p>
                  ) : (
                    <p className="text-xs text-gray-500 font-mono mt-0.5">
                      Awaiting budget authorization
                    </p>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* Content area - log or report viewer */}
          <div className="flex-1 flex flex-col min-h-0 bg-black">
            {effectiveView === 'report' && selectedTask?.status === 'completed' ? (
              <ReportViewer taskId={selectedTask.task_id} paymentStatus={selectedTask.payment_status} />
            ) : (
              <LogViewer
                taskId={selectedTask?.task_id}
                isRunning={Boolean(pendingHandle) || selectedTask?.status === 'running'}
                extraEntries={logExtraEntries}
              />
            )}
          </div>

          {/* Actions area at bottom */}
          {selectedTask && (
            <div className="p-4 border-t border-white/[0.06] bg-black">
              <div className="max-w-4xl mx-auto">
                <TaskActions
                  task={selectedTask}
                  activeView={viewToShow}
                  onViewChange={setActiveView}
                  onCancel={selectedTask.status === 'running' ? handleCancel : undefined}
                  isCancelling={isCancelling}
                  onPaymentRetrySuccess={onTaskUpdate}
                  onRetryResearch={selectedTask.status === 'failed' ? handleRetryResearch : undefined}
                  isRetryingResearch={isRetryingResearch}
                />
              </div>
            </div>
          )}
        </>
      ) : (
        /* Empty state - new research */
        <div className="flex-1 flex flex-col items-center justify-center p-8 corner-frame">
          <div className="text-center mb-10">
            <div className="inline-flex items-center justify-center w-20 h-20 rounded-2xl bg-brand-blue mb-6 shadow-lg">
              <Layers className="w-10 h-10 text-black" />
            </div>
            <h1 className="text-3xl font-semibold text-white mb-3 tracking-tight font-serif">
              Research Agent
            </h1>
            <p className="text-gray-400 max-w-md leading-relaxed">
              Enter a Twitter handle, paste a URL, or upload a PDF to generate
              a comprehensive research report.
            </p>
          </div>
          <ResearchInput onSubmit={handleResearchInput} isSubmitting={isSubmitting} />

          {/* Footer info */}
          <div className="mt-16 text-center">
            <p className="text-xs text-gray-600 font-mono tracking-wider">
              POWERED BY AI
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
