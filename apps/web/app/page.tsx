"use client";

import { useState, type FormEvent } from "react";
import type { CheckOutcome, SourcedAnswer, SupportStatus } from "@/lib/contracts";

const SUPPORT_LABEL: Record<SupportStatus, string> = {
  FONDEE: "Citation vérifiée",
  INCERTAINE: "Citation vérifiée avec réserves",
  BLOQUEE: "Bloquée",
};

const SUPPORT_STYLE: Record<SupportStatus, string> = {
  FONDEE: "bg-emerald-100 text-emerald-900 dark:bg-emerald-900 dark:text-emerald-100",
  INCERTAINE: "bg-amber-100 text-amber-900 dark:bg-amber-900 dark:text-amber-100",
  BLOQUEE: "bg-rose-100 text-rose-900 dark:bg-rose-900 dark:text-rose-100",
};

const OUTCOME_SYMBOL: Record<CheckOutcome, string> = {
  OK: "✓",
  ECHEC: "✗",
  INDETERMINE: "?",
  NON_EVALUE: "—",
};

export default function Home() {
  const [question, setQuestion] = useState("");
  const [asOf, setAsOf] = useState("");
  const [answer, setAnswer] = useState<SourcedAnswer | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    setAnswer(null);
    try {
      const response = await fetch("/api/answer", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, as_of: asOf }),
      });
      const payload = (await response.json()) as SourcedAnswer | { detail?: unknown };
      if (!response.ok) {
        const detail = "detail" in payload && typeof payload.detail === "string" ? payload.detail : "erreur";
        setError(detail);
      } else {
        setAnswer(payload as SourcedAnswer);
      }
    } catch {
      setError("service injoignable");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto max-w-3xl px-4 py-8">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold">Avocat Expert</h1>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          Prototype interne — recherche sourcée dans le corpus officiel ingéré. Ne constitue pas une consultation
          juridique.
        </p>
      </header>

      <form onSubmit={submit} className="space-y-3">
        <label className="block">
          <span className="text-sm font-medium">Question</span>
          <textarea
            className="mt-1 w-full rounded border border-slate-300 bg-transparent p-2 dark:border-slate-700"
            rows={3}
            maxLength={4000}
            required
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
          />
        </label>
        <label className="block">
          <span className="text-sm font-medium">Date d’appréciation du droit (facultative)</span>
          <input
            type="date"
            className="mt-1 block rounded border border-slate-300 bg-transparent p-2 dark:border-slate-700"
            value={asOf}
            onChange={(e) => setAsOf(e.target.value)}
          />
        </label>
        <button
          type="submit"
          disabled={loading}
          className="rounded bg-slate-900 px-4 py-2 text-white disabled:opacity-50 dark:bg-slate-100 dark:text-slate-900"
        >
          {loading ? "Recherche…" : "Rechercher"}
        </button>
      </form>

      {error && (
        <p role="alert" className="mt-6 rounded bg-rose-100 p-3 text-rose-900">
          {error}
        </p>
      )}

      {answer && (
        <section className="mt-8 space-y-4" aria-live="polite">
          <div className={`rounded p-3 ${SUPPORT_STYLE[answer.status]}`}>
            <p className="font-medium">{SUPPORT_LABEL[answer.status]}</p>
            <p className="text-sm">{answer.summary}</p>
          </div>

          {answer.statements.map((s) => (
            <article key={s.citation?.official_id ?? s.text} className="rounded border border-slate-200 p-4 dark:border-slate-800">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="font-medium">{s.text}</h2>
                <span className={`rounded px-2 py-0.5 text-xs ${SUPPORT_STYLE[s.support]}`}>{SUPPORT_LABEL[s.support]}</span>
              </div>
              {s.quote && (
                <blockquote className="mt-3 whitespace-pre-line border-l-4 border-slate-300 pl-3 text-sm dark:border-slate-700">
                  {s.quote}
                </blockquote>
              )}
              {s.verification && (
                <ul className="mt-3 grid gap-1 text-xs text-slate-600 dark:text-slate-400">
                  {s.verification.checks.map((c) => (
                    <li key={c.check}>
                      <span aria-label={c.outcome}>{OUTCOME_SYMBOL[c.outcome]}</span> {c.check} — {c.detail}
                    </li>
                  ))}
                </ul>
              )}
            </article>
          ))}

          {answer.uncertainties.length > 0 && (
            <div className="rounded border border-amber-300 p-3 text-sm">
              <p className="font-medium">Incertitudes signalées</p>
              <ul className="list-disc pl-5">
                {answer.uncertainties.map((u) => (
                  <li key={u}>{u}</li>
                ))}
              </ul>
            </div>
          )}
          <p className="text-xs text-slate-500">{answer.disclaimer}</p>
        </section>
      )}
    </main>
  );
}
