/* eslint-disable @next/next/no-img-element */
"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import {
  acceptQuest,
  assetUrl,
  exitSocial,
  generateWorldImage,
  getGameSession,
  initSocial,
  moveGameWorld,
  pickupGameItem,
  previewQuest,
  sendSocialMessage,
  teleportGameWorld,
} from "@/lib/api";
import type {
  ActiveSocialSession,
  GameQuestPreviewResponse,
  GameSessionSnapshotResponse,
  WorldNpc,
} from "@/lib/types";
import { useGameUiStore } from "@/stores/game-ui";

const STORAGE_KEY = "daqs:last-game-session";

function prettify(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function extractDialogue(content: unknown): string {
  if (!content) {
    return "";
  }
  if (typeof content === "string") {
    return content;
  }
  if (typeof content === "object" && content !== null) {
    const payload = content as Record<string, unknown>;
    if (typeof payload.dialogue === "string") {
      return payload.dialogue;
    }
    if (typeof payload.text === "string") {
      return payload.text;
    }
    if (typeof payload.reply === "string") {
      return payload.reply;
    }
  }
  return JSON.stringify(content);
}

function queryKey(gameSessionId: string) {
  return ["game-session", gameSessionId] as const;
}

function formatTimestamp(value?: string | null) {
  if (!value) {
    return "Unknown";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

export function GameShell({ gameSessionId }: { gameSessionId: string }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const recoveryTriggeredRef = useRef(false);
  const routeDoneTimerRef = useRef<number | null>(null);
  const [message, setMessage] = useState("");
  const [recentlyCompletedStep, setRecentlyCompletedStep] = useState<string | null>(null);
  const journalOpen = useGameUiStore((state) => state.journalOpen);
  const previewOpen = useGameUiStore((state) => state.previewOpen);
  const questPreview = useGameUiStore((state) => state.questPreview);
  const setJournalOpen = useGameUiStore((state) => state.setJournalOpen);
  const setPreviewOpen = useGameUiStore((state) => state.setPreviewOpen);
  const setQuestPreview = useGameUiStore((state) => state.setQuestPreview);

  const sessionQuery = useQuery({
    queryKey: queryKey(gameSessionId),
    queryFn: () => getGameSession(gameSessionId),
  });

  const syncSnapshot = (snapshot: GameSessionSnapshotResponse) => {
    const previous = queryClient.getQueryData<GameSessionSnapshotResponse>(queryKey(gameSessionId));
    const previousRoute = previous?.active_quest?.plan ?? [];
    const nextRoute = snapshot.active_quest?.plan ?? [];
    const linearProgressed =
      previousRoute.length > 0 &&
      nextRoute.length + 1 === previousRoute.length &&
      previousRoute.slice(1).every((step, index) => step === nextRoute[index]);

    if (linearProgressed) {
      const completed = previousRoute[0];
      setRecentlyCompletedStep(completed);
      if (routeDoneTimerRef.current !== null) {
        window.clearTimeout(routeDoneTimerRef.current);
      }
      routeDoneTimerRef.current = window.setTimeout(() => {
        setRecentlyCompletedStep((current) => (current === completed ? null : current));
      }, 1800);
    }

    queryClient.setQueryData(queryKey(gameSessionId), snapshot);
  };

  const moveMutation = useMutation({
    mutationFn: (targetLocationId: string) =>
      moveGameWorld(gameSessionId, targetLocationId),
    onSuccess: syncSnapshot,
  });

  const pickupMutation = useMutation({
    mutationFn: (itemId: string) => pickupGameItem(gameSessionId, itemId),
    onSuccess: syncSnapshot,
  });

  const teleportMutation = useMutation({
    mutationFn: ({
      portalId,
      targetLocationId,
    }: {
      portalId: string;
      targetLocationId?: string;
    }) => teleportGameWorld(gameSessionId, portalId, targetLocationId),
    onSuccess: syncSnapshot,
  });

  const talkMutation = useMutation({
    mutationFn: (npc: WorldNpc) =>
      initSocial(gameSessionId, npc.social_persona ?? "persona_cyber", !!npc.dialogue_quest),
    onSuccess: syncSnapshot,
  });

  const socialMutation = useMutation({
    mutationFn: ({
      socialSessionId,
      text,
    }: {
      socialSessionId: string;
      text: string;
    }) => sendSocialMessage(gameSessionId, socialSessionId, text),
    onSuccess: (snapshot) => {
      syncSnapshot(snapshot);
      setMessage("");
    },
  });

  const exitSocialMutation = useMutation({
    mutationFn: (socialSessionId?: string) => exitSocial(gameSessionId, socialSessionId),
    onSuccess: syncSnapshot,
  });

  const previewMutation = useMutation({
    mutationFn: ({
      questGoal,
      questName,
    }: {
      questGoal: string;
      questName: string;
    }) => previewQuest(gameSessionId, questGoal, questName),
    onSuccess: (preview: GameQuestPreviewResponse) => {
      queryClient.setQueryData<GameSessionSnapshotResponse | undefined>(
        queryKey(gameSessionId),
        (current) =>
          current
            ? {
                ...current,
                quest_journal: preview.quest_journal,
              }
            : current,
      );
      setQuestPreview(preview);
      setPreviewOpen(true);
    },
  });

  const acceptMutation = useMutation({
    mutationFn: ({
      questGoal,
      questName,
    }: {
      questGoal: string;
      questName: string;
    }) => acceptQuest(gameSessionId, questGoal, questName),
    onSuccess: (snapshot) => {
      syncSnapshot(snapshot);
      setPreviewOpen(false);
      setJournalOpen(true);
    },
  });

  const session = sessionQuery.data;
  const activeSocial = session?.active_social_session ?? null;
  const activeRoute = session?.active_quest?.plan ?? [];
  const currentLocationId = session?.world_snapshot.location.id ?? null;
  const imageQuery = useQuery({
    queryKey: ["world-image", currentLocationId],
    queryFn: () => generateWorldImage(currentLocationId || ""),
    enabled: Boolean(currentLocationId) && !activeSocial,
    staleTime: 0,
    refetchOnWindowFocus: false,
  });

  useEffect(() => {
    const error = sessionQuery.error as Error | null;
    if (!error || recoveryTriggeredRef.current) {
      return;
    }
    if (error.message !== "Game session not found") {
      return;
    }
    recoveryTriggeredRef.current = true;
    window.localStorage.removeItem(STORAGE_KEY);
    router.replace("/play");
  }, [sessionQuery.error, router]);

  useEffect(() => () => {
    if (routeDoneTimerRef.current !== null) {
      window.clearTimeout(routeDoneTimerRef.current);
    }
  }, []);

  if (sessionQuery.isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center px-6">
        <div className="panel-shell w-full max-w-xl rounded-[28px] px-8 py-10 text-center">
          <p className="section-kicker">Link Sync</p>
          <h1 className="mt-3 font-[family:var(--font-display)] text-4xl text-white">
            Recovering your run
          </h1>
        </div>
      </div>
    );
  }

  if (sessionQuery.error || !session) {
    return (
      <div className="flex min-h-screen items-center justify-center px-6">
        <div className="panel-shell w-full max-w-xl rounded-[28px] px-8 py-10">
          <p className="section-kicker">Session Fault</p>
          <h1 className="mt-3 font-[family:var(--font-display)] text-4xl text-white">
            Session is unavailable
          </h1>
          <p className="mt-4 text-ui-muted">
            {(sessionQuery.error as Error | undefined)?.message ??
              "The backend did not return a valid session snapshot."}
          </p>
        </div>
      </div>
    );
  }

  const actionBusy =
    moveMutation.isPending ||
    pickupMutation.isPending ||
    teleportMutation.isPending ||
    talkMutation.isPending ||
    socialMutation.isPending ||
    acceptMutation.isPending ||
    exitSocialMutation.isPending;
  const inventory = Object.entries(session.player_snapshot.inventory.items ?? {});
  const resolvedImagePath = assetUrl(
    imageQuery.data?.image_path ?? session.world_snapshot.image_path ?? null,
  );
  const renderImageSrc =
    resolvedImagePath && !activeSocial
      ? `${resolvedImagePath}${resolvedImagePath.includes("?") ? "&" : "?"}v=${imageQuery.dataUpdatedAt || 0}`
      : null;

  const submitSocial = (socialSessionId: string) => {
    const text = message.trim();
    if (!text) {
      return;
    }
    socialMutation.mutate({ socialSessionId, text });
  };

  return (
    <main className="min-h-screen px-4 py-4 md:px-6 lg:px-8">
      <div className="mx-auto grid max-w-[1600px] gap-4 xl:grid-cols-[320px_minmax(0,1fr)_360px]">
        <aside className="panel-shell rounded-[28px] p-5">
          <p className="section-kicker">Session</p>
          <h1 className="mt-3 font-[family:var(--font-display)] text-3xl text-white">
            {session.world_snapshot.location.name}
          </h1>
          <p className="mt-2 text-sm text-ui-muted">
            {session.world_snapshot.location.description || "No lore available for this zone yet."}
          </p>

          <div className="mt-6 rounded-[22px] border border-white/8 bg-white/3 p-4">
            <p className="section-kicker">Objective</p>
            <p className="mt-2 text-sm leading-7 text-white">
              {session.active_quest?.name ??
                (session.player_snapshot.goal ? prettify(session.player_snapshot.goal) : "No active quest accepted")}
            </p>
          </div>

          <div className="mt-6 rounded-[22px] border border-white/8 bg-white/3 p-4">
            <p className="section-kicker">Current Route</p>
            {recentlyCompletedStep ? (
              <motion.div
                animate={{ opacity: 1, y: 0 }}
                className="mt-3 rounded-[14px] border border-[var(--line-strong)] bg-[rgba(235,185,97,0.1)] px-3 py-2 text-xs text-white"
                initial={{ opacity: 0, y: -6 }}
              >
                <span className="mr-2 text-[var(--accent)]">Done</span>
                {recentlyCompletedStep}
              </motion.div>
            ) : null}
            {session.active_quest ? (
              activeRoute.length ? (
                <ol className="mt-3 space-y-2 text-xs leading-6 text-ui-muted">
                  {activeRoute.map((step, index) => (
                    <li
                      key={step + index}
                      className={
                        index === 0
                          ? "rounded-[12px] border border-[var(--line)] bg-[rgba(110,208,220,0.1)] px-2 py-1 text-white"
                          : ""
                      }
                    >
                      <span className="mr-2 font-[family:var(--font-mono)] text-[var(--accent)]">
                        {index + 1}.
                      </span>
                      {index === 0 ? <span className="mr-2 text-[var(--accent)]">Now</span> : null}
                      {step}
                    </li>
                  ))}
                </ol>
              ) : (
                <p className="mt-2 text-sm text-ui-muted">
                  Route unavailable. Planner could not build a valid path for the current world state.
                </p>
              )
            ) : (
              <p className="mt-2 text-sm text-ui-muted">
                Accept a quest to see a live tactical route.
              </p>
            )}
          </div>

          <div className="mt-6">
            <div className="flex items-center justify-between">
              <p className="section-kicker">Inventory</p>
              <button
                className="btn-ghost rounded-full px-4 py-2 text-xs font-medium"
                onClick={() => setJournalOpen(!journalOpen)}
                type="button"
              >
                {journalOpen ? "Hide Journal" : "Open Journal"}
              </button>
            </div>
            <div className="mt-3 space-y-2">
              {inventory.length ? (
                inventory.map(([itemId, count]) => (
                  <div
                    key={itemId}
                    className="panel-etched flex items-center justify-between rounded-[18px] px-4 py-3"
                  >
                    <span className="text-sm text-white">{prettify(itemId)}</span>
                    <span className="rounded-full border border-white/10 px-3 py-1 font-[family:var(--font-mono)] text-xs text-[var(--accent)]">
                      x{count}
                    </span>
                  </div>
                ))
              ) : (
                <p className="rounded-[18px] border border-dashed border-white/10 px-4 py-5 text-sm text-ui-muted">
                  Inventory is empty.
                </p>
              )}
            </div>
          </div>

          <div className="mt-6 rounded-[22px] border border-[var(--line)] bg-[var(--panel-soft)] p-4">
            <p className="section-kicker">Signal</p>
            <p className="mt-2 font-[family:var(--font-mono)] text-xs text-ui-muted">
              Session {gameSessionId.slice(0, 8)} • Mode {session.ui_context.mode}
            </p>
            <p className="mt-3 text-xs text-ui-muted">
              Journal entries {session.quest_journal.entries.length} • Events{" "}
              {session.quest_journal.history.length}
            </p>
          </div>
        </aside>

        <section className="panel-shell overflow-hidden rounded-[30px]">
          <div className="border-b border-white/8 px-6 py-5">
            <p className="section-kicker">
              {activeSocial ? "Social Channel" : "World Layer"}
            </p>
            <div className="mt-2 flex flex-wrap items-end justify-between gap-4">
              <div>
                <h2 className="font-[family:var(--font-display)] text-4xl text-white">
                  {activeSocial
                    ? prettify(activeSocial.persona_id)
                    : session.world_snapshot.location.name}
                </h2>
                <p className="mt-2 max-w-3xl text-sm text-ui-muted">
                  {activeSocial
                    ? "Dialogue remains session-bound and can be resumed across refreshes."
                    : session.world_snapshot.location.description}
                </p>
              </div>
              {activeSocial ? (
                <button
                  className="btn-ghost rounded-full px-5 py-3 text-sm font-medium"
                  onClick={() =>
                    exitSocialMutation.mutate(activeSocial.social_session_id)
                  }
                  type="button"
                >
                  Leave Dialogue
                </button>
              ) : null}
            </div>
          </div>

          <div className="grid gap-6 px-6 py-6">
            <motion.div
              animate={{ opacity: 1, y: 0 }}
              className="overflow-hidden rounded-[28px] border border-white/8 bg-[radial-gradient(circle_at_top,rgba(110,208,220,0.14),transparent_40%),linear-gradient(180deg,rgba(14,18,28,0.95),rgba(8,10,14,0.98))] p-6"
              initial={{ opacity: 0, y: 10 }}
              transition={{ duration: 0.32 }}
            >
              {!activeSocial ? (
                <div className="space-y-6">
                  <div className="max-w-3xl">
                    <p className="section-kicker">Exploration</p>
                    <h3 className="mt-3 font-[family:var(--font-display)] text-3xl text-white">
                      {session.world_snapshot.location.name}
                    </h3>
                    <p className="mt-4 max-w-2xl text-base leading-8 text-ui-muted">
                      {session.world_snapshot.location.description ||
                        "The world state is available, but this location has no authored description."}
                    </p>
                  </div>

                  <div className="overflow-hidden rounded-[22px] border border-white/8 bg-black/20">
                    {renderImageSrc ? (
                      <img
                        alt={session.world_snapshot.location.name}
                        className="h-[320px] w-full object-cover"
                        src={renderImageSrc}
                      />
                    ) : (
                      <div className="flex h-[320px] items-center justify-center text-sm text-ui-muted">
                        Visual is being prepared for this location.
                      </div>
                    )}
                    <div className="flex items-center justify-between border-t border-white/8 px-4 py-3 text-xs text-ui-muted">
                      <span>Location visual</span>
                      <span>
                        {imageQuery.isPending || imageQuery.isFetching ? "Generating..." : "Ready"}
                      </span>
                    </div>
                  </div>

                  <div className="grid gap-4 lg:grid-cols-3">
                      <div className="panel-etched rounded-[22px] p-4">
                        <p className="section-kicker">Exits</p>
                        <div className="mt-3 flex flex-wrap gap-3">
                          {session.world_snapshot.exits.length ? (
                            session.world_snapshot.exits.map((exit) => (
                              <button
                                key={exit.id}
                                className="btn-primary rounded-full px-4 py-2 text-sm font-medium"
                                disabled={actionBusy}
                                onClick={() => moveMutation.mutate(exit.id)}
                                type="button"
                              >
                                {exit.name}
                              </button>
                            ))
                          ) : (
                            <p className="text-sm text-ui-muted">No traversable exits.</p>
                          )}
                        </div>
                      </div>

                      <div className="panel-etched rounded-[22px] p-4">
                        <p className="section-kicker">Portals</p>
                        <div className="mt-3 space-y-3">
                          {session.world_snapshot.portals_nearby?.length ? (
                            session.world_snapshot.portals_nearby.map((portal) => (
                              <div
                                key={portal.id}
                                className="flex items-center justify-between rounded-[16px] border border-white/6 bg-black/15 px-3 py-3"
                              >
                                <div>
                                  <p className="text-sm text-white">{portal.name}</p>
                                  <p className="text-xs text-ui-muted">
                                    Destination: {portal.target_location_name}
                                  </p>
                                  {portal.requires_item ? (
                                    <p className="text-xs text-ui-muted">
                                      Key: {prettify(portal.requires_item)}
                                    </p>
                                  ) : null}
                                  {!portal.is_available && portal.blocked_reason ? (
                                    <p className="text-xs text-[var(--danger)]">
                                      {portal.blocked_reason}
                                    </p>
                                  ) : null}
                                </div>
                                <button
                                  className="btn-ghost rounded-full px-3 py-2 text-xs font-medium"
                                  disabled={actionBusy || !portal.is_available}
                                  onClick={() =>
                                    teleportMutation.mutate({
                                      portalId: portal.id,
                                      targetLocationId: portal.target_location_id,
                                    })
                                  }
                                  type="button"
                                >
                                  Teleport
                                </button>
                              </div>
                            ))
                          ) : (
                            <p className="text-sm text-ui-muted">No portals in this location.</p>
                          )}
                        </div>
                      </div>

                      <div className="panel-etched rounded-[22px] p-4">
                        <p className="section-kicker">Field Items</p>
                        <div className="mt-3 space-y-3">
                          {session.world_snapshot.items_nearby.length ? (
                            session.world_snapshot.items_nearby.map((item) => (
                              <div
                                key={item.id}
                                className="flex items-center justify-between rounded-[16px] border border-white/6 bg-black/15 px-3 py-3"
                              >
                                <div>
                                  <p className="text-sm text-white">{item.name}</p>
                                  <p className="text-xs text-ui-muted">
                                    {item.description || "Uncatalogued relic."}
                                  </p>
                                </div>
                                <button
                                  className="btn-ghost rounded-full px-3 py-2 text-xs font-medium"
                                  disabled={actionBusy}
                                  onClick={() => pickupMutation.mutate(item.id)}
                                  type="button"
                                >
                                  Pickup
                                </button>
                              </div>
                            ))
                          ) : (
                            <p className="text-sm text-ui-muted">Nothing to collect here.</p>
                          )}
                        </div>
                      </div>
                  </div>

                  <div className="panel-etched rounded-[22px] p-4">
                    <p className="section-kicker">Nearby NPCs</p>
                    <div className="mt-3 grid gap-3 md:grid-cols-2">
                      {session.world_snapshot.npcs_nearby.length ? (
                        session.world_snapshot.npcs_nearby.map((npc) => (
                          <button
                            key={npc.id}
                            className="rounded-[18px] border border-white/8 bg-white/3 px-4 py-4 text-left transition hover:border-[var(--line-strong)] hover:bg-white/6"
                            disabled={actionBusy}
                            onClick={() => talkMutation.mutate(npc)}
                            type="button"
                          >
                            <p className="font-[family:var(--font-display)] text-xl text-white">
                              {npc.name}
                            </p>
                            <p className="mt-2 text-sm text-ui-muted">
                              {npc.personality || npc.description || "No behavioral profile loaded."}
                            </p>
                            <p className="mt-3 section-kicker">
                              {npc.dialogue_quest ? "Quest-bearing signal" : "Dialogue available"}
                            </p>
                          </button>
                        ))
                      ) : (
                        <p className="text-sm text-ui-muted">No active NPC signatures at this location.</p>
                      )}
                    </div>
                  </div>
                </div>
              ) : (
                <SocialConsole
                  activeSocial={activeSocial}
                  busy={socialMutation.isPending}
                  message={message}
                  onMessageChange={setMessage}
                  onSubmit={submitSocial}
                />
              )}
            </motion.div>
          </div>
        </section>

        <aside className="panel-shell rounded-[28px] p-5">
          <p className="section-kicker">Quest Board</p>
          <h2 className="mt-3 font-[family:var(--font-display)] text-3xl text-white">
            Tactical Briefing
          </h2>
          <p className="mt-3 text-sm leading-7 text-ui-muted">
            Preview mission intent before accepting it into the active run.
          </p>

          <div className="mt-6 space-y-3">
            {session.world_snapshot.available_quests.length ? (
              session.world_snapshot.available_quests.map((quest) => (
                <button
                  key={quest.id}
                  className="panel-etched w-full rounded-[20px] px-4 py-4 text-left transition hover:border-[var(--line-strong)]"
                  disabled={previewMutation.isPending}
                  onClick={() =>
                    previewMutation.mutate({
                      questGoal: quest.goal,
                      questName: quest.name,
                    })
                  }
                  type="button"
                >
                  <p className="font-medium text-white">{quest.name}</p>
                  <p className="mt-2 text-xs text-ui-muted">{quest.goal}</p>
                </button>
              ))
            ) : (
              <p className="rounded-[18px] border border-dashed border-white/10 px-4 py-5 text-sm text-ui-muted">
                No questable artifacts are currently available.
              </p>
            )}
          </div>

          <AnimatePresence>
            {previewOpen && questPreview ? (
              <motion.div
                animate={{ opacity: 1, y: 0 }}
                className="mt-6 rounded-[22px] border border-[var(--line)] bg-black/20 p-4"
                exit={{ opacity: 0, y: 8 }}
                initial={{ opacity: 0, y: 8 }}
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="section-kicker">Preview</p>
                    <h3 className="mt-2 font-[family:var(--font-display)] text-2xl text-white">
                      {questPreview.payload?.mission?.toString?.() ? "Mission Offered" : "Quest Analysis"}
                    </h3>
                  </div>
                  <button
                    className="btn-ghost rounded-full px-3 py-2 text-xs"
                    onClick={() => setPreviewOpen(false)}
                    type="button"
                  >
                    Close
                  </button>
                </div>
                <p className="mt-4 text-sm text-ui-muted">
                  {questPreview.error ??
                    (extractDialogue(questPreview.payload) ||
                      "Planner returned a structured quest payload.")}
                </p>
                {questPreview.plan.length ? (
                  <ol className="mt-4 space-y-2 text-sm text-ui-muted">
                    {questPreview.plan.map((step, index) => (
                      <li key={step + index}>
                        <span className="mr-2 font-[family:var(--font-mono)] text-[var(--accent)]">
                          {index + 1}.
                        </span>
                        {step}
                      </li>
                    ))}
                  </ol>
                ) : null}
                {questPreview.status === "success" ? (
                  <button
                    className="btn-primary mt-5 rounded-full px-5 py-3 text-sm font-medium"
                    disabled={acceptMutation.isPending}
                    onClick={() =>
                      acceptMutation.mutate({
                        questGoal: questPreview.quest_goal,
                        questName: questPreview.quest_name,
                      })
                    }
                    type="button"
                  >
                    Accept Mission
                  </button>
                ) : null}
              </motion.div>
            ) : null}
          </AnimatePresence>

          <AnimatePresence>
            {journalOpen ? (
              <motion.div
                animate={{ opacity: 1, y: 0 }}
                className="mt-6 rounded-[22px] border border-[var(--line-strong)] bg-[rgba(235,185,97,0.08)] p-4"
                exit={{ opacity: 0, y: 8 }}
                initial={{ opacity: 0, y: 8 }}
              >
                <p className="section-kicker">Quest Journal</p>
                <div className="mt-4 space-y-4">
                  {session.quest_journal.entries.length ? (
                    session.quest_journal.entries.map((entry) => (
                      <div
                        key={entry.id}
                        className="rounded-[18px] border border-white/10 bg-black/15 p-4"
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <h3 className="font-[family:var(--font-display)] text-2xl text-white">
                              {entry.quest_name}
                            </h3>
                            <p className="mt-2 text-xs uppercase tracking-[0.16em] text-[var(--accent)]">
                              {entry.status}
                            </p>
                          </div>
                          <p className="text-right text-xs text-ui-muted">
                            Updated
                            <br />
                            {formatTimestamp(entry.updated_at)}
                          </p>
                        </div>
                        {entry.plan.length ? (
                          <ol className="mt-4 space-y-2 text-sm text-ui-muted">
                            {entry.plan.map((step, index) => (
                              <li key={step + index}>
                                <span className="mr-2 font-[family:var(--font-mono)] text-[var(--accent)]">
                                  {index + 1}.
                                </span>
                                {step}
                              </li>
                            ))}
                          </ol>
                        ) : (
                          <p className="mt-4 text-sm text-ui-muted">
                            No plan steps stored for this journal entry.
                          </p>
                        )}
                      </div>
                    ))
                  ) : (
                    <p className="rounded-[18px] border border-dashed border-white/10 px-4 py-5 text-sm text-ui-muted">
                      The quest journal is empty.
                    </p>
                  )}
                </div>
                <div className="mt-6">
                  <p className="section-kicker">History</p>
                  <div className="mt-3 max-h-64 space-y-3 overflow-y-auto pr-2">
                    {session.quest_journal.history.length ? (
                      session.quest_journal.history
                        .slice()
                        .reverse()
                        .map((event) => (
                          <div
                            key={event.id}
                            className="rounded-[16px] border border-white/8 bg-black/15 px-3 py-3"
                          >
                            <div className="flex items-center justify-between gap-3">
                              <p className="text-sm text-white">{event.summary}</p>
                              <span className="text-[10px] uppercase tracking-[0.16em] text-ui-muted">
                                {event.type}
                              </span>
                            </div>
                            <p className="mt-2 text-xs text-ui-muted">
                              {formatTimestamp(event.timestamp)}
                            </p>
                          </div>
                        ))
                    ) : (
                      <p className="text-sm text-ui-muted">
                        No quest-related events recorded yet.
                      </p>
                    )}
                  </div>
                </div>
              </motion.div>
            ) : null}
          </AnimatePresence>
        </aside>
      </div>
    </main>
  );
}

function SocialConsole({
  activeSocial,
  busy,
  message,
  onMessageChange,
  onSubmit,
}: {
  activeSocial: ActiveSocialSession;
  busy: boolean;
  message: string;
  onMessageChange: (value: string) => void;
  onSubmit: (socialSessionId: string) => void;
}) {
  return (
    <div className="grid gap-5">
      <div className="rounded-[24px] border border-white/8 bg-black/15 p-4">
        <p className="section-kicker">Persona</p>
        <h3 className="mt-2 font-[family:var(--font-display)] text-3xl text-white">
          {prettify(activeSocial.persona_id)}
        </h3>
      </div>

      <div className="max-h-[48vh] space-y-3 overflow-y-auto pr-2">
        {activeSocial.history.map((entry, index) => {
          const role = String(entry.role ?? "assistant");
          const bubble =
            role === "user"
              ? "ml-auto bg-[rgba(110,208,220,0.14)] border-[var(--line)]"
              : "mr-auto bg-[rgba(235,185,97,0.09)] border-[var(--line-strong)]";
          return (
            <div
              key={`${role}-${index}`}
              className={`max-w-[85%] rounded-[22px] border px-4 py-3 ${bubble}`}
            >
              <p className="section-kicker mb-2">{role}</p>
              <p className="text-sm leading-7 text-white">
                {extractDialogue(entry.content)}
              </p>
            </div>
          );
        })}
      </div>

      <div className="rounded-[22px] border border-white/8 bg-black/20 p-4">
        <label className="section-kicker" htmlFor="social-message">
          Signal
        </label>
        <textarea
          className="mt-3 min-h-28 w-full rounded-[18px] border border-white/10 bg-black/30 px-4 py-3 text-sm text-white outline-none placeholder:text-ui-muted"
          id="social-message"
          onChange={(event) => onMessageChange(event.target.value)}
          placeholder="Say something with intent."
          value={message}
        />
        <div className="mt-4 flex justify-end">
          <button
            className="btn-primary rounded-full px-5 py-3 text-sm font-medium"
            disabled={busy}
            onClick={() => onSubmit(activeSocial.social_session_id)}
            type="button"
          >
            Send Message
          </button>
        </div>
      </div>
    </div>
  );
}
