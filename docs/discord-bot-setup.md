# Discord Bot 설정 가이드

이 문서는 `Codex Discord Agents`를 처음 설치하는 사람이 Discord 봇을 직접 만들고, 채널 ID를 복사하고, `.env`를 채우고, `tmux` 런타임까지 올릴 수 있도록 설명하는 빠른 가이드입니다.

## 1. Python 의존성 설치
```bash
./scripts/install_agent_team_deps.sh
```

이 명령은 로컬 `.venv`를 만들고 `discord.py`를 설치합니다.

## 2. Discord 봇 만들기

### 2-1. 앱 생성

1. [Discord Developer Portal](https://discord.com/developers/applications) 에 접속합니다.
2. `New Application`을 누릅니다.
3. 앱 이름을 입력하고 생성합니다.

### 2-2. Bot 추가

1. 왼쪽 메뉴에서 `Bot`으로 이동합니다.
2. `Add Bot`을 눌러 봇을 추가합니다.
3. 생성된 Bot Token은 잠시 뒤 `.env`에 넣습니다.

### 2-3. Message Content Intent 활성화

1. 같은 `Bot` 화면에서 아래쪽 `Privileged Gateway Intents`를 찾습니다.
2. `MESSAGE CONTENT INTENT`를 켭니다.
3. 저장합니다.

이 프로젝트는 채널의 자연어 메시지를 읽어야 하므로 이 설정이 필수입니다.

### 2-4. 서버 초대 링크 만들기

1. `OAuth2` -> `URL Generator`로 이동합니다.
2. `Scopes`에서 아래를 체크합니다.
   - `bot`
   - `applications.commands`
3. `Bot Permissions`에서 최소 아래 권한을 체크합니다.
   - `View Channels`
   - `Send Messages`
   - `Read Message History`
4. 필요하다면 아래도 추가합니다.
   - `Create Public Threads`
   - `Send Messages in Threads`
5. 생성된 URL로 봇을 서버에 초대합니다.

## 3. Discord 개발자 모드 켜기

1. Discord 앱 `사용자 설정`으로 이동합니다.
2. `고급` 메뉴를 엽니다.
3. `개발자 모드`를 켭니다.

이제 채널 우클릭이나 사용자 우클릭 시 `ID 복사`가 보입니다.

## 4. 채널 만들기

권장 채널:

- `#라우터`
- `#pm`
- `#백엔드`
- `#프론트엔드`
- `#qa`
- `#보안`

## 5. 로컬 env 파일 생성
```bash
cp .agent_team.env.example .agent_team.env
```

아래 값을 채워 넣습니다.

- `DISCORD_BOT_TOKEN`
- `DISCORD_ROUTER_CHANNEL_ID`
- `DISCORD_PM_CHANNEL_ID`
- `DISCORD_BACKEND_CHANNEL_ID`
- `DISCORD_FRONTEND_CHANNEL_ID`
- `DISCORD_QA_CHANNEL_ID`
- `DISCORD_SECURITY_CHANNEL_ID`
- `DISCORD_OWNER_USER_ID`
- `AGENT_TEAM_WORKSPACE_ROOT`

채널 ID는 각 채널 우클릭 -> `ID 복사`로 가져옵니다.

오너 사용자 ID도 본인 프로필 우클릭 -> `ID 복사`로 가져옵니다.

`AGENT_TEAM_WORKSPACE_ROOT`에는 실제로 작업할 프로젝트 루트 경로를 넣습니다.

예:

```env
AGENT_TEAM_WORKSPACE_ROOT=/Users/your-name/Desktop/MyRealProject
```

이 값을 설정해야 각 역할 에이전트가 해당 프로젝트의 `AGENTS.md`, 코드, 스크립트, git 상태를 기준으로 움직입니다.

선택값:
- `DISCORD_CHANNEL_ID`: fallback 용 기본 PM 채널
- `DISCORD_BE_LEAD_CHANNEL_ID` 같은 세부 override 채널 ID
- `AGENT_TEAM_USE_CODEX_EXEC=1`: 각 역할이 실제 `codex exec`를 사용하도록 설정
- `AGENT_TEAM_CODEX_TIMEOUT_SECONDS=120`: 역할별 응답 생성 타임아웃
- `AGENT_TEAM_CODEX_PERMISSION_MODE=danger-full-access`: 권한 질의 없이 넓은 권한으로 Codex 세션 실행

## 6. tmux 팀 세션 재생성
```bash
./scripts/start_agent_team_tmux.sh --recreate
```

이 명령을 실행하면:

- `.agent_team.env`를 읽고
- `.venv/bin/python`을 사용하고
- Discord 설정값이 있으면 자동으로 Discord 모드로 올라갑니다

맥을 계속 켜둬야 외부에서 Discord로 작업을 시킬 수 있습니다. 잠자기 방지는 아래 스크립트로 켜고 끌 수 있습니다.

```bash
./scripts/agent_team_awake_on.sh
./scripts/agent_team_awake_off.sh
./scripts/agent_team_awake_status.sh
```


## 7. 첫 테스트

`#pm`에서 아래처럼 테스트할 수 있습니다.

```text
!task 모바일 결제 콜백 테스트
```

그다음 아래를 확인합니다.

- router window
- PM window
- logs window

`!task` 없이 자연어로도 바로 대화할 수 있습니다.

- `#pm`: 일반 메시지가 PM 요청 또는 기존 task 후속 대화로 처리됩니다.
- `#router`: 일반 메시지가 PM 진입점으로 들어가고, 답변도 같은 채널로 돌아옵니다.
- `#backend`: 일반 메시지가 기본적으로 `BE Lead`에게 들어갑니다.
- `#frontend`: 일반 메시지가 기본적으로 `FE Lead`에게 들어갑니다.
- `#qa`: 일반 메시지가 `QA`에게 들어갑니다.
- `#security`: 일반 메시지가 `Security`에게 들어갑니다.

자연어 요청을 보내면 먼저 "요청 확인 / 처리 중" 메시지가 올라오고, 처리 완료 후 최종 응답이 이어서 올라옵니다.

## 8. 지원 명령어
```text
!task <title>
!handoff <task_id> <from_role> <to_role> <message>
!scope <task_id> <path> [path...]
!review-done <task_id> <commit_message>
!status
!status <task_id>
!roles
!health
!help
```

`!review-done`은 리드 채널용 명령입니다.
- `#백엔드` / `#프론트엔드`에서 리드가 검토 완료를 선언할 때 사용합니다.
- 자동 커밋은 해당 task의 `write_scope`에 등록된 파일만 대상으로 합니다.
- `write_scope`가 없으면 커밋하지 않고 `!scope` 사용 안내를 반환합니다.

## 9. 현재 동작 방식
- 각 역할의 outbox 메시지는 매핑된 Discord 채널로 다시 전송됩니다.
- `#router` 채널은 다른 채널에서 올라온 역할 업데이트도 `Router Feed` 형태로 함께 받아서, 교차 역할 협업 상황을 한 곳에서 볼 수 있습니다.
- 역할 응답이 `[주의]`, `[차단]`, `[리스크]`로 시작하면, 설정된 오너 계정을 원래 채널과 `Router Feed` 양쪽에서 멘션합니다.
- PM이 최종 응답을 보낼 때는 오너 멘션을 함께 붙일 수 있습니다.
- 공용 채널도 지원합니다.
  - `backend` 채널: 기본적으로 `BE Lead`가 사용자 메시지를 받고, `BE Lead`와 `BE Dev`가 모두 이 채널로 응답할 수 있습니다.
  - `frontend` 채널: 기본적으로 `FE Lead`가 사용자 메시지를 받고, `FE Lead`와 `FE Dev`가 모두 이 채널로 응답할 수 있습니다.
- 자연어 메시지에 기존 `TASK-...` ID를 같이 적으면, 해당 역할이 그 task 맥락을 이어서 대화합니다.

## 10. 한계와 주의사항
- `AGENT_TEAM_USE_CODEX_EXEC=1`이면 각 역할 runner가 로컬 `codex exec`를 직접 호출합니다.
- 각 역할은 자기 Codex `session_id`를 저장하고 이후 메시지를 `codex exec resume`으로 이어가므로, 역할별 장기 대화 맥락을 유지할 수 있습니다.
- 기본 권한 모드는 `danger-full-access`라 권한 질의는 줄어들지만, 그만큼 PM/lead 역할이 무리하거나 위험한 요청을 먼저 걸러야 합니다.
- 현재 지속성은 `task별`이 아니라 `역할별`입니다. 즉 `PM`, `BE Lead`, `QA`는 자기 대화 맥락을 기억하지만, task마다 별도 세션을 자동 생성하지는 않습니다.
- 다음 단계 업그레이드는 `task별 persistent session` 또는 깊은 조사 작업을 위한 `fork` 기반 하위 스레드입니다.

## 11. 보안 주의사항

- `.agent_team.env`는 절대 커밋하지 마세요.
- Discord Bot Token이 노출되면 바로 `Reset Token`으로 교체하세요.
- 오너 사용자 ID, 채널 ID는 공개되어도 보통 큰 문제는 아니지만, 토큰은 비밀번호와 같은 수준으로 관리해야 합니다.
