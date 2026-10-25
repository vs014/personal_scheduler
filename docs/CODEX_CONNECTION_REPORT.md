# Codex 웹 환경과 CLI 환경 목록 불일치 — 문의 자료

## 현재 상태

여백 0.2.7의 피드백 클라우드 전송은 환경 접근 단계에서 막혀 있습니다.
사용자가 보내 준 화면과 공식 공개 소스를 근거로 작성했습니다.
실제 사용자 계정의 웹/CLI 계정 식별자나 서버 내부 상태는 개발 세션에서 검증하지 못했습니다.

- Windows에서 여백을 실행합니다. 내장 공식 Codex CLI 버전은 0.164.0입니다.
- 사용자는 웹과 CLI에 같은 ChatGPT 계정으로 로그인했고 개인용 작업공간이라고 확인했습니다.
- Codex 웹 환경 목록에 `personal_scheduler`가 보입니다. 연결 저장소는 `vs014/personal_scheduler`, 공유 상태는 비공개입니다.
- CLI 로그인 상태 확인은 `Logged in using ChatGPT`로 성공했습니다.
- 환경 이름을 지정한 조회는 `no cloud environments are available for this workspace`로 실패합니다.
- 환경 필터 없는 작업 목록 조회는 성공했고 조회된 작업은 0건입니다.
- 클라우드 작업 생성 성공은 확인되지 않았습니다. 앱은 전송 성공으로 표시하지 않습니다.

## 지원팀 전달용 영문

Subject: Codex environment visible on web, but Codex CLI 0.164.0 returns an empty environment catalog

I use a personal ChatGPT workspace on Windows. The Codex web environment list shows an environment named `personal_scheduler`, connected to `vs014/personal_scheduler` (private visibility). I selected the same ChatGPT account when signing into the CLI.

My local application invokes the official Codex CLI 0.164.0 as follows:

```text
codex -c forced_login_method="chatgpt" login status
codex -c forced_login_method="chatgpt" cloud list --limit 20 --json --env personal_scheduler
codex -c forced_login_method="chatgpt" cloud list --limit 20 --json
```

Observed results:

1. Login status succeeds: `Logged in using ChatGPT`.
2. The environment-filtered command fails: `no cloud environments are available for this workspace`.
3. The unfiltered task-list command succeeds and returns an empty tasks array.

The application has not confirmed any successful cloud task creation. It does not extract browser cookies or tokens or call a custom/private HTTP endpoint; it invokes the official CLI. The account/workspace identifiers behind the web and CLI sessions have not been independently compared.

Could you confirm whether this web environment is expected to be visible to `codex cloud` for this account/workspace, and investigate the empty environment catalog or advise the supported connection method? Please also clarify any environment-type or account eligibility restrictions.

The public npm `latest` version was checked during this investigation and was 0.164.0. The tagged source resolves both names and IDs only after fetching the environment catalog, and fails immediately when the catalog is empty. Consequently, changing the environment input to an ID would not bypass this failure.

## 공식 근거

- CLI 환경 해석 소스: https://github.com/openai/codex/blob/rust-v0.164.0/codex-rs/cloud-tasks/src/lib.rs#L203
- CLI 환경 목록 조회 소스: https://github.com/openai/codex/blob/rust-v0.164.0/codex-rs/cloud-tasks/src/env_detect.rs
- 공개 배포 버전: https://registry.npmjs.org/@openai/codex/latest

## 취급 및 다음 단계

이 문서는 문의 초안이며 지원팀에 자동 전송되지 않았습니다.
OpenAI 도움말(https://help.openai.com)의 지원 문의에 영문 내용을 사용할 수 있습니다.
비밀번호·인증 코드·로그인 리디렉션 주소·토큰·auth.json은 첨부하지 않습니다.
이 사례가 서비스 장애인지, 환경 종류/연결 경로의 차이인지, 계정 매핑 문제인지는 아직 미확정입니다.
반복 로그인·환경 삭제/재생성·이름 변경·보안 검증 해제를 해결책으로 안내하지 않습니다.
현재 앱의 선택 피드백 복사/파일 내보내기는 임시 전달 방법으로 유지됩니다.
