const trimTrailingSlash = (value: string) => value.replace(/\/+$/, '');

export const DEFAULT_LOCAL_API_URL = 'http://localhost:8000';
export const PUBLIC_API_URL = (process.env.NEXT_PUBLIC_API_URL ?? '').trim();
export const PUBLIC_APP_URL = trimTrailingSlash((process.env.NEXT_PUBLIC_APP_URL ?? '').trim());
export const DISABLE_AUTH = process.env.NEXT_PUBLIC_DISABLE_AUTH === 'true';
export const LITE_MODE = process.env.NEXT_PUBLIC_LITE_MODE === 'true';

export function resolvePublicAppUrl(): string {
  if (PUBLIC_APP_URL) {
    return PUBLIC_APP_URL;
  }

  if (typeof window !== 'undefined') {
    return trimTrailingSlash(window.location.origin);
  }

  return '';
}

export function getSkillUrl(): string {
  const appUrl = resolvePublicAppUrl();
  return appUrl ? `${appUrl}/skill.md` : '';
}
