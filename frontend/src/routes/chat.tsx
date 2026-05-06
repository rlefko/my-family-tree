import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";

import { apiFetch } from "@/api/client";

export const Route = createFileRoute("/chat")({
  component: ChatPage,
});

type ChatResponse = {
  text: string;
  model: string;
  provider: string;
};

function ChatPage() {
  const [prompt, setPrompt] = useState("");
  const [reply, setReply] = useState<string>("");
  const [busy, setBusy] = useState(false);

  async function send() {
    if (!prompt.trim()) return;
    setBusy(true);
    setReply("");
    try {
      const res = await apiFetch<ChatResponse>("/api/v1/chat", {
        method: "POST",
        body: JSON.stringify({
          tree_id: "00000000-0000-0000-0000-000000000000",
          message: prompt,
        }),
      });
      setReply(res.text);
    } catch (e) {
      setReply(`Error: ${String((e as { message?: string }).message ?? e)}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="p-6">
      <h1 className="text-2xl font-semibold">Chat</h1>
      <p className="mt-1 text-sm text-zinc-500">
        Ask the assistant about your tree. v1 is non-streaming; streaming + tool-call rendering
        lands in the next iteration.
      </p>
      <div className="mt-4 flex gap-2">
        <input
          className="flex-1 rounded border border-zinc-300 px-3 py-2"
          placeholder="Who are the parents of Jane Doe?"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
        />
        <button
          className="rounded bg-indigo-600 px-4 py-2 text-white disabled:opacity-50"
          onClick={send}
          disabled={busy}
        >
          {busy ? "..." : "Send"}
        </button>
      </div>
      <pre className="mt-4 whitespace-pre-wrap rounded bg-zinc-100 p-3 text-sm">{reply}</pre>
    </section>
  );
}
