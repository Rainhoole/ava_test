'use client';

import { useEffect, useState } from 'react';
import Sidebar from '@/components/Sidebar';
import MainPanel from '@/components/MainPanel';
import { useWorkspaceTasks } from '@/hooks/useWorkspaceTasks';

export default function Workspace() {
  const [preferredTaskId, setPreferredTaskId] = useState<string | null>(null);

  useEffect(() => {
    const syncPreferredTask = () => {
      const params = new URLSearchParams(window.location.search);
      setPreferredTaskId(params.get('task'));
    };

    syncPreferredTask();
    window.addEventListener('popstate', syncPreferredTask);
    return () => window.removeEventListener('popstate', syncPreferredTask);
  }, []);

  const {
    tasks,
    selectedTask,
    isLoadingTasks,
    isSubmitting,
    refreshTasks,
    submitTask,
    selectTask,
    startNewResearch,
  } = useWorkspaceTasks(preferredTaskId);

  return (
    <main className="workspace-shell flex h-dvh overflow-hidden">
      <Sidebar
        tasks={tasks}
        selectedTaskId={selectedTask?.task_id ?? null}
        onSelectTask={selectTask}
        onNewResearch={startNewResearch}
        isLoading={isLoadingTasks}
      />
      <MainPanel
        selectedTask={selectedTask}
        onSubmitResearch={submitTask}
        isSubmitting={isSubmitting}
        onTaskUpdate={refreshTasks}
      />
    </main>
  );
}
