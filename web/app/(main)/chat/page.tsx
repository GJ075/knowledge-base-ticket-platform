"use client";

import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import {
  Suspense,
  useEffect,
  useRef,
  useState,
} from "react";

import { CitationList } from "@/components/citation-list";
import {
  Button,
  ButtonSecondary,
  EmptyState,
  Spinner,
  Textarea,
} from "@/components/ui";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { streamChat } from "@/lib/sse";
import type {
  ChatMessage,
  ConversationDetail,
  ConversationSummary,
  Paginated,
} from "@/lib/types";
import { cn, formatDate } from "@/lib/utils";

export default function ChatPage() {
  return (
    <Suspense fallback={<Spinner label="加载问答" />}>
      <ChatPageInner />
    </Suspense>
  );
}

function ChatPageInner() {
  const { user } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const conversationId = searchParams.get("conversation_id");

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState("");
  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  const conversationsQuery = useQuery({
    queryKey: ["conversations"],
    queryFn: () =>
      apiFetch<Paginated<ConversationSummary>>("/conversations"),
    enabled: Boolean(user),
  });

  const conversationQuery = useQuery({
    queryKey: ["conversation", conversationId],
    queryFn: () =>
      apiFetch<ConversationDetail>(`/conversations/${conversationId}`),
    enabled: Boolean(user && conversationId && !streaming),
  });

  useEffect(() => {
    if (conversationQuery.data && !streaming) {
      setMessages(conversationQuery.data.messages);
    }
  }, [conversationQuery.data, streaming]);

  useEffect(() => {
    if (!conversationId) {
      setMessages([]);
    }
  }, [conversationId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const deleteMutation = useMutation({
    mutationFn: (id: string) =>
      apiFetch<void>(`/conversations/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["conversations"],
      });
      if (conversationId) {
        newChat();
      }
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : "删除会话失败"),
  });

  function newChat() {
    setMessages([]);
    setInput("");
    setError("");
    router.replace("/chat");
  }

  function openConversation(id: string) {
    setError("");
    setMessages([]);
    router.push(`/chat?conversation_id=${id}`);
  }

  async function send() {
    const text = input.trim();
    if (!text || streaming) {
      return;
    }
    setError("");
    setInput("");
    const userMessage: ChatMessage = {
      id: `temp-user-${Date.now()}`,
      role: "user",
      content: text,
      citations: null,
      created_at: new Date().toISOString(),
    };
    const assistantMessage: ChatMessage = {
      id: `temp-assistant-${Date.now()}`,
      role: "assistant",
      content: "",
      citations: null,
      created_at: new Date().toISOString(),
    };
    setMessages((previous) => [
      ...previous,
      userMessage,
      assistantMessage,
    ]);
    setStreaming(true);
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      await streamChat(
        {
          conversation_id: conversationId ?? undefined,
          message: text,
        },
        {
          onMeta: (data) => {
            if (!conversationId) {
              router.replace(
                `/chat?conversation_id=${data.conversation_id}`,
              );
            }
            void queryClient.invalidateQueries({
              queryKey: ["conversations"],
            });
          },
          onCitations: (citations) => {
            setMessages((previous) => {
              const next = [...previous];
              const last = next[next.length - 1];
              if (last && last.role === "assistant") {
                next[next.length - 1] = { ...last, citations };
              }
              return next;
            });
          },
          onToken: (delta) => {
            setMessages((previous) => {
              const next = [...previous];
              const last = next[next.length - 1];
              if (last && last.role === "assistant") {
                next[next.length - 1] = {
                  ...last,
                  content: last.content + delta,
                };
              }
              return next;
            });
          },
          onDone: () => {
            void queryClient.invalidateQueries({
              queryKey: ["conversations"],
            });
          },
          onError: (data) => {
            setError(data.message);
            setMessages((previous) => {
              const last = previous[previous.length - 1];
              if (
                last &&
                last.role === "assistant" &&
                !last.content
              ) {
                return previous.slice(0, -1);
              }
              return previous;
            });
          },
        },
        controller.signal,
      );
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        setError(
          err instanceof Error ? err.message : "发送失败，请重试",
        );
      }
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  }

  function stop() {
    abortRef.current?.abort();
    setStreaming(false);
  }

  const conversations = conversationsQuery.data?.items ?? [];

  return (
    <div className="flex h-[calc(100vh-3rem)] gap-4">
      <aside className="flex w-64 shrink-0 flex-col rounded-lg border border-slate-200 bg-white">
        <div className="border-b border-slate-200 p-3">
          <Button className="w-full" onClick={newChat}>
            新对话
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto p-2">
          {conversationsQuery.isLoading ? (
            <p className="p-2 text-xs text-slate-500">加载会话...</p>
          ) : null}
          {!conversationsQuery.isLoading &&
          conversations.length === 0 ? (
            <p className="p-2 text-xs text-slate-500">还没有会话</p>
          ) : null}
          {conversations.map((conversation) => (
            <div
              key={conversation.id}
              className={cn(
                "group flex items-start gap-1 rounded-md p-2",
                conversation.id === conversationId
                  ? "bg-slate-100"
                  : "hover:bg-slate-50",
              )}
            >
              <button
                className="min-w-0 flex-1 text-left"
                onClick={() => openConversation(conversation.id)}
              >
                <div className="truncate text-sm text-slate-800">
                  {conversation.title}
                </div>
                <div className="mt-1 text-xs text-slate-400">
                  {formatDate(conversation.updated_at)}
                </div>
              </button>
              <button
                className="invisible shrink-0 px-1 text-slate-400 hover:text-red-600 group-hover:visible"
                aria-label="删除会话"
                onClick={() => {
                  if (window.confirm("确定删除这个会话吗？")) {
                    deleteMutation.mutate(conversation.id);
                  }
                }}
              >
                ×
              </button>
            </div>
          ))}
        </div>
      </aside>

      <section className="flex min-w-0 flex-1 flex-col rounded-lg border border-slate-200 bg-white">
        <div className="border-b border-slate-200 px-4 py-3">
          <h1 className="text-sm font-semibold text-slate-900">
            知识库问答
          </h1>
          <p className="mt-1 text-xs text-slate-500">
            回答基于企业文档，并附带引用；历史仅本人可见。
          </p>
        </div>

        <div className="flex-1 space-y-4 overflow-y-auto p-4">
          {messages.length === 0 ? (
            <EmptyState
              title="输入问题开始问答"
              description="例如：公司食堂在哪里？"
            />
          ) : null}
          {messages.map((message) => (
            <div
              key={message.id}
              className={
                message.role === "user"
                  ? "flex justify-end"
                  : "flex justify-start"
              }
            >
              <div
                className={
                  message.role === "user"
                    ? "max-w-[80%] rounded-lg bg-slate-900 px-4 py-2 text-sm text-white"
                    : "max-w-[85%] rounded-lg bg-slate-100 px-4 py-2 text-sm text-slate-800"
                }
              >
                <p className="whitespace-pre-wrap">
                  {message.content ||
                    (streaming && message.role === "assistant"
                      ? "..."
                      : "")}
                </p>
                {message.role === "assistant" ? (
                  <CitationList citations={message.citations} />
                ) : null}
              </div>
            </div>
          ))}
          <div ref={bottomRef} />
        </div>

        {error ? (
          <div className="border-t border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        ) : null}

        <div className="border-t border-slate-200 p-3">
          <form
            className="flex items-end gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              void send();
            }}
          >
            <Textarea
              rows={2}
              className="flex-1 resize-none"
              placeholder="输入问题，Enter 发送，Shift+Enter 换行"
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void send();
                }
              }}
            />
            {streaming ? (
              <ButtonSecondary type="button" onClick={stop}>
                停止
              </ButtonSecondary>
            ) : (
              <Button type="submit" disabled={!input.trim()}>
                发送
              </Button>
            )}
          </form>
        </div>
      </section>
    </div>
  );
}
