# Mobius

집단 온라인 공격의 확산 신호를 탐지하고, 설명 가능한 위험도·증거 패키지·대응 가이드를 제공하는 웹 서비스입니다.

## 구조

- `apps/web`: Next.js 대시보드 (피해자 보호 / B2B 역할별 화면 분리)
- `apps/api`: FastAPI API, 인증·인가, 모델 추론, 증거 패키징
- `services/workers`: 수집·분석·PDF 생성 비동기 워커
- `services/ml`: 학습·평가·백테스트 코드
- `data/synthetic`: 개인정보가 없는 재구성 시연 데이터
- `data/raw`, `data/processed`: 학습용 공개 데이터셋(Git 미포함, [DATASET_LICENSES.md](docs/DATASET_LICENSES.md) 참고)
- `artifacts`: 학습된 모델 체크포인트·평가 로그

## 구현된 기능

1. Google OAuth / 데모 로그인 후 JWT 세션 발급, 초대 기반 역할·조직 부여, 조직별(tenant) 데이터 격리(RBAC).
2. synthetic replay 이벤트 또는 YouTube·NAVER Search 공식 API [커넥터](docs/CONNECTOR.md)로 이벤트를 공통 데이터 계약으로 수집.
3. 언급 증가율·플랫폼 간 확산·유해성·협조 행동 의심 신호를 0~1로 정규화해 가중합 위험도·단계·근거·대응 가이드를 산출.
4. `artifacts/text-classifier*`에 학습 모델이 있으면 KLUE-RoBERTa 유해성 확률과 K-MHaS 기반 멀티라벨 공격 유형 분류를 위험도 입력으로 사용하고, 없으면 규칙 기반 fallback으로 동작.
5. 이미지 OCR·perceptual hash 유사도로 밈 재유포를 탐지하고(멀티모달), 영상은 확장 계약으로 시뮬레이션.
6. Neo4j에 계정·대상·해시태그 temporal graph를 증분 저장해 클러스터·중심성·동시성 기반 협조 행동 신호를 시각화.
7. 위험 단계 진입 시 이메일 알림(쿨다운·묶음 처리)을 발송하고 PostgreSQL에 알림·감사 이력을 영속화.
8. 각 이벤트 SHA-256과 패키지 해시를 포함하는 PDF·JSON 증거 ZIP을 생성, 다운로드 이력을 감사 로그로 기록.
9. 웹 대시보드에서 피해자 보호/B2B 관점을 전환해 시연.

## API

FastAPI가 실행되면 Swagger UI는 `http://localhost:8000/docs`에서 확인할 수 있습니다.

| 영역 | 주요 엔드포인트 |
| --- | --- |
| 시스템 | `GET /health`, `GET /v1/model-status` |
| 인증 | `GET /v1/me`, `GET /v1/auth/providers`, `POST /v1/auth/demo-login`, `GET /v1/auth/login/{provider}`, `GET /v1/auth/callback/{provider}`, `POST /v1/admin/invitations` |
| 대상/이벤트 | `GET·POST /v1/targets`, `GET /v1/targets/{id}/monitoring-rule`, `POST /v1/targets/{id}/events:ingest`, `GET /v1/targets/{id}/events`, `GET /v1/targets/{id}/events/ingested` |
| 커넥터 | `GET /v1/connectors/{youtube,naver-search}/status`, `POST /v1/targets/{id}/connectors/{youtube,naver-search}/sync` |
| 위험도/대시보드 | `GET /v1/dashboard`, `GET /v1/targets/{id}/risk`, `GET /v1/targets/{id}/attack-types` |
| 그래프 | `GET /v1/targets/{id}/graph` |
| 멀티모달 | `POST /v1/analyze-image`, `POST /v1/analyze-video` |
| 증거 | `GET /v1/targets/{id}/evidence-manifest`, `GET /v1/targets/{id}/evidence-package`, `GET /v1/targets/{id}/evidence/history` |
| 알림 | `GET /v1/targets/{id}/alerts`, `GET /v1/targets/{id}/alerts/history`, `GET /v1/targets/{id}/notifications/history` |
| 감사/개인정보 | `GET /v1/audit-logs`, `GET /v1/retention-policy` |

## 로컬 실행

1. Docker Desktop을 실행한 뒤 `docker compose up --build`로 API·PostgreSQL·Redis·Neo4j를 시작합니다.
2. Node.js 환경에서 `npm.cmd install` 후 `npm.cmd run dev:web`로 웹 대시보드를 시작합니다.
3. Google OAuth·SMTP·YouTube/NAVER API 키는 `.env`(→ `.env.example` 참고)에 설정하면 실제 로그인·발송·수집으로 전환되며, 미설정 시 동일 인터페이스가 시뮬레이션으로 동작합니다.

API 상태 확인: `http://localhost:8000/health`

## 문서

- [PROJECT_REPORT.md](docs/PROJECT_REPORT.md): 문제정의·해결방안·결론(평가 결과 포함) 종합 보고서
- [EVALUATION.md](docs/EVALUATION.md): 모델 평가·백테스트 수치와 재현 방법
- [OPERATIONS.md](docs/OPERATIONS.md): 운영·보안·한계 정책
- [DATASET_LICENSES.md](docs/DATASET_LICENSES.md): 학습 데이터 출처·라이선스
- [CONNECTOR.md](docs/CONNECTOR.md): YouTube·NAVER Search 공식 API 커넥터 사용법
