'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { Task, Engine } from '@/types';
import { fetchTasks, submitResearch, fetchTask } from '@/lib/api';
import { ensureAuthenticated } from '@/lib/fluxa';
import Sidebar from '@/components/Sidebar';
import MainPanel from '@/components/MainPanel';

const POLL_INTERVAL = 5000; // 5 seconds

export default function Workspace() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);
  const [isLoadingTasks, setIsLoadingTasks] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const selectedTaskRef = useRef<Task | null>(null);

  useEffect(() => {
    selectedTaskRef.current = selectedTask;
  }, [selectedTask]);

  // Load tasks
  const loadTasks = useCallback(async () => {
    try {
      const response = await fetchTasks(100);
      setTasks(response.tasks);

      // Update selected task if it exists
      if (selectedTaskRef.current) {
        const updated = response.tasks.find((t) => t.task_id === selectedTaskRef.current?.task_id);
        if (updated) {
          setSelectedTask(updated);
        }
      }
    } catch (err) {
      console.error('Failed to load tasks:', err);
    } finally {
      setIsLoadingTasks(false);
    }
  }, []);

  // Initial load
  useEffect(() => {
    const init = async () => {
      const authResult = await ensureAuthenticated();
      if (!authResult.success) {
        console.error('Failed to authenticate:', authResult.error);
      }
      await loadTasks();
    };

    init();
  }, [loadTasks]);

  // Poll for updates when there are running tasks
  useEffect(() => {
    const hasRunningTasks = tasks.some((t) => t.status === 'running' || t.status === 'pending');

    if (!hasRunningTasks) return;

    const interval = setInterval(loadTasks, POLL_INTERVAL);
    return () => clearInterval(interval);
  }, [tasks, loadTasks]);

  // Poll selected task more frequently when running
  useEffect(() => {
    if (!selectedTask || selectedTask.status !== 'running') return;

    const interval = setInterval(async () => {
      try {
        const updated = await fetchTask(selectedTask.task_id);
        setSelectedTask(updated);

        // Also update in the list
        setTasks((prev) =>
          prev.map((t) => (t.task_id === updated.task_id ? updated : t))
        );
      } catch (err) {
        console.error('Failed to update task:', err);
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [selectedTask?.task_id, selectedTask?.status]);

  // Submit research with engine and optional payment info
  const handleSubmitResearch = async (handle: string, engine: Engine, mandateId?: string, budgetUsd?: number, fluxaJwt?: string, file?: File) => {
    setIsSubmitting(true);
    try {
      const task = await submitResearch({
        handle,
        engine,
        mandate_id: mandateId,
        budget_usd: budgetUsd,
        fluxa_jwt: fluxaJwt,
      }, file);
      setTasks((prev) => [task, ...prev]);
      setSelectedTask(task);
    } catch (err) {
      console.error('Failed to submit research:', err);
    } finally {
      setIsSubmitting(false);
    }
  };

  // Handle task selection
  const handleSelectTask = (task: Task | null) => {
    selectedTaskRef.current = task;
    setSelectedTask(task);
  };

  // New research
  const handleNewResearch = () => {
    selectedTaskRef.current = null;
    setSelectedTask(null);
  };

  return (
    <main className="flex h-screen overflow-hidden">
      <Sidebar
        tasks={tasks}
        selectedTaskId={selectedTask?.task_id ?? null}
        onSelectTask={handleSelectTask}
        onNewResearch={handleNewResearch}
        isLoading={isLoadingTasks}
      />
      <MainPanel
        selectedTask={selectedTask}
        onSubmitResearch={handleSubmitResearch}
        isSubmitting={isSubmitting}
        onTaskUpdate={loadTasks}
      />
    </main>
  );
}
