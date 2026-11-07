# Architecture

Galaxy → USB/ADB → 공식 Android Auto DHU는 수동 테스트 환경입니다. 별도 FastAPI 서비스가 ADB 상태와 Logcat을 읽고 SQLite 세션에 연결합니다. Logcat 원본과 DB는 로컬 `results/`에만 보관합니다. API는 로그를 파싱하고 마스킹한 뒤 Vue 대시보드에 전달합니다. AI 진단에는 최대 50개 경고·오류 이벤트(없으면 앞 30개)만 전송하며, Pydantic 구조 검증과 근거 ID 검증을 거칩니다. API 키가 없으면 규칙 기반으로 처리합니다.

DHU 프로세스 실행 여부를 연결 성공으로 추정하지 않습니다. 화면 출력과 포커스, 주행 제한 등은 사용자가 관찰해 기록합니다. 경고 로그만으로 장애를 판정하지 않습니다.
