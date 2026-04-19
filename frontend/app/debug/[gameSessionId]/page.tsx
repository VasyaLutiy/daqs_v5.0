"use client";

import { useQuery } from "@tanstack/react-query";

import { getGameSession } from "@/lib/api";

export default function DebugSessionPage({
  params,
}: {
  params: { gameSessionId: string };
}) {
  const sessionQuery = useQuery({
    queryKey: ["debug-session", params.gameSessionId],
    queryFn: () => getGameSession(params.gameSessionId),
  });

  return (
    <main className="min-h-screen px-6 py-10">
      <div className="panel-shell mx-auto max-w-6xl rounded-[28px] p-6">
        <p className="section-kicker">Debug Session</p>
        <h1 className="mt-3 font-[family:var(--font-display)] text-4xl text-white">
          {params.gameSessionId}
        </h1>
        <pre className="mt-6 overflow-x-auto rounded-[22px] border border-white/8 bg-black/30 p-4 text-xs text-ui-muted">
          {JSON.stringify(sessionQuery.data ?? null, null, 2)}
        </pre>
      </div>
    </main>
  );
}
