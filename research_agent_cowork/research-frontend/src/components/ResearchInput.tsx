'use client';

import { useState, useRef, useEffect } from 'react';
import { ArrowRight, Loader2, Wallet } from 'lucide-react';
import {
  getStoredMandate,
  hasValidMandate,
  DEFAULT_BUDGET_USD,
  formatUSD,
} from '@/lib/fluxa';
import { Engine } from '@/types';

interface ResearchInputProps {
  onSubmit: (handle: string, engine: Engine) => void;
  isSubmitting: boolean;
  disabled?: boolean;
  placeholder?: string;
}

export default function ResearchInput({
  onSubmit,
  isSubmitting,
  disabled = false,
  placeholder = 'elonmusk',
}: ResearchInputProps) {
  const [handle, setHandle] = useState('');
  const engine: Engine = 'openai';
  const [hasMandateReady, setHasMandateReady] = useState(false);
  const [mandateBudget, setMandateBudget] = useState<number | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Check for existing mandate on mount (client-side only)
  useEffect(() => {
    const checkMandate = () => {
      const valid = hasValidMandate(DEFAULT_BUDGET_USD);
      setHasMandateReady(valid);
      if (valid) {
        const mandate = getStoredMandate();
        setMandateBudget(mandate?.budget_usd || null);
      }
    };
    checkMandate();
  }, []);

  useEffect(() => {
    if (!isSubmitting && !disabled) {
      inputRef.current?.focus();
    }
  }, [isSubmitting, disabled]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = handle.trim();
    if (!trimmed || isSubmitting || disabled) return;

    const normalizedHandle = trimmed.startsWith('@') ? trimmed : `@${trimmed}`;
    onSubmit(normalizedHandle, engine);
    setHandle('');
  };

  return (
    <form onSubmit={handleSubmit} className="w-full max-w-xl mx-auto">
      <div className="relative flex items-center border-b border-gray-700 focus-within:border-brand-blue transition-colors">
        <span className="text-gray-500 text-lg font-medium pl-2 pr-2">@</span>
        <input
          ref={inputRef}
          type="text"
          value={handle}
          onChange={(e) => setHandle(e.target.value.replace(/^@+/, ''))}
          placeholder={placeholder}
          disabled={isSubmitting || disabled}
          className="flex-1 bg-transparent py-4 text-white placeholder-gray-600 focus:outline-none disabled:opacity-50 text-base"
        />
        <button
          type="submit"
          disabled={!handle.trim() || isSubmitting || disabled}
          className="ml-2 mb-2 p-3 rounded-xl bg-brand-blue text-black hover:bg-brand-blue-hover disabled:opacity-30 disabled:hover:bg-brand-blue transition-all"
        >
          {isSubmitting ? (
            <Loader2 className="w-5 h-5 animate-spin" />
          ) : (
            <ArrowRight className="w-5 h-5" />
          )}
        </button>
      </div>

      {/* Payment info */}
      <div className="flex items-center justify-center gap-2 mt-3">
        {hasMandateReady && mandateBudget ? (
          <div className="flex items-center gap-2 text-xs text-emerald-400">
            <Wallet className="w-3 h-3" />
            <span>Budget: {formatUSD(mandateBudget)}</span>
          </div>
        ) : (
          <p className="text-xs text-gray-600 text-center font-mono tracking-wide">
            REQUIRES BUDGET AUTHORIZATION
          </p>
        )}
      </div>
    </form>
  );
}
