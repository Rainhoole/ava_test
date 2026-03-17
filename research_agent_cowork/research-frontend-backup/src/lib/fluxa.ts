/**
 * Fluxa Payment Utilities
 *
 * Handles Fluxa agent ID generation, registration, JWT management,
 * and mandate management for the frontend payment flow.
 */

const FLUXA_AGENT_ID_KEY = 'fluxa_agent_id';
const FLUXA_AGENT_TOKEN_KEY = 'fluxa_agent_token';
const FLUXA_JWT_KEY = 'fluxa_jwt';
const FLUXA_MANDATE_KEY = 'fluxa_mandate';

// Default research budget in USD
export const DEFAULT_BUDGET_USD = 2;

// Mandate validity in days
export const DEFAULT_MANDATE_DAYS = 30;

// Check if we're in a browser environment
const isBrowser = typeof window !== 'undefined';

// Fluxa API endpoints
const FLUXA_AGENT_ID_API = 'https://agentid.fluxapay.xyz';
const FLUXA_WALLET_API = 'https://walletapi.fluxapay.xyz';

interface StoredMandate {
  mandate_id: string;
  budget_usd: number;
  created_at: string;
  expires_at: string;
  authorization_url?: string;
  authorized: boolean;
}

/**
 * Generate a unique Fluxa agent ID for this browser session.
 * The ID is stored in localStorage for persistence.
 */
export function generateFluxaAgentId(): string {
  if (!isBrowser) return '';

  // Check if we already have an agent ID
  const existingId = localStorage.getItem(FLUXA_AGENT_ID_KEY);
  if (existingId) {
    return existingId;
  }

  // Generate a new agent ID
  const timestamp = Date.now().toString(36);
  const randomPart = Math.random().toString(36).substring(2, 10);
  const agentId = `fluxa_${timestamp}_${randomPart}`;

  // Store it
  localStorage.setItem(FLUXA_AGENT_ID_KEY, agentId);

  return agentId;
}

/**
 * Get the current Fluxa agent ID, or null if none exists.
 */
export function getFluxaAgentId(): string | null {
  if (!isBrowser) return null;
  return localStorage.getItem(FLUXA_AGENT_ID_KEY);
}

/**
 * Clear the stored Fluxa agent ID.
 */
export function clearFluxaAgentId(): void {
  if (!isBrowser) return;
  localStorage.removeItem(FLUXA_AGENT_ID_KEY);
  localStorage.removeItem(FLUXA_AGENT_TOKEN_KEY);
  localStorage.removeItem(FLUXA_JWT_KEY);
}

/**
 * Store the Fluxa agent token (used for JWT refresh).
 */
function storeAgentToken(token: string): void {
  if (!isBrowser) return;
  localStorage.setItem(FLUXA_AGENT_TOKEN_KEY, token);
}

/**
 * Get the stored Fluxa agent token.
 */
function getAgentToken(): string | null {
  if (!isBrowser) return null;
  return localStorage.getItem(FLUXA_AGENT_TOKEN_KEY);
}

/**
 * Store the JWT for API authentication.
 */
function storeJwt(jwt: string): void {
  if (!isBrowser) return;
  localStorage.setItem(FLUXA_JWT_KEY, jwt);
}

/**
 * Get the stored JWT.
 */
export function getJwt(): string | null {
  if (!isBrowser) return null;
  return localStorage.getItem(FLUXA_JWT_KEY);
}

/**
 * Check if a JWT is expired (or will expire within bufferSeconds).
 * Decodes the base64 payload to read the `exp` claim.
 */
function isJwtExpired(jwt: string, bufferSeconds: number = 60): boolean {
  try {
    const parts = jwt.split('.');
    if (parts.length !== 3) return true;
    // base64url → base64 → decode
    const payload = parts[1].replace(/-/g, '+').replace(/_/g, '/');
    const decoded = JSON.parse(atob(payload));
    if (!decoded.exp) return true;
    const nowSec = Math.floor(Date.now() / 1000);
    return decoded.exp <= nowSec + bufferSeconds;
  } catch {
    return true; // If we can't decode, treat as expired
  }
}

/**
 * Register a new agent with Fluxa and get initial JWT.
 * Returns true if successful.
 */
export async function registerAgentId(): Promise<{ success: boolean; error?: string }> {
  if (!isBrowser) {
    return { success: false, error: 'Not in browser environment' };
  }

  // Check if already registered (has token)
  if (getAgentToken() && getJwt()) {
    return { success: true };
  }

  // Generate a unique email for this browser instance
  const uniqueId = generateFluxaAgentId();
  const email = `${uniqueId}@research.local`;
  const agentName = `ResearchAgent-${uniqueId.slice(-8)}`;
  const clientInfo = window.location.origin;

  try {
    const response = await fetch(`${FLUXA_AGENT_ID_API}/register`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        email: email,
        agent_name: agentName,
        client_info: clientInfo,
      }),
    });

    const data = await response.json();

    if (response.ok && data.token && data.jwt) {
      storeAgentToken(data.token);
      storeJwt(data.jwt);
      // Store the agent_id returned from API
      if (data.agent_id) {
        localStorage.setItem(FLUXA_AGENT_ID_KEY, data.agent_id);
      }
      return { success: true };
    } else {
      return {
        success: false,
        error: data.error || data.message || `Registration failed: ${response.status}`,
      };
    }
  } catch (error) {
    return {
      success: false,
      error: error instanceof Error ? error.message : 'Failed to register agent',
    };
  }
}

/**
 * Refresh the JWT using the stored token.
 */
export async function refreshJwt(): Promise<{ success: boolean; error?: string }> {
  if (!isBrowser) {
    return { success: false, error: 'Not in browser environment' };
  }

  const agentId = getFluxaAgentId();
  const token = getAgentToken();

  if (!agentId || !token) {
    // Need to register first
    return registerAgentId();
  }

  try {
    const response = await fetch(`${FLUXA_AGENT_ID_API}/refresh`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ agent_id: agentId, token }),
    });

    const data = await response.json();

    if (response.ok && data.jwt) {
      storeJwt(data.jwt);
      return { success: true };
    } else {
      // Token might be invalid, try re-registering
      clearFluxaAgentId();
      return registerAgentId();
    }
  } catch (error) {
    return {
      success: false,
      error: error instanceof Error ? error.message : 'Failed to refresh JWT',
    };
  }
}

/**
 * Ensure we have a valid, non-expired JWT.
 * Registers if needed, refreshes if expired or about to expire.
 */
export async function ensureAuthenticated(): Promise<{ success: boolean; jwt?: string; error?: string }> {
  if (!isBrowser) {
    return { success: false, error: 'Not in browser environment' };
  }

  let jwt = getJwt();

  // If no JWT at all, need to register
  if (!jwt) {
    const result = await registerAgentId();
    if (!result.success) {
      return result;
    }
    jwt = getJwt();
  }

  // If JWT is expired or about to expire, refresh it
  if (jwt && isJwtExpired(jwt, 120)) {
    console.log('[Fluxa] JWT expired or expiring soon, refreshing...');
    const refreshResult = await refreshJwt();
    if (!refreshResult.success) {
      return { success: false, error: refreshResult.error || 'JWT refresh failed' };
    }
    jwt = getJwt();
  }

  if (jwt) {
    return { success: true, jwt };
  }

  return { success: false, error: 'Failed to obtain JWT' };
}

/**
 * Store a mandate in localStorage.
 */
export function storeMandate(mandate: StoredMandate): void {
  if (!isBrowser) return;
  localStorage.setItem(FLUXA_MANDATE_KEY, JSON.stringify(mandate));
}

/**
 * Get the stored mandate, or null if none exists.
 */
export function getStoredMandate(): StoredMandate | null {
  if (!isBrowser) return null;

  const stored = localStorage.getItem(FLUXA_MANDATE_KEY);
  if (!stored) return null;

  try {
    const mandate = JSON.parse(stored) as StoredMandate;

    // Check if mandate has expired
    if (new Date(mandate.expires_at) < new Date()) {
      clearStoredMandate();
      return null;
    }

    return mandate;
  } catch {
    return null;
  }
}

/**
 * Clear the stored mandate.
 */
export function clearStoredMandate(): void {
  if (!isBrowser) return;
  localStorage.removeItem(FLUXA_MANDATE_KEY);
}

/**
 * Check if the stored mandate is authorized.
 */
export function isMandateAuthorized(): boolean {
  const mandate = getStoredMandate();
  return mandate?.authorized ?? false;
}

/**
 * Mark the stored mandate as authorized.
 */
export function markMandateAuthorized(): void {
  if (!isBrowser) return;
  const mandate = getStoredMandate();
  if (mandate) {
    mandate.authorized = true;
    storeMandate(mandate);
  }
}

/**
 * Create a new mandate and store it.
 * Returns the mandate with authorization URL.
 */
export function createAndStoreMandate(
  mandate_id: string,
  budget_usd: number,
  authorization_url?: string,
  valid_days: number = DEFAULT_MANDATE_DAYS
): StoredMandate {
  const now = new Date();
  const expiresAt = new Date(now.getTime() + valid_days * 24 * 60 * 60 * 1000);

  const mandate: StoredMandate = {
    mandate_id,
    budget_usd,
    created_at: now.toISOString(),
    expires_at: expiresAt.toISOString(),
    authorization_url,
    authorized: false,
  };

  storeMandate(mandate);
  return mandate;
}

/**
 * Check if we have a valid, authorized mandate with sufficient budget.
 */
export function hasValidMandate(requiredBudget: number = DEFAULT_BUDGET_USD): boolean {
  const mandate = getStoredMandate();
  if (!mandate) return false;
  if (!mandate.authorized) return false;
  if (mandate.budget_usd < requiredBudget) return false;
  return true;
}

/**
 * Format USD amount for display.
 */
export function formatUSD(amount: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  }).format(amount);
}

/**
 * Format payment status for display.
 */
export function formatPaymentStatus(status: string): {
  label: string;
  color: 'gray' | 'yellow' | 'blue' | 'green' | 'red';
} {
  switch (status) {
    case 'pending':
      return { label: 'Pending', color: 'gray' };
    case 'authorized':
      return { label: 'Authorized', color: 'blue' };
    case 'processing':
      return { label: 'Processing', color: 'yellow' };
    case 'completed':
      return { label: 'Paid', color: 'green' };
    case 'failed':
      return { label: 'Failed', color: 'red' };
    case 'skipped':
      return { label: 'Skipped', color: 'gray' };
    default:
      return { label: status, color: 'gray' };
  }
}

// ==================== Fluxa API (Direct Frontend Calls) ====================

export interface CreateMandateResponse {
  success: boolean;
  mandateId?: string;
  authorizationUrl?: string;
  error?: string;
}

export interface MandateDetails {
  mandateId: string;
  status: string;
  isEnabled: boolean;
  naturalLanguage?: string;
  category?: string;
  currency?: string;
  limitAmount?: string;
  spentAmount?: string;
  pendingSpentAmount?: string;
  remainingAmount?: string;
  validFrom?: string;
  validUntil?: string;
  hostAllowlist?: string[];
  mandateHash?: string;
  signedAt?: string;
  createdAt?: string;
}

/**
 * Create an intent mandate by calling Fluxa API directly from frontend.
 * This returns an authorization URL that the user must visit to sign.
 * Automatically handles authentication and JWT refresh.
 */
export async function createIntentMandate(
  budgetUsd: number,
  validDays: number = DEFAULT_MANDATE_DAYS,
  description?: string
): Promise<CreateMandateResponse> {
  if (!isBrowser) {
    return { success: false, error: 'Not in browser environment' };
  }

  // Ensure we have authentication
  const authResult = await ensureAuthenticated();
  if (!authResult.success || !authResult.jwt) {
    return { success: false, error: authResult.error || 'Failed to authenticate' };
  }

  const validSeconds = validDays * 24 * 60 * 60;
  // USDC has 6 decimals
  const limitAmount = Math.floor(budgetUsd * 1_000_000).toString();

  const payload = {
    intent: {
      naturalLanguage: description || `Research agent budget of $${budgetUsd.toFixed(2)} USDC valid for ${validDays} days`,
      category: 'research_data',
      currency: 'USDC',
      limitAmount,
      validForSeconds: validSeconds,
      hostAllowlist: [],
    },
  };

  // Make request with JWT authentication
  const makeRequest = async (jwt: string): Promise<Response> => {
    return fetch(`${FLUXA_WALLET_API}/api/mandates/create-intent`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${jwt}`,
      },
      body: JSON.stringify(payload),
    });
  };

  try {
    let response = await makeRequest(authResult.jwt);
    let data = await response.json();

    // Handle auth failures - try refreshing JWT and retry once
    const isAuthError = response.status === 401 || response.status === 403 ||
      (data.error && typeof data.error === 'string' && data.error.toLowerCase().includes('jwt'));

    if (isAuthError) {
      console.log('[Fluxa] Auth error on mandate creation, refreshing JWT...');
      const refreshResult = await refreshJwt();
      if (refreshResult.success) {
        const newJwt = getJwt();
        if (newJwt) {
          response = await makeRequest(newJwt);
          data = await response.json();
        }
      }
    }

    if (response.ok && data.mandateId) {
      return {
        success: true,
        mandateId: data.mandateId,
        authorizationUrl: data.authorizationUrl,
      };
    } else {
      return {
        success: false,
        error: data.error || data.message || `Failed to create mandate: ${response.status}`,
      };
    }
  } catch (error) {
    return {
      success: false,
      error: error instanceof Error ? error.message : 'Failed to create mandate',
    };
  }
}

/**
 * Fetch details for a specific mandate.
 * Uses the wallet API with JWT authentication.
 */
export async function fetchMandateById(
  mandateId: string
): Promise<{ success: boolean; mandate?: MandateDetails; error?: string }> {
  if (!isBrowser) {
    return { success: false, error: 'Not in browser environment' };
  }

  const authResult = await ensureAuthenticated();
  if (!authResult.success || !authResult.jwt) {
    return { success: false, error: authResult.error || 'Failed to authenticate' };
  }

  const makeRequest = async (jwt: string): Promise<Response> => {
    return fetch(`${FLUXA_WALLET_API}/api/mandates/agent/${mandateId}`, {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${jwt}`,
      },
    });
  };

  try {
    let response = await makeRequest(authResult.jwt);
    let data = await response.json();

    const isAuthError = response.status === 401 || response.status === 403 ||
      (data.error && typeof data.error === 'string' && data.error.toLowerCase().includes('jwt'));

    if (isAuthError) {
      const refreshResult = await refreshJwt();
      if (refreshResult.success) {
        const newJwt = getJwt();
        if (newJwt) {
          response = await makeRequest(newJwt);
          data = await response.json();
        }
      }
    }

    const mandate = data?.mandateId
      ? data
      : data?.mandate
      ? data.mandate
      : Array.isArray(data?.mandates)
      ? data.mandates[0]
      : null;

    if (response.ok && mandate?.mandateId) {
      return { success: true, mandate };
    }

    return {
      success: false,
      error: data?.error || data?.message || `Failed to fetch mandate: ${response.status}`,
    };
  } catch (error) {
    return {
      success: false,
      error: error instanceof Error ? error.message : 'Failed to fetch mandate',
    };
  }
}
