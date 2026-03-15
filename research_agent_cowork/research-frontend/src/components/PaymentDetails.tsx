'use client';

import {
  CheckCircle,
  Clock,
  Cpu,
  ExternalLink,
  Loader2,
  Receipt,
  Wrench,
  XCircle,
} from 'lucide-react';
import { formatPaymentStatus, formatUSD } from '@/lib/fluxa';
import { usePaymentDetails } from '@/hooks/usePaymentDetails';

interface PaymentDetailsProps {
  taskId: string;
  onClose?: () => void;
}

export default function PaymentDetails({ taskId, onClose }: PaymentDetailsProps) {
  const { details, isLoading, error } = usePaymentDetails(taskId);

  if (isLoading) {
    return (
      <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-6">
        <div className="flex items-center justify-center gap-2 text-gray-500">
          <Loader2 className="h-5 w-5 animate-spin" />
          <span>Loading payment details...</span>
        </div>
      </div>
    );
  }

  if (error || !details) {
    return (
      <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-6">
        <div className="flex items-center gap-2 text-red-400">
          <XCircle className="h-5 w-5" />
          <span>{error || 'Failed to load payment details'}</span>
        </div>
      </div>
    );
  }

  const status = formatPaymentStatus(details.payment_status);

  const StatusIcon = () => {
    switch (details.payment_status) {
      case 'completed':
        return <CheckCircle className="h-5 w-5 text-emerald-400" />;
      case 'failed':
        return <XCircle className="h-5 w-5 text-red-400" />;
      case 'processing':
        return <Loader2 className="h-5 w-5 animate-spin text-amber-400" />;
      case 'skipped':
        return <Clock className="h-5 w-5 text-gray-500" />;
      default:
        return <Clock className="h-5 w-5 text-gray-500" />;
    }
  };

  return (
    <div className="overflow-hidden rounded-2xl border border-white/10 bg-white/[0.03]">
      <div className="flex items-center justify-between border-b border-white/[0.06] p-4">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-white/5">
            <Receipt className="h-4 w-4 text-gray-400" />
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

      <div className="space-y-3 p-4">
        <div className="flex items-center justify-between py-2">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-purple-500/10">
              <Cpu className="h-4 w-4 text-purple-400" />
            </div>
            <div>
              <p className="text-sm font-medium text-white">Token Usage</p>
              <p className="text-xs text-gray-500">LLM processing cost</p>
            </div>
          </div>
          <span className="font-mono text-sm text-white">{formatUSD(details.claude_cost_usd)}</span>
        </div>

        <div className="flex items-center justify-between py-2">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-sky-500/10">
              <Wrench className="h-4 w-4 text-sky-400" />
            </div>
            <div>
              <p className="text-sm font-medium text-white">Tool Calls</p>
              <p className="text-xs text-gray-500">{details.tool_calls} calls @ $0.01 each</p>
            </div>
          </div>
          <span className="font-mono text-sm text-white">{formatUSD(details.tool_cost_usd)}</span>
        </div>

        <div className="my-2 border-t border-white/[0.06]" />

        <div className="flex items-center justify-between py-2">
          <span className="font-semibold text-white">Total Cost</span>
          <span className="font-mono font-semibold text-white">{formatUSD(details.total_cost_usd)}</span>
        </div>

        {details.budget_usd > 0 && (
          <div className="mt-2 rounded-xl border border-white/[0.06] bg-white/5 p-3">
            <div className="flex items-center justify-between text-sm">
              <span className="text-gray-400">Budget</span>
              <span className="font-mono text-white">{formatUSD(details.budget_usd)}</span>
            </div>
            <div className="mt-1 flex items-center justify-between text-sm">
              <span className="text-gray-400">Charged</span>
              <span className="font-mono text-emerald-400">{formatUSD(details.payment_amount_usd)}</span>
            </div>
            {details.budget_usd > details.payment_amount_usd && (
              <div className="mt-1 flex items-center justify-between text-sm">
                <span className="text-gray-400">Saved</span>
                <span className="font-mono text-emerald-400">
                  {formatUSD(details.budget_usd - details.payment_amount_usd)}
                </span>
              </div>
            )}
          </div>
        )}

        {details.payment_tx_hash && (
          <div className="mt-3">
            <a
              href={`https://basescan.org/tx/${details.payment_tx_hash}`}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 text-sm text-brand-blue hover:text-brand-blue-hover"
            >
              <span className="truncate font-mono">{details.payment_tx_hash.slice(0, 20)}...</span>
              <ExternalLink className="h-4 w-4 flex-shrink-0" />
            </a>
          </div>
        )}

        {details.payment_error && (
          <div className="mt-3 rounded-xl border border-red-500/20 bg-red-500/10 p-3">
            <p className="text-sm text-red-400">{details.payment_error}</p>
          </div>
        )}
      </div>

      {onClose && (
        <div className="px-4 pb-4">
          <button
            onClick={onClose}
            className="w-full rounded-xl px-4 py-2 text-sm text-gray-400 transition-colors hover:bg-white/5 hover:text-white"
          >
            Close
          </button>
        </div>
      )}
    </div>
  );
}
