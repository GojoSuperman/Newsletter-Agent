# AI 뉴스레터 에이전트 — 수집부터 발행까지

매일 아침 AI 뉴스를 **자동으로 모아서, 중요한 5건만 고르고, 3문장으로 요약하고, 요약이 원문과 맞는지 검사한 뒤, Discord로 보내주는** 에이전트입니다. 같은 파이프라인을 브라우저 대시보드에서 직접 돌리고 결과를 살펴볼 수도 있습니다. 운영 지표용 대시보드 외에, 잡지처럼 읽고 발송 여부를 직접 고르는 로컬 리더 앱도 함께 제공합니다.

모두의연구소 「에이전트 팀 꾸리기」 캠프의 *뉴스레터 에이전트 — 수집부터 발행까지* 수업을 그대로 구현한 프로젝트입니다. 수업이 제시한 다섯 단계, 설계 선택지, 검증 방법을 코드로 옮겼고, 그 위에 대시보드와 GitHub Actions 자동 실행을 얹었습니다.

```
 인터넷 뉴스 (RSS 7곳 + Hacker News API, 24시간 창, 약 20~120건)
      │
      ▼
 ① 수집   ── 시간 창 필터 · URL 중복 제거 · 죽은 소스 격리
      ▼
 ② 선별   ── 40건 묶음 예선 → 본선, 정확히 5건 (LLM)
      ▼
 ③ 취재   ── 원문 추출(trafilatura) → headline / summary / why 3칸 (LLM, 기사별 병렬)
      ▼
 ④ 검수   ── 요약이 원문에 근거하는지 LLM이 대조, 탈락 사유 기록
      ▼
 ⑤ 발행   ── Discord 웹훅 (dry_run이면 미리보기만, 이 단계에 LLM 없음)
```

---

## 목차

- [무엇을 하는가](#무엇을-하는가)
- [빠른 시작](#빠른-시작)
- [사용법](#사용법)
- [설계 — 수업의 결정을 그대로](#설계--수업의-결정을-그대로)
- [설정 파일 audience.yaml](#설정-파일-audienceyaml)
- [실행 기록과 지표](#실행-기록과-지표)
- [폴더 구조](#폴더-구조)
- [테스트](#테스트)
- [알려진 한계](#알려진-한계)
- [참고 문서](#참고-문서)

---

## 무엇을 하는가

| 단계 | 하는 일 | 핵심 규칙 |
|---|---|---|
| ① 수집 | `audience.yaml`의 소스 목록을 돌며 최근 N시간 기사를 모은다 | 소스 하나가 죽어도 나머지는 계속, 죽은 소스는 로그에 이름을 남긴다 |
| ② 선별 | 후보 전체를 서로 견주어 가장 중요한 5건을 고른다 | 40건씩 묶어 예선 → 본선. 당사자 발표(tier 1)는 상한 내에서 경쟁 면제. 건수는 코드가 강제 |
| ③ 취재 | 기사 원문을 가져와 세 칸으로 요약한다 | 원문 600자 미만이면 "본문 부족"으로 제외. `why`는 해석이라 검수 대상이 아님 |
| ④ 검수 | 요약의 headline·summary가 원문에 근거하는지 판정한다 | 번역·단위 환산은 허용, 원문에 없는 주장("업계 최초")은 탈락. 통과분만 발행 |
| ⑤ 발행 | Discord 채널에 임베드 카드로 보낸다 | dry_run이면 보내지 않고 미리보기. 0건이면 보내지 않음. 웹훅 실패는 예외 |

실제 실행 예시 (2026-09-14):

```
① 수집    24시간 창 · 23건 · 소스 8/8
② 선별    23 → 5건 · 본선만 · 면제 1
③ 취재    본문 부족 → 제외 · Hacker News · A.I. Slopware Is Everywhere Now...
③ 취재    완료 · AI타임스 · 아모데이 "AI 속도 조절 최대 난제는 중국과의 경쟁"
③ 취재    완료 · TechCrunch · 오바마, 인공지능 안전망 구축의 필요성 강조
③ 취재    완료 · OpenAI · Perplexity, GPT-6 Astra로 끝까지 신뢰할 수 있는 시스템
③ 취재    완료 · Hacker News · 버니 샌더스, ASI 개발자에게 20년 형량 제안
④ 검수    2/4 통과
   ✗ 탈락 · OpenAI · Perplexity, GPT-6 Astra로... · 업계 최초와 관련된 주장이 원문에 언급되지 않았다.
   ✗ 탈락 · Hacker News · 버니 샌더스... · 법안에 대한 구체적인 내용이나 지지 의사를 명시하는 부분이 원문에 없습니다.
⑤ 발행    Discord · 2건
```

---

## 빠른 시작

요구 사항: Python 3.14, [uv](https://docs.astral.sh/uv/), OpenAI API 키. Discord로 실제 발송하려면 웹훅 URL.

```bash
git clone https://github.com/GojoSuperman/Newsletter-Agent.git
cd Newsletter-Agent
uv sync

cp .env.example .env          # 아래 키를 채운다
uv run python run.py --hours 24 --dry-run     # 한 바퀴 돌려 보기 (Discord 미발송)
```

`.env`에 넣을 값:

| 키 | 필수 | 설명 |
|---|---|---|
| `OPENAI_API_KEY` | 예 | 선별·취재·검수 세 노드가 사용 |
| `OPENAI_MODEL` | 아니오 | 기본 `gpt-4o-mini` |
| `DISCORD_WEBHOOK_URL` | 실제 발송 시 | Discord 채널 설정 → 연동 → 웹후크 → URL 복사. `--dry-run`이면 없어도 됨 |

`.env`는 `.gitignore`에 있어 커밋되지 않습니다. 웹훅 URL은 비밀번호와 같으니 공유하지 마세요.

---

## 사용법

### 0. 리더 앱 — 버튼으로 만들고 잡지처럼 읽기 (권장)

```bash
uv run uvicorn app.server:app --port 8100     # http://127.0.0.1:8100
```

- 처음 열면 설정 패널이 뜹니다. OpenAI 키(필수)와 Discord 웹훅(선택)을 넣으면 `store/local/settings.json`에 저장됩니다. `.env`는 필요 없습니다.
- **▶ 오늘 치 만들기** → 수집·선별·취재·검수가 차례로 진행되고 끝나면 왼쪽 목록에 새 호가 생깁니다. Discord로는 보내지 않습니다.
- 본문의 **발행본 / 검수 탈락 / 수집 전체** 탭으로 그날 결과를 읽습니다.
- 마음에 들면 **Discord로 보내기**를 누릅니다. 한 호는 한 번만 보낼 수 있습니다.
- 기존 대시보드(`web/`, 포트 8000)는 운영 지표용으로 그대로 남아 있습니다.

바탕화면 바로가기: `scripts/windows/바로가기-만들기.ps1`을 PowerShell에서 실행하면 아이콘이 붙은 **AI 뉴스레터** 바로가기가 생깁니다. 더블클릭하면 WSL에서 서버를 켜고 앱 창(Edge/Chrome 앱 모드)을 띄우며, 그 창을 닫으면 서버도 꺼집니다. (WSL 배포판 이름이 `Ubuntu`가 아니면 `AI뉴스레터.bat` 안의 `-d Ubuntu`를 바꾸세요.)

### 1. 터미널에서 한 번 실행

```bash
uv run python run.py --hours 24 --dry-run   # Discord로 보내지 않음
uv run python run.py --hours 24             # 실제 발송
uv run python run.py --hours 48 --dry-run   # 수집 창을 48시간으로
```

다섯 줄의 단계별 로그를 출력하고, 결과 전체(`store/local/runs/<id>.json`)와 지표 한 줄(`store/local/metrics.jsonl`)을 남깁니다.

### 2. 대시보드에서 실행하고 살펴보기

```bash
uv run uvicorn web.app:app --port 8000
```

브라우저에서 http://127.0.0.1:8000 을 엽니다.

- **▶ 실행** — 지금 이 컴퓨터에서 파이프라인을 돌립니다. 노드가 끝날 때마다 로그가 실시간으로 흐르고, 끝나면 깔때기 숫자와 발행 카드가 채워집니다. `dry_run` 체크를 끄면 실제로 Discord에 보냅니다.
- **⟳ GitHub에서 가져오기** — 새로 돌리지 않고, GitHub Actions가 자동 실행해 커밋한 결과를 내려받습니다(`git pull`). 키를 쓰지 않습니다.
- **과거 실행** 표 — 실행마다 수집·선별·취재·추출률·검수·발행 건수와 실패 소스, 소요 시간. **출처** 열이 GitHub 자동 실행과 로컬 실행을 구분합니다. 실행 ID를 클릭하면 그날의 로그·카드·탈락 사유를 다시 볼 수 있습니다.
- **소스별 기여** — 최근 30회 발행 카드가 어느 매체에서 왔는지 막대로 보여 줍니다.

대시보드에는 로그인이 없습니다. 이 컴퓨터에서만 보는 용도이며, `127.0.0.1`에만 바인딩하세요. 외부에 열면 누구나 OpenAI 크레딧을 쓰고 Discord에 글을 올릴 수 있습니다.

### 3. GitHub Actions 수동 실행

`.github/workflows/daily.yml`은 자동 스케줄이 꺼져 있습니다. Actions 탭에서 수동으로만 돌릴 수 있습니다.

설정:

1. 저장소 → Settings → Secrets and variables → Actions
   - Secrets: `OPENAI_API_KEY`, `DISCORD_WEBHOOK_URL`
   - Variables(선택): `OPENAI_MODEL`
2. Actions 탭 → **daily-newsletter** → Run workflow에서 `dry_run`을 체크하고 한 번 수동 실행해 초록 체크를 확인합니다.
3. 이후로도 자동으로는 돌지 않습니다. Actions 탭에서 Run workflow를 눌러야 실행되며, 실행 기록은 봇이 `chore: 실행 기록 YYYY-MM-DD` 커밋으로 남깁니다.

실패하면 GitHub가 저장소 소유자에게 알림 메일을 보냅니다. 수업이 말한 "돌았는지 확인할 경로"입니다.

### 4. 소스 관문 검사 (소스를 추가·교체할 때)

```bash
uv run python -m newsletter.sources_check
```

소스마다 최근 기사 3건의 원문을 실제로 가져와 세 관문을 잽니다. 매일 돌리는 것이 아니라 소스를 채택할 때 한 번 돌립니다.

| 관문 | 뜻 | 기준 |
|---|---|---|
| G1 본문 | 요약을 쓸 재료가 뽑히는가 | 원문 600자 이상 (없으면 LLM이 제목만 보고 지어냄) |
| G2 생존 | 최근에도 글이 올라오는가 | 14일 내 건수 |
| G3 접근 | 자동 수집을 막지 않는가 | robots.txt 허용 여부 (우리 User-Agent로 확인) |

---

## 설계 — 수업의 결정을 그대로

수업은 단계마다 선택지를 늘어놓고 하나를 고른 뒤 "조건이 달라지면 다른 답이 맞다"고 강조합니다. 이 프로젝트는 그 선택을 그대로 따랐습니다.

| 갈림길 | 고른 것 | 버린 것과 이유 |
|---|---|---|
| 만드는 순서 | 빈 노드 5개로 뼈대를 먼저 세우고 하나씩 채움 | 부품을 다 만들고 조립하면 규격 불일치를 마지막 날 발견 |
| 수집 경로 | RSS (Hacker News는 공개 API) | 스크래핑은 유지보수 비용이 크고, 집계 서비스는 판단을 외주 주는 것 |
| 소스 채택 | 관문(G1·G2·G3) 통과 후 등급 | "괜찮아 보이는 곳"은 몇 달 뒤 아무도 설명 못 함 |
| 선별 구조 | 2단 상대평가 (예선 → 본선) | 개별 채점은 점수가 몰려 5건이 안 갈라지고, 전부 한 번에 넣으면 중간을 놓침 |
| 건수 강제 | 코드가 자름 (`[:pick_count]`) | "5개만 골라 줘"라는 부탁은 늘 지켜지지 않음 |
| 출력 구조 | headline / summary / why 세 칸 (Pydantic) | 한 덩어리로 받으면 어디까지가 사실이고 어디부터 해석인지 코드가 모름 |
| 검수 방식 | LLM에 요약과 원문을 함께 주고 근거 판정 | 숫자 문자열 대조는 "three months → 3개월" 같은 번역·단위 환산을 오탐 |
| 못 채우는 날 | 되돌아가지 않고 있는 만큼만 발행 | 규칙 하나가 재시도 설계 전체를 대신함 |
| 발행 경로 | Discord 웹훅, dry_run 먼저 | 되돌릴 수 없는 단계라 LLM을 넣지 않음 |
| 설정 위치 | `audience.yaml` | 프롬프트에 박아 두면 편집 방향을 정하는 사람이 못 고침 |

구현에서 지킨 원칙:

- **State에는 단계 사이를 건너가는 것만** 담고, 리듀서(`operator.add`)는 여러 워커가 동시에 쓰는 `drafted`와 모든 노드가 한 줄씩 남기는 `log`에만 붙입니다. 노드는 자기가 바꾼 키만 돌려줍니다.
- **조용한 실패 금지.** 결과물을 바꾸는 건너뜀(소스 실패, 본문 추출 실패, 검수 탈락)은 반드시 로그나 지표에 남깁니다. 날짜가 없는 항목 한 건이 빠지는 건 조용해도 됩니다.
- **노드는 의존성을 인자로 받는 순수 함수**입니다(`http_get`, `ask`, `extract`, `post`). `graph.py`가 `functools.partial`로 묶어 LangGraph에 등록하고, 테스트는 가짜를 꽂습니다. 그래서 76개 테스트가 네트워크·OpenAI·Discord를 한 번도 호출하지 않습니다.
- **③ 취재는 기사 수만큼 팬아웃**합니다(`Send`). 기사끼리 서로 볼 필요가 없기 때문입니다. ② 선별과 ④ 검수는 다른 항목을 봐야 답할 수 있어 펼치지 않습니다.
- **대시보드는 파이프라인을 호출만** 합니다. `newsletter/`는 화면이 있는지 모르고, GitHub Actions는 화면 없이 `run.py`만 부릅니다.

그래프는 `newsletter/graph.py`의 `build()`가 만들며, `collect → select → [report × N] → verify → publish`입니다. 선별 결과가 0건이면 취재를 건너뛰고 곧장 검수로 갑니다.

---

## 설정 파일 audience.yaml

분야마다 달라지는 내용은 전부 여기 있습니다. 코드에는 "AI 뉴스"가 박혀 있지 않아서, 이 파일만 바꾸면 채용 공고·논문·주식 뉴스레터로 옮길 수 있습니다.

```yaml
audience: 국내 AI 개발팀                      # 프롬프트에 들어가는 독자
question: 이번 주 우리가 일하는 방식이 바뀔 만한가   # 선별 기준
topics: [모델·API, 인프라·비용, 규제·정책, 오픈소스, 제품·서비스]
pick_count: 5           # 발행 목표 건수
tone: 간결한 존댓말. 과장 없이.
min_body: 600           # G1 관문. 원문이 이보다 짧으면 요약하지 않는다
shortlist_batch: 40     # 예선 한 묶음 크기
tier1_max: 2            # 당사자 발표(tier 1) 경쟁 면제 상한

sources:
  - {name: OpenAI,     url: https://openai.com/blog/rss.xml, tier: 1, kind: rss}
  - {name: TechCrunch, url: https://techcrunch.com/category/artificial-intelligence/feed/, tier: 2, kind: rss}
  - {name: Hacker News, url: "https://hn.algolia.com/api/v1/search_by_date?tags=story&query=AI", tier: 2, kind: hn}
```

- `tier: 1`은 사건의 당사자가 직접 발표하는 곳(공식 블로그)입니다. 매체 대여섯 곳이 같은 사건을 기사로 쓸 때 자리를 독점하지 않도록, 상한(`tier1_max`) 안에서 경쟁 없이 통과시키고 나머지는 경쟁에 참여합니다.
- `kind`는 `rss` 또는 `hn`(Hacker News Algolia API)만 허용합니다.
- 필수 키가 빠지거나 타입이 틀리면 **시작 시점에** `ConfigError`로 멈춥니다. 런타임에 터지지 않게 하기 위해서입니다.

---

## 실행 기록과 지표

실행마다 두 가지가 남습니다.

| 파일 | 내용 |
|---|---|
| `runs/<run_id>.json` | 최종 State 전체. 수집 목록, 선별 이유, 요약 3칸, 원문, 검수 통과분, 로그 |
| `metrics.jsonl` | 실행당 JSON 한 줄. 깔때기 숫자와 소요 시간 |

```json
{"run_id": "20260914T060133", "hours": 24, "collected": 23, "picked": 5, "drafted": 4,
 "extract_ok": 4, "verified": 2, "published": 2, "dead_sources": [],
 "by_source": {"AI타임스": 1, "TechCrunch": 1},
 "seconds": {"collect": 3.1, "select": 4.2, "report": 18.4, "verify": 6.0, "publish": 0.4},
 "dry_run": false}
```

이 숫자로 수업이 말한 "내린 결정을 재 보기"를 합니다. 본문 추출 성공률(`drafted/picked`)이 떨어지면 어떤 소스가 구조를 바꿨거나 차단을 시작한 것이고, 한 달 내내 `by_source`에 0건인 소스는 G2를 잃은 것입니다.

**저장 위치는 출처에 따라 둘로 나뉩니다.**

| 출처 | 경로 | 커밋 |
|---|---|---|
| GitHub Actions | `store/runs/`, `store/metrics.jsonl` | 봇이 매일 커밋·push |
| 이 컴퓨터 (대시보드·`run.py`) | `store/local/runs/`, `store/local/metrics.jsonl` | 안 됨 (gitignore) |

한 파일에 섞으면 `git pull` 때 로컬 기록이 덮어써지기 때문입니다. 대시보드는 두 곳을 합쳐 시각순으로 보여 주고, 출처 열로 구분합니다.

---

## 폴더 구조

```
Newsletter-Agent/
├─ newsletter/                 # 파이프라인. 화면과 무관
│  ├─ state.py                 # Brief(State) · Article · Pick · Draft · Verdict
│  ├─ config.py                # audience.yaml 로더 + 검증
│  ├─ llm.py                   # OpenAI 구조화 출력 헬퍼 (1회 재시도)
│  ├─ graph.py                 # build() · run_timed() · real_nodes() · merge_delta()
│  ├─ metrics.py               # summarize() · metrics.jsonl append/read
│  ├─ store.py                 # github / local 저장 경로 분리
│  ├─ sources_check.py         # 관문 G1·G2·G3 검사 CLI
│  └─ nodes/
│     ├─ collect.py            # ① 수집   (수업 섹션 5)
│     ├─ select.py             # ② 선별   (섹션 7)
│     ├─ report.py             # ③ 취재   (섹션 8)
│     ├─ verify.py             # ④ 검수   (섹션 9)
│     └─ publish.py            # ⑤ 발행   (섹션 10)
├─ app/                        # 리더 앱 (독자 화면, 포트 8100)
│  ├─ server.py                # FastAPI: 설정·호 목록·실행·Discord 발송 API
│  ├─ settings.py              # store/local/settings.json 로더·검증
│  └─ static/                  # index.html · app.js · style.css (프레임워크 없음)
├─ web/
│  ├─ app.py                   # FastAPI: /api/run(SSE) · /api/runs · /api/run/{id} · /api/config · /api/sync
│  └─ static/                  # index.html · app.js · style.css (프레임워크 없음)
├─ run.py                      # CLI 한 번 실행. Actions가 이것만 부른다
├─ audience.yaml               # 독자·기준·토픽·톤·소스
├─ store/                      # 실행 기록 (위 표 참고)
├─ tests/                      # pytest 76개, 네트워크 없음
├─ docs/superpowers/           # 설계 스펙과 구현 플랜
└─ .github/workflows/daily.yml # 매일 07:30 KST
```

### API

| 경로 | 역할 |
|---|---|
| `POST /api/run` `{hours, dry_run}` | 실행 예약, `run_id` 반환. 동시 실행 1개 제한 |
| `GET /api/run/{id}/events` | SSE. 노드가 끝날 때마다 `{node, update}`, 마지막에 `{node:"__end__", state}` |
| `GET /api/run/{id}` | 저장된 최종 State (GitHub → 로컬 순으로 찾음) |
| `GET /api/runs` | 두 출처의 지표를 합친 목록 (각 행에 `origin`) |
| `GET /api/config` | `audience.yaml` 내용 |
| `POST /api/sync` | `git pull --rebase --autostash` 실행, `{ok, output}` |

---

## 테스트

```bash
uv run pytest            # 76 passed
uv run pytest -v tests/test_select.py
```

모든 테스트가 네트워크·OpenAI·Discord 없이 돕니다. 노드가 의존성을 인자로 받기 때문에 가짜 RSS 바이트, 가짜 LLM 응답, 가짜 HTTP `post`를 꽂습니다. 검증하는 것의 예:

- 시간 창 밖·날짜 없는 항목 제외, `?utm=` 꼬리표 떼고 중복 제거, 죽은 소스 격리와 로그
- 예선 묶음 수, 본선에서 정확히 N건, LLM이 모르는 URL·초과분 무시, tier 1 면제 상한
- 원문 600자 미만이면 "본문 부족" 로그와 함께 제외, 팬아웃이 기사 수만큼 워커를 띄움
- 검수 프롬프트에 `why`가 들어가지 않음, 탈락 사유가 로그에 남음
- dry_run이면 HTTP 호출 0회, 0건이면 발송 안 함, 웹훅 URL 없으면 예외
- SSE 이벤트 순서, 저장 파일, 버려진 실행의 잠금 해제, `git pull` 실패가 예외가 아닌 응답으로 보고됨

---

## 알려진 한계

수업이 "다루지 않은 것"으로 남긴 부분과 운영하며 확인한 것입니다.

- **평가셋이 없습니다.** 같은 날 두 번 돌리면 선별·검수 결과가 다릅니다(LLM 비결정성). 프롬프트를 고쳤을 때 좋아졌는지는 기사 30~50건에 사람이 정답을 붙인 평가셋으로만 알 수 있습니다.
- **사람 승인 단계가 없습니다.** 검수를 통과하면 바로 발행합니다. 발행 전에 사람이 한 번 보려면 그래프를 멈췄다 재개하는 기능이 필요합니다.
- **모든 노드가 같은 모델을 씁니다.** 예선처럼 판단이 단순한 곳은 더 싼 모델로 내릴 수 있습니다.
- **스크래핑은 하지 않습니다.** RSS도 API도 없는 분야로 옮기려면 robots.txt 확인과 구조 변경 감지가 통째로 따라옵니다.
- **GitHub 러너에서 일부 사이트의 본문 추출이 실패합니다.** 로컬에서는 성공하는 기사가 러너에서는 "본문 부족"으로 빠지는 경우가 있습니다(러너 IP 차단으로 추정). `metrics.jsonl`의 추출률로 추적합니다.
- **검수 노드에서 LLM 호출이 실패하면 그날 실행이 실패합니다.** 건별로 조용히 탈락시키면 검수 없이 누락된 것을 알 수 없어 일부러 예외로 둡니다. Actions 알림으로 드러납니다.
- **대시보드와 리더 앱은 모두 로컬 전용**입니다. 인증이 없으니 외부에 열지 마세요.
- **리더 앱의 설정 파일(`store/local/settings.json`)에 API 키가 평문으로 저장됩니다.** 파일 권한은 600으로 제한하지만, 공용 컴퓨터에서는 쓰지 마세요.

---

## 참고 문서

- `docs/superpowers/specs/2026-09-14-newsletter-agent-design.md` — 설계 스펙 (범위, State, 노드 규칙, 화면, 에러 처리)
- `docs/superpowers/plans/2026-09-14-newsletter-agent.md` — 구현 플랜 (수업 순서대로 12개 태스크, TDD)
- Anthropic, [Building Effective Agents](https://www.anthropic.com/research/building-effective-agents) — 수업의 워크플로 패턴 출처
- [LangGraph](https://langchain-ai.github.io/langgraph/) · [feedparser](https://feedparser.readthedocs.io/) · [trafilatura](https://trafilatura.readthedocs.io/) · [Hacker News Algolia API](https://hn.algolia.com/api)

---

이 저장소는 Claude Code와 함께 만들었습니다. 설계·플랜·구현의 모든 결정은 `docs/superpowers/`와 커밋 이력에 남아 있습니다.
