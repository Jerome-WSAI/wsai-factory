"use client";

import { FormEvent, useEffect, useState, useTransition } from "react";

import { chatTurnAction, loadModulesAction } from "@/app/actions";

type ModuleSummary = {
  job_id: string;
  module: string;
  files: string[];
};

type ChatMessage =
  | { id: string; role: "user"; text: string }
  | {
      id: string;
      role: "brain";
      text: string;
      status: string;
      downloadHref: string;
    }
  | { id: string; role: "error"; text: string };

function catalogLabel(item: ModuleSummary): string {
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

function newId(): string {
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export default function HomePage() {
  const [query, setQuery] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
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
    const demand = query.trim();
    if (demand === "") {
      return;
    }
    const userMsg: ChatMessage = { id: newId(), role: "user", text: demand };
    const history = messages
      .filter(
        (msg): msg is Extract<ChatMessage, { role: "user" | "brain" }> =>
          msg.role === "user" || msg.role === "brain",
      )
      .map((msg) =>
        msg.role === "user"
          ? { role: "user" as const, content: msg.text }
          : { role: "assistant" as const, content: msg.text },
      );
    setMessages((prev) => [...prev, userMsg]);
    setQuery("");
    startTransition(async () => {
      const data = await chatTurnAction({ message: demand, history });
      if (!data.ok) {
        setMessages((prev) => [
          ...prev,
          {
            id: newId(),
            role: "error",
            text: `${data.error.code}: ${data.error.message}`,
          },
        ]);
        return;
      }
      let text = data.result.reply;
      if (data.result.status === "need_info" && data.result.question !== "") {
        text = `${data.result.reply}\n\nQuestion: ${data.result.question}`;
      }
      let downloadHref = "";
      if (data.result.order.queued) {
        downloadHref = data.result.order.download_url;
        text = `${data.result.reply}\n\nOutil prêt: ${data.result.order.zip_name} (${data.result.order.module_count} module(s)).`;
      }
      setMessages((prev) => [
        ...prev,
        {
          id: newId(),
          role: "brain",
          text,
          status: data.result.status,
          downloadHref,
        },
      ]);
    });
  }

  return (
    <main className="shell">
      <section className="hero">
        <p className="brand">WSAI Factory</p>
        <h1>Commande d’outil</h1>
        <p className="lede">
          Discute ton besoin. Le backend Render assemble modules + frontend et
          te livre un ZIP prêt à tester.
        </p>
      </section>

      <section
        className="chat"
        aria-label="Conversation commande"
        data-testid="software-demand-result"
      >
        {messages.length === 0 ? (
          <p className="lede">Décris l’outil voulu.</p>
        ) : null}
        {messages.map((msg) => {
          if (msg.role === "user") {
            return (
              <article key={msg.id} className="bubble user" data-role="user">
                <p className="bubble-label">Toi</p>
                <p>{msg.text}</p>
              </article>
            );
          }
          if (msg.role === "error") {
            return (
              <article key={msg.id} className="bubble error" data-role="error">
                <p className="bubble-label">Erreur</p>
                <p className="error">{msg.text}</p>
              </article>
            );
          }
          return (
            <article key={msg.id} className="bubble stock" data-role="brain">
              <p className="bubble-label">Factory ({msg.status})</p>
              <p style={{ whiteSpace: "pre-wrap" }}>{msg.text}</p>
              {msg.downloadHref !== "" ? (
                <p>
                  <a
                    href={msg.downloadHref}
                    data-testid="assembled-zip-download"
                  >
                    Télécharger le ZIP
                  </a>
                </p>
              ) : null}
            </article>
          );
        })}
      </section>

      <form
        className="query chat-compose"
        onSubmit={onSubmit}
        data-testid="software-demand-form"
      >
        <label htmlFor="q">Message / demande</label>
        <textarea
          id="q"
          name="q"
          data-testid="software-demand-input"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          required
          rows={3}
          placeholder='ex. "Je veux un outil basé sur linkedin"'
        />
        <button
          type="submit"
          disabled={pending}
          data-testid="software-demand-submit"
        >
          {pending ? "Envoi…" : "Envoyer"}
        </button>
      </form>

      <section className="catalog" aria-label="Modules en stock">
        <h2>Modules disponibles</h2>
        <p className="lede">{modulesNote}</p>
        <ul>
          {modules.map((item) => (
            <li key={`${item.job_id}/${item.module}`}>
              <button
                type="button"
                className="ghost"
                onClick={() =>
                  setQuery(
                    `Je veux un outil prêt basé sur ${catalogLabel(item)} (${item.job_id}/${item.module})`,
                  )
                }
              >
                {item.job_id}/{item.module}
              </button>
              <span>{item.files.join(", ")}</span>
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
