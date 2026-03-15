'use client';

import { useEffect, useState, useRef, useCallback } from 'react';
import {
  Receipt,
  Cpu,
  Wrench,
  Loader2,
  CheckCircle,
  XCircle,
  Clock,
  ExternalLink,
  Wallet,
} from 'lucide-react';
import { fetchPaymentDetails, retryPayment } from '@/lib/api';
import { PaymentDetails as PaymentDetailsType } from '@/types';
import {
  formatUSD,
  formatPaymentStatus,
  createIntentMandate,
  fetchMandateById,
  DEFAULT_BUDGET_USD,
} from '@/lib/fluxa';

const MANDATE_POLL_INTERVAL_MS = 5000;
const MANDATE_POLL_TIMEOUT_MS = 30 * 60 * 1000;

type RetryStep = 'idle' | 'creating' | 'authorize' | 'waiting' | 'retrying';

interface PaymentDetailsProps {
  taskId: string;
  onClose?: () => void;
  onRetrySuccess?: () => void;
}

export default function PaymentDetails({ taskId, onClose, onRetrySuccess }: PaymentDetailsProps) {
  const [details, setDetails] = useState<PaymentDetailsType | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retryError, setRetryError] = useState<string | null>(null);
  const [retryStep, setRetryStep] = useState<RetryStep>('idle');
  const [authUrl, setAuthUrl] = useState<string | null>(null);
  const [newMandateId, setNewMandateId] = useState<string | null>(null);

  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollStartedAtRef = useRef<number | null>(null);

  const stopPolling = useCallback(() => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
    pollStartedAtRef.current = null;
  }, []);

  useEffect(() => {
    return () => {
      stopPolling();
    };
  }, [stopPolling]);

  useEffect(() => {
    const loadDetails = async () => {
      setIsLoading(true);
      setError(null);

      try {
        const data = await fetchPaymentDetails(taskId);
        setDetails(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load payment details');
      } finally {
        setIsLoading(false);
      }
    };

    loadDetails();
  }, [taskId]);

  const startPolling = (mandateId: string) => {
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
          setRetryError('Mandate approval timed out. Please try again.');
          setRetryStep('idle');
          return;
        }

        const result = await fetchMandateById(mandateId);
        if (!result.success || !result.mandate) return;

        const status = result.mandate.status?.toLowerCase?.() ?? '';
        const isSigned = ['signed', 'active', 'authorized', 'enabled'].includes(status);
        const isAuthorized = isSigned || Boolean(result.mandate.signedAt) || Boolean(result.mandate.isEnabled);

        if (!isAuthorized) return;

        // Mandate approved — now retry payment with the new mandate
        stopPolling();
        setRetryStep('retrying');

        const payResult = await retryPayment(taskId, mandateId);
        if (payResult.success) {
          const data = await fetchPaymentDetails(taskId);
          setDetails(data);
          setRetryStep('idle');
          setRetryError(null);
          onRetrySuccess?.();
        } else {
          setRetryError(payResult.error || payResult.payment_error || 'Payment retry failed');
          const data = await fetchPaymentDetails(taskId);
          setDetails(data);
          setRetryStep('idle');
        }
      } catch (err) {
        // Don't stop polling on transient errors
      } finally {
        inFlight = false;
      }
    }, MANDATE_POLL_INTERVAL_MS);
  };

  const handleRetryPayment = async () => {
    setRetryStep('creating');
    setRetryError(null);

    try {
      // Create a new mandate for the retry
      const budgetAmount = details?.total_cost_usd
        ? Math.max(details.total_cost_usd, DEFAULT_BUDGET_USD)
        : DEFAULT_BUDGET_USD;

      const result = await createIntentMandate(
        budgetAmount,
        1,
        `Payment retry: ${formatUSD(details?.total_cost_usd ?? 0)} for research task`
      );

      if (result.success && result.mandateId && result.authorizationUrl) {
        setNewMandateId(result.mandateId);
        setAuthUrl(result.authorizationUrl);
        setRetryStep('authorize');
      } else {
        setRetryError(result.error || 'Failed to create budget authorization');
        setRetryStep('idle');
      }
    } catch (err) {
      setRetryError(err instanceof Error ? err.message : 'Failed to create mandate');
      setRetryStep('idle');
    }
  };

  const handleOpenWallet = () => {
    if (!authUrl || !newMandateId) return;
    window.open(authUrl, '_blank', 'noopener,noreferrer');
    setRetryStep('waiting');
    startPolling(newMandateId);
  };

  const handleCancelRetry = () => {
    stopPolling();
    setRetryStep('idle');
    setAuthUrl(null);
    setNewMandateId(null);
    setRetryError(null);
  };

  if (isLoading) {
    return (
      <div className="bg-white/[0.03] rounded-2xl border border-white/10 p-6">
        <div className="flex items-center justify-center gap-2 text-gray-500">
          <Loader2 className="w-5 h-5 animate-spin" />
          <span>Loading payment details...</span>
        </div>
      </div>
    );
  }

  if (error || !details) {
    return (
      <div className="bg-white/[0.03] rounded-2xl border border-white/10 p-6">
        <div className="flex items-center gap-2 text-red-400">
          <XCircle className="w-5 h-5" />
          <span>{error || 'Failed to load payment details'}</span>
        </div>
      </div>
    );
  }

  const status = formatPaymentStatus(details.payment_status);

  const StatusIcon = () => {
    switch (details.payment_status) {
      case 'completed':
        return <CheckCircle className="w-5 h-5 text-emerald-400" />;
      case 'failed':
        return <XCircle className="w-5 h-5 text-red-400" />;
      case 'processing':
        return <Loader2 className="w-5 h-5 text-amber-400 animate-spin" />;
      case 'skipped':
        return <Clock className="w-5 h-5 text-gray-500" />;
      default:
        return <Clock className="w-5 h-5 text-gray-500" />;
    }
  };

  return (
    <div className="bg-white/[0.03] rounded-2xl border border-white/10 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-white/[0.06]">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-white/5 flex items-center justify-center">
            <Receipt className="w-4 h-4 text-gray-400" />
          </div>
          <span className="font-medium text-white">Budget Usage</span>
        </div>
        <div className="flex items-center gap-2">
          <StatusIcon />
          <span
            className={`text-sm font-medium ${
              status.color === 'green'
                ? 'text-emerald-400'
                : status.color === 'red'
                ? 'text-red-400'
                : status.color === 'yellow'
                ? 'text-amber-400'
                : status.color === 'blue'
                ? 'text-sky-400'
                : 'text-gray-500'
            }`}
          >
            {status.label}
          </span>
        </div>
      </div>

      {/* Cost Breakdown */}
      <div className="p-4 space-y-3">
        {/* Token Usage Cost */}
        <div className="flex items-center justify-between py-2">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-purple-500/10 flex items-center justify-center">
              <Cpu className="w-4 h-4 text-purple-400" />
            </div>
            <div>
              <p className="text-sm font-medium text-white">Token Usage</p>
              <p className="text-xs text-gray-500">LLM processing cost</p>
            </div>
          </div>
          <span className="font-mono text-sm text-white">
            {formatUSD(details.claude_cost_usd)}
          </span>
        </div>

        {/* Tool Calls Cost */}
        <div className="flex items-center justify-between py-2">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-sky-500/10 flex items-center justify-center">
              <Wrench className="w-4 h-4 text-sky-400" />
            </div>
            <div>
              <p className="text-sm font-medium text-white">Tool Calls</p>
              <p className="text-xs text-gray-500">
                {details.tool_calls} calls @ $0.01 each
              </p>
            </div>
          </div>
          <span className="font-mono text-sm text-white">
            {formatUSD(details.tool_cost_usd)}
          </span>
        </div>

        {/* Divider */}
        <div className="border-t border-white/[0.06] my-2" />

        {/* Total */}
        <div className="flex items-center justify-between py-2">
          <span className="font-semibold text-white">Total Cost</span>
          <span className="font-mono font-semibold text-white">
            {formatUSD(details.total_cost_usd)}
          </span>
        </div>

        {/* Budget vs Actual */}
        {details.budget_usd > 0 && (
          <div className="bg-white/5 rounded-xl p-3 mt-2 border border-white/[0.06]">
            <div className="flex items-center justify-between text-sm">
              <span className="text-gray-400">Budget</span>
              <span className="font-mono text-white">{formatUSD(details.budget_usd)}</span>
            </div>
            <div className="flex items-center justify-between text-sm mt-1">
              <span className="text-gray-400">Charged</span>
              <span className="font-mono text-emerald-400">
                {formatUSD(details.payment_amount_usd)}
              </span>
            </div>
            {details.budget_usd > details.payment_amount_usd && (
              <div className="flex items-center justify-between text-sm mt-1">
                <span className="text-gray-400">Saved</span>
                <span className="font-mono text-emerald-400">
                  {formatUSD(details.budget_usd - details.payment_amount_usd)}
                </span>
              </div>
            )}
          </div>
        )}

        {/* Transaction Hash */}
        {details.payment_tx_hash && (
          <div className="mt-3">
            <a
              href={`https://basescan.org/tx/${details.payment_tx_hash}`}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 text-sm text-brand-blue hover:text-brand-blue-hover"
            >
              <span className="font-mono truncate">{details.payment_tx_hash.slice(0, 20)}...</span>
              <ExternalLink className="w-4 h-4 flex-shrink-0" />
            </a>
          </div>
        )}

        {/* Payment Error */}
        {details.payment_error && (
          <div className="mt-3 p-3 bg-red-500/10 rounded-xl border border-red-500/20">
            <p className="text-sm text-red-400">{details.payment_error}</p>
          </div>
        )}

        {/* Retry error */}
        {retryError && (
          <div className="mt-2 p-3 bg-red-500/10 rounded-xl border border-red-500/20">
            <p className="text-sm text-red-400">{retryError}</p>
          </div>
        )}

        {/* Retry Payment Flow */}
        {details.payment_status === 'failed' && (
          <div className="mt-3 space-y-2">
            {retryStep === 'idle' && (
              <button
                onClick={handleRetryPayment}
                className="w-full flex items-center justify-center gap-2 py-2.5 px-4 text-sm font-medium text-white bg-brand-blue hover:bg-brand-blue-hover rounded-xl transition-all"
              >
                <Receipt className="w-4 h-4" />
                <span>Retry Payment</span>
              </button>
            )}

            {retryStep === 'creating' && (
              <div className="flex items-center justify-center gap-2 py-2.5 px-4 text-sm text-gray-400">
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Creating new budget authorization...</span>
              </div>
            )}

            {retryStep === 'authorize' && (
              <div className="space-y-2">
                <p className="text-sm text-gray-400 text-center">
                  A new budget of {formatUSD(details.total_cost_usd > DEFAULT_BUDGET_USD ? details.total_cost_usd : DEFAULT_BUDGET_USD)} has been created. Approve it in your wallet to proceed.
                </p>
                <div className="flex gap-2">
                  <button
                    onClick={handleOpenWallet}
                    className="flex-1 flex items-center justify-center gap-2 py-2.5 px-4 text-sm font-medium text-white bg-brand-blue hover:bg-brand-blue-hover rounded-xl transition-all"
                  >
                    <Wallet className="w-4 h-4" />
                    <span>Go to wallet</span>
                  </button>
                  <button
                    onClick={handleCancelRetry}
                    className="py-2.5 px-4 text-sm font-medium text-gray-400 hover:text-white hover:bg-white/5 rounded-xl transition-all border border-white/10"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}

            {retryStep === 'waiting' && (
              <div className="space-y-2">
                <div className="flex items-center justify-center gap-2 py-2.5 px-4 text-sm text-gray-400">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Waiting for wallet approval...</span>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={handleOpenWallet}
                    className="flex-1 py-2 px-4 text-sm text-gray-400 hover:text-white hover:bg-white/5 rounded-xl transition-all border border-white/10 text-center"
                  >
                    Open wallet again
                  </button>
                  <button
                    onClick={handleCancelRetry}
                    className="py-2 px-4 text-sm text-gray-400 hover:text-white hover:bg-white/5 rounded-xl transition-all border border-white/10"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}

            {retryStep === 'retrying' && (
              <div className="flex items-center justify-center gap-2 py-2.5 px-4 text-sm text-gray-400">
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Processing payment...</span>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Footer */}
      {onClose && (
        <div className="px-4 pb-4">
          <button
            onClick={onClose}
            className="w-full py-2 px-4 text-sm text-gray-400 hover:text-white hover:bg-white/5 rounded-xl transition-colors"
          >
            Close
          </button>
        </div>
      )}
    </div>
  );
}
