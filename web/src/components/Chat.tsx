import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { useRun } from "./ui";

type Msg = { role: "user" | "assistant"; text: string };

/** Chat with Claude. With a job folder, it edits that application and the PDFs re-render. */
export default function Chat({ job, title, hints, onEdited, full }: {
  job?: string; title?: string; hints?: string[]; onEdited?: () => void; full?: boolean;
}) {
  const storageKey = `chat:${job ?? "general"}`;
  const [chatId, setChatId] = useState(() => localStorage.getItem(storageKey) ?? "");
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [runId, setRunId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const box = useRef<HTMLDivElement>(null);

  const load = async (id: string) => {
    if (!id) { setMessages([]); return; }
    const c = await api.get<{ messages: Msg[] }>(`/api/chat/${id}`);
    setMessages(c.messages ?? []);
  };
  useEffect(() => { load(chatId); }, [chatId]); // eslint-disable-line

  const { run, lines } = useRun(runId, async () => {
    setRunId(null);
    await load(chatId);
    onEdited?.();
  });
  useEffect(() => { box.current?.scrollTo({ top: box.current.scrollHeight, behavior: "smooth" }); }, [messages.length, lines.length]);

  const send = async (text?: string) => {
    const message = (text ?? input).trim();
    if (!message || runId) return;
    setError("");
    setInput("");
    setMessages((m) => [...m, { role: "user", text: message }]);
    try {
      const r = await api.post<{ run: string; chat_id: string }>("/api/chat", { message, chat_id: chatId, job: job ?? "" });
      if (r.chat_id !== chatId) { setChatId(r.chat_id); localStorage.setItem(storageKey, r.chat_id); }
      setRunId(r.run);
    } catch (e) { setError((e as Error).message); }
  };
  const reset = () => { localStorage.removeItem(storageKey); setChatId(""); setMessages([]); };
  const activity = lines.filter((l) => l.kind === "tool" || l.kind === "warn").slice(-3);

  return (
    <div className={`chat ${full ? "chat-full" : ""}`}>
      <div className="chat-head">
        <h3>{title ?? "Chat with Claude"}</h3>
        <button className="linkbtn small" onClick={reset}>New chat</button>
      </div>
      <div className="chat-msgs" ref={box}>
        {!messages.length && (
          <div className="muted small">
            {job ? "Ask for any change to this application. Claude edits it and the PDFs update." :
              "Ask Claude to change your profile or facts, adjust your writing style, or explain anything about your applications."}
          </div>)}
        {messages.map((m, i) => <div key={i} className={`msg msg-${m.role}`}>{m.text}</div>)}
        {runId && (
          <div className="msg msg-assistant muted small">
            <span className="spinner" />{run?.status === "running" ? "Claude is working..." : "Starting..."}
            {activity.map((l, i) => <div key={i} className="mono" style={{ fontSize: 11 }}>{l.text}</div>)}
          </div>)}
        {error && <div className="notice notice-error">{error}</div>}
      </div>
      {!messages.length && hints && (
        <div className="chat-hints">{hints.map((h) => <button key={h} onClick={() => send(h)}>{h}</button>)}</div>)}
      <div className="chat-input">
        <textarea rows={2} value={input} placeholder="Type a change..." onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }} />
        <button className="btn" disabled={!input.trim() || !!runId} onClick={() => send()}>Send</button>
      </div>
    </div>
  );
}
