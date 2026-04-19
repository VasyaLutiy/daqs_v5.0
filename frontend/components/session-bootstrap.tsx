"use client";

import { useMutation } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { createGameSession } from "@/lib/api";

const STORAGE_KEY = "daqs:last-game-session";

export function SessionBootstrap() {
  const router = useRouter();
  const createSession = useMutation({
    mutationFn: createGameSession,
    onSuccess: (data) => {
      window.localStorage.setItem(STORAGE_KEY, data.game_session_id);
      router.replace(`/play/${data.game_session_id}`);
    },
  });

  useEffect(() => {
    const cached = window.localStorage.getItem(STORAGE_KEY);
    if (cached) {
      router.replace(`/play/${cached}`);
      return;
    }
    createSession.mutate();
  }, [createSession, router]);

  return (
    <main className="flex min-h-screen items-center justify-center px-6">
      <div className="panel-shell w-full max-w-xl rounded-[28px] px-8 py-10 text-center">
        <p className="section-kicker">Session Forge</p>
        <h1 className="mt-3 font-[family:var(--font-display)] text-4xl text-white">
          Opening a fresh command channel
        </h1>
        <p className="mt-4 text-ui-muted">
          Provisioning your guest session and pulling the current world snapshot.
        </p>
        {createSession.error ? (
          <p className="mt-6 rounded-2xl border border-[var(--danger)]/40 bg-[rgba(255,123,123,0.08)] px-4 py-3 text-sm text-[var(--danger)]">
            {(createSession.error as Error).message}
          </p>
        ) : (
          <div className="mx-auto mt-8 h-2 w-48 overflow-hidden rounded-full bg-white/10">
            <div className="h-full w-1/2 animate-pulse rounded-full bg-[var(--accent)]" />
          </div>
        )}
      </div>
    </main>
  );
}
