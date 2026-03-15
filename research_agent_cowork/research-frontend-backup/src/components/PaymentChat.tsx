'use client';

import { useState, useEffect, useRef } from 'react';
import { Bot, User, ExternalLink, Loader2, CheckCircle, Wallet } from 'lucide-react';
import {
  createIntentMandate,
  getJwt,
  DEFAULT_BUDGET_USD,
  DEFAULT_MANDATE_DAYS,
  formatUSD,
} from '@/lib/fluxa';

interface Message {
  id: string;
  role: 'assistant' | 'user' | 'system';
  content: string;
  timestamp: Date;
  action?: {
    type: 'authorize' | 'confirm' | 'ask_budget';
    url?: string;
  };
}

interface PaymentChatProps {
  handle: string;
  onAuthorized: (mandateId: string, budgetUsd: number, fluxaJwt: string) => void;
  onCancel: () => void;
}

export default function PaymentChat({ handle, onAuthorized, onCancel }: PaymentChatProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [authUrl, setAuthUrl] = useState<string | null>(null);
  const [mandateId, setMandateId] = useState<string | null>(null);
  const [step, setStep] = useState<'ask' | 'creating' | 'authorize' | 'waiting' | 'done'>('ask');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Initial message - always ask for new budget per research
  useEffect(() => {
    addMessage('assistant', `To research **${handle}**, I need a ${formatUSD(DEFAULT_BUDGET_USD)} budget from your Fluxa Wallet.\n\nTypical cost: $0.50 - $2.00 per research.`, {
      type: 'ask_budget',
    });
  }, [handle]);

  const addMessage = (role: 'assistant' | 'user' | 'system', content: string, action?: Message['action']) => {
    const msg: Message = {
      id: Date.now().toString(),
      role,
      content,
      timestamp: new Date(),
      action,
    };
    setMessages(prev => [...prev, msg]);
  };

  const handleApprove = async () => {
    setStep('creating');
    addMessage('user', `Approve ${formatUSD(DEFAULT_BUDGET_USD)} budget`);
    setIsLoading(true);

    addMessage('assistant', `Creating budget request...`);

    const result = await createIntentMandate(
      DEFAULT_BUDGET_USD,
      1,
      `Research budget for ${handle}: ${formatUSD(DEFAULT_BUDGET_USD)} USDC`
    );

    setIsLoading(false);

    if (result.success && result.mandateId && result.authorizationUrl) {
      setMandateId(result.mandateId);
      setAuthUrl(result.authorizationUrl);
      setStep('authorize');

      addMessage('assistant', `Please approve the budget in your Fluxa Wallet.`, {
        type: 'authorize',
        url: result.authorizationUrl,
      });
    } else {
      addMessage('system', `Failed to create budget: ${result.error || 'Unknown error'}`);
      setStep('ask');
    }
  };

  const handleOpenAuth = () => {
    if (authUrl) {
      window.open(authUrl, '_blank', 'noopener,noreferrer');
      setStep('waiting');
      addMessage('assistant', `Wallet opened. After approving, click "Budget Approved" below.`);
    }
  };

  const handleConfirmAuth = () => {
    if (mandateId) {
      const jwt = getJwt();
      if (!jwt) {
        addMessage('system', 'Authentication error: JWT not found');
        return;
      }

      setStep('done');
      addMessage('user', `Budget approved`);
      addMessage('assistant', `Budget confirmed! Starting research for **${handle}**...`);

      setTimeout(() => {
        onAuthorized(mandateId, DEFAULT_BUDGET_USD, jwt);
      }, 1000);
    }
  };

  return (
    <div className="flex-1 flex flex-col bg-black">
      {/* Chat header */}
      <div className="px-6 py-4 border-b border-white/[0.06] bg-black">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-sky-500/10 flex items-center justify-center">
            <Wallet className="w-4 h-4 text-brand-blue" />
          </div>
          <div>
            <h3 className="font-medium text-white">Research Budget</h3>
            <p className="text-xs text-gray-500">Fluxa Wallet</p>
          </div>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        {messages.map((msg) => (
          <div key={msg.id} className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : ''}`}>
            {msg.role === 'assistant' && (
              <div className="w-8 h-8 rounded-full bg-white/5 flex items-center justify-center flex-shrink-0">
                <Bot className="w-4 h-4 text-gray-400" />
              </div>
            )}

            <div className={`max-w-md ${msg.role === 'user' ? 'order-first' : ''}`}>
              <div
                className={`rounded-2xl px-4 py-3 ${
                  msg.role === 'user'
                    ? 'bg-brand-blue text-black'
                    : msg.role === 'system'
                    ? 'bg-red-500/10 text-red-400 border border-red-500/20'
                    : 'bg-white/5 border border-white/10'
                }`}
              >
                <p className="text-sm whitespace-pre-wrap">{msg.content}</p>

                {/* Budget approval buttons */}
                {msg.action?.type === 'ask_budget' && step === 'ask' && (
                  <div className="mt-3 flex flex-wrap gap-2">
                    <button
                      onClick={handleApprove}
                      disabled={isLoading}
                      className="px-4 py-2 bg-emerald-500 text-black text-sm font-medium rounded-xl hover:bg-emerald-400 disabled:opacity-50 transition-colors"
                    >
                      Approve Budget
                    </button>
                    <button
                      onClick={onCancel}
                      disabled={isLoading}
                      className="px-4 py-2 bg-white/5 text-gray-300 text-sm font-medium rounded-xl hover:bg-white/10 disabled:opacity-50 transition-colors border border-white/10"
                    >
                      Cancel
                    </button>
                  </div>
                )}

                {/* Open wallet button */}
                {msg.action?.type === 'authorize' && step === 'authorize' && (
                  <button
                    onClick={handleOpenAuth}
                    className="mt-3 flex items-center gap-2 px-4 py-2 bg-brand-blue text-black text-sm font-medium rounded-xl hover:bg-brand-blue-hover transition-colors"
                  >
                    <ExternalLink className="w-4 h-4" />
                    Open Fluxa Wallet
                  </button>
                )}
              </div>

              <p className="text-xs text-gray-600 mt-1 px-2">
                {msg.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </p>
            </div>

            {msg.role === 'user' && (
              <div className="w-8 h-8 rounded-full bg-white/5 flex items-center justify-center flex-shrink-0">
                <User className="w-4 h-4 text-gray-400" />
              </div>
            )}
          </div>
        ))}

        {isLoading && (
          <div className="flex gap-3">
            <div className="w-8 h-8 rounded-full bg-white/5 flex items-center justify-center flex-shrink-0">
              <Bot className="w-4 h-4 text-gray-400" />
            </div>
            <div className="bg-white/5 border border-white/10 rounded-2xl px-4 py-3">
              <Loader2 className="w-5 h-5 animate-spin text-gray-500" />
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Bottom action bar */}
      <div className="px-6 py-4 border-t border-white/[0.06] bg-black">
        {step === 'waiting' && (
          <div className="flex gap-3">
            <button
              onClick={handleConfirmAuth}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-3 bg-emerald-500 text-black font-medium rounded-xl hover:bg-emerald-400 transition-colors"
            >
              <CheckCircle className="w-5 h-5" />
              Budget Approved
            </button>
            <button
              onClick={handleOpenAuth}
              className="px-4 py-3 text-gray-400 hover:text-white hover:bg-white/5 rounded-xl transition-colors"
            >
              Open Again
            </button>
          </div>
        )}

        {step === 'ask' && (
          <p className="text-center text-xs text-gray-600">
            Unused budget will remain in your wallet
          </p>
        )}

        {step === 'done' && (
          <div className="flex items-center justify-center gap-2 text-emerald-400">
            <CheckCircle className="w-5 h-5" />
            <span className="font-medium">Budget Approved</span>
          </div>
        )}
      </div>
    </div>
  );
}
