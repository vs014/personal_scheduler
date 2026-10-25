import { test, expect } from "@playwright/test";

const password = "browser-isolated-password-2026";
test.describe.configure({ mode: "serial" });

test("처음 설정하고 날짜 없는 할 일을 저장·계획·완료·복원한다", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await page.getByLabel("비밀번호", { exact: true }).fill(password);
  await page.getByLabel("비밀번호 확인", { exact: true }).fill(password);
  await page.getByRole("button", { name: "내 공간 만들기" }).click();
  await expect(
    page.getByRole("heading", { name: "오늘은, 조금 가볍게." }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "받은함", exact: false })
    .first()
    .click();
  await page.getByLabel("빠르게 할 일 추가").fill("침대 구매하기");
  await page.getByRole("button", { name: "추가", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "침대 구매하기 할 일 · 날짜 미정" }),
  ).toBeVisible();
  await page.reload();
  await page
    .getByRole("button", { name: "받은함", exact: false })
    .first()
    .click();
  await page
    .getByRole("button", { name: "침대 구매하기 할 일 · 날짜 미정" })
    .click();
  await page.getByLabel("실제 마감일 (선택)").fill("2026-12-20");
  await page.getByRole("button", { name: "저장", exact: true }).click();
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await page.getByRole("button", { name: "오늘 하기", exact: true }).click();
  await expect(
    page.getByText("마감 2026-12-20", { exact: false }),
  ).toBeVisible();
  await page.getByRole("button", { name: /침대 구매하기 할 일/ }).click();
  await page
    .getByRole("button", { name: "실행 계획 해제 · 할 일과 마감일은 유지" })
    .click();
  await expect(page.getByLabel("실제 마감일 (선택)")).toHaveValue("2026-12-20");
  await page.getByRole("button", { name: "저장", exact: true }).click();
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await page
    .getByRole("button", { name: "침대 구매하기 완료", exact: true })
    .click();
  await page.getByRole("button", { name: "완료 기록", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "침대 구매하기 완료 취소" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "침대 구매하기 완료 취소" }).click();
  await expect(page.getByText("해낸 일이 여기에 쌓일 거예요")).toBeVisible();
  expect(errors).toEqual([]);
});

test.beforeEach(async ({ page }, testInfo) => {
  if (testInfo.title.startsWith("처음 설정")) return;
  await page.goto("/");
  await page.getByLabel("비밀번호", { exact: true }).fill(password);
  await page.getByRole("button", { name: "들어가기" }).click();
  await expect(
    page.getByRole("heading", { name: "오늘은, 조금 가볍게." }),
  ).toBeVisible();
});

test("피드백 대화를 이어가고 선택한 대화만 확인 후 전달한다", async ({
  page,
}) => {
  await page.getByRole("button", { name: "질문 · 피드백" }).click();
  await expect(
    page.getByText("피드백 도움말 · 일정 등록 AI와 별개입니다."),
  ).toBeVisible();
  await page.getByRole("button", { name: "기능 제안", exact: true }).click();
  await page.getByLabel("제목 (선택)").fill("중요한 할 일 추천");
  await page
    .getByLabel("어떤 상황에서 필요한 기능인가요?")
    .fill("아침에 중요한 할 일 세 개를 보고 싶어요.");
  await page.getByRole("button", { name: "피드백 저장하고 대화 열기" }).click();
  await expect(
    page.getByRole("dialog", { name: "중요한 할 일 추천" }),
  ).toBeVisible();
  await expect(
    page.getByText("아침에 중요한 할 일 세 개를 보고 싶어요.", { exact: true }),
  ).toBeVisible();
  await page
    .getByLabel("대화 이어쓰기")
    .fill("대기중인 일은 추천에서 제외해 주세요.");
  await page.getByRole("button", { name: "대화 저장", exact: true }).click();
  await expect(
    page.getByText("대기중인 일은 추천에서 제외해 주세요.", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "처리 기록", exact: true }).click();
  await page
    .getByRole("combobox", { name: "상태", exact: true })
    .selectOption("검토 중");
  await page.getByRole("button", { name: "처리 기록 저장" }).click();
  await expect(page.locator(".thread-meta").getByText("검토 중")).toBeVisible();
  await page.getByRole("button", { name: "닫기", exact: true }).click();
  await page.reload();
  await page.getByRole("button", { name: "개선 기록", exact: true }).click();
  await page.getByRole("button", { name: /중요한 할 일 추천/ }).click();
  await expect(
    page.getByText("대기중인 일은 추천에서 제외해 주세요.", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "닫기", exact: true }).click();
  await page.getByLabel("중요한 할 일 추천 전달 선택").check();
  await page.getByRole("button", { name: "전달 파일 (1)" }).click();
  await expect(
    page.getByRole("dialog", { name: "개발자 전달 내용 확인" }),
  ).toBeVisible();
  const preview = await page.locator(".export-preview").innerText();
  const exported = JSON.parse(preview);
  expect(exported.feedback).toHaveLength(1);
  expect(exported.feedback[0].messages).toHaveLength(4);
  expect(preview).not.toContain("침대 구매하기");
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "확인한 내용 내려받기" }).click();
  expect((await download).suggestedFilename()).toMatch(/여백-피드백-.*\.json/);
  await page.getByRole("button", { name: "닫기", exact: true }).click();
  await page.screenshot({
    path: "test-results/feedback-desktop.png",
    fullPage: true,
  });
});

test("문서 두 종류를 앱에서 읽고 내려받는다", async ({ page }) => {
  await page.getByRole("button", { name: "개발 현황", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "여백 · 사용자용 한 장" }),
  ).toBeVisible();
  await page.getByRole("button", { name: /개발용 상세 기록 구조/ }).click();
  await expect(
    page.getByRole("heading", { name: "여백 · 개발용 상세 기록" }),
  ).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "문서 내려받기" }).click();
  expect((await download).suggestedFilename()).toBe("개발용-상세기록.md");
  await page.screenshot({
    path: "test-results/docs-desktop.png",
    fullPage: true,
  });
});

test("휴대폰 크기에서 메뉴·캘린더·피드백을 사용할 수 있다", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator(".sidebar")).not.toBeVisible();
  await page.screenshot({
    path: "test-results/today-mobile.png",
    fullPage: true,
    animations: "disabled",
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.getByRole("button", { name: "메뉴 열기" }).click();
  await page
    .locator(".sidebar")
    .getByRole("button", { name: "캘린더", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "나의 시간, 나의 속도." }),
  ).toBeVisible();
  await page.getByRole("button", { name: "일정 추가" }).click();
  await page.getByLabel("제목", { exact: true }).fill("날짜만 정한 방문");
  await page.getByRole("button", { name: "저장", exact: true }).click();
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await expect(
    page.getByRole("button", { name: /날짜만 정한 방문 일정.*시간 미정/ }),
  ).toBeVisible();
  await page.getByRole("button", { name: "질문 · 피드백" }).click();
  await page.getByText("바로 확인하는 앱 사용 안내").click();
  await page.getByRole("button", { name: "오늘 하기와 마감일" }).click();
  await expect(page.locator(".guide-answer")).toContainText("마감일은 유지");
  await page
    .getByLabel("어떤 점이 궁금한가요?")
    .fill("여러 기기에서 쓰려면 어떻게 하나요?");
  await page.getByRole("button", { name: "피드백 저장하고 대화 열기" }).click();
  await expect(page.getByRole("dialog")).toContainText(
    "이 피드백 창은 자동 AI 답변을 제공하지 않습니다",
  );
  await page.screenshot({
    path: "test-results/conversation-mobile.png",
    fullPage: true,
  });
});

test("저장 실패 시 성공으로 표시하지 않고 작성 내용을 유지한다", async ({
  page,
}) => {
  await page.getByRole("button", { name: "질문 · 피드백" }).click();
  await page
    .getByLabel("어떤 점이 궁금한가요?")
    .fill("네트워크 실패 시 유지할 질문");
  await page.route("**/api/feedback", (route) =>
    route.request().method() === "POST"
      ? route.fulfill({
          status: 503,
          contentType: "application/json",
          body: JSON.stringify({ detail: "저장소 점검 중입니다." }),
        })
      : route.continue(),
  );
  await page.getByRole("button", { name: "피드백 저장하고 대화 열기" }).click();
  await expect(page.getByRole("alert")).toContainText("저장소 점검 중입니다.");
  await expect(page.getByLabel("어떤 점이 궁금한가요?")).toHaveValue(
    "네트워크 실패 시 유지할 질문",
  );
  await page.unroute("**/api/feedback");
  await page.getByRole("button", { name: "피드백 저장하고 대화 열기" }).click();
  await expect(
    page.getByRole("dialog", { name: "네트워크 실패 시 유지할 질문" }),
  ).toBeVisible();
});

test("대화에서 선택지를 고르고 승인한 뒤에만 일정이 저장된다 (AI 응답 모의)", async ({
  page,
}) => {
  await page.route("**/api/ai/status", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        active: "test-account",
        accounts: [
          {
            client_id: "test-account",
            label: "테스트용 모의 계정",
            connected: true,
            model: "test-model",
          },
        ],
      }),
    }),
  );
  await page.getByRole("button", { name: "대화로 등록", exact: true }).click();
  const turns: { content: string; request_id: string }[] = [];
  await page.route("**/api/conversations/*/turn", async (route) => {
    turns.push(route.request().postDataJSON());
    if (turns.length === 2)
      await route.fulfill({
        status: 503,
        json: { detail: "테스트 연결 실패" },
      });
    else await route.continue();
  });
  const before = await (await page.request.get("/api/items")).json();
  await page
    .getByLabel("일정 대화 입력")
    .fill("이번 주말 친구와 저녁 먹기로 했어");
  await page
    .getByRole("button", { name: "AI에게 보내기", exact: true })
    .click();
  await expect(
    page.getByText("식사 날짜를 골라 주세요", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("dialog", { name: "등록 전 확인" }),
  ).not.toBeVisible();
  expect(await (await page.request.get("/api/items")).json()).toHaveLength(
    before.length,
  );
  await page.getByRole("button", { name: "토요일", exact: true }).click();
  await page.getByRole("button", { name: "일요일", exact: true }).click();
  await page.getByRole("button", { name: "토요일", exact: true }).click();
  await page.getByRole("button", { name: "시간 미정", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "선택한 답변 한 번에 보내기" }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "장소 미정", exact: true }).click();
  expect(turns).toHaveLength(1);
  await page
    .getByRole("button", { name: "선택한 답변 한 번에 보내기" })
    .click();
  await expect(page.getByRole("alert")).toContainText("테스트 연결 실패");
  await expect(
    page.getByRole("button", { name: "토요일", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(
    page.getByRole("button", { name: "시간 미정", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await page
    .getByRole("button", { name: "선택한 답변 한 번에 보내기" })
    .click();
  await expect(
    page.getByRole("heading", { name: "친구와 저녁 식사", exact: true }),
  ).toBeVisible();
  expect(await (await page.request.get("/api/items")).json()).toHaveLength(
    before.length,
  );
  await page.getByRole("button", { name: "확인한 내용 등록" }).click();
  await expect(
    page.getByText("1개 등록 완료 · 받은함과 캘린더에서 확인하세요."),
  ).toBeVisible();
  expect(turns).toHaveLength(3);
  expect(turns[1]).toEqual(turns[2]);
  expect(turns[2].content).toContain("토요일");
  expect(turns[2].content).toContain("시간 미정");
  expect(turns[2].content).toContain("장소 미정");
  const items = await (await page.request.get("/api/items")).json();
  expect(items).toHaveLength(before.length + 1);
  const event = items.find(
    (i: { title: string }) => i.title === "친구와 저녁 식사",
  );
  expect(event.planned_date).toBe("2026-10-31");
  expect(event.start_time).toBeNull();
  await page.reload();
  await page.getByRole("button", { name: "대화로 등록", exact: true }).click();
  await page
    .getByRole("button", { name: /이번 주말 친구와 저녁 먹기로 했어/ })
    .click();
  await expect(
    page.getByText("1개 등록 완료 · 받은함과 캘린더에서 확인하세요."),
  ).toBeVisible();
});

test("AI 연결 진단 실패를 표시하고 재검사 성공을 로그인 성공과 구분한다", async ({
  page,
}) => {
  let checks = 0;
  await page.route("**/api/ai/diagnose", async (route) => {
    checks += 1;
    await route.fulfill({
      json:
        checks === 1
          ? {
              ok: false,
              message:
                "[TLS-CERT] ChatGPT 인증 서버 정보 확인: 서버 인증서를 검증하지 못했습니다.",
            }
          : {
              ok: true,
              message:
                "인증 서버의 공개 정보에 연결했습니다. 계정 로그인·토큰 교환·AI 응답 성공을 의미하지는 않습니다.",
            },
    });
  });
  await page.getByRole("button", { name: "대화로 등록", exact: true }).click();
  await page.getByRole("button", { name: "인증 서버 연결 확인" }).click();
  await expect(page.getByRole("alert")).toContainText("[TLS-CERT]");
  await page.getByRole("button", { name: "인증 서버 연결 확인" }).click();
  await expect(page.getByRole("alert")).toHaveCount(0);
  await expect(page.getByRole("status")).toContainText(
    "성공을 의미하지는 않습니다",
  );
  await expect(page.getByText("AI 미연결 ·", { exact: false })).toBeVisible();
});

test("오늘 하기와 삭제를 되돌리고 분류를 수정한다", async ({page}) => {
  await page.getByRole("button", {name:"받은함", exact:false}).first().click();
  await page.getByLabel("빠르게 할 일 추가").fill("되돌리기 확인용");
  await page.getByRole("button", {name:"추가", exact:true}).click();
  const row=page.locator("article.task-row").filter({hasText:"되돌리기 확인용"});
  await row.getByRole("button", {name:"오늘 하기", exact:true}).click();
  await page.getByRole("button", {name:"되돌리기", exact:true}).click();
  await expect(row.getByRole("button", {name:"오늘 하기", exact:true})).toBeVisible();
  await row.locator(".task-main").click();
  await page.getByLabel("분류", {exact:true}).selectOption("구매");
  await page.getByRole("button", {name:"저장", exact:true}).click();
  await expect(page.getByRole("heading", {name:"구매 · 1", exact:true})).toBeVisible();
  await row.locator(".task-main").click();
  await page.getByRole("button", {name:"삭제", exact:true}).click();
  await page.getByRole("button", {name:"삭제 확인", exact:true}).click();
  await expect(row).toHaveCount(0);
  await page.getByRole("button", {name:"되돌리기", exact:true}).click();
  await expect(row).toBeVisible();
});

test("피드백 전체 선택·해제와 확인 후 복사를 지원한다", async ({page}) => {
  await page.getByRole("button", {name:"개선 기록", exact:true}).click();
  await page.getByRole("button", {name:"현재 목록 전체 선택"}).click();
  const boxes=page.locator('.feedback-row input[type="checkbox"]');
  expect(await boxes.count()).toBeGreaterThan(0);
  for(const box of await boxes.all()) await expect(box).toBeChecked();
  await page.getByRole("button", {name:"전체 해제",exact:true}).click();
  for(const box of await boxes.all()) await expect(box).not.toBeChecked();
  await page.getByRole("button", {name:"현재 목록 전체 선택"}).click();
  await page.getByRole("button", {name:/전달 파일/}).click();
  await page.evaluate(() => Object.defineProperty(navigator, 'clipboard', {value:{writeText:async (text:string) => { (window as unknown as {copied:string}).copied=text; }},configurable:true}));
  await page.getByRole("button", {name:"개발 AI에 보낼 내용 복사"}).click();
  await expect(page.getByRole("status")).toContainText("아직 전달되지는 않았습니다");
  expect(await page.evaluate(() => (window as unknown as {copied:string}).copied)).toContain('personal-scheduler-feedback/v1');
});

test("선택한 피드백을 확인한 뒤 Codex 작업으로 보내고 중복을 막는다 (CLI 모의)", async ({page}) => {
  await page.getByRole("button", {name:"개선 기록",exact:true}).click();
  await page.getByLabel("Codex 환경 이름 또는 ID").fill("scheduler-test");
  await page.getByRole("button", {name:"연결 설정 저장",exact:true}).click();
  await page.getByRole("button", {name:"Codex 연결 확인",exact:true}).click();
  await expect(page.getByText("Codex 로그인과 환경 접근을 확인했습니다.",{exact:false})).toBeVisible();
  await page.getByRole("button", {name:"현재 목록 전체 선택"}).click();
  await page.getByRole("button", {name:/선택한 피드백 보내기 전 확인/}).click();
  const modal=page.getByRole("dialog",{name:"Codex 전송 내용 확인"});
  await expect(modal).toBeVisible();
  expect((await (await page.request.get('/test/codex-creates')).json()).count).toBe(0);
  await modal.getByRole('button',{name:'확인한 피드백 Codex로 보내기'}).click();
  await expect(modal).not.toBeVisible();
  await expect(page.getByRole('link',{name:'Codex 작업 열기'})).toHaveAttribute('href','https://chatgpt.com/codex/tasks/task_browser_test',{timeout:15000});
  await page.getByRole('button',{name:'작업 상태 확인',exact:true}).click();
  await expect(page.getByText('건 · 검토 완료',{exact:false})).toBeVisible();
  await page.getByRole("button", {name:/선택한 피드백 보내기 전 확인/}).click();
  await expect(modal.getByRole('button',{name:'확인한 피드백 Codex로 보내기'})).toBeDisabled();
  expect((await (await page.request.get('/test/codex-creates')).json()).count).toBe(1);
});
