'use client';

import { useState } from 'react';
import { FileText, ScrollText, XCircle, Loader2, Receipt, CheckCircle, Clock, AlertCircle, RotateCcw } from 'lucide-react';
import { Task } from '@/types';
import { cn } from '@/lib/utils';
import PaymentDetails from './PaymentDetails';
import { formatUSD, formatPaymentStatus } from '@/lib/fluxa';

interface TaskActionsProps {
  task: Task;
  activeView: 'log' | 'report';
  onViewChange: (view: 'log' | 'report') => void;
  onCancel?: () => void;
  isCancelling?: boolean;
  onPaymentRetrySuccess?: () => void;
  onRetryResearch?: () => void;
  isRetryingResearch?: boolean;
}

export default function TaskActions({
  task,
  activeView,
  onViewChange,
  onCancel,
  isCancelling = false,
  onPaymentRetrySuccess,
  onRetryResearch,
  isRetryingResearch = false,
}: TaskActionsProps) {
  const isPaymentFailed = task.payment_status === 'failed';
  const [showPaymentDetails, setShowPaymentDetails] = useState(isPaymentFailed);

  const isCompleted = task.status === 'completed';
  const isRunning = task.status === 'running';
  const canCancel = isRunning && onCancel;

  const paymentStatus = formatPaymentStatus(task.payment_status);

  const PaymentStatusIcon = () => {
    switch (task.payment_status) {
      case 'completed':
        return <CheckCircle className="w-3 h-3" />;
      case 'failed':
        return <AlertCircle className="w-3 h-3" />;
      case 'processing':
        return <Loader2 className="w-3 h-3 animate-spin" />;
      default:
        return <Clock className="w-3 h-3" />;
    }
  };

  return (
    <>
      <div className="flex items-center gap-3 p-3 bg-white/[0.03] rounded-2xl border border-white/10">
        {/* View tabs */}
        <div className="flex items-center bg-white/5 rounded-xl p-1">
          <button
            onClick={() => onViewChange('report')}
            disabled={!isCompleted || isPaymentFailed}
            className={cn(
              'flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all',
              activeView === 'report'
                ? 'bg-brand-blue text-black shadow-sm'
                : 'text-gray-400 hover:text-white',
              (!isCompleted || isPaymentFailed) && 'opacity-40 cursor-not-allowed'
            )}
          >
            <FileText className="w-4 h-4" />
            <span>Report</span>
            {!isCompleted && (
              <span className="text-xs opacity-60">(pending)</span>
            )}
            {isCompleted && isPaymentFailed && (
              <span className="text-xs opacity-60">(locked)</span>
            )}
          </button>
          <button
            onClick={() => onViewChange('log')}
            className={cn(
              'flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all',
              activeView === 'log'
                ? 'bg-brand-blue text-black shadow-sm'
                : 'text-gray-400 hover:text-white'
            )}
          >
            <ScrollText className="w-4 h-4" />
            <span>Log</span>
          </button>
        </div>

        {/* Task info */}
        <div className="flex-1 flex items-center justify-center gap-4">
          {/* Payment status badge */}
          {task.payment_status !== 'skipped' && (
            <button
              onClick={() => setShowPaymentDetails(!showPaymentDetails)}
              className={cn(
                'flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium transition-all',
                paymentStatus.color === 'green' && 'bg-emerald-500/10 text-emerald-400',
                paymentStatus.color === 'red' && 'bg-red-500/10 text-red-400',
                paymentStatus.color === 'yellow' && 'bg-amber-500/10 text-amber-400',
                paymentStatus.color === 'blue' && 'bg-sky-500/10 text-sky-400',
                paymentStatus.color === 'gray' && 'bg-white/5 text-gray-400',
                'hover:opacity-80'
              )}
            >
              <PaymentStatusIcon />
              <span>
                {task.payment_amount_usd > 0
                  ? formatUSD(task.payment_amount_usd)
                  : paymentStatus.label}
              </span>
            </button>
          )}

          {/* Cost display for skipped payments */}
          {task.payment_status === 'skipped' && task.cost_usd > 0 && (
            <span className="text-sm text-gray-500 font-mono">
              {formatUSD(task.cost_usd)}
            </span>
          )}
        </div>

        {/* Cancel button */}
        {canCancel && (
          <button
            onClick={onCancel}
            disabled={isCancelling}
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-red-400 hover:text-red-300 hover:bg-red-500/10 rounded-xl transition-all disabled:opacity-50 border border-red-500/20"
          >
            {isCancelling ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <XCircle className="w-4 h-4" />
            )}
            <span>Cancel</span>
          </button>
        )}

        {/* Retry Research button for failed tasks */}
        {task.status === 'failed' && onRetryResearch && (
          <button
            onClick={onRetryResearch}
            disabled={isRetryingResearch}
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-brand-blue hover:text-white hover:bg-brand-blue/10 rounded-xl transition-all disabled:opacity-50 border border-brand-blue/30"
          >
            {isRetryingResearch ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <RotateCcw className="w-4 h-4" />
            )}
            <span>Retry</span>
          </button>
        )}

        {/* Budget details button for completed tasks */}
        {isCompleted && task.payment_status !== 'skipped' && (
          <button
            onClick={() => setShowPaymentDetails(!showPaymentDetails)}
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-400 hover:text-white hover:bg-white/5 rounded-xl transition-all border border-white/10"
          >
            <Receipt className="w-4 h-4" />
            <span>Budget</span>
          </button>
        )}
      </div>

      {/* Payment Details Panel */}
      {showPaymentDetails && (
        <div className="mt-3">
          <PaymentDetails
            taskId={task.task_id}
            onClose={() => setShowPaymentDetails(false)}
            onRetrySuccess={onPaymentRetrySuccess}
          />
        </div>
      )}
    </>
  );
}
