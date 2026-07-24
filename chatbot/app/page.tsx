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
              data.result.note,
              `hits: ${data.result.hit_count}`,
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
        <h1>Stock chatbot</h1>
        <p className="lede">
          Interroge uniquement les modules déjà rangés dans le stock. Aucune
          ligne de code n’est inventée.
        </p>
        <form className="query" onSubmit={onSubmit}>
          <label htmlFor="q">Requête</label>
          <textarea
            id="q"
            name="q"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            required
            rows={3}
            placeholder="ex. hello, src/app.py, cas1"
          />
          <button type="submit" disabled={pending}>
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
                onClick={() => setQuery(item.module)}
              >
                {item.job_id}/{item.module}
              </button>
              <span>{item.files.join(", ")}</span>
            </li>
          ))}
        </ul>
      </section>
      <section className="result" aria-live="polite">
        <pre>{output === "" ? "Les résultats du stock apparaîtront ici." : output}</pre>
      </section>
    </main>
  );
}
