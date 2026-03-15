import { startTransition, useCallback, useEffect, useRef, useState } from 'react';
import { fetchTask, fetchTasks, submitResearch } from '@/lib/api';
import { ensureAuthenticated } from '@/lib/fluxa';
import { DISABLE_AUTH } from '@/lib/runtime';
import type { Engine, Task } from '@/types';

const TASK_POLL_INTERVAL_MS = 5000;
const SELECTED_TASK_POLL_INTERVAL_MS = 2000;

export function useWorkspaceTasks(initialTaskId?: string | null) {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);
  const [isLoadingTasks, setIsLoadingTasks] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const selectedTaskRef = useRef<Task | null>(null);
  const preferredTaskIdRef = useRef<string | null>(initialTaskId ?? null);

  useEffect(() => {
    selectedTaskRef.current = selectedTask;
  }, [selectedTask]);

  useEffect(() => {
    preferredTaskIdRef.current = initialTaskId ?? null;

    if (!initialTaskId) {
      return;
    }

    const preferredTask = tasks.find((task) => task.task_id === initialTaskId);
    if (!preferredTask || selectedTaskRef.current?.task_id === preferredTask.task_id) {
      return;
    }

    selectedTaskRef.current = preferredTask;
    setSelectedTask(preferredTask);
  }, [initialTaskId, tasks]);

  const applyTaskSnapshot = useCallback((nextTasks: Task[]) => {
    startTransition(() => {
      setTasks(nextTasks);

      const preferredTaskId = preferredTaskIdRef.current;
      if (preferredTaskId) {
        const preferredTask = nextTasks.find((task) => task.task_id === preferredTaskId);
        if (preferredTask && selectedTaskRef.current?.task_id !== preferredTask.task_id) {
          selectedTaskRef.current = preferredTask;
          setSelectedTask(preferredTask);
          return;
        }
      }

      if (!selectedTaskRef.current && nextTasks.length > 0) {
        selectedTaskRef.current = nextTasks[0];
        setSelectedTask(nextTasks[0]);
        return;
      }

      if (selectedTaskRef.current) {
        const updatedTask = nextTasks.find((task) => task.task_id === selectedTaskRef.current?.task_id);
        if (updatedTask) {
          setSelectedTask(updatedTask);
        }
      }
    });
  }, []);

  const refreshTasks = useCallback(async () => {
    try {
      const response = await fetchTasks(100);
      applyTaskSnapshot(response.tasks);
    } catch (err) {
      console.error('Failed to load tasks:', err);
    } finally {
      setIsLoadingTasks(false);
    }
  }, [applyTaskSnapshot]);

  useEffect(() => {
    let active = true;

    const init = async () => {
      if (!DISABLE_AUTH) {
        const authResult = await ensureAuthenticated();
        if (!authResult.success) {
          console.error('Failed to authenticate:', authResult.error);
        }
      }

      if (active) {
        await refreshTasks();
      }
    };

    void init();

    return () => {
      active = false;
    };
  }, [refreshTasks]);

  useEffect(() => {
    const hasRunningTasks = tasks.some((task) => task.status === 'running' || task.status === 'pending');
    if (!hasRunningTasks) {
      return;
    }

    const interval = window.setInterval(() => {
      void refreshTasks();
    }, TASK_POLL_INTERVAL_MS);

    return () => window.clearInterval(interval);
  }, [tasks, refreshTasks]);

  useEffect(() => {
    if (!selectedTask || selectedTask.status !== 'running') {
      return;
    }

    const interval = window.setInterval(async () => {
      try {
        const updatedTask = await fetchTask(selectedTask.task_id);
        startTransition(() => {
          setSelectedTask(updatedTask);
          setTasks((prev) => prev.map((task) => (task.task_id === updatedTask.task_id ? updatedTask : task)));
        });
      } catch (err) {
        console.error('Failed to update task:', err);
      }
    }, SELECTED_TASK_POLL_INTERVAL_MS);

    return () => window.clearInterval(interval);
  }, [selectedTask]);

  const submitTask = useCallback(
    async (
      handle: string,
      engine: Engine,
      mandateId?: string,
      budgetUsd?: number,
      fluxaJwt?: string
    ) => {
      setIsSubmitting(true);

      try {
        const nextTask = await submitResearch({
          handle,
          engine,
          mandate_id: mandateId,
          budget_usd: budgetUsd,
          fluxa_jwt: fluxaJwt,
        });

        startTransition(() => {
          setTasks((prev) => [nextTask, ...prev]);
          selectedTaskRef.current = nextTask;
          setSelectedTask(nextTask);
        });
      } catch (err) {
        console.error('Failed to submit research:', err);
      } finally {
        setIsSubmitting(false);
      }
    },
    []
  );

  const selectTask = useCallback((task: Task | null) => {
    selectedTaskRef.current = task;
    setSelectedTask(task);
  }, []);

  const startNewResearch = useCallback(() => {
    selectedTaskRef.current = null;
    setSelectedTask(null);
  }, []);

  return {
    tasks,
    selectedTask,
    isLoadingTasks,
    isSubmitting,
    refreshTasks,
    submitTask,
    selectTask,
    startNewResearch,
  };
}
