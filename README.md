# 🏀 DJ-KBL-bot (프로농구 카카오톡 챗봇 MVP)

KBL(한국프로농구) 실시간 경기 정보, 오늘의 경기 일정, 그리고 **Daum 스포츠 연동 구단별/맞대결 일정 검색(`#KT vs LG`)** 기능을 제공하는 카카오톡 챗봇 백엔드 시스템입니다.

---

## ✨ 주요 기능

1. **오늘의 KBL 경기 조회 (`POST /integrations/kakao/skills/today-games`)**
   - KST(`Asia/Seoul`) 기준 당일 예정·진행 중·종료 경기 목록 및 경기장 정보 제공
2. **구단 맞대결 및 팀 일정 검색 (`POST /integrations/kakao/skills/match-search`)**
   - `#KT vs LG`, `#정관장vs소노`, `#현대모비스` 등 KBL 10개 전 구단 약칭/정식명칭 인식
   - Daum 스포츠 3단계 Fallback(ARMS API → Hermes API → Daum 통합검색 파싱) 연동
3. **실시간 스코어 조회 (`POST /integrations/kakao/skills/live-score`)**
   - 수집(`IngestionWorker`)과 조회(Redis Snapshot Read Path)를 완전 분리하여 카카오 5초 타임아웃(SLA) 보장
4. **보안 및 장애 내성**
   - 카카오 `botUserKey` 평문 미저장: `HMAC-SHA256` 인덱스 + `AES-256-GCM`(AAD 바인딩) 암호화
   - 모든 카카오 스킬 요청에 대해 예외·검증 오류 발생 시에도 **HTTP 200 OK + 안내 말풍선** 반환 보장
5. **VPS + Cloudflare Tunnel 원클릭 배포**
   - 방화벽 포트(80/443/5432/6379) 외부 노출 없이 Cloudflare Tunnel로 즉시 HTTPS 연동

---

## 📂 디렉터리 구조

```text
DJ-KBL-bot/
├── 프로농구봇_MVP_PRD_기술설계_v1.1.pdf
└── kbl-bot/
    ├── docker-compose.yml
    ├── Dockerfile
    ├── requirements.txt
    ├── .env.example
    ├── main.py
    ├── deploy/
    │   ├── setup_vps.sh
    │   └── deploy.sh
    ├── core/
    │   ├── config.py
    │   ├── logging.py
    │   ├── exceptions.py
    │   ├── security/crypto.py
    │   ├── db/{models.py, session.py}
    │   └── cache/redis.py
    ├── services/
    │   ├── provider/{interface.py, daum.py, mock.py}
    │   ├── search/parser.py
    │   ├── game/service.py
    │   ├── user/service.py
    │   └── ingestion/worker.py
    ├── apps/kakao/
    │   ├── schemas.py
    │   ├── builder.py
    │   └── router.py
    └── tests/
        ├── test_crypto.py
        ├── test_daum_and_search.py
        ├── test_kakao_builder.py
        └── test_provider.py
```

---

## 🚀 빠른 시작 (VPS / Docker Compose)

```bash
cd kbl-bot

# 1. Ubuntu VPS 초기 세팅 (Docker + 2GB Swap + UFW + .env 시크릿 자동 생성)
sudo ./deploy/setup_vps.sh

# 2. Cloudflare Quick Tunnel로 즉시 HTTPS 기동 및 카카오 오픈빌더 URL 발급
sudo ./deploy/deploy.sh --quick
```

---

## 🧪 테스트 실행

```bash
cd kbl-bot
pytest
```
