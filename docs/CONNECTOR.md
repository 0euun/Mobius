# YouTube 공식 API Connector

`POST /v1/targets/{target_id}/connectors/youtube/sync`

```json
{
  "query": "브랜드X",
  "max_videos": 3,
  "max_comments_per_video": 30
}
```

YouTube 공개 영상 검색 결과의 최신 영상과 게시된 댓글만 가져온다. 댓글 비활성화 영상은 건너뛰며, 결과는 `events:ingest`와 동일하게 tenant별 마스킹 이벤트로 저장된다. API quota와 YouTube 정책을 준수하도록 소량 동기화부터 사용한다.

# NAVER Search 공식 API Connector

`POST /v1/targets/{target_id}/connectors/naver-search/sync`

```json
{
  "query": "브랜드X",
  "sources": ["news", "blog", "cafearticle"],
  "display": 20
}
```

지원 소스는 `news`, `blog`, `cafearticle`, `kin`, `webkr`이다. API HUB의 `X-NCP-APIGW-API-KEY-ID`, `X-NCP-APIGW-API-KEY` 인증 방식을 사용한다. 검색 결과의 제목·설명·발행 시각·링크를 확산 신호 이벤트로 저장하며, 원문 페이지를 무단 수집하지 않는다.
