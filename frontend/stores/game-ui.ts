"use client";

import { create } from "zustand";

import type { GameQuestPreviewResponse } from "@/lib/types";

interface GameUiState {
  journalOpen: boolean;
  previewOpen: boolean;
  questPreview: GameQuestPreviewResponse | null;
  setJournalOpen: (open: boolean) => void;
  setPreviewOpen: (open: boolean) => void;
  setQuestPreview: (preview: GameQuestPreviewResponse | null) => void;
}

export const useGameUiStore = create<GameUiState>((set) => ({
  journalOpen: false,
  previewOpen: false,
  questPreview: null,
  setJournalOpen: (journalOpen) => set({ journalOpen }),
  setPreviewOpen: (previewOpen) => set({ previewOpen }),
  setQuestPreview: (questPreview) => set({ questPreview }),
}));
