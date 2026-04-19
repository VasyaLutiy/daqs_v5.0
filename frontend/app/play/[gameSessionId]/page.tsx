import { GameShell } from "@/components/game-shell";

export default async function PlaySessionPage({
  params,
}: {
  params: Promise<{ gameSessionId: string }>;
}) {
  const { gameSessionId } = await params;
  return <GameShell gameSessionId={gameSessionId} />;
}
