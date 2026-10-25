import { useEffect, useRef, useState } from "react";
import { api, Item } from "./api";
type Proposal = {
  reply: string;
  questions: { prompt: string; options: string[] }[];
  items: Item[];
};
type Chat = {
  id: string;
  revision: number;
  status: string;
  history: { role: string; content: string }[];
  proposal: Proposal | null;
  saved_ids: string[];
};
type Account = {
  client_id: string;
  label: string;
  connected: boolean;
  model: string;
};
type Status = { active: string; accounts: Account[] };
export default function Assistant({
  onSaved,
}: {
  onSaved: () => Promise<void>;
}) {
  const [status, setStatus] = useState<Status>({ active: "", accounts: [] });
  const [models, setModels] = useState<{ id: string; name: string }[]>([]);
  const [chats, setChats] = useState<Chat[]>([]);
  const [chat, setChat] = useState<Chat | null>(null);
  const [input, setInput] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [previewOpen, setPreviewOpen] = useState(false);
  const previewRef = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    setPreviewOpen(
      !!chat?.proposal?.items.length &&
        !chat.proposal.questions.length &&
        chat.status === "작성 중",
    );
  }, [chat?.id, chat?.revision]);
  useEffect(() => {
    if (previewOpen) previewRef.current?.showModal();
    else previewRef.current?.close();
  }, [previewOpen]);
  const [busy, setBusy] = useState(false);
  const [answers, setAnswers] = useState<Record<number, string>>({});
  useEffect(() => {
    setAnswers({});
  }, [chat?.id, chat?.revision]);
  const questions =
    chat?.status === "작성 중" ? chat.proposal?.questions || [] : [];
  const combined = [
    ...questions.flatMap((q, i) =>
      answers[i] ? [`${q.prompt}\n내 선택: ${answers[i]}`] : [],
    ),
    input.trim(),
  ]
    .filter(Boolean)
    .join("\n\n");
  const ready =
    !!combined &&
    (questions.length === 0 ||
      questions.every((_, i) => answers[i]) ||
      !!input.trim());
  const key = useRef(crypto.randomUUID());
  const account = status.accounts.find((a) => a.client_id === status.active);
  const load = async () => {
    setStatus(await api("/ai/status"));
    setChats(await api("/conversations"));
  };
  useEffect(() => {
    load().catch((e) => setError(e.message));
    if (new URLSearchParams(location.search).get("chatgpt") === "error")
      setError(
        new URLSearchParams(location.search).get("reason") ||
          "ChatGPT 로그인 또는 구독 권한 검증에 실패했습니다. 다시 연결해 주세요.",
      );
  }, []);
  const action = async (fn: () => Promise<void>) => {
    setError("");
    setNotice("");
    setBusy(true);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : "처리하지 못했습니다.");
    } finally {
      setBusy(false);
    }
  };
  const connect = (client_id = "") =>
    action(async () => {
      const r = await api<{ url: string }>("/ai/connect", "POST", {
        client_id,
      });
      window.location.assign(r.url);
    });
  const modelList = () =>
    action(async () => {
      setModels(await api("/ai/models"));
    });
  const choose = async (client_id: string, model = "") => {
    setStatus(await api("/ai/select", "POST", { client_id, model }));
    setModels([]);
  };
  const updateChat = async (c: Chat) => {
    setChat(c);
    setChats((previous) => [c, ...previous.filter((item) => item.id !== c.id)]);
  };
  async function send(content: string) {
    if (!content.trim()) return;
    await action(async () => {
      let c = chat;
      if (!c) c = await api<Chat>("/conversations", "POST");
      setChat(c);
      const started = performance.now();
      const r = await api<Chat>(`/conversations/${c.id}/turn`, "POST", {
        content,
        revision: c.revision,
        request_id: key.current,
      });
      await updateChat(r);
      setNotice(
        `답변을 받는 데 ${((performance.now() - started) / 1000).toFixed(1)}초 걸렸습니다.`,
      );
      setInput("");
      key.current = crypto.randomUUID();
    });
  }
  function assistantText(message: { role: string; content: string }) {
    if (message.role === "user") return message.content;
    try {
      return (JSON.parse(message.content) as Proposal).reply;
    } catch {
      return message.content;
    }
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">TALK, CHOOSE, CONFIRM</p>
          <h1>말로 전하고, 확인해서 담아요.</h1>
          <p className="muted">
            일정·할 일을 이야기하면 AI가 필요한 정보만 확인합니다. 마지막 승인
            전에는 등록하지 않아요.
          </p>
        </div>
      </div>
      <section className="panel assistant-settings">
        <h2>ChatGPT 연결</h2>
        <p className="small muted">
          일정 등록 대화만 OpenAI에 전송합니다. 기존 일정·피드백 전체는 자동
          전송하지 않습니다. ChatGPT 구독의 사용량·앱 한도가 적용되며, 유료
          API로 자동 전환하지 않습니다. 승인 화면에서 크레딧 사용을 허용하지
          않도록 확인하세요.
        </p>
        <div className="inline assistant-controls">
          <button className="primary" disabled={busy} onClick={() => connect()}>
            Continue with ChatGPT
          </button>
          <button
            className="secondary"
            disabled={busy}
            onClick={() =>
              action(async () => {
                const result = await api<{ ok: boolean; message: string }>(
                  "/ai/diagnose",
                  "POST",
                );
                if (result.ok) setNotice(result.message);
                else setError(result.message);
              })
            }
          >
            인증 서버 연결 확인
          </button>
          {status.accounts.length > 0 && (
            <label>
              사용할 계정
              <select
                disabled={busy}
                value={status.active}
                onChange={(e) => action(() => choose(e.target.value))}
              >
                {status.accounts.map((a) => (
                  <option key={a.client_id} value={a.client_id}>
                    {a.label}
                    {a.connected ? "" : " · 재연결 필요"}
                  </option>
                ))}
              </select>
            </label>
          )}
          {account && (
            <>
              <button
                className="secondary"
                disabled={busy}
                onClick={() => connect(account.client_id)}
              >
                선택 계정 다시 연결
              </button>
              <button
                className="secondary"
                disabled={busy}
                onClick={() =>
                  action(async () => {
                    const r = await api<{ message: string }>(
                      "/ai/disconnect",
                      "POST",
                    );
                    setNotice(r.message);
                    await load();
                  })
                }
              >
                연결 해제
              </button>
            </>
          )}
        </div>
        {account?.connected && (
          <div className="inline assistant-controls">
            <button className="secondary" disabled={busy} onClick={modelList}>
              사용 가능한 모델 불러오기
            </button>
            <label>
              AI 모델
              <select
                value={account.model}
                disabled={busy}
                onChange={(e) =>
                  action(() => choose(account.client_id, e.target.value))
                }
              >
                <option value="">모델을 선택해 주세요</option>
                {account.model &&
                  !models.some((m) => m.id === account.model) && (
                    <option>{account.model}</option>
                  )}
                {models.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name}
                  </option>
                ))}
              </select>
            </label>
          </div>
        )}
        <p className="small muted">
          {account?.connected
            ? "로그인됨 · 모델을 선택하고 실제 첫 응답을 확인해 주세요."
            : "AI 미연결 · 위 로그인 버튼에서 본인의 계정으로 연결해 주세요."}{" "}
          <a
            href="https://chatgpt.com/settings/usage"
            target="_blank"
            rel="noreferrer"
          >
            ChatGPT 사용량 확인
          </a>
        </p>
      </section>
      {error && (
        <p className="error-banner" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="notice" role="status">
          {notice}
        </p>
      )}
      <div className="assistant-layout">
        <aside className="panel assistant-settings">
          <button
            className="secondary full"
            disabled={busy}
            onClick={() => {
              setChat(null);
              setInput("");
              setNotice("");
              key.current = crypto.randomUUID();
            }}
          >
            새 대화
          </button>
          <h3>최근 대화</h3>
          {chats.map((c) => (
            <button
              className="chat-list-item"
              disabled={busy}
              key={c.id}
              onClick={() => {
                setChat(c);
                setInput("");
                key.current = crypto.randomUUID();
              }}
            >
              {c.history.find((m) => m.role === "user")?.content.slice(0, 45) ||
                "새 대화"}
              <small>{c.status}</small>
            </button>
          ))}
        </aside>
        <section className="panel assistant-settings">
          <h2>일정·할 일 대화</h2>
          {!chat?.history.length && (
            <p className="muted">
              예: “이번 주말에 친구와 저녁 먹기로 했어.” 또는 “섬유유연제 사기,
              침대 구매하기를 할 일로 넣어줘.”
            </p>
          )}
          <div className="assistant-history">
            {chat?.history.map((m, i) => (
              <div
                className={`message ${m.role === "user" ? "mine" : ""}`}
                key={i}
              >
                <span>{m.role === "user" ? "나" : "ChatGPT"}</span>
                <p>{assistantText(m)}</p>
              </div>
            ))}
          </div>
          {chat?.status === "작성 중" &&
            chat.proposal?.questions.map((q, i) => (
              <div className="assistant-question" key={i}>
                <strong>{q.prompt}</strong>
                <div className="inline assistant-controls">
                  {q.options.map((o, j) => (
                    <button
                      className={answers[i] === o ? "primary" : "secondary"}
                      aria-pressed={answers[i] === o}
                      disabled={busy}
                      key={j}
                      onClick={() => {
                        key.current = crypto.randomUUID();
                        setAnswers((previous) => ({ ...previous, [i]: o }));
                      }}
                    >
                      {o}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          {(!chat || chat.status === "작성 중") && (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                send(combined);
              }}
            >
              {questions.length > 0 && (
                <p className="small muted">
                  각 질문의 답을 모두 고른 뒤 한 번에 보내세요. 선택만 할 때는
                  AI를 호출하지 않습니다. 선택지에 없는 답은 아래에 적어 주세요.
                </p>
              )}
              {combined.length > 4000 && (
                <p role="alert">답변이 너무 깁니다. 추가 설명을 줄여 주세요.</p>
              )}
              <label>
                대화 입력
                <textarea
                  aria-label="일정 대화 입력"
                  rows={3}
                  maxLength={4000}
                  value={input}
                  disabled={busy}
                  onChange={(e) => {
                    setInput(e.target.value);
                    key.current = crypto.randomUUID();
                  }}
                  placeholder="원하는 일정, 추가 설명, 수정할 내용을 적어주세요"
                />
              </label>
              <button
                className="primary"
                disabled={
                  busy ||
                  !ready ||
                  combined.length > 4000 ||
                  !account?.connected ||
                  !account.model
                }
              >
                {busy
                  ? "AI 응답을 기다리는 중…"
                  : questions.length
                    ? "선택한 답변 한 번에 보내기"
                    : "AI에게 보내기"}
              </button>
            </form>
          )}
          {chat?.proposal &&
            chat.status === "작성 중" &&
            !chat.proposal.questions.length && (
              <button className="primary" onClick={() => setPreviewOpen(true)}>
                등록 내용 확인
              </button>
            )}
          {chat?.proposal && (
            <dialog
              className="registration-dialog" aria-label="등록 전 확인"
              ref={previewRef}
              onCancel={() => setPreviewOpen(false)}
            >
              <section className="assistant-preview">
                <button
                  className="secondary"
                  disabled={busy}
                  onClick={() => setPreviewOpen(false)}
                >
                  대화로 돌아가기
                </button>
                {error && <p role="alert">{error}</p>}
                <h2>
                  {chat.status === "저장 완료" ? "등록한 내용" : "등록 전 확인"}
                </h2>
                {chat.proposal.items.map((it, i) => (
                  <article className="note-card" key={i}>
                    <h3>{it.title}</h3>
                    <p>
                      {it.kind} · {it.category || "기타"}
                    </p>
                    <p>
                      계획일: {it.planned_date || "미정"} / 마감일:{" "}
                      {it.deadline || "없음"}
                      <br />
                      시간: {it.time_mode}
                      {it.start_time && ` · ${it.start_time}`}
                      {it.end_time && ` ~ ${it.end_time}`}
                      <br />
                      장소: {it.location || "미정"}
                    </p>
                    {it.description && <p>{it.description}</p>}
                  </article>
                ))}
                {chat.status === "작성 중" && (
                  <>
                    <p className="small muted">
                      수정할 내용은 위 대화창에 알려주세요. 선택지에 없는 답도
                      직접 입력할 수 있어요.
                    </p>
                    <div className="inline assistant-controls">
                      <button
                        className="primary"
                        disabled={
                          busy ||
                          !!chat.proposal.questions.length ||
                          !chat.proposal.items.length
                        }
                        onClick={() =>
                          action(async () => {
                            const result = await api<Chat>(
                              `/conversations/${chat.id}/confirm`,
                              "POST",
                              { revision: chat.revision },
                            );
                            await updateChat(result);
                            await onSaved();
                            setNotice(
                              `${result.saved_ids.length}개를 저장했습니다. 받은함·캘린더에서 확인하세요.`,
                            );
                          })
                        }
                      >
                        확인한 내용 등록
                      </button>
                      <button
                        className="secondary"
                        disabled={busy}
                        onClick={() =>
                          action(async () => {
                            await updateChat(
                              await api(
                                `/conversations/${chat.id}/cancel`,
                                "POST",
                                { revision: chat.revision },
                              ),
                            );
                          })
                        }
                      >
                        등록 취소
                      </button>
                    </div>
                  </>
                )}

              </section>
            </dialog>
          )}
          {chat?.status === "저장 완료" && (
            <p role="status">
              {chat.saved_ids.length}개 등록 완료 · 받은함과 캘린더에서
              확인하세요.
            </p>
          )}
        </section>
      </div>
    </>
  );
}
