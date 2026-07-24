"use client";

import { FormEvent, useEffect, useState, useTransition } from "react";

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

type OkResponse = {
  ok: true;
  result: {
    hit_count: number;
    note: string;
    hits: Hit[];
  };
};

type ErrResponse = {
  ok: false;
  error: { code: string; message: string };
};

export default function HomePage() {
  const [query, setQuery] = useState("");
  const [output, setOutput] = useState("");
  const [modules, setModules] = useState<ModuleSummary[]>([]);
  const [modulesNote, setModulesNote] = useState("");
  const [pending, startTransition] = useTransition();

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const response = await fetch("/api/modules");
      const data = (await response.json()) as {
        ok: boolean;
        result?: { modules: ModuleSummary[]; note: string };
        error?: { message: string };
      };
      if (cancelled) {
        return;
      }
      if (data.ok && data.result !== undefined) {
        setModules(data.result.modules);
        setModulesNote(data.result.note);
        return;
      }
      setModulesNote(data.error?.message ?? "stock listing failed");
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  function onSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    startTransition(async () => {
      const response = await fetch("/api/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query }),
      });
      const text = await response.text();
      try {
        const data = JSON.parse(text) as OkResponse | ErrResponse;
        if (data.ok) {
          const blocks = data.result.hits.map((hit) => {
            return [
              `job: ${hit.job_id}`,
              `module: ${hit.module}`,
              `path: ${hit.relative_path}`,
              "---",
              hit.content,
            ].join("\n");
          });
          setOutput(
            [
              "Logiciel reçu depuis le stock (verbatim) :",
              data.result.note,
              `fichiers: ${data.result.hit_count}`,
              "",
              ...blocks,
            ].join("\n\n"),
          );
          return;
        }
        setOutput(`${data.error.code}: ${data.error.message}`);
      } catch {
        setOutput(text);
      }
    });
  }

  return (
    <main className="shell">
      <section className="hero">
        <p className="brand">WSAI Factory</p>
        <h1>Demande un logiciel</h1>
        <p className="lede">
          Écris ce que tu veux. Le frontend ne cherche que dans le stock déjà
          ingéré — tu reçois les fichiers tels quels, jamais du code inventé.
        </p>
        <form className="query" onSubmit={onSubmit} data-testid="software-demand-form">
          <label htmlFor="q">Ta demande</label>
          <textarea
            id="q"
            name="q"
            data-testid="software-demand-input"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            required
            rows={3}
            placeholder='ex. "scheduling software" ou "convert human duration labels"'
          />
          <button type="submit" disabled={pending} data-testid="software-demand-submit">
            {pending ? "Recherche…" : "Recevoir le logiciel"}
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
                onClick={() => setQuery(item.module)}
              >
                {item.job_id}/{item.module}
              </button>
              <span>{item.files.join(", ")}</span>
            </li>
          ))}
        </ul>
      </section>
      <section className="result" aria-live="polite" data-testid="software-demand-result">
        <pre>
          {output === ""
            ? "Le logiciel demandé apparaîtra ici après envoi."
            : output}
        </pre>
      </section>
    </main>
  );
}
