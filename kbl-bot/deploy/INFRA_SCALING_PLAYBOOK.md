# 🚀 KBL봇 1,000명 동시 접속(Burst) 대응 인프라 확장 플레이북

> **현재 상태**: 🟢 **준비 완료 (Dry-Run 대기 모드)** — 현재 운영 중인 OCI 프로덕션 서버(`168.110.6.240`)는 건드리지 않고, 추후 트래픽 증가 시 **명령어 한 줄로 즉시 적용**할 수 있도록 모든 스크립트와 설정 템플릿을 준비해 두었습니다.

---

## 1. 트래픽 규모별 단계적 실행 로드맵 ($0 무과금 유지)

```mermaid
flowchart LR
    P0["현재 상태 (Phase 0)<br/>활성 1,000명 / 동시 클릭 ~200명"] --> P1["1단계: 소프트웨어 튜닝<br/>DB 풀 확장 & uvloop 최적화"]
    P1 --> P2["2단계: 인그레스 제한 해제<br/>Cloudflare 정식 터널 / Caddy HTTPS"]
    P2 --> P3["3단계: OCI 무료 ARM 확장<br/>A1.Flex (4 OCPU / 24GB RAM)"]
```

| 단계 | 실행 시점 (Trigger) | 예상 소요 시간 | 추가 비용 | 핵심 효과 |
| :---: | :--- | :---: | :---: | :--- |
| **1단계** | 채널 친구 **500명 돌파** 또는 경기일 피크타임 진입 전 | **약 1분** | **$0 (무료)** | DB 커넥션 풀 `30 → 75` 확장, 읽기 전용 요청 DB 커밋 생략, Uvicorn `uvloop`+`httptools` 적용 |
| **2단계** | 1초 내 동시 클릭 **200건 초과** (`HTTP 429` 발생 시) | **약 5분** | **$0 (무료)** | `trycloudflare.com` 임시 터널의 200 동시 요청 제한 완전 해제 |
| **3단계** | 채널 친구 **5,000명 이상** 대규모 시즌/플레이오프 | **약 15분** | **$0 (OCI Always Free)** | `VM.Standard.E2.1.Micro`(1GB) → `VM.Standard.A1.Flex`(4 OCPU / 24GB RAM) 무료 전환 및 멀티 워커(4 Workers) 가동 |

---

## 2. 단계별 즉시 실행 명령어 (One-Command Runbook)

### ✅ 사전 점검 (언제든 안전하게 실행 가능 — 서버 변경 없음)
```bash
cd /Users/dj/Desktop/DJ-KBL-bot/kbl-bot
python3 deploy/scale_up_1000_users.py --check
```

---

### ⚡ [1단계] 소프트웨어 고성능 튜닝 즉시 적용 (추후 실행용)
[`core/db/session.py`](file:///Users/dj/Desktop/DJ-KBL-bot/kbl-bot/core/db/session.py)의 커넥션 풀 확장(`pool_size=25, max_overflow=50`), 읽기 전용 캐시 히트 요청의 불필요한 `session.commit()` 생략, [`Dockerfile`](file:///Users/dj/Desktop/DJ-KBL-bot/kbl-bot/Dockerfile)의 `uvloop`/`httptools` 적용을 자동으로 수행합니다.

```bash
# 1. 로컬 코드에 고성능 튜닝 패치 자동 적용
python3 deploy/scale_up_1000_users.py --apply

# 2. OCI 실서버에 반영 및 컨테이너 재시작
scp -i ~/Downloads/ssh-key-2026-10-31.key core/db/session.py ubuntu@168.110.6.240:/tmp/session.py
ssh -i ~/Downloads/ssh-key-2026-10-31.key ubuntu@168.110.6.240 \
  "sudo docker cp /tmp/session.py kbl_api:/app/core/db/session.py && sudo docker restart kbl_api"
```

---

### 🌐 [2단계] 인그레스 200 동시 연결 제한 해제 (추후 실행용)
`trycloudflare.com` Quick Tunnel의 200 동시 요청 제한을 해제하기 위한 **Cloudflare Named Tunnel 설정(`cloudflared_config.yml`)**, **Caddy 직접 HTTPS 설정(`Caddyfile`)**, **PostgreSQL `max_connections=200` 튜닝 SQL(`postgres_1000_users.sql`)**이 `deploy/ingress_ready/` 폴더에 자동 생성됩니다.

```bash
# 설정 파일 일괄 생성
python3 deploy/scale_up_1000_users.py --generate-ingress --domain kblbot.yourdomain.com

# PostgreSQL max_connections=200 확장 적용 시 (OCI 서버)
scp -i ~/Downloads/ssh-key-2026-10-31.key deploy/ingress_ready/postgres_1000_users.sql ubuntu@168.110.6.240:/tmp/
ssh -i ~/Downloads/ssh-key-2026-10-31.key ubuntu@168.110.6.240 \
  "sudo docker exec -i kbl_postgres psql -U postgres -f /tmp/postgres_1000_users.sql && sudo docker restart kbl_postgres"
```

---

### 📊 [벤치마크] 동시 접속 부하 테스트 실행 (추후 검증용)
카카오 스킬 2.0 표준 페이로드로 100~1,000건의 동시 요청을 발생시켜 `p50`, `p95`, `p99` 응답 지연시간과 카카오 5초 SLA(`5,000ms`) 통과 여부를 실측합니다.

```bash
# OCI 서버 내부 로컬호스트 대상 500 동시 요청 벤치마크 예시
python3 deploy/scale_up_1000_users.py --benchmark --concurrency 500 --url http://127.0.0.1:8000
```
