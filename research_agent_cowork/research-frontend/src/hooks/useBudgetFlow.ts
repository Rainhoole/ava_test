import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  createIntentMandate,
  DEFAULT_BUDGET_USD,
  ensureAuthenticated,
  fetchMandateById,
  formatUSD,
} from '@/lib/fluxa';
import type { BudgetEntry, Engine, Task } from '@/types';

const MANDATE_POLL_INTERVAL_MS = 5000;
const MANDATE_POLL_TIMEOUT_MS = 30 * 60 * 1000;

interface UseBudgetFlowOptions {
  selectedTask: Task | null;
  onAuthorizedResearch: (
    handle: string,
    engine: Engine,
    mandateId?: string,
    budgetUsd?: number,
    fluxaJwt?: string
  ) => Promise<void>;
}

export function useBudgetFlow({ selectedTask, onAuthorizedResearch }: UseBudgetFlowOptions) {
  const [pendingHandle, setPendingHandle] = useState<string | null>(null);
  const [pendingEngine, setPendingEngine] = useState<Engine>('openai');
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
    setBudgetEntries((prev) => prev.map((entry) => ({ ...entry, actions: undefined })));
  };

  const stopPolling = useCallback(() => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }

    pollStartedAtRef.current = null;
  }, []);

  const resetBudgetFlow = useCallback(() => {
    stopPolling();
    setBudgetEntries([]);
    setBudgetHandle(null);
    setBudgetStep('idle');
    setMandateId(null);
    setAuthUrl(null);
    budgetSeqRef.current = 1;
  }, [stopPolling]);

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
  }, [selectedTask, pendingHandle]);

  useEffect(() => {
    if (selectedTask && budgetHandle && selectedTask.handle !== budgetHandle) {
      setBudgetEntries([]);
      setBudgetHandle(null);
    }
  }, [selectedTask, budgetHandle]);

  useEffect(() => () => stopPolling(), [stopPolling]);

  const handleBudgetCancel = () => {
    resetBudgetFlow();
    setPendingHandle(null);
    pendingHandleRef.current = null;
  };

  const startPolling = (currentMandateId: string) => {
    stopPolling();
    pollStartedAtRef.current = Date.now();
    let inFlight = false;

    pollTimerRef.current = setInterval(async () => {
      if (inFlight) {
        return;
      }

      inFlight = true;

      try {
        const elapsed = Date.now() - (pollStartedAtRef.current ?? Date.now());
        if (elapsed > MANDATE_POLL_TIMEOUT_MS) {
          stopPolling();
          setBudgetStep('waiting');
          clearBudgetActions();
          addBudgetEntry({
            role: 'assistant',
            content: 'Still waiting for approval. Go to wallet to approve - I will keep checking automatically.',
            actions: [
              {
                id: 'open-wallet-timeout',
                label: 'Go to wallet',
                variant: 'primary',
                onClick: () => handleOpenWallet(),
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
        if (!result.success || !result.mandate) {
          return;
        }

        const status = result.mandate.status?.toLowerCase?.() ?? '';
        const isSigned = ['signed', 'active', 'authorized', 'enabled'].includes(status);
        const isAuthorized = isSigned || Boolean(result.mandate.signedAt) || Boolean(result.mandate.isEnabled);

        if (!isAuthorized) {
          return;
        }

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
                onClick: () => {
                  void handleApproveBudget();
                },
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
        if (currentHandle) {
          await onAuthorizedResearch(
            currentHandle,
            currentEngine,
            currentMandateId,
            DEFAULT_BUDGET_USD,
            authResult.jwt
          );
        }
      } finally {
        inFlight = false;
      }
    }, MANDATE_POLL_INTERVAL_MS);
  };

  const handleOpenWallet = (overrideAuthUrl?: string, overrideMandateId?: string) => {
    const nextAuthUrl = overrideAuthUrl ?? authUrl;
    const nextMandateId = overrideMandateId ?? mandateId;
    if (!nextAuthUrl || !nextMandateId) {
      return;
    }

    window.open(nextAuthUrl, '_blank', 'noopener,noreferrer');
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
          onClick: () => handleOpenWallet(nextAuthUrl, nextMandateId),
        },
        {
          id: 'cancel-waiting',
          label: 'Cancel',
          variant: 'ghost',
          onClick: handleBudgetCancel,
        },
      ],
    });
    startPolling(nextMandateId);
  };

  const handleApproveBudget = async () => {
    const currentHandle = pendingHandleRef.current ?? pendingHandle;
    if (!currentHandle || isCreatingRef.current) {
      return;
    }

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
          content: 'Budget request created. Go to wallet to approve - I will check automatically.',
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
              onClick: () => {
                void handleApproveBudget();
              },
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

  const beginBudgetedResearch = (handle: string, engine: Engine) => {
    resetBudgetFlow();
    setPendingHandle(handle);
    setPendingEngine(engine);
    pendingHandleRef.current = handle;
    pendingEngineRef.current = engine;
    setBudgetHandle(handle);
    setBudgetStep('creating');
    addBudgetEntry({
      role: 'assistant',
      content: `To research **${handle}**, I need a ${formatUSD(DEFAULT_BUDGET_USD)} budget from your Fluxa Wallet.\n\nTypical cost: $0.50 - $2.00 per research.`,
      actions: [
        {
          id: 'cancel-budget',
          label: 'Cancel',
          variant: 'secondary',
          onClick: handleBudgetCancel,
        },
      ],
    });

    void handleApproveBudget();
  };

  const showBudgetEntries = Boolean(
    budgetEntries.length &&
      (pendingHandle || (selectedTask && budgetHandle && selectedTask.handle === budgetHandle))
  );

  const logExtraEntries = useMemo(
    () => (showBudgetEntries ? budgetEntries : []),
    [showBudgetEntries, budgetEntries]
  );

  return {
    budgetEntries,
    budgetStep,
    pendingHandle,
    displayHandle: selectedTask?.handle ?? pendingHandle ?? '',
    logExtraEntries,
    beginBudgetedResearch,
  };
}
