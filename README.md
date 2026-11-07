# AI-Assisted IVI Phone Connectivity Validation & Diagnostics

실제 Android Auto Desktop Head Unit(DHU)와 USB 연결된 스마트폰의 테스트를 기록하는 개발자용 PoC입니다. DHU 및 차량 무선 스택을 구현하지 않습니다. 관찰 결과와 AI 추론을 구분합니다.

## 백엔드 실행

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

API 문서: http://127.0.0.1:8000/docs. `ADB_PATH`가 비어 있으면 Windows 기본 SDK 위치를 찾습니다. OpenAI를 쓰려면 `backend/.env`의 `OPENAI_API_KEY`를 입력하세요. 키가 없으면 규칙 기반 분석으로 동작합니다. `OPENAI_MODEL` 기본값은 `gpt-6-luna`이며 사용 가능 여부는 계정에 따라 다릅니다. 분석 버튼을 누를 때만 API가 호출됩니다.

## 프론트엔드 실행

```powershell
cd frontend
npm install
npm run dev
```

http://127.0.0.1:5173 에 접속합니다. 백엔드와 프론트엔드를 각각 실행해야 합니다.

## 실제 테스트 절차

1. `scripts/check-device.ps1`로 ADB 상태를 확인합니다. 화면에는 장치 식별자를 노출하지 않습니다.
2. DHU가 필요하면 `scripts/start-dhu.ps1`을 실행합니다. DHU 프로세스 존재는 연결 성공 판정이 아닙니다.
3. 대시보드에서 테스트 케이스를 선택하고 **세션 시작**을 누릅니다.
4. **Logcat 시작**을 누른 다음 DHU에서 해당 테스트를 수동 수행합니다. 연결 해제·재연결은 직접 수행합니다. DHU에서 지원하는 명령은 설치된 DHU의 도움말/공식 문서를 확인하세요.
5. **Logcat 중지**, 실제 결과와 PASS/FAIL/BLOCKED를 기록합니다. 관찰하지 않은 테스트는 NOT_RUN으로 둡니다.
6. **로그 통계**에서 세션별 로그량, 분당 추이, 경고·오류 상위 태그와 연결·오디오·화면 관련 이벤트를 확인합니다. **로그 탐색**에서 마스킹된 이벤트 ID를 확인한 뒤 필요하면 **진단 실행**을 누릅니다. 원본 다운로드는 로컬 민감정보가 포함될 수 있으므로 대시보드는 마스킹된 로그만 내려받습니다.
7. 보고서 탭에서 Markdown을 생성합니다. 스크린샷은 `results/screenshots/`에 로컬로 보관하고 메모에 파일명을 기록합니다.

장치가 분리되면 수집기는 중지됩니다. 다시 연결한 뒤 새 세션을 시작하세요. 수집 로그와 세션 DB는 `results/`에 저장되며 Git에서 제외됩니다.

짧은 실기기 수집 검증은 저장소 루트에서 `python scripts/smoke-live.py`로 실행할 수 있습니다. 새 TC-01 세션을 `NOT_RUN`으로 만들고 2초간 Logcat을 수집하며 테스트 PASS/FAIL 판정은 하지 않습니다.

TC-03 오디오 포커스 검증 기록은 `docs/test-report.md`에 있습니다. `scripts/tc03-focus.dhu`와 `scripts/run-tc03-focus.ps1`은 DHU의 공식 `focus audio off/on` 명령을 실행하고 단계별 화면을 저장한 시험용 스크립트입니다. 사용자의 청취 확인을 통해서만 오디오 중단·복구를 판정하세요. 이번 실기기 실행에서는 스크립트 종료 때 DHU가 비정상 종료되어 일반 실행으로 다시 띄웠습니다. 창이 열려 있다는 사실만으로 연결 복구를 확정할 수 없으므로 화면과 콘솔의 연결 성공 표시를 확인하세요.

마스킹은 이메일, 전화번호, 주요 장치 식별자 등의 일반적 패턴에 적용됩니다. 예외적인 개인정보가 남을 수 있으므로 로그를 외부로 공유하거나 OpenAI 진단을 실행하기 전에 내용을 확인하세요.

로그 통계는 원본 파일의 파싱 가능한 모든 줄을 집계하고, 연결·오디오·화면 이벤트는 명시한 태그와 문구로 분류합니다. 수치는 장애 판정이 아닙니다. AI 진단은 테스트 종류에 맞는 관련 이벤트를 파일 끝까지 탐색해 최대 50건과 요약 통계만 전송합니다. 기존에 저장한 AI 결과는 자동으로 재분석하지 않으며, 새 입력 기준을 적용하려면 해당 세션에서 다시 진단해야 합니다. 재실행은 OpenAI API 비용이 발생할 수 있습니다.

PT 자료용 화면은 **AI 진단 → 세션 선택 → 발표용 보기**에서 엽니다. 왼쪽에 실제 세션 로그의 분당 막대 그래프와 집계, 오른쪽에 저장된 AI 분석을 한 화면에 표시합니다. `adb forward --list`, `off/on`, `gain` 등 주요 명령과 용어에는 화면에서 한국어 설명이 붙습니다. 브라우저를 16:9 크기로 열어 화면을 캡처하면 됩니다. 사용자 판정과 AI 가설을 함께 보이되, 로그 건수를 장애 건수로 설명하지 마세요.

## 테스트

```powershell
cd backend
python -m pytest -q
```

테스트는 ADB와 OpenAI를 Mock으로 처리하며 API 크레딧을 사용하지 않습니다. 실제 DHU 조작과 테스트 판정은 수동 검증이 필요합니다.

## 범위

- 연결 장치 조회, 테스트 세션/결과, Logcat 시작/중지, 마스킹된 로그 탐색, 규칙/LLM 진단, Markdown 보고서
- DHU 화면과 Android Auto 연결 성공은 사용자가 관찰해 기록합니다. ADB 로그만으로 Android Auto 내부 연결 상태나 차량 Bluetooth/Wi-Fi 호환성을 확정하지 않습니다.

설계와 테스트 시나리오: [architecture.md](docs/architecture.md), [test-plan.md](docs/test-plan.md).
