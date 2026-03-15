'use client';

import { useState, useRef, useEffect } from 'react';
import { ArrowRight, Loader2, Wallet, Paperclip, X, FileText } from 'lucide-react';
import {
  getStoredMandate,
  hasValidMandate,
  DEFAULT_BUDGET_USD,
  formatUSD,
} from '@/lib/fluxa';
import { Engine } from '@/types';

interface ResearchInputProps {
  onSubmit: (handle: string, engine: Engine, file?: File) => void;
  isSubmitting: boolean;
  disabled?: boolean;
}

function isUrl(input: string): boolean {
  return /^https?:\/\//.test(input);
}

export default function ResearchInput({
  onSubmit,
  isSubmitting,
  disabled = false,
}: ResearchInputProps) {
  const [input, setInput] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const engine: Engine = 'openai';
  const [hasMandateReady, setHasMandateReady] = useState(false);
  const [mandateBudget, setMandateBudget] = useState<number | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

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

    if (file) {
      // File upload takes priority
      onSubmit(file.name, engine, file);
      setFile(null);
      setInput('');
      return;
    }

    const trimmed = input.trim();
    if (!trimmed || isSubmitting || disabled) return;

    // Detect URL vs handle
    const target = isUrl(trimmed) ? trimmed : (trimmed.startsWith('@') ? trimmed : `@${trimmed}`);
    onSubmit(target, engine);
    setInput('');
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0];
    if (selected && selected.type === 'application/pdf') {
      setFile(selected);
    }
    // Reset file input so the same file can be re-selected
    e.target.value = '';
  };

  const clearFile = () => {
    setFile(null);
  };

  const hasInput = file || input.trim();

  return (
    <form onSubmit={handleSubmit} className="w-full max-w-xl mx-auto">
      {/* File attachment preview */}
      {file && (
        <div className="flex items-center gap-2 mb-2 px-2 py-2 bg-white/5 rounded-xl border border-white/10">
          <FileText className="w-4 h-4 text-brand-blue flex-shrink-0" />
          <span className="text-sm text-white truncate flex-1">{file.name}</span>
          <span className="text-xs text-gray-500">{(file.size / 1024).toFixed(0)} KB</span>
          <button
            type="button"
            onClick={clearFile}
            className="p-1 hover:bg-white/10 rounded-lg transition-colors"
          >
            <X className="w-3.5 h-3.5 text-gray-400" />
          </button>
        </div>
      )}

      <div className="relative flex items-center border-b border-gray-700 focus-within:border-brand-blue transition-colors">
        <input
          ref={inputRef}
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={file ? 'PDF attached — click submit' : '@handle or paste a URL'}
          disabled={isSubmitting || disabled || !!file}
          className="flex-1 bg-transparent py-4 pl-2 text-white placeholder-gray-600 focus:outline-none disabled:opacity-50 text-base"
        />
        {/* PDF upload button */}
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={isSubmitting || disabled}
          className="p-2 text-gray-500 hover:text-white hover:bg-white/5 rounded-lg transition-all disabled:opacity-30"
          title="Upload PDF"
        >
          <Paperclip className="w-5 h-5" />
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,application/pdf"
          onChange={handleFileChange}
          className="hidden"
        />
        {/* Submit button */}
        <button
          type="submit"
          disabled={!hasInput || isSubmitting || disabled}
          className="ml-1 mb-2 p-3 rounded-xl bg-brand-blue text-black hover:bg-brand-blue-hover disabled:opacity-30 disabled:hover:bg-brand-blue transition-all"
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
