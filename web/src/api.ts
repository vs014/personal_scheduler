export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

export async function api<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      method,
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-Scheduler-Client": "web",
      },
      ...(method !== "GET" ? { body: JSON.stringify(body ?? {}) } : {}),
    });
  } catch {
    throw new ApiError(
      "서버에 연결하지 못했습니다. 입력은 그대로 두고 다시 시도해 주세요.",
      0,
    );
  }
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    if (response.status === 401 && path !== "/login")
      window.dispatchEvent(new Event("session-expired"));
    throw new ApiError(
      typeof data.detail === "string"
        ? data.detail
        : "요청을 처리하지 못했습니다.",
      response.status,
    );
  }
  const result = await response.json();
  if (response.headers.get("X-Scheduler-Undo"))
    window.dispatchEvent(
      new CustomEvent("item-undo", { detail: response.headers.get("X-Scheduler-Undo") }),
    );
  return result;
}

export type Item = {
  id: string;
  revision: number;
  title: string;
  kind: "할 일" | "일정";
  original_text?: string;
  category?: string;
  description: string;
  status: "미시작" | "진행중" | "완료";
  flag: "없음" | "대기중" | "나중에";
  importance: "보통" | "중요";
  planned_date: string | null;
  deadline: string | null;
  time_mode: "미정" | "시간 확정" | "종일";
  start_time: string | null;
  end_time: string | null;
  location: string;
  created_at?: string;
  updated_at?: string;
};
export type Thread = {
  id: string;
  revision: number;
  title: string;
  kind: "질문" | "오류" | "기능 제안";
  page: string;
  status: string;
  priority: string;
  resolution: string;
  release_version: string;
  created_at: string;
  updated_at: string;
  messages: { id: string; role: string; content: string; created_at: string }[];
  history: { detail: string; created_at: string }[];
};
export const statuses = [
  "접수",
  "검토 중",
  "예정",
  "작업 중",
  "확인 요청",
  "반영 완료",
  "보류",
];
export const today = () =>
  new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
export const dateLabel = (date: string) =>
  new Intl.DateTimeFormat("ko-KR", {
    timeZone: "Asia/Seoul",
    month: "long",
    day: "numeric",
    weekday: "short",
  }).format(new Date(`${date}T12:00:00+09:00`));
export const timestamp = (value: string) =>
  new Date(value).toLocaleString("ko-KR", {
    timeZone: "Asia/Seoul",
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
export const blankItem = (): Item => ({
  id: "",
  revision: 1,
  title: "",
  kind: "할 일",
  description: "",
  status: "미시작",
  flag: "없음",
  importance: "보통",
  planned_date: null,
  deadline: null,
  time_mode: "미정",
  start_time: null,
  end_time: null,
  location: "",
});
export function itemBody(item: Item) {
  const { id, created_at, updated_at, ...body } = item;
  return body;
}
export function download(
  name: string,
  text: string,
  type = "application/json",
) {
  const url = URL.createObjectURL(
    new Blob([text], { type: `${type};charset=utf-8` }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
