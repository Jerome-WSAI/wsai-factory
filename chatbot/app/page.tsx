"use client";

import { FormEvent, useEffect, useState, useTransition } from "react";

import { loadModulesAction, queryStockAction } from "@/app/actions";

type Hit = {
  job_id: string;
  module: string;
  relative_path: string;
  content: string;
};

type ModuleSummary = {
  job_id: string;
  module: string;
  files: string[];
};

function catalogQuery(item: ModuleSummary): string {
  const fromJob = item.job_id
    .split("-")
    .filter((part) => part.length > 2 && !/^\d/.test(part) && part.length < 40);
  if (fromJob.length > 0) {
    const candidate = fromJob[0];
    if (candidate !== undefined) {
      return candidate;
    }
  }
  return item.job_id;
}

export default function HomePage() {
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<Hit[]>([]);
  const [resultNote, setResultNote] = useState("");
  const [errorText, setErrorText] = useState("");
  const [modules, setModules] = useState<ModuleSummary[]>([]);
  const [modulesNote, setModulesNote] = useState("");
  const [pending, startTransition] = useTransition();

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const data = await loadModulesAction();
      if (cancelled) {
        return;
      }
      if (data.ok) {
        setModules(data.result.modules);
        setModulesNote(data.result.note);
        return;
      }
      setModulesNote(`${data.error.code}: ${data.error.message}`);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  function onSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    startTransition(async () => {
      const data = await queryStockAction(query);
      if (data.ok) {
        setHits(data.result.hits);
        setResultNote(data.result.note);
        setErrorText("");
        return;
      }
      setHits([]);
      setResultNote("");
      setErrorText(`${data.error.code}: ${data.error.message}`);
    });
  }

  return (
    <main className="shell">
      <section className="hero">
        <p className="brand">WSAI Factory</p>
        <h1>Cherche dans le stock</h1>
        <p className="lede">
          Recherche substring dans les modules déjà ingérés. Tu reçois les
          fichiers stockés tels quels — aucun code n&apos;est généré.
        </p>
        <form className="query" onSubmit={onSubmit} data-testid="software-demand-form">
          <label htmlFor="q">Requête stock</label>
          <textarea
            id="q"
            name="q"
            data-testid="software-demand-input"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            required
            rows={3}
            placeholder='ex. "duration" ou "timer"'
          />
          <button type="submit" disabled={pending} data-testid="software-demand-submit">
            {pending ? "Recherche…" : "Chercher dans le stock"}
          </button>
        </form>
      </section>
      <section className="catalog" aria-label="Modules en stock">
        <h2>Modules en stock</h2>
        <p className="lede">{modulesNote}</p>
        <ul>
          {modules.map((item) => (
            <li key={`${item.job_id}/${item.module}`}>
              <button
                type="button"
                className="ghost"
                onClick={() => setQuery(catalogQuery(item))}
              >
                {item.job_id}/{item.module}
              </button>
              <span>{item.files.join(", ")}</span>
            </li>
          ))}
        </ul>
      </section>
      <section className="result" aria-live="polite" data-testid="software-demand-result">
        {errorText !== "" ? <p className="error">{errorText}</p> : null}
        {errorText === "" && hits.length === 0 ? (
          <p className="lede">
            Les fichiers stock correspondants apparaîtront ici après envoi.
          </p>
        ) : null}
        {hits.length > 0 ? (
          <div className="hits">
            <p className="lede">
              {resultNote} · {hits.length} fichier(s)
            </p>
            {hits.map((hit) => (
              <article
                key={`${hit.job_id}/${hit.relative_path}`}
                className="hit"
              >
                <header>
                  <p className="hit-meta">
                    <span>{hit.job_id}</span>
                    <span>{hit.module}</span>
                    <span>{hit.relative_path}</span>
                  </p>
                </header>
                <pre>{hit.content}</pre>
              </article>
            ))}
          </div>
        ) : null}
      </section>
    </main>
  );
}
