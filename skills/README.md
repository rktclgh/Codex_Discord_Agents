# Codex Team Skills

이 폴더는 `Discord_Agents`가 전제로 삼는 역할별 Codex 팀 스킬 문서를 모아둔 곳입니다.

이 저장소의 에이전트 구조를 이해할 때 중요한 건 단순히 “어떤 채널이 어떤 역할로 연결되는가”만이 아닙니다.
실제로는 각 역할이:

- 무엇을 책임지는지
- 어떤 수준의 판단을 해야 하는지
- 어떤 방식으로 handoff 해야 하는지
- 어떤 기준으로 리뷰/보고해야 하는지

를 함께 알아야 전체 시스템이 제대로 이해됩니다.

그래서 역할별 스킬 문서를 이 저장소에 함께 포함했습니다.

## 포함된 역할

- `project-pm`
- `project-backend-lead`
- `project-backend-dev`
- `project-frontend-lead`
- `project-frontend-dev`
- `project-qa`
- `project-security-review`

## 역할별 요약

### PM

- 사용자 요구사항을 문제 정의로 재정리
- acceptance criteria 생성
- work packet 분해
- 역할별 상태 취합
- 최종 사용자 보고 책임

### Backend Lead

- 백엔드 설계/계약/API 경계 정의
- QA / Security 이슈를 백엔드 작업으로 변환
- Backend Dev 산출물 리뷰
- PM에 백엔드 상태 보고

### Backend Dev

- 리드가 분리한 백엔드 구현 작업 수행
- 지정된 범위 안에서 코드/테스트 작업
- 결과를 Backend Lead에게 반환

### Frontend Lead

- 프론트 구조/상태 경계/UX 영향 검토
- QA / Security 입력을 프론트 작업으로 변환
- Frontend Dev 산출물 리뷰
- PM에 프론트 상태 보고

### Frontend Dev

- 리드가 분리한 프론트 구현 작업 수행
- 지정된 범위 안에서 UI/API 연동 작업
- 결과를 Frontend Lead에게 반환

### QA

- 예측 가능한 장애 지점 발굴
- 재현 시나리오 및 회귀 포인트 정리
- defect packet 형태로 Lead에게 전달

### Security

- 공격면, 인증/인가, 검증, 노출 위험 검토
- 보안 이슈를 실행 가능한 조치 항목으로 정리
- Backend Lead / Frontend Lead에 handoff

## 왜 이 문서가 중요한가

다른 사람이 이 저장소를 볼 때 보통 이런 의문을 가집니다.

- 왜 PM이 단순 챗봇이 아니라 오케스트레이터처럼 동작하는가
- 왜 Backend 채널의 기본 수신자가 BE Lead인가
- 왜 QA와 Security가 직접 구현보다 리드에게 이슈를 넘기는가
- 왜 Lead가 검토 완료 후 커밋 흐름을 가진가

이 질문의 답은 전부 이 스킬 문서에 담겨 있습니다.

즉 이 폴더는 단순 참고자료가 아니라, 이 저장소의 협업 거버넌스를 설명하는 설계 문서이기도 합니다.

## 사용 팁

- 역할 동작을 바꾸고 싶으면 해당 스킬 문서부터 수정하는 것이 좋습니다.
- README와 코드만 바꾸면 시스템의 구조는 보이지만, 역할의 판단 기준까지는 전달되지 않을 수 있습니다.
- 공개 저장소 관점에서는 이 폴더가 “이 팀이 어떤 원칙으로 움직이는지”를 보여주는 역할을 합니다.
