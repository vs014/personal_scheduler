import { useEffect, useRef, useState } from "react";
import { api, timestamp } from "./api";
type Settings = { environment: string; branch: string };
type Job = {
  id: string;
  status: string;
  url: string;
  message: string;
  count: number;
  created: number;
  destination: Settings;
  snapshot?: unknown;
};
export default function CodexDelivery({ selected }: { selected: string[] }) {
  const [config, setConfig] = useState<Settings>({
    environment: "",
    branch: "codex/feedback-delivery",
  });
  const [saved, setSaved] = useState("");
  const [environments, setEnvironments] = useState<
    { id: string; name: string }[]
  >([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [preview, setPreview] = useState<Job | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [receipts, setReceipts] = useState<Record<string, string>>({});
  const dialog = useRef<HTMLDialogElement>(null);
  const loadJobs = async () => setJobs(await api<Job[]>("/codex/jobs"));
  useEffect(() => {
    api<Settings>("/codex/settings")
      .then((c) => {
        setConfig(c);
        setSaved(JSON.stringify(c));
      })
      .catch((e) => setError(e.message));
    loadJobs().catch((e) => setError(e.message));
    const timer = setInterval(() => {
      if (document.visibilityState === "visible") loadJobs().catch(() => {});
    }, 3000);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    if (preview) dialog.current?.showModal();
    else dialog.current?.close();
  }, [preview]);
  const action = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : "처리하지 못했습니다.");
    } finally {
      setBusy(false);
    }
  };
  const dirty = JSON.stringify(config) !== saved;
  return (
    <section className="panel" style={{ marginBottom: 20 }}>
      <h2>개발 AI에게 보내기</h2>
      <p className="muted">
        선택한 피드백으로 새 Codex 클라우드 검토 작업을 만듭니다. 현재 Codex
        대화에 추가되는 방식은 아닙니다. 접수 후에도 설치된 앱은 자동 변경되지
        않습니다.
      </p>
      <details open>
        <summary>처음 연결하기 · 설정 변경</summary>
        <p>
          일정 등록 AI와 별도로 Codex에 한 번 로그인하세요. Codex 사용량과 계정
          권한이 적용됩니다. 별도 유료 API로 전환하지 않습니다.
        </p>
        <button
          className="secondary"
          disabled={busy}
          onClick={() =>
            action(async () => {
              const r = await api<{ message: string }>("/codex/login", "POST");
              setMessage(r.message);
            })
          }
        >
          Codex 로그인 창 열기
        </button>
        <div className="inline assistant-controls">
          <button
            className="secondary"
            disabled={busy}
            onClick={() =>
              action(async () => {
                const r = await api<{ connected: boolean; message: string }>(
                  "/codex/connection",
                  "POST",
                );
                if (r.connected) setMessage(r.message);
                else setError(r.message);
              })
            }
          >
            로그인 상태 확인
          </button>
          <button
            className="secondary"
            disabled={busy}
            onClick={() =>
              action(async () => {
                const r = await api<{
                  ok: boolean;
                  message: string;
                  environments: { id: string; name: string }[];
                }>("/codex/environments", "POST");
                setEnvironments(r.environments);
                if (r.ok) setMessage(r.message);
                else setError(r.message);
              })
            }
          >
            최근 Codex 작업에서 환경 찾기
          </button>
        </div>
        {environments.length > 0 && (
          <label>
            작업에서 확인된 환경
            <select
              aria-label="작업에서 확인된 환경"
              value={
                environments.some((e) => e.id === config.environment)
                  ? config.environment
                  : ""
              }
              onChange={(e) => {
                if (e.target.value)
                  setConfig({ ...config, environment: e.target.value });
              }}
            >
              <option value="">이 프로젝트의 환경을 선택하세요</option>
              {environments.map((e) => (
                <option value={e.id} key={e.id}>
                  {e.name} · {e.id}
                </option>
              ))}
            </select>
          </label>
        )}
        <p className="small muted">
          로그인 상태와 환경 접근은 별도로 확인합니다. 환경 찾기는 최근 작업
          최대 100개의 환경을 보여주며, 모든 환경 목록을 보장하지는 않습니다.
        </p>
        <div className="form-grid">
          <label>
            Codex 환경 이름 또는 ID
            <input
              value={config.environment}
              maxLength={200}
              placeholder="Codex 환경 설정에 표시되는 이름"
              onChange={(e) =>
                setConfig({ ...config, environment: e.target.value })
              }
            />
          </label>
          <label>
            개발 브랜치
            <input
              value={config.branch}
              maxLength={200}
              onChange={(e) => setConfig({ ...config, branch: e.target.value })}
            />
          </label>
        </div>
        <p className="small muted">
          vs014/personal_scheduler 저장소가 연결된 환경을 선택하세요. 브랜치에
          최신 앱 코드가 있어야 검토할 수 있습니다.
        </p>
        <div className="inline assistant-controls">
          <button
            className="secondary"
            disabled={
              busy || !config.environment.trim() || !config.branch.trim()
            }
            onClick={() =>
              action(async () => {
                const c = await api<Settings>("/codex/settings", "PUT", config);
                setConfig(c);
                setSaved(JSON.stringify(c));
                setMessage("설정을 저장했습니다. 연결 확인을 눌러 주세요.");
              })
            }
          >
            연결 설정 저장
          </button>
          <button
            className="secondary"
            disabled={busy || dirty || !config.environment}
            onClick={() =>
              action(async () => {
                const r = await api<{ ok: boolean; message: string }>(
                  "/codex/check",
                  "POST",
                );
                if (r.ok) setMessage(r.message);
                else setError(r.message);
              })
            }
          >
            Codex 연결 확인
          </button>
        </div>
      </details>
      <button
        className="primary"
        disabled={busy || !selected.length || dirty || !config.environment}
        onClick={() =>
          action(async () => {
            setPreview(
              await api<Job>("/codex/preview", "POST", { ids: selected }),
            );
          })
        }
      >
        선택한 피드백 보내기 전 확인 ({selected.length})
      </button>
      {dirty && (
        <p className="small muted">변경한 연결 설정을 먼저 저장하세요.</p>
      )}
      {!preview && error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {!preview && message && <p role="status">{message}</p>}
      <dialog
        ref={dialog}
        className="registration-dialog"
        aria-label="Codex 전송 내용 확인"
        onCancel={() => setPreview(null)}
      >
        {preview && (
          <>
            <h2>이 피드백을 Codex로 보낼까요?</h2>
            <p>
              {preview.count}건 · 환경: {preview.destination.environment} ·
              브랜치: {preview.destination.branch}
            </p>
            <p>
              아래 피드백 대화와 처리 이력, 앱 버전을 보냅니다. 일정 전체나
              로그인 정보는 첨부하지 않습니다.
            </p>
            <pre className="export-preview">
              {JSON.stringify(preview.snapshot, null, 2)}
            </pre>
            <p>상태: {preview.status}</p>
            {error && (
              <p role="alert" className="error">
                {error}
              </p>
            )}
            <div className="inline assistant-controls">
              <button
                className="secondary"
                disabled={busy}
                onClick={() => setPreview(null)}
              >
                닫기
              </button>
              <button
                className="primary"
                disabled={
                  busy || !["확인 대기", "연결 필요"].includes(preview.status)
                }
                onClick={() =>
                  action(async () => {
                    await api(`/codex/jobs/${preview.id}/send`, "POST");
                    setPreview(null);
                    await loadJobs();
                    setMessage(
                      "전송 대기열에 저장했습니다. 아래에서 접수 여부를 확인하세요.",
                    );
                  })
                }
              >
                확인한 피드백 Codex로 보내기
              </button>
            </div>
            {!["확인 대기", "연결 필요"].includes(preview.status) && (
              <p>
                같은 내용의 전송 기록이 있습니다. 중복 전송하지 않습니다. 아래
                기록을 확인하세요.
              </p>
            )}
          </>
        )}
      </dialog>
      {jobs.length > 0 && (
        <details open>
          <summary>전송 기록</summary>
          {jobs.map((job) => (
            <article className="note-card" key={job.id}>
              <strong>
                {job.count}건 · {job.status}
              </strong>
              <p className="small muted">
                {timestamp(new Date(job.created * 1000).toISOString())} ·{" "}
                {job.destination.environment}
              </p>
              <p>{job.message}</p>
              {job.url && (
                <div className="inline assistant-controls">
                  <a href={job.url} target="_blank" rel="noreferrer">
                    Codex 작업 열기
                  </a>
                  <button
                    className="secondary"
                    disabled={busy}
                    onClick={() =>
                      action(async () => {
                        await api(`/codex/jobs/${job.id}/refresh`, "POST");
                        await loadJobs();
                      })
                    }
                  >
                    작업 상태 확인
                  </button>
                </div>
              )}
              {job.status === "연결 필요" && (
                <button
                  className="secondary"
                  disabled={busy}
                  onClick={() =>
                    action(async () => {
                      await api(`/codex/jobs/${job.id}/send`, "POST");
                      await loadJobs();
                    })
                  }
                >
                  같은 설정으로 다시 보내기
                </button>
              )}
              {job.status === "접수 확인 필요" && (
                <>
                  <a
                    href="https://chatgpt.com/codex"
                    target="_blank"
                    rel="noreferrer"
                  >
                    Codex 작업 목록에서 접수 확인
                  </a>
                  <label>
                    이 피드백으로 생성된 작업 링크
                    <input
                      value={receipts[job.id] || ""}
                      onChange={(e) =>
                        setReceipts({ ...receipts, [job.id]: e.target.value })
                      }
                    />
                  </label>
                  <button
                    className="secondary"
                    disabled={busy || !receipts[job.id]}
                    onClick={() =>
                      action(async () => {
                        await api(`/codex/jobs/${job.id}/receipt`, "POST", {
                          url: receipts[job.id],
                        });
                        await loadJobs();
                      })
                    }
                  >
                    확인한 작업 연결
                  </button>
                </>
              )}
            </article>
          ))}
        </details>
      )}
    </section>
  );
}
