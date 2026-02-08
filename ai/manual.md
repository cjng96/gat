# gat Configuration Python 파일 작성 가이드

`gat`은 파이썬 파일(`gat_app.py`, `gat_my.py` 등) 내에 설정과 실행 로직을 통합하여 관리합니다. 이 문서는 해당 파일을 작성하는 상세 방법과 API를 안내합니다.

## 기본 구조

모든 `gat` 설정 파일은 `myGat` 클래스를 포함해야 합니다.

```python
class myGat:
    def __init__(self, helper, **_):
        # 1. YAML 설정 로드
        helper.configStr("yaml", """
name: my-app
type: app
servers:
  - name: dev
    host: 192.168.0.10
    id: ubuntu
    deployRoot: /home/ubuntu/my-app
""")

    # 필요한 테스크 메서드들을 오버라이드합니다.
```

## 커멘드라인
- -v: 상세 로그 지원

## 설정 값 상세 (YAML Reference)

`helper.configStr("yaml", ...)`에 사용되는 주요 설정값 목록입니다.

### 최상위 설정 (Root Level)
- `name`: (string, 필수) 프로젝트 이름. 배포 시 파일명이나 식별자로 사용됩니다.
- `type`: (string, 필수) `app` (애플리케이션) 또는 `sys` (시스템 설정).
- `cmd`: (list 또는 string) 기본 실행 커맨드. `getRunCmd`를 오버라이드하지 않을 경우 사용됩니다. (기본값: `./{name}`)
- `defaultVars`: (dict) 모든 서버에서 공통으로 사용할 변수들.
- `servers`: (list) 대상 서버들의 목록.
- `deploy`: (dict) 배포 관련 상세 설정.
- `serve`: (dict) `gat serve` 실행 시의 동작 설정.
- `test`: (dict) `gat test` 실행 시의 동작 설정.
  - `cmd`: (list) 테스트 실행 커맨드.
- `s3`: (dict) AWS S3 관련 설정 (S3 연동 기능 사용 시).
  - `key`: AWS Access Key.
  - `secret`: AWS Secret Key.

### 서버 설정 (servers)
- `name`: (string, 필수) 서버 식별자. `gat <name> deploy` 명령 시 사용됩니다.
- `host`: (string, 필수) 접속 주소 (IP 또는 도메인). `port`가 0이면 로컬 연결로 간주합니다.
- `id`: (string, 필수) SSH 접속 사용자 ID.
- `port`: (int, 기본값: 22) SSH 접속 포트.
- `keyFile`: (string) SSH 개인키 경로.
- `pw`: (string) 접속 비밀번호 (비권장, keyFile 사용 권장).
- `deployRoot`: (string, 배포 시 필수) 서버 내 배포가 이루어질 루트 경로.
- `owner`: (string) 배포된 파일의 소유자(User)를 지정합니다. 지정 시 배포 후 해당 사용자로 `chown` 및 `chmod 775`를 수행합니다.
- `vars`: (dict) 해당 서버 전용 변수들. `defaultVars`와 병합됩니다.
- `dkName` / `ctrName`: (string) 도커/컨테이너 이름. 지정 시 모든 명령이 해당 컨테이너 내부에서 실행됩니다.
- `dkId` / `ctrId`: (string) 컨테이너 내부에서 명령을 실행할 사용자 ID 또는 컨테이너 ID.
- `gitBranch`: (string) `git` 전략 사용 시 배포할 브랜치명.

### 배포 설정 (deploy)
- `strategy`: (string, 필수) 배포 방식. `zip` (로컬 빌드 후 압축 전송) 또는 `git` (서버에서 직접 git clone).
- `include`: (list) 배포에 포함할 파일/디렉토리 패턴.
  - 리스트 요소는 경로 다음중 하나
    - string: 폴더 경로(예: `.`(하위호환을 위해 `*`도 지원됨), `bin`) 혹은 파일 경로
      - deployRoot + src path가 dest가 된다.(out/a -> deployRoot/out/a)
      - glob지원 안됨
    - object: 대상 경로 변경을 위한 개체 `{ src: "local/folder", target: "remote/targetFolder" }` 형태
      - 파일 하나만 지정도 지원된다. 이때 dest에 파일명까지 적어야한다.
      - 단 target path는 deployRoot하위 패스다. 절대 패스 지원 안함
- `exclude`: (list) 배포에서 제외할 패턴.
- `sharedLinks`: (list) `shared` 디렉토리에 생성되고 각 릴리스에서 심볼릭 링크로 연결될 파일/디렉토리 목록. (예: `logs`, `config/database.json`)
- `maxRelease`: (int, 기본값: 5) 서버에 유지할 최대 릴리스 개수.
- `followLinks`: (bool, 기본값: false) `zip` 전략 시 심볼릭 링크를 파일로 간주하여 따라갈지 여부.
- `gitRepo`: (string) `git` 전략 사용 시의 원격 저장소 주소.

### 실행 설정 (serve)
- `patterns`: (list) `gat serve` 모드에서 파일 변경을 감시할 대상 패턴 목록. (예: `["*.py", "*.json"]`)



## 주요 메서드 (Life Cycle)

### `setupTask(util, remote, local, **_)`
- 목적: 서버의 기초 환경(패키지 설치, 설정 파일 수정 등)을 설정합니다.
- 실행: `gat SERVER_NAME setup` 명령 시 실행됩니다.

### `buildTask(util, local, remote, **_)`
- 목적: 애플리케이션을 빌드합니다. (컴파일, 번들링 등)
- 실행: `serve`, `test`, `deploy` 과정에서 자동으로 호출됩니다.

### `getRunCmd(util, local, remote, **_)`
- 목적: 애플리케이션 실행 커맨드를 정의합니다.
- 반환: 실행 인자들의 리스트 (예: `['python3', 'main.py']`)

### `deployPreTask / deployPostTask`
- 목적: 배포 전/후에 필요한 추가 작업을 수행합니다.
- 실행: `gat SERVER_NAME deploy` 명령 시 실행됩니다.

## 주요 객체 API

### `remote` (Conn 객체)
원격 서버 또는 컨테이너와의 상호작용을 담당합니다.
- `run(cmd)`: 명령 실행 (실패 시 예외 발생).
- `runOutput(cmd)`: 명령 실행 후 결과 문자열 반환.
- `uploadFile(src, dest, sudo=False)`: 로컬 파일을 원격지로 전송.
- `makeFile(content, path, sudo=False)`: 원격지에 직접 내용이 담긴 파일 생성.
- `configLine(path, regexp, line, sudo=False)`: 설정 파일의 특정 라인을 정규식으로 찾아 수정.
- `configBlock(path, marker, block, sudo=False)`: 마커 사이의 설정 블록을 관리.

### `local` (Conn 객체)
로컬 머신에서의 작업을 담당하며, `remote`와 동일한 API를 제공합니다.

### `util` (MyUtil 객체)
유틸리티 기능을 제공합니다.
- `util.config`: 로드된 설정 정보에 접근.
- `util.isRestart`: `serve` 모드에서 파일 변경에 의한 재시작 여부 확인.

## 작성 예시

### 애플리케이션 배포 설정 (`gat_app.py`)

```python
config = """
name: my-web-app
type: app
deploy:
  strategy: zip
  include:
    - "bin/app"
    - "config/*.json"
  sharedLinks:
    - "logs"
    - "config/database.json"
servers:
  - name: prod
    host: web-server.com
    id: deploy-user
    deployRoot: /var/www/my-app
    owner: www-data
"""

class myGat:
    def __init__(self, helper, **_):
        helper.configStr("yaml", config)

    def buildTask(self, util, local, **_):
        local.run("go build -o bin/app main.go")

    def deployPostTask(self, util, remote, local, **_):
        # 배포 후 서비스 재시작
        remote.run("sudo systemctl restart my-app")
```

### 시스템 설정 (`gat_sys.py`)

```python
class myGat:
    def __init__(self, helper, **_):
        helper.configStr("yaml", """
name: base-system
type: sys
servers:
  - name: worker-1
    host: 10.0.0.5
    id: admin
""")

    def setupTask(self, util, remote, local, **_):
        # 패키지 설치
        remote.run("sudo apt-get update && sudo apt-get install -y nginx")
        
        # Nginx 설정 수정
        remote.configLine(
            path="/etc/nginx/nginx.conf",
            regexp="worker_connections",
            line="worker_connections 1024;",
            sudo=True
        )
```


## 팁 및 주의사항
- Variable Expansion: YAML 내에서 `${VAR}` 또는 `{{var}}` 형식을 사용하여 환경 변수나 설정값을 동적으로 주입할 수 있습니다.
- Sudo: `sudo` 권한이 필요한 명령은 메서드의 `sudo=True` 인자를 활용하거나 커맨드에 직접 `sudo`를 포함하세요. 비밀번호는 필요 시 터미널에서 자동으로 요청됩니다.
- Container: `servers` 설정에 `dkName`을 지정하면 모든 `remote` 명령이 자동으로 해당 컨테이너 내부에서 실행됩니다.
