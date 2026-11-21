import { API_BASE } from "./api";
import type { Citation } from "./types";

interface MetaEvent {
  conversation_id: string;
  user_message_id: string;
}

interface DoneEvent {
  assistant_message_id: string;
}

interface UsedCitationsEvent {
  items: Citation[];
  fallback: boolean;
  invalid_refs: number;
  degraded?: boolean;
}

interface ErrorEvent {
  code: string;
  message: string;
}

interface Callbacks {
  onMeta?: (data: MetaEvent) => void;
  onCitations?: (items: Citation[]) => void;
  onUsedCitations?: (data: UsedCitationsEvent) => void;
  onToken?: (delta: string) => void;
  onDone?: (data: DoneEvent) => void;
  onError?: (data: ErrorEvent) => void;
}

export async function streamChat(
  payload: { conversation_id?: string; message: string },
  callbacks: Callbacks,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(`${API_BASE}/chat/stream`, {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify(payload),
    signal,
  });

  if (!response.ok) {
    let message = `请求失败（${response.status}）`;
    try {
      const body = await response.json();
      if (body?.error?.message) {
        message = body.error.message;
      }
    } catch {
      // ignore invalid error body
    }
    callbacks.onError?.({ code: "HTTP_ERROR", message });
    return;
  }

  if (!response.body) {
    callbacks.onError?.({
      code: "STREAM_ERROR",
      message: "浏览器不支持流式响应",
    });
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) {
        break;
      }
      buffer += decoder.decode(value, { stream: true });
      let boundary = buffer.indexOf("\n\n");
      while (boundary >= 0) {
        const raw = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const lines = raw.split("\n");
        const eventLine = lines.find((line) => line.startsWith("event:"));
        const dataLine = lines.find((line) => line.startsWith("data:"));
        if (eventLine && dataLine) {
          const event = eventLine.slice(6).trim();
          try {
            const data = JSON.parse(dataLine.slice(5).trim());
            switch (event) {
              case "meta":
                callbacks.onMeta?.(data);
                break;
              case "citations":
                callbacks.onCitations?.(data.items ?? []);
                break;
              case "used_citations":
                callbacks.onUsedCitations?.({
                  items: data.items ?? [],
                  fallback: Boolean(data.fallback),
                  invalid_refs: Number(data.invalid_refs ?? 0),
                  degraded: Boolean(data.degraded),
                });
                break;
              case "token":
                callbacks.onToken?.(data.delta ?? "");
                break;
              case "done":
                callbacks.onDone?.(data);
                break;
              case "error":
                callbacks.onError?.(data);
                break;
            }
          } catch {
            // ignore malformed event
          }
        }
        boundary = buffer.indexOf("\n\n");
      }
    }
  } catch (err) {
    if ((err as Error).name !== "AbortError") {
      callbacks.onError?.({
        code: "STREAM_ERROR",
        message: "流式连接中断",
      });
    }
  } finally {
    reader.releaseLock();
  }
}
