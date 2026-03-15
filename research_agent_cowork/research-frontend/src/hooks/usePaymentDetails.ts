import { useEffect, useState } from 'react';
import { fetchPaymentDetails } from '@/lib/api';
import type { PaymentDetails } from '@/types';

export function usePaymentDetails(taskId: string) {
  const [details, setDetails] = useState<PaymentDetails | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    const loadDetails = async () => {
      setIsLoading(true);
      setError(null);

      try {
        const nextDetails = await fetchPaymentDetails(taskId);
        if (active) {
          setDetails(nextDetails);
        }
      } catch (err) {
        if (active) {
          setError(err instanceof Error ? err.message : 'Failed to load payment details');
        }
      } finally {
        if (active) {
          setIsLoading(false);
        }
      }
    };

    void loadDetails();

    return () => {
      active = false;
    };
  }, [taskId]);

  return {
    details,
    isLoading,
    error,
  };
}
