"use client";

import { useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { stackGraphClient, type AskResponse } from "@stackgraph/shared";
import { CitationChip } from "@stackgraph/design-system";
import { useEvidenceStore } from "@/lib/evidenceStore";
import styles from "./ask.module.css";

interface Turn {
  id: number;
  question: string;
  response?: AskResponse;
  error?: boolean;
}

interface BusinessMapContext {
  title: string;
  template: string;
  viewMode?: "value-chain" | "organization";
  stages: Array<{
    name: string;
    capabilities: Array<{ name: string; maturity: number }>;
  }>;
  organizationUnits?: Array<{
    name: string;
    functions: string[];
  }>;
}

interface AskRequest {
  id: number;
  requestQuestion: string;
}

const SUGGESTIONS = [
  "Which Tier-1 applications use unsupported runtimes?",
  "What are our largest modernization opportunities?",
  "Show all applications that depend on axios",
];

const MAP_SUGGESTIONS = [
  "Where are the largest gaps in this business map?",
  "Which mapped capabilities need the most maturity attention?",
  "What capabilities should we consider adding next?",
];

function serializeBusinessMap(context: BusinessMapContext): string {
  if (context.viewMode === "organization" && context.organizationUnits) {
    const units = context.organizationUnits.map((unit) =>
      `${unit.name}: ${unit.functions.length ? unit.functions.join(", ") : "no assigned functions"}`,
    );
    return `Organization map \"${context.title}\". ${units.join(" | ")}`;
  }
  const stages = context.stages.map((stage) => {
    const capabilities = stage.capabilities.length
      ? stage.capabilities.map((capability) => `${capability.name} (maturity ${capability.maturity}/5)`).join(", ")
      : "no mapped capabilities";
    return `${stage.name}: ${capabilities}`;
  });
  return `Business map \"${context.title}\" using the ${context.template} template. ${stages.join(" | ")}`;
}

export default function AskPage() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [businessMapContext, setBusinessMapContext] = useState<BusinessMapContext | null>(null);
  const openEvidence = useEvidenceStore((s) => s.open);
  const nextId = useRef(1);
  const listEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("source") !== "business-map") return;
    try {
      const raw = window.sessionStorage.getItem("stackgraph.ask.business-map-context");
      if (raw) setBusinessMapContext(JSON.parse(raw) as BusinessMapContext);
    } catch {
      // An unavailable map snapshot should fall back to the standard Ask experience.
    }
  }, []);

  const ask = useMutation({
    mutationFn: (request: AskRequest) => stackGraphClient.ask({ question: request.requestQuestion }),
    onSuccess: (response, request) => {
      setTurns((t) => t.map((turn) => (turn.id === request.id ? { ...turn, response } : turn)));
      requestAnimationFrame(() => listEndRef.current?.scrollIntoView({ behavior: "smooth" }));
    },
    onError: (_e, request) => {
      setTurns((t) => t.map((turn) => (turn.id === request.id ? { ...turn, error: true } : turn)));
    },
  });

  const submit = (question: string) => {
    const q = question.trim();
    if (!q) return;
    const id = nextId.current++;
    setTurns((t) => [...t, { id, question: q }]);
    setInput("");
    ask.mutate({
      id,
      requestQuestion: businessMapContext ? `${q}\n\nAttached business-map context:\n${serializeBusinessMap(businessMapContext)}` : q,
    });
  };

  const suggestions = businessMapContext ? MAP_SUGGESTIONS : SUGGESTIONS;

  return (
    <div className={styles.page}>
      <header className={styles.head}>
        <h1 className={styles.title}>Ask your estate</h1>
        <p className={styles.subtitle}>
          {businessMapContext ? "Ask across the current business map and the evidence already in your estate." : "Answered from your facts, text-first, always cited — never generated from model memory."}
        </p>
        {businessMapContext ? (
          <div className={styles.contextBanner}>
            <span className="sg-mono">BIZ MAP</span>
            <strong>{businessMapContext.title}</strong>
            <small>
              {businessMapContext.viewMode === "organization" && businessMapContext.organizationUnits
                ? `${businessMapContext.organizationUnits.length} units · ${businessMapContext.organizationUnits.reduce((total, unit) => total + unit.functions.length, 0)} mapped functions`
                : `${businessMapContext.stages.length} stages · ${businessMapContext.stages.reduce((total, stage) => total + stage.capabilities.length, 0)} mapped capabilities`}
            </small>
            <button
              type="button"
              onClick={() => {
                window.sessionStorage.removeItem("stackgraph.ask.business-map-context");
                setBusinessMapContext(null);
              }}
            >
              Detach
            </button>
          </div>
        ) : null}
      </header>

      {turns.length === 0 ? (
        <div className={styles.empty}>
          <p className={styles.emptyLabel}>Try asking</p>
          <div className={styles.suggestions}>
            {suggestions.map((s) => (
              <button key={s} type="button" className={styles.suggestion} onClick={() => submit(s)}>
                {s}
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div className={styles.thread}>
          {turns.map((turn) => (
            <div key={turn.id} className={styles.turn}>
              <div className={styles.question}>
                <span className={styles.qMark} aria-hidden="true">
                  ?
                </span>
                <span>{turn.question}</span>
              </div>
              <div className={styles.answer}>
                {turn.error ? (
                  <p className={styles.errorText}>Couldn’t reach the estate. Try again.</p>
                ) : turn.response ? (
                  <AnswerView response={turn.response} onCite={openEvidence} />
                ) : (
                  <p className={styles.thinking}>
                    <span className={styles.dot} />
                    <span className={styles.dot} />
                    <span className={styles.dot} />
                  </p>
                )}
              </div>
            </div>
          ))}
          <div ref={listEndRef} />
        </div>
      )}

      <form
        className={styles.composer}
        onSubmit={(e) => {
          e.preventDefault();
          submit(input);
        }}
      >
        <input
          className={styles.composerInput}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask your estate…"
          aria-label="Ask your estate"
        />
        <button className={styles.send} type="submit" disabled={!input.trim() || ask.isPending}>
          Ask
        </button>
      </form>
    </div>
  );
}

function AnswerView({
  response,
  onCite,
}: {
  response: AskResponse;
  onCite: (factId: string, label?: string) => void;
}) {
  return (
    <div className={styles.answerBody}>
      {response.result_kind === "UNSUPPORTED" ? (
        <p className={styles.unsupported}>{response.text}</p>
      ) : (
        <p className={styles.answerText}>{response.text}</p>
      )}

      {response.result_kind === "TABLE" && response.rows && response.rows.length > 0 ? (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                {Object.keys(response.rows[0]).map((k) => (
                  <th key={k}>{k}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {response.rows.map((row, i) => (
                <tr key={i}>
                  {Object.values(row).map((v, j) => (
                    <td key={j} className="sg-mono">
                      {String(v)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {response.citations.length > 0 ? (
        <div className={styles.citations}>
          {response.citations.map((c) => (
            <CitationChip key={c.fact_id} label={c.label} onOpen={() => onCite(c.fact_id, c.label)} />
          ))}
        </div>
      ) : null}
    </div>
  );
}
