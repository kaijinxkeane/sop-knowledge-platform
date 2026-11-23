import { useQuery } from "@tanstack/react-query";
import { api, authFetch, unwrap, type Schemas } from "@/api/client";
import { ServerError, call } from "@/api/errors";

export type Conversation = Schemas["ConversationOut"];
export type StoredMessage = Schemas["MessageOut"];
export type Reason = NonNullable<Schemas["FeedbackIn"]["reason"]>;

/** One citation, as streamed and as stored in a message's sections. */
export type Citation = {
  n: number;
  document_id: string;
  title: string;
  vault_path?: string;
  heading?: string | null;
  part?: string | null;
  part_number?: number | null;
  version?: string | null;
  written_by?: string | null;
  approved_by?: string | null;
  approval?: string | null;
  approved_on?: string | null;
};

export type Section = {
  space: string | null;
  text: string;
  citations: Citation[];
  no_answer?: boolean;
  unavailable?: boolean;
  hidden?: boolean;
  contact?: string | null;
  confidence?: string | null;
};

export const useConversations = () =>
  useQuery({
    queryKey: ["conversations"],
    queryFn: () => unwrap(api.GET("/api/v1/conversations", { params: { query: { limit: 100 } } })),
  });

export const useMessages = (id: string | null) =>
  useQuery({
    queryKey: ["conversation", id, "messages"],
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/conversations/{conversation_id}/messages", {
          params: { path: { conversation_id: id! } },
        }),
      ),
    enabled: !!id,
    staleTime: Infinity, // replaced from the stream as answers arrive
  });

/** Department names for section headings. */
export const useSpaces = () =>
  useQuery({ queryKey: ["spaces"], queryFn: () => unwrap(api.GET("/api/v1/spaces")), staleTime: Infinity });

export const createConversation = () => call(api.POST("/api/v1/conversations", { body: { title: "" } }));

export const sendFeedback = (id: string, helpful: boolean, reason?: Reason, comment = "") =>
  call(
    api.POST("/api/v1/messages/{message_id}/feedback", {
      params: { path: { message_id: id } },
      body: { helpful, reason: reason ?? null, comment },
    }),
  );

export const requestSop = (key: string, space: string) =>
  call(api.POST("/api/v1/me/gaps/request", { body: { key, space } }));

export const myGaps = () => unwrap(api.GET("/api/v1/me/gaps"));

export type StreamEvent =
  | { event: "routing"; data: { spaces: string[]; reason: string } }
  | { event: "agent_dispatched"; data: { space: string; title: string } }
  | { event: "token"; data: { space: string; text: string } }
  | { event: "citation"; data: Citation & { space: string } }
  | {
      event: "section_done";
      data: { space: string; no_answer: boolean; unavailable: boolean; confidence?: string | null; contact?: string | null };
    }
  | { event: "done"; data: { message_id: string; question_id: string; answered: boolean } };

/** Split an SSE byte stream into events. */
export function parseSse(buffer: string): { events: StreamEvent[]; rest: string } {
  const events: StreamEvent[] = [];
  const blocks = buffer.split("\n\n");
  const rest = blocks.pop() ?? "";
  for (const block of blocks) {
    let event = "message";
    const data: string[] = [];
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
    }
    if (!data.length) continue;
    try {
      events.push({ event, data: JSON.parse(data.join("\n")) } as StreamEvent);
    } catch {
      // a malformed event is skipped, never shown
    }
  }
  return { events, rest };
}

/** Ask, and hand each event to `onEvent` as it arrives. Aborting `signal` stops it. */
export async function streamAnswer(
  conversationId: string,
  question: string,
  onEvent: (e: StreamEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  const res = await authFetch(
    new Request(`${window.location.origin}/api/v1/conversations/${encodeURIComponent(conversationId)}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify({ content: question }),
      credentials: "same-origin",
      signal,
    }),
  );
  if (!res.ok || !res.body) {
    const detail = await res
      .json()
      .then((b: { detail?: unknown }) => b.detail)
      .catch(() => null);
    throw new ServerError(res.status, typeof detail === "string" && detail.length <= 200 ? detail : null);
  }
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    const parsed = parseSse(buffer + value);
    buffer = parsed.rest;
    parsed.events.forEach(onEvent);
  }
  parseSse(buffer + "\n\n").events.forEach(onEvent);
}
