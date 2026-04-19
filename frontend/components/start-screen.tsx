import Link from "next/link";

export function StartScreen() {
  return (
    <main className="relative flex min-h-screen items-center overflow-hidden px-6 py-12">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_20%_20%,rgba(235,185,97,0.18),transparent_26%),radial-gradient(circle_at_80%_10%,rgba(110,208,220,0.18),transparent_28%)]" />
      <div className="panel-shell relative mx-auto grid w-full max-w-6xl gap-10 rounded-[32px] px-8 py-10 lg:grid-cols-[1.15fr_0.85fr] lg:px-12 lg:py-14">
        <section className="space-y-8">
          <div className="space-y-3">
            <p className="section-kicker">Neuro-Symbolic Adventure</p>
            <h1 className="max-w-3xl font-[family:var(--font-display)] text-5xl leading-none text-white md:text-6xl">
              DAQS
              <span className="block text-[var(--accent)]">Oracle Engine</span>
            </h1>
            <p className="max-w-2xl text-lg leading-8 text-ui-muted">
              A tactical fantasy-tech interface for exploration, dialogue, and quest play.
              Every move is constrained by world logic, while the narrative still feels alive.
            </p>
          </div>

          <div className="flex flex-wrap gap-4">
            <Link
              href="/play"
              className="btn-primary rounded-full px-6 py-3 text-sm font-medium tracking-[0.12em]"
            >
              Start Journey
            </Link>
            <Link
              href="/debug/demo"
              className="btn-ghost rounded-full px-6 py-3 text-sm font-medium tracking-[0.12em]"
            >
              Debug Console
            </Link>
          </div>
        </section>

        <section className="grid gap-4">
          {[
            {
              title: "World Layer",
              copy: "Move across authored locations, inspect exits, gather items, and maintain objective clarity without debug clutter.",
            },
            {
              title: "Social Layer",
              copy: "Enter session-safe NPC conversations with persistent persona state and a dedicated dialogue shell.",
            },
            {
              title: "Quest Layer",
              copy: "Preview mission intent, accept a plan, and keep the active objective visible at all times.",
            },
          ].map((card) => (
            <article
              key={card.title}
              className="panel-etched rounded-[24px] px-5 py-5"
            >
              <p className="section-kicker mb-2">Layer</p>
              <h2 className="font-[family:var(--font-display)] text-2xl text-white">
                {card.title}
              </h2>
              <p className="mt-3 text-sm leading-7 text-ui-muted">{card.copy}</p>
            </article>
          ))}
        </section>
      </div>
    </main>
  );
}
