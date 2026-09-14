# 뉴스레터 에이전트 프로젝트 설계

> 모두의연구소 「뉴스레터 에이전트 — 수집부터 발행까지」 수업을 그대로 구현하고, 그 위에 웹 대시보드를 얹는다.
> 결정된 것: OpenAI · AI 뉴스 · Discord + 대시보드 · GitHub Actions 포함 · FastAPI + 순수 HTML/JS.

---

## 1. 목표와 범위

**목표**: 브라우저에서 [실행] 버튼을 누르면 수집 → 선별 → 요약 → 검수 → 발행 다섯 단계가 돌고, 각 단계의 결과와 지표가 화면에 보인다. 같은 파이프라인이 매일 아침 GitHub Actions로 자동 실행되어 Discord로 발행된다.

**원칙**: 교재 코드(`newsletter/`)와 화면 코드(`web/`)를 분리한다. 화면은 교재 파이프라인을 "부르기만" 하고, 교재 파이프라인은 화면이 있는지 모른다. GitHub Actions는 화면 없이 `run.py`만 돌린다.

**범위에 넣는 것**
- 수업 섹션 2~13의 코드 전부 (State, 노드 5개, 관문 검사, 예선·본선, 3칸 스키마, LLM 대조 검수, Discord 웹훅, dry_run, metrics.jsonl, audience.yaml)
- 대시보드: 실행 버튼, 실시간 로그, 단계별 결과 카드, 깔때기 숫자, 과거 실행 목록, dry_run 토글
- GitHub Actions 매일 07:30 KST 실행

**범위에서 빼는 것** (수업도 "다루지 않은 것"으로 명시)
- 평가셋·회귀 검사, 발행 전 사람 승인, 단계별 모델 분리, 스크래핑, 로그인, DB

---

## 2. 폴더 구조

```
Newsletter-Agent/
├─ newsletter/                 # 교재 코드. 화면과 무관
│  ├─ __init__.py
│  ├─ state.py                 # Brief(State) · Article · Pick · Draft · Verdict 타입
│  ├─ sources.py               # SOURCES 목록 + 관문 검사(G1·G2·G3) 도구
│  ├─ nodes/
│  │  ├─ collect.py            # ① 수집   (섹션 5)
│  │  ├─ select.py             # ② 선별   (섹션 7, 예선→본선)
│  │  ├─ report.py             # ③ 요약   (섹션 8, 본문추출 + 팬아웃)
│  │  ├─ verify.py             # ④ 검수   (섹션 9, LLM 대조)
│  │  └─ publish.py            # ⑤ 발행   (섹션 10, Discord + dry_run)
│  ├─ graph.py                 # build() · run()  (섹션 2)
│  ├─ config.py                # audience.yaml 로더 + 검증 (섹션 13)
│  ├─ metrics.py               # store/metrics.jsonl append/read (섹션 12)
│  └─ llm.py                   # OpenAI 클라이언트 + 구조화 출력 헬퍼
├─ web/
│  ├─ app.py                   # FastAPI
│  └─ static/
│     ├─ index.html
│     ├─ app.js
│     └─ style.css
├─ run.py                      # CLI 한 번 실행 (Actions·터미널용)
├─ audience.yaml               # 독자·기준·토픽·톤
├─ store/                      # metrics.jsonl · runs/<id>.json (gitignore)
├─ tests/                      # pytest
├─ .github/workflows/daily.yml
├─ requirements.txt
├─ .env.example
└─ README.md
```

수업은 `graph.py` 한 파일에 다 넣지만, 노드를 파일로 나누는 게 유일한 차이다. 노드 하나가 한 파일이면 "섹션 N = 파일 하나"로 대응이 더 잘 보인다.

---

## 3. 파이프라인 (교재 그대로)

### State
```python
class Brief(TypedDict):
    hours: int
    dry_run: bool
    collected: list[Article]                 # ①
    picked:    list[Pick]                    # ②
    drafted:   Annotated[list[Draft], add]   # ③ 팬아웃 워커가 합침
    verified:  list[Draft]                   # ④ 통과분
    log:       Annotated[list[str], add]
```
리듀서는 수업대로 `drafted`·`log`에만 붙인다.

### 노드별 책임

| 노드 | 입력 → 출력 | 핵심 규칙 (수업) |
|---|---|---|
| collect | hours → collected | RSS(2칸) + HN API(1칸). 시간 창, URL 중복 제거, 소스 실패 격리 + 로그(조용한 실패 방지) |
| select | collected → picked | 40건 묶음 예선 → 본선. Pydantic으로 정확히 N건 강제. tier 1(당사자 발표) 경쟁 면제, 상한 있음 |
| report | picked → drafted | trafilatura 본문 추출(600자 미만이면 탈락 기록). Send로 기사별 팬아웃. 출력 headline/summary/why 3칸 |
| verify | drafted → verified | LLM에 요약+원문 주고 근거 판정. headline·summary만 검사, why는 제외. 미달이면 재시도 없이 통과분만 |
| publish | verified → log | dry_run이면 미리보기만. 아니면 Discord 웹훅. 이 노드에 LLM 없음 |

### 팬아웃
수업 섹션 8대로 `report`는 `Send`로 기사 수만큼 워커를 띄운다. 그래프는 `select → [report × N] → verify`.

### 지표 (metrics.jsonl 한 줄)
```json
{"run_id":"2026-09-14T07:30","collected":104,"picked":5,"drafted":5,
 "extract_ok":4,"verified":4,"published":4,"dead_sources":["DeepMind"],
 "by_source":{"TechCrunch":2,"AI타임스":2},"seconds":{"collect":3.1,"report":18.4},
 "dry_run":false}
```

### audience.yaml
```yaml
audience: "국내 AI 개발팀"
question: "이번 주 우리가 일하는 방식이 바뀔 만한가"
topics: [모델·API, 인프라·비용, 규제·정책, 오픈소스]
pick_count: 5
tone: "간결한 존댓말"
sources:
  - {name: OpenAI, url: ..., tier: 1}
  - {name: TechCrunch, url: ..., tier: 2}
```
로드 시 필수 키·타입을 검증해 오타를 시작 시점에 잡는다 (수업이 지적한 YAML 약점 보완).

---

## 4. 대시보드

### 화면 (한 페이지)
```
┌─────────────────────────────────────────────────┐
│ AI 뉴스레터 에이전트        [dry_run ☑] [▶ 실행] │
├────────────────┬────────────────────────────────┤
│ 깔때기          │ 실시간 로그                     │
│ 수집 104        │ ① 수집  24시간 창 · 104건       │
│ 선별   5        │ ② 선별  104 → 5건               │
│ 추출   4        │ ③ 취재  5건 (본문 실패 1)       │
│ 검수   4        │ ④ 검수  4/5 통과               │
│ 발행   4        │ ⑤ 발행  dry_run · 4건           │
├────────────────┴────────────────────────────────┤
│ 발행 카드 ×4  (headline / summary / why / 출처)  │
│   검수 탈락 1건은 회색 + 사유 표시                │
├─────────────────────────────────────────────────┤
│ 과거 실행 (metrics.jsonl 표) · 소스별 기여 · 추출률│
└─────────────────────────────────────────────────┘
```

### API
| 경로 | 역할 |
|---|---|
| `POST /api/run` | 실행 시작. body `{hours, dry_run}`. run_id 반환. 동시 실행 1개 제한 |
| `GET /api/run/{id}/events` | SSE. 노드가 끝날 때마다 `log`·중간 State를 흘림 |
| `GET /api/runs` | metrics.jsonl 전체 |
| `GET /api/run/{id}` | 해당 실행의 최종 State (`store/runs/<id>.json`) |
| `GET /api/config` | audience.yaml 내용 (읽기 전용) |

실시간 로그는 LangGraph `stream(mode="updates")`를 그대로 SSE로 넘긴다. 별도 큐·워커 없음.

### 프론트
프레임워크 없는 HTML + `app.js` + `style.css`. `EventSource`로 로그 수신, `fetch`로 나머지. 차트는 CSS 막대로 충분하니 라이브러리 없음.

---

## 5. 자동 실행

`.github/workflows/daily.yml`: cron `30 22 * * *`(UTC = 07:30 KST). `run.py --hours 24`를 돌리고 `store/metrics.jsonl`을 커밋해 되돌려 push(실행 기록이 저장소에 쌓임). 키는 `OPENAI_API_KEY`·`DISCORD_WEBHOOK_URL` Secrets. 실패 시 Actions 자체 알림에 맡긴다(수업의 "돌았는지 확인할 경로").

---

## 6. 에러 처리

- 소스 1곳 실패 → 격리, `dead_sources`에 기록, 계속 진행
- 본문 추출 실패 → 그 기사만 탈락, `extract_ok`에 반영
- LLM 호출 실패 → 해당 노드에서 1회 재시도 후 예외. 대시보드는 로그에 에러 표시, Actions는 실패 종료
- 검수 통과 0건 → 발행 건너뛰고 로그. Discord에는 안 보냄
- Discord 웹훅 실패 → 예외. 발행은 되돌릴 수 없는 단계라 조용히 넘기지 않음

---

## 7. 테스트

- `tests/test_graph.py`: 빈 노드 뼈대가 한 바퀴 도는지 (섹션 2)
- `tests/test_collect.py`: 고정 RSS 샘플로 시간 창·중복 제거·소스 실패 격리
- `tests/test_select.py`: 가짜 LLM 응답으로 예선→본선 건수, N건 강제
- `tests/test_verify.py`: 가짜 판정으로 통과/탈락 분기, why 미검사
- `tests/test_publish.py`: dry_run이면 HTTP 호출 없음
- `tests/test_config.py`: audience.yaml 필수 키 누락 시 시작 실패
- `tests/test_api.py`: FastAPI TestClient로 /api/runs·/api/config
- 실제 네트워크·OpenAI는 테스트에서 호출하지 않는다 (monkeypatch)

---

## 8. 구현 순서 (수업 순서 그대로)

| 단계 | 산출물 | 수업 섹션 |
|---|---|---|
| 0 | 저장소 초기화, requirements, .env.example, audience.yaml 초안 | 1 |
| 1 | State + 빈 노드 5개 + build/run + run.py → "0건 5줄" 출력 | 2 |
| 2 | 대시보드 뼈대: 실행 버튼 + SSE 로그 (빈 노드 로그가 화면에 흐름) | — |
| 3 | collect 채우기 + 관문 검사 스크립트 | 3~5 |
| 4 | select 채우기 (예선·본선, Pydantic) | 6~7 |
| 5 | report 채우기 (본문 추출, 팬아웃, 3칸) | 8 |
| 6 | verify 채우기 (LLM 대조) | 9 |
| 7 | publish 채우기 (dry_run, Discord) + 대시보드 카드 | 10 |
| 8 | GitHub Actions | 11 |
| 9 | metrics.jsonl + 대시보드 깔때기·과거 실행 | 12 |
| 10 | audience.yaml 분리 + config 검증 | 13 |

단계 2를 일찍 두는 이유: 수업의 "첫날부터 도는 물건" 원칙을 화면에도 적용해, 이후 노드를 채울 때마다 화면 숫자가 0에서 벗어나는 걸 눈으로 본다.

---

