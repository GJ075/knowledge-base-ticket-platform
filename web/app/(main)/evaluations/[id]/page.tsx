"use client";

import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import {
  Badge,
  Button,
  ButtonSecondary,
  Card,
  Dialog,
  EmptyState,
  ErrorState,
  Input,
  PageHeader,
  Select,
  TableSkeleton,
  Textarea,
} from "@/components/ui";
import { API_BASE, apiFetch } from "@/lib/api";
import type {
  DocumentItem,
  EvalCase,
  EvalCaseInput,
  EvalDatasetDetail,
  EvalRetrievalMode,
  EvalRun,
  EvalTurnInput,
  Paginated,
} from "@/lib/types";
import {
  EVAL_MODE_LABEL,
  EVAL_RUN_STATUS_LABEL,
  formatDate,
  formatPercent,
} from "@/lib/utils";

function blankTurn(): EvalTurnInput {
  return {
    question: "",
    reference_answer: "",
    expected_type: "answerable",
    required_document_ids: [],
  };
}

export default function DatasetDetailPage() {
  const params = useParams<{ id: string }>();
  const datasetId = params.id;
  const router = useRouter();
  const queryClient = useQueryClient();

  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [mode, setMode] = useState<EvalRetrievalMode>("question");

  const [editorOpen, setEditorOpen] = useState(false);
  const [editingCase, setEditingCase] = useState<EvalCase | null>(null);
  const [caseTitle, setCaseTitle] = useState("");
  const [caseTags, setCaseTags] = useState("");
  const [turns, setTurns] = useState<EvalTurnInput[]>([blankTurn()]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [sampleSize, setSampleSize] = useState(5);
  const initializedRef = useRef<string | null>(null);

  const datasetQuery = useQuery({
    queryKey: ["eval", "dataset", datasetId],
    queryFn: () =>
      apiFetch<EvalDatasetDetail>(`/eval/datasets/${datasetId}`),
  });

  const documentsQuery = useQuery({
    queryKey: ["documents", "ready"],
    queryFn: () =>
      apiFetch<Paginated<DocumentItem>>("/documents?page_size=100"),
  });

  const runsQuery = useQuery({
    queryKey: ["eval", "runs", datasetId],
    queryFn: () => apiFetch<{ items: EvalRun[] }>(`/eval/runs?dataset_id=${datasetId}`),
  });

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["eval"] });
  };

  const openCreate = () => {
    setEditingCase(null);
    setCaseTitle("");
    setCaseTags("");
    setTurns([blankTurn()]);
    setError("");
    setEditorOpen(true);
  };

  const openEdit = (item: EvalCase) => {
    setEditingCase(item);
    setCaseTitle(item.title);
    setCaseTags(item.tags.join(", "));
    setTurns(
      item.turns.map((turn) => ({
        question: turn.question,
        reference_answer: turn.reference_answer ?? "",
        expected_type: turn.expected_type,
        required_document_ids: [...turn.required_document_ids],
      })),
    );
    setError("");
    setEditorOpen(true);
  };

  const saveMutation = useMutation({
    mutationFn: (payload: EvalCaseInput) => {
      if (editingCase) {
        return apiFetch<EvalCase>(`/eval/cases/${editingCase.id}`, {
          method: "PUT",
          body: JSON.stringify(payload),
        });
      }
      return apiFetch<EvalCase>(
        `/eval/datasets/${datasetId}/cases`,
        { method: "POST", body: JSON.stringify(payload) },
      );
    },
    onSuccess: (saved) => {
      setEditorOpen(false);
      setNotice(editingCase ? "用例已更新" : "用例已创建");
      if (!editingCase) {
        setSelected((prev) => new Set(prev).add(saved.id));
      }
      refresh();
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : "保存失败"),
  });

  const deleteMutation = useMutation({
    mutationFn: (caseId: string) =>
      apiFetch<void>(`/eval/cases/${caseId}`, { method: "DELETE" }),
    onSuccess: () => {
      setNotice("用例已删除");
      refresh();
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : "删除失败"),
  });

  const runMutation = useMutation({
    mutationFn: () =>
      apiFetch<EvalRun>(`/eval/datasets/${datasetId}/runs`, {
        method: "POST",
        body: JSON.stringify({
          retrieval_mode: mode,
          case_ids: selectedCaseIds,
        }),
      }),
    onSuccess: (run) => {
      router.push(`/evaluations/runs/${run.id}`);
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : "启动失败"),
  });

  const dataset = datasetQuery.data;

  useEffect(() => {
    if (dataset && initializedRef.current !== dataset.id) {
      initializedRef.current = dataset.id;
      setSelected(new Set(dataset.cases.map((item) => item.id)));
    }
  }, [dataset]);

  const selectedCaseIds = (dataset?.cases ?? [])
    .filter((item) => selected.has(item.id))
    .map((item) => item.id);

  const toggleCase = (caseId: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(caseId)) {
        next.delete(caseId);
      } else {
        next.add(caseId);
      }
      return next;
    });
  };

  const pickRandom = () => {
    const ids = (dataset?.cases ?? []).map((item) => item.id);
    for (let index = ids.length - 1; index > 0; index -= 1) {
      const swap = Math.floor(Math.random() * (index + 1));
      [ids[index], ids[swap]] = [ids[swap], ids[index]];
    }
    const size = Math.min(
      Math.max(1, sampleSize),
      Math.max(ids.length, 1),
    );
    setSelected(new Set(ids.slice(0, size)));
  };

  const readyDocuments =
    documentsQuery.data?.items.filter(
      (item) => item.index_status === "ready",
    ) ?? [];

  const submitCase = () => {
    setError("");
    const cleaned = turns.map((turn) => ({
      ...turn,
      question: turn.question.trim(),
      reference_answer: turn.reference_answer?.trim() || null,
    }));
    if (!caseTitle.trim()) {
      setError("请填写用例标题");
      return;
    }
    if (cleaned.length === 0 || cleaned.length > 5) {
      setError("用例必须包含 1–5 个轮次");
      return;
    }
    for (let index = 0; index < cleaned.length; index += 1) {
      const turn = cleaned[index];
      if (!turn.question) {
        setError(`第 ${index + 1} 轮问题不能为空`);
        return;
      }
      if (turn.expected_type === "answerable") {
        if (!turn.reference_answer) {
          setError(`第 ${index + 1} 轮需要填写参考答案`);
          return;
        }
        if (turn.required_document_ids.length === 0) {
          setError(`第 ${index + 1} 轮需要选择必引文档`);
          return;
        }
      }
    }
    saveMutation.mutate({
      title: caseTitle.trim(),
      tags: caseTags
        .split(",")
        .map((tag) => tag.trim())
        .filter(Boolean),
      turns: cleaned,
    });
  };

  if (datasetQuery.isLoading) {
    return <TableSkeleton rows={5} columns={4} />;
  }
  if (datasetQuery.error || !dataset) {
    return (
      <ErrorState
        message={
          datasetQuery.error instanceof Error
            ? datasetQuery.error.message
            : "数据集不存在"
        }
        onRetry={() => void datasetQuery.refetch()}
      />
    );
  }

  return (
    <div>
      <PageHeader
        title={dataset.name}
        description={dataset.description || undefined}
        action={
          <div className="flex flex-wrap items-center gap-2">
            <a
              href={`${API_BASE}/eval/datasets/${dataset.id}/export`}
              className="inline-flex items-center rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              导出 JSONL
            </a>
            <ButtonSecondary onClick={openCreate}>
              新增用例
            </ButtonSecondary>
          </div>
        }
      />

      {notice ? (
        <p className="mb-4 rounded-md bg-emerald-50 px-4 py-2 text-sm text-emerald-700">
          {notice}
        </p>
      ) : null}
      {error ? (
        <div className="mb-4">
          <ErrorState message={error} />
        </div>
      ) : null}

      <Card className="mb-6">
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-sm text-slate-600">
            运行范围：已选 {selectedCaseIds.length}/
            {dataset.cases.length} 条用例
          </span>
          <Select
            id="eval-retrieval-mode"
            name="retrieval_mode"
            value={mode}
            className="w-44"
            onChange={(event) =>
              setMode(event.target.value as EvalRetrievalMode)
            }
          >
            <option value="question">当前问题检索</option>
            <option value="rewritten">历史改写检索</option>
          </Select>
          <div className="flex items-center gap-2">
            <Input
              type="number"
              name="sample_size"
              min={1}
              max={Math.max(dataset.cases.length, 1)}
              value={sampleSize}
              className="w-20"
              aria-label="随机抽取条数"
              onChange={(event) =>
                setSampleSize(Number(event.target.value) || 1)
              }
            />
            <ButtonSecondary
              onClick={pickRandom}
              disabled={dataset.cases.length === 0}
            >
              随机抽取
            </ButtonSecondary>
          </div>
          <Button
            disabled={
              runMutation.isPending || selectedCaseIds.length === 0
            }
            onClick={() => {
              setError("");
              setNotice("");
              runMutation.mutate();
            }}
          >
            {runMutation.isPending
              ? "启动中..."
              : `开始运行（${selectedCaseIds.length}）`}
          </Button>
        </div>
      </Card>

      <section className="mb-8">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-semibold text-slate-900">
            用例（{dataset.cases.length}）
          </h2>
          <div className="flex items-center gap-3 text-sm text-slate-500">
            <span>
              已选 {selectedCaseIds.length}/{dataset.cases.length}
            </span>
            <button
              className="text-slate-600 hover:underline"
              onClick={() =>
                setSelected(new Set(dataset.cases.map((item) => item.id)))
              }
            >
              全选
            </button>
            <button
              className="text-slate-600 hover:underline"
              onClick={() => setSelected(new Set())}
            >
              清空
            </button>
          </div>
        </div>
        {dataset.cases.length === 0 ? (
          <EmptyState
            title="还没有用例"
            description="新增用例，或从 JSONL 导入"
          />
        ) : (
          <div className="space-y-3">
            {dataset.cases.map((item) => (
              <Card key={item.id}>
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-start gap-3">
                    <input
                      type="checkbox"
                      className="mt-1"
                      name={`select-case-${item.id}`}
                      checked={selected.has(item.id)}
                      onChange={() => toggleCase(item.id)}
                      aria-label={`选择用例 ${item.title}`}
                    />
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="font-medium text-slate-900">
                          {item.title}
                        </h3>
                        {item.tags.map((tag) => (
                          <Badge
                            key={tag}
                            className="bg-slate-100 text-slate-600"
                          >
                            {tag}
                          </Badge>
                        ))}
                      </div>
                      <p className="mt-1 text-xs text-slate-500">
                        {item.turns.length} 个轮次
                      </p>
                    </div>
                  </div>
                  <div className="flex gap-3 text-sm">
                    <button
                      className="text-slate-600 hover:underline"
                      onClick={() => openEdit(item)}
                    >
                      编辑
                    </button>
                    <button
                      className="text-red-600 hover:underline"
                      onClick={() => {
                        if (
                          window.confirm(`确认删除用例「${item.title}」？`)
                        ) {
                          deleteMutation.mutate(item.id);
                        }
                      }}
                    >
                      删除
                    </button>
                  </div>
                </div>
                <div className="mt-3 space-y-2">
                  {item.turns.map((turn) => (
                    <div
                      key={turn.id}
                      className="rounded-md bg-slate-50 px-3 py-2 text-sm"
                    >
                      <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
                        <span className="shrink-0">
                          第 {turn.turn_index} 轮
                        </span>
                        <Badge
                          className={
                            turn.expected_type === "answerable"
                              ? "shrink-0 bg-blue-50 text-blue-700"
                              : "shrink-0 bg-amber-50 text-amber-700"
                          }
                        >
                          {turn.expected_type === "answerable"
                            ? "可回答"
                            : "应拒答"}
                        </Badge>
                        {turn.required_documents
                          .slice(0, 3)
                          .map((document, index) => (
                            <span key={`${document.id}-${index}`}>
                              《{document.title}》
                            </span>
                          ))}
                        {turn.required_documents.length > 3 ? (
                          <span className="shrink-0">
                            等 {turn.required_documents.length} 篇
                          </span>
                        ) : null}
                      </div>
                      <p className="mt-1 text-slate-800">
                        {turn.question}
                      </p>
                      {turn.reference_answer ? (
                        <p className="mt-1 text-xs text-slate-500">
                          参考答案：{turn.reference_answer}
                        </p>
                      ) : null}
                    </div>
                  ))}
                </div>
              </Card>
            ))}
          </div>
        )}
      </section>

      <section>
        <h2 className="mb-3 text-lg font-semibold text-slate-900">
          运行记录
        </h2>
        {(runsQuery.data?.items.length ?? 0) === 0 ? (
          <EmptyState title="还没有运行记录" />
        ) : (
          <Card className="overflow-x-auto p-0">
            <table className="w-full text-sm">
              <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase text-slate-500">
                <tr>
                  <th className="px-4 py-3">时间</th>
                  <th className="px-4 py-3">模式</th>
                  <th className="px-4 py-3">状态</th>
                  <th className="px-4 py-3">进度</th>
                  <th className="px-4 py-3">通过率</th>
                  <th className="px-4 py-3">发起人</th>
                </tr>
              </thead>
              <tbody>
                {(runsQuery.data?.items ?? []).map((run) => (
                  <tr
                    key={run.id}
                    className="border-b border-slate-100 last:border-0"
                  >
                    <td className="px-4 py-3">
                      <Link
                        href={`/evaluations/runs/${run.id}`}
                        className="text-slate-900 hover:underline"
                      >
                        {formatDate(run.created_at)}
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-slate-600">
                      {EVAL_MODE_LABEL[run.retrieval_mode]}
                    </td>
                    <td className="px-4 py-3 text-slate-600">
                      {EVAL_RUN_STATUS_LABEL[run.status]}
                    </td>
                    <td className="px-4 py-3 text-slate-600">
                      {run.completed_items}/{run.total_items}
                    </td>
                    <td className="px-4 py-3 text-slate-600">
                      {formatPercent(run.metrics?.pass_rate)}
                    </td>
                    <td className="px-4 py-3 text-slate-600">
                      {run.created_by}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )}
      </section>

      <Dialog
        open={editorOpen}
        title={editingCase ? "编辑用例" : "新增用例"}
        onClose={() => setEditorOpen(false)}
        className="max-w-3xl"
      >
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-sm text-slate-600">
                标题
              </label>
              <Input
                value={caseTitle}
                maxLength={255}
                onChange={(event) => setCaseTitle(event.target.value)}
              />
            </div>
            <div>
              <label className="mb-1 block text-sm text-slate-600">
                标签（逗号分隔）
              </label>
              <Input
                value={caseTags}
                onChange={(event) => setCaseTags(event.target.value)}
                placeholder="single_turn, answerable"
              />
            </div>
          </div>

          {turns.map((turn, index) => (
            <div
              key={index}
              className="rounded-md border border-slate-200 p-3"
            >
              <div className="mb-2 flex items-center justify-between">
                <p className="text-sm font-medium text-slate-700">
                  第 {index + 1} 轮
                </p>
                <button
                  className="text-sm text-red-600 hover:underline disabled:opacity-50"
                  disabled={turns.length <= 1}
                  onClick={() =>
                    setTurns(turns.filter((_, i) => i !== index))
                  }
                >
                  删除本轮
                </button>
              </div>
              <div className="space-y-2">
                <Textarea
                  rows={2}
                  placeholder="问题"
                  maxLength={2000}
                  value={turn.question}
                  onChange={(event) =>
                    setTurns(
                      turns.map((item, i) =>
                        i === index
                          ? { ...item, question: event.target.value }
                          : item,
                      ),
                    )
                  }
                />
                <div className="flex flex-wrap items-center gap-3">
                  <Select
                    className="w-40"
                    value={turn.expected_type}
                    onChange={(event) =>
                      setTurns(
                        turns.map((item, i) =>
                          i === index
                            ? {
                                ...item,
                                expected_type: event.target
                                  .value as EvalTurnInput["expected_type"],
                              }
                            : item,
                        ),
                      )
                    }
                  >
                    <option value="answerable">可回答</option>
                    <option value="unanswerable">应拒答</option>
                  </Select>
                  {turn.expected_type === "answerable" ? (
                    <span className="text-xs text-slate-500">
                      需要参考答案与必引文档
                    </span>
                  ) : null}
                </div>
                <Textarea
                  rows={2}
                  placeholder="参考答案（应拒答轮次可留空）"
                  value={turn.reference_answer ?? ""}
                  onChange={(event) =>
                    setTurns(
                      turns.map((item, i) =>
                        i === index
                          ? {
                              ...item,
                              reference_answer: event.target.value,
                            }
                          : item,
                      ),
                    )
                  }
                />
                <div>
                  <p className="mb-1 text-xs text-slate-500">
                    必引文档
                  </p>
                  <div className="max-h-32 space-y-1 overflow-y-auto rounded-md border border-slate-200 p-2">
                    {readyDocuments.length === 0 ? (
                      <p className="text-xs text-slate-400">
                        没有可检索文档
                      </p>
                    ) : (
                      readyDocuments.map((document) => (
                        <label
                          key={document.id}
                          className="flex items-center gap-2 text-sm text-slate-700"
                        >
                          <input
                            type="checkbox"
                            checked={turn.required_document_ids.includes(
                              document.id,
                            )}
                            onChange={(event) =>
                              setTurns(
                                turns.map((item, i) =>
                                  i === index
                                    ? {
                                        ...item,
                                        required_document_ids:
                                          event.target.checked
                                            ? [
                                                ...item.required_document_ids,
                                                document.id,
                                              ]
                                            : item.required_document_ids.filter(
                                                (id) => id !== document.id,
                                              ),
                                      }
                                    : item,
                                ),
                              )
                            }
                          />
                          {document.title}
                        </label>
                      ))
                    )}
                  </div>
                </div>
              </div>
            </div>
          ))}

          <ButtonSecondary
            disabled={turns.length >= 5}
            onClick={() => setTurns([...turns, blankTurn()])}
          >
            增加一轮（最多 5 轮）
          </ButtonSecondary>

          <div className="flex justify-end gap-2">
            <ButtonSecondary onClick={() => setEditorOpen(false)}>
              取消
            </ButtonSecondary>
            <Button
              disabled={saveMutation.isPending}
              onClick={submitCase}
            >
              {saveMutation.isPending ? "保存中..." : "保存"}
            </Button>
          </div>
          {error ? <ErrorState message={error} /> : null}
        </div>
      </Dialog>
    </div>
  );
}
