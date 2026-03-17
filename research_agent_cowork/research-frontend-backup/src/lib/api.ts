import { Task, TaskListResponse, ReportResponse, ConfigResponse, PaymentDetails, ResearchRequest, RetryPaymentResponse } from '@/types';
import { ensureAuthenticated, getJwt } from './fluxa';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';

async function withAuthHeaders(init: RequestInit = {}): Promise<RequestInit> {
  const authResult = await ensureAuthenticated();
  if (!authResult.success || !authResult.jwt) {
    throw new Error(authResult.error || 'Authentication required');
  }

  const headers = new Headers(init.headers || {});
  headers.set('Authorization', `Bearer ${authResult.jwt}`);
  return { ...init, headers };
}

export async function fetchTasks(limit = 50, offset = 0, status?: string): Promise<TaskListResponse> {
  const params = new URLSearchParams({
    limit: limit.toString(),
    offset: offset.toString(),
  });
  if (status) {
    params.append('status', status);
  }

  const res = await fetch(`${API_BASE}/research_lists_magic?${params}`, await withAuthHeaders());
  if (!res.ok) {
    throw new Error(`Failed to fetch tasks: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchTask(taskId: string): Promise<Task> {
  const res = await fetch(`${API_BASE}/research/${taskId}`, await withAuthHeaders());
  if (!res.ok) {
    throw new Error(`Failed to fetch task: ${res.statusText}`);
  }
  return res.json();
}

export async function submitResearch(request: ResearchRequest, file?: File): Promise<Task> {
  if (file) {
    // Use FormData for file upload (POST /research/upload)
    const formData = new FormData();
    formData.append('handle', request.handle);
    formData.append('mandate_id', request.mandate_id || '');
    formData.append('budget_usd', String(request.budget_usd ?? 2));
    if (request.fluxa_jwt) formData.append('fluxa_jwt', request.fluxa_jwt);
    if (request.engine) formData.append('engine', request.engine);
    formData.append('file', file);

    // Don't set Content-Type — browser sets multipart boundary automatically
    const authInit = await withAuthHeaders({ method: 'POST', body: formData });
    // Remove Content-Type if withAuthHeaders set it (FormData needs boundary)
    const headers = new Headers(authInit.headers);
    headers.delete('Content-Type');

    const res = await fetch(`${API_BASE}/research/upload`, { ...authInit, headers });
    if (!res.ok) {
      throw new Error(`Failed to submit research: ${res.statusText}`);
    }
    return res.json();
  }

  // JSON path for handle/URL-only requests
  const res = await fetch(`${API_BASE}/research`, await withAuthHeaders({
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(request),
  }));
  if (!res.ok) {
    throw new Error(`Failed to submit research: ${res.statusText}`);
  }
  return res.json();
}

export async function cancelTask(taskId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/research/${taskId}`, await withAuthHeaders({
    method: 'DELETE',
  }));
  if (!res.ok) {
    throw new Error(`Failed to cancel task: ${res.statusText}`);
  }
}

export async function fetchReport(taskId: string): Promise<ReportResponse> {
  const res = await fetch(`${API_BASE}/research/${taskId}/report`, await withAuthHeaders());
  if (!res.ok) {
    throw new Error(`Failed to fetch report: ${res.statusText}`);
  }
  return res.json();
}

export async function downloadReport(taskId: string): Promise<Blob> {
  const res = await fetch(`${API_BASE}/research/${taskId}/report?download=true`, await withAuthHeaders());
  if (!res.ok) {
    throw new Error(`Failed to download report: ${res.statusText}`);
  }
  return res.blob();
}

export async function downloadLog(taskId: string): Promise<Blob> {
  const res = await fetch(`${API_BASE}/research/${taskId}/log`, await withAuthHeaders());
  if (!res.ok) {
    throw new Error(`Failed to download log: ${res.statusText}`);
  }
  return res.blob();
}

export async function fetchConfig(): Promise<ConfigResponse> {
  const res = await fetch(`${API_BASE}/config`, await withAuthHeaders());
  if (!res.ok) {
    throw new Error(`Failed to fetch config: ${res.statusText}`);
  }
  return res.json();
}

export async function createLogStream(taskId: string, fromLine = 0): Promise<EventSource> {
  const authResult = await ensureAuthenticated();
  const jwt = authResult.jwt || getJwt();
  if (!authResult.success || !jwt) {
    throw new Error(authResult.error || 'Authentication required');
  }
  const params = new URLSearchParams({ from_line: fromLine.toString(), jwt });
  return new EventSource(`${API_BASE}/research/${taskId}/replay?${params.toString()}`);
}

// ==================== Payment API ====================
// Note: Mandate creation is done directly via fluxa.ts -> Fluxa API

export async function fetchPaymentDetails(taskId: string): Promise<PaymentDetails> {
  const res = await fetch(`${API_BASE}/research/${taskId}/payment`, await withAuthHeaders());
  if (!res.ok) {
    throw new Error(`Failed to fetch payment details: ${res.statusText}`);
  }
  return res.json();
}

export async function retryResearch(taskId: string): Promise<Task> {
  const res = await fetch(`${API_BASE}/research/${taskId}/retry`, await withAuthHeaders({
    method: 'POST',
  }));
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || `Failed to retry research: ${res.statusText}`);
  }
  return res.json();
}

export async function retryPayment(taskId: string, mandateId: string): Promise<RetryPaymentResponse> {
  const jwt = getJwt();
  const res = await fetch(`${API_BASE}/research/${taskId}/retry-payment`, await withAuthHeaders({
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ mandate_id: mandateId, fluxa_jwt: jwt }),
  }));
  return res.json();
}
