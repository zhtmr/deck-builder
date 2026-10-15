# system-model.json 명세

장표의 모든 토폴로지·흐름 슬라이드는 이 파일 하나에서 그려진다. 예시는 `examples/recap/system-model.json`.

```jsonc
{
  "system": { "name": "Recap", "summary": "한 문장 설명", "repo": "경로", "generated_at": "YYYY-MM-DD" },
  "nodes": [
    {
      "id": "api",                 // 영문 소문자·숫자·하이픈. 다른 곳에서 참조하는 키
      "label": "API 서버",          // 장표 표기. 10자 안팎
      "kind": "service",           // 아래 표 중 하나 (모양·색 결정)
      "tech": "Spring Boot",       // 보조 표기. 20자 안팎
      "tier": 2,                   // 선택. 왼→오 열 번호(0부터). 레이아웃이 꼬일 때만 지정
      "evidence": ["api-server/src/.../UploadController.java:3"]  // 필수. 파일:라인
    }
  ],
  "edges": [
    {
      "id": "e-api-kafka",
      "from": "api", "to": "kafka",   // 요청(또는 메시지)이 나가는 방향
      "label": "stt.requested",       // 2~3단어. 토픽명·엔드포인트·프로토콜
      "protocol": "Kafka",            // HTTP | gRPC | SQL | Kafka | AMQP | S3 | SSE | WebSocket | Process | File ...
      "async": true,                  // 큐/이벤트/웹훅 등 비동기면 true → 점선 + 흐르는 애니메이션
      "evidence": ["api-server/.../UploadController.java:10"]
    }
  ],
  "flows": [
    {
      "id": "record-to-minutes",
      "title": "녹음에서 회의록까지",
      "description": "이 흐름이 보여 주는 설계 포인트 1~2문장",
      "steps": [
        { "edge": "e-web-nginx", "note": "무슨 일이 일어나는지 한 줄" },
        { "edge": "e-nginx-api", "note": "응답은 reverse:true 로 같은 간선을 거꾸로", "reverse": true }
      ]
    }
  ]
}
```

## kind

| kind | 언제 | 모양 |
|---|---|---|
| `client` | 브라우저, 모바일 앱, CLI, 데스크톱 앱(Tauri 등) | 둥근 사각형 |
| `gateway` | Nginx, API Gateway, 로드밸런서, BFF | 사각형 |
| `service` | 요청을 받는 서버 애플리케이션 | 사각형 |
| `worker` | 큐를 소비하는 백그라운드 처리기 | 사각형 |
| `job` | 스케줄/배치 작업, cron | 사각형 |
| `ai` | LLM API, 모델 서빙, 에이전트 런타임 | 육각형 |
| `queue` | Kafka, RabbitMQ, Redis Stream, SQS | 파이프 |
| `db` | RDB, NoSQL | 원통 |
| `cache` | Redis(캐시 용도), Memcached | 사각형 |
| `storage` | S3, MinIO, NAS, 파일 시스템 | 원통 |
| `external` | 외부 SaaS·사내 타 시스템(Slack, 결제, SSO) | 점선 사각형 |

## 추출 규칙 (system-explorer 용)

**노드가 되는 것** — 독립 배포 단위(compose 서비스, k8s Deployment, 별도 프로세스), 상태를 가진 인프라, 외부 시스템.
**노드가 아닌 것** — 클래스, 패키지, 모듈. 하나의 Spring Boot 앱 안의 컨트롤러·서비스 계층은 노드 하나다.
예외: 사용자가 "모듈 구조"를 강조해 달라고 했다면 모듈을 노드로 삼은 두 번째 모델 파일을 만든다.

**간선이 되는 것** — 실제 호출 코드가 있는 연결. 설정에만 있고 호출이 없는 연결은 넣지 않는다.

스택별로 확인할 곳:

| 스택 | 진입점 | 나가는 호출 | 설정 |
|---|---|---|---|
| Spring Boot | `@RestController`, `@*Mapping`, `@KafkaListener`, `@RabbitListener`, `@Scheduled` | `RestTemplate`, `WebClient`, `@FeignClient`, `KafkaTemplate.send`, JPA/MyBatis 매퍼 | `application*.yml`, `build.gradle` |
| FastAPI / Python | `@app.get`, `APIRouter`, Celery `@task`, 컨슈머 루프 | `httpx`, `requests`, `boto3`, `anthropic`/`openai`, `subprocess` | `.env*`, `settings.py`, `pyproject.toml` |
| Node / TS | Express/Nest 라우트, Next API route | `fetch`, `axios`, SDK 클라이언트, `EventSource` | `package.json`, `.env*` |
| Tauri / 데스크톱 | `#[tauri::command]`, 프런트 `invoke()` | `Command::new` (R·Python 스크립트 실행), 파일 I/O | `tauri.conf.json` |
| 인프라 | `docker-compose*.yml`, k8s, Dockerfile `CMD` | `depends_on`, 환경변수의 호스트명 | — |

**흐름(flows) 고르는 법** — 발표에서 말하고 싶은 설계 포인트가 드러나는 흐름 1~3개. 대표 사용자 시나리오 하나는 반드시 포함. 한 흐름의 단계는 12개 이하(넘으면 두 흐름으로 쪼갠다). 각 단계 `note` 는 "무엇을 왜"를 25자 안팎으로.

**근거(evidence)** — 모든 노드·간선에 최소 1개. 직접 Read 로 열어 확인한 라인만 적는다. 추측으로 넣은 연결은 `"evidence": []` 로 두고 `"inferred": true` 를 붙인다(장표에는 넣지 않거나 "추정" 표기).
