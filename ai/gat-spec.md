# gat (God of All Tools) Spec

`gat`은 파이썬 기반의 Configuration Management Tool로, Chef나 Ansible과 유사하지만 단일 파이썬 파일과 YAML 설정을 통해 더욱 단순하고 직관적인 조작을 지향합니다.

## 1. 프로그램 개요
- [x] 목적: 서버 환경 설정(Setup), 애플리케이션 배포(Deploy), 로컬 개발 서버 구동(Serve) 및 테스트(Test) 자동화.
- [x] 특징: 
  - [x] 명세와 실행 스크립트의 통합 (`gat_app.py`, `gat_my.py` 등).
  - [x] SSH, Docker, Podman을 통한 원격 및 컨테이너 내부 실행 지원.
  - [x] Capistrano 방식의 배포 전략 (releases/shared/current 구조).
  - [x] 소스 변경 감지 및 자동 재시작 (Watchdog 이용).

## 2. 주요 구성 요소
### 2.1 Conn (Connection)
- [x] 실행 대상(Local, Remote SSH, Container)에 대한 추상화 계층.
- [x] 주요 메서드:
  - [x] `run(cmd)`: 명령어 실행.
  - [x] `runOutput(cmd)`: 명령어 실행 후 결과(stdout) 반환.
  - [x] `uploadFile(src, dest)`, `downloadFile(src, dest)`: 파일 전송.
  - [x] `makeFile(content, path)`: 원격지에 파일 생성.
  - [x] `configLine(path, regexp, line)`: 설정 파일의 특정 라인 수정 (Regex).
  - [x] `configBlock(path, marker, block)`: 마커를 이용한 설정 블록 관리.
  - [x] `containerConn(name)`: 현재 연결을 통해 컨테이너 내부 연결 생성.

### 2.2 Main (Task Orchestrator)
- [x] 각 커맨드에 따른 작업 흐름 제어.
- [x] 작업 종류:
  - [x] `taskSetup`: 서버 기초 환경 설정.
  - [x] `taskDeploy`: 애플리케이션 배포.
  - [x] `taskServe`: 로컬 개발 서버 구동.
  - [x] `taskTest`: 유닛 테스트 실행.

### 2.3 Config & Helper
- [x] `gat.yml` 및 파이썬 내 정의된 설정 로드.
- [x] Helper 객체를 통해 `setupTask`, `deployTask` 등에서 유틸리티 기능 제공.

## 3. 동작 흐름
### 3.1 초기화 (init)
- [x] `gat init app` 또는 `gat init sys` 명령어로 기본 템플릿 파일 생성.

### 3.2 개발 및 테스트 (serve, test)
- [x] 1. 지정된 패턴의 파일 변경을 감시 (Watchdog).
- [x] 2. 변경 발생 시 구동 중인 프로세스 종료 후 재시작.
- [x] 3. `buildTask` -> `runTask` (또는 `test.cmd`) 순으로 실행.

### 3.3 설정 (setup)
- [x] 1. 대상 서버/컨테이너 접속.
- [x] 2. `setupTask`에 정의된 로직 수행 (패키지 설치, 설정 파일 수정 등).
- [x] 3. `gatHelper.py`를 원격지에 배포하여 복잡한 설정 작업을 보조.

### 3.4 배포 (deploy)
- [x] 1. 로컬에서 `buildTask` 수행.
- [x] 2. 배포 전략(zip, git 등)에 따라 소스 준비.
- [x] 3. 원격지에 `releases/YYYYMMDD_HHMMSS` 폴더 생성 및 업로드.
- [x] 4. `shared` 폴더와 심볼릭 링크 연결.
- [x] 5. `current` 심볼릭 링크를 최신 릴리스로 교체.
- [x] 6. `deployPostTask` 실행.

## 4. 특수 기능
- [x] Multi-hop Execution: SSH로 접속한 서버 내의 Docker/Podman 컨테이너 내부로 명령 전달.
- [x] S3 Integration: AWS S3로부터 파일 리스트 조회 및 다운로드 지원.
- [x] OS Abstraction: Ubuntu, CentOS, macOS 등을 감지하고 패키지 매니저(apt, yum) 호출 추상화.
- [x] Sudo Password handling: `sudo`가 필요한 명령 실행 시 비밀번호 입력 및 `ASKPASS`를 통한 자동화 지원.