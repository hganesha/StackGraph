"use client";

import { useRef, useState } from "react";
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

const SUGGESTIONS = [
  "Which Tier-1 applications use unsupported runtimes?",
  "What are our largest modernization opportunities?",
  "Show all applications that depend on axios",
];

export default function AskPage() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const openEvidence = useEvidenceStore((s) => s.open);
  const nextId = useRef(1);
  const listEndRef = useRef<HTMLDivElement>(null);

  const ask = useMutation({
    mutationFn: (question: string) => stackGraphClient.ask({ question }),
    onSuccess: (response, question) => {
      setTurns((t) => t.map((turn) => (turn.question === question && !turn.response ? { ...turn, response } : turn)));
      requestAnimationFrame(() => listEndRef.current?.scrollIntoView({ behavior: "smooth" }));
    },
    onError: (_e, question) => {
      setTurns((t) => t.map((turn) => (turn.question === question && !turn.response ? { ...turn, error: true } : turn)));
    },
  });

  const submit = (question: string) => {
    const q = question.trim();
    if (!q) return;
    setTurns((t) => [...t, { id: nextId.current++, question: q }]);
    setInput("");
    ask.mutate(q);
  };

  return (
    <div className={styles.page}>
      <header className={styles.head}>
        <h1 className={styles.title}>Ask your estate</h1>
        <p className={styles.subtitle}>
          Answered from your facts, text-first, always cited — never generated from model memory.
        </p>
      </header>

      {turns.length === 0 ? (
        <div className={styles.empty}>
          <p className={styles.emptyLabel}>Try asking</p>
          <div className={styles.suggestions}>
            {SUGGESTIONS.map((s) => (
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
