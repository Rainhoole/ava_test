import { Task, TaskListResponse, ReportResponse, PaymentDetails, ResearchRequest } from '@/types';
import { ensureAuthenticated, getJwt } from './fluxa';
import { DISABLE_AUTH, LITE_MODE, PUBLIC_API_URL } from './runtime';

const API_BASE = PUBLIC_API_URL;
const USE_DEMO_FALLBACK = LITE_MODE || API_BASE.trim() === '';
const DEMO_TASKS_PATH = '/demo/tasks.json';
const DEMO_REPORTS_BASE = '/demo/reports';

async function fetchDemoTasks(): Promise<TaskListResponse> {
  const res = await fetch(DEMO_TASKS_PATH, { cache: 'no-store' });
  if (!res.ok) {
    throw new Error(`Failed to fetch demo tasks: ${res.statusText}`);
  }
  return res.json();
}

async function fetchDemoReport(taskId: string): Promise<ReportResponse> {
  const reportRes = await fetch(`${DEMO_REPORTS_BASE}/${taskId}.md`, { cache: 'no-store' });
  if (!reportRes.ok) {
    throw new Error(`Failed to fetch demo report: ${reportRes.statusText}`);
  }
  const content = await reportRes.text();

  const tasks = await fetchDemoTasks().catch(() => ({ tasks: [], total: 0 } as TaskListResponse));
  const task = tasks.tasks.find((t) => t.task_id === taskId);

  return {
    task_id: taskId,
    handle: task?.handle || '@axis_robotics',
    status: 'completed',
    report: {
      content,
      filename: `${taskId}_report.md`,
      size_bytes: new TextEncoder().encode(content).length,
    },
  };
}

async function withAuthHeaders(init: RequestInit = {}): Promise<RequestInit> {
  if (DISABLE_AUTH) {
    return init;
  }

  const authResult = await ensureAuthenticated();
  if (!authResult.success || !authResult.jwt) {
    throw new Error(authResult.error || 'Authentication required');
  }

  const headers = new Headers(init.headers || {});
  headers.set('Authorization', `Bearer ${authResult.jwt}`);
  return { ...init, headers };
}

export async function fetchTasks(limit = 50, offset = 0, status?: string): Promise<TaskListResponse> {
  if (USE_DEMO_FALLBACK) {
    return fetchDemoTasks();
  }

  const params = new URLSearchParams({
    limit: limit.toString(),
    offset: offset.toString(),
  });
  if (status) {
    params.append('status', status);
  }

  try {
    const res = await fetch(`${API_BASE}/research_lists_magic?${params}`, await withAuthHeaders());
    if (!res.ok) {
      throw new Error(`Failed to fetch tasks: ${res.statusText}`);
    }
    const data = await res.json() as TaskListResponse;
    if (USE_DEMO_FALLBACK && (!data.tasks || data.tasks.length === 0)) {
      return fetchDemoTasks();
    }
    return data;
  } catch (err) {
    if (USE_DEMO_FALLBACK) {
      return fetchDemoTasks();
    }
    throw err;
  }
}

export async function fetchTask(taskId: string): Promise<Task> {
  const res = await fetch(`${API_BASE}/research/${taskId}`, await withAuthHeaders());
  if (!res.ok) {
    throw new Error(`Failed to fetch task: ${res.statusText}`);
  }
  return res.json();
}

export async function submitResearch(request: ResearchRequest): Promise<Task> {
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
  if (USE_DEMO_FALLBACK) {
    return fetchDemoReport(taskId);
  }

  try {
    const res = await fetch(`${API_BASE}/research/${taskId}/report`, await withAuthHeaders());
    if (!res.ok) {
      throw new Error(`Failed to fetch report: ${res.statusText}`);
    }
    return res.json();
  } catch (err) {
    if (USE_DEMO_FALLBACK) {
      return fetchDemoReport(taskId);
    }
    throw err;
  }
}

export async function downloadReport(taskId: string): Promise<Blob> {
  if (USE_DEMO_FALLBACK) {
    const demo = await fetch(`${DEMO_REPORTS_BASE}/${taskId}.md`, { cache: 'no-store' });
    if (!demo.ok) {
      throw new Error(`Failed to download demo report: ${demo.statusText}`);
    }
    return demo.blob();
  }

  try {
    const res = await fetch(`${API_BASE}/research/${taskId}/report?download=true`, await withAuthHeaders());
    if (!res.ok) {
      throw new Error(`Failed to download report: ${res.statusText}`);
    }
    return res.blob();
  } catch (err) {
    if (USE_DEMO_FALLBACK) {
      const demo = await fetch(`${DEMO_REPORTS_BASE}/${taskId}.md`, { cache: 'no-store' });
      if (!demo.ok) {
        throw new Error(`Failed to download demo report: ${demo.statusText}`);
      }
      return demo.blob();
    }
    throw err;
  }
}

export async function createLogStream(taskId: string, fromLine = 0): Promise<EventSource> {
  if (DISABLE_AUTH) {
    const params = new URLSearchParams({ from_line: fromLine.toString() });
    return new EventSource(`${API_BASE}/research/${taskId}/replay?${params.toString()}`);
  }

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
