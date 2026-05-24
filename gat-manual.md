# GAT 사용 매뉴얼

이 문서는 현재 작업 폴더의 `gat` 스크립트들과 `/Users/cjng96/iner/gat`의 실제 구현을 기준으로 정리한 로컬 매뉴얼이다.
대상은 `/Users/cjng96/iner/provision`에서 사용하는 Python 기반 배포/프로비저닝 툴 `gat`이다.

검토 기준:

- 실제 스크립트: [pg.py](/Users/cjng96/iner/provision/pg.py), [web.py](/Users/cjng96/iner/provision/web.py), [wikijs.py](/Users/cjng96/iner/provision/wikijs.py), [stalwart.py](/Users/cjng96/iner/provision/stalwart.py) 등
- 실제 런타임: [/Users/cjng96/iner/gat/gat/gat.py](/Users/cjng96/iner/gat/gat/gat.py)
- 공용 헬퍼: [/Users/cjng96/iner/gat/gat/plugin.py](/Users/cjng96/iner/gat/gat/plugin.py)
- 템플릿: [/Users/cjng96/iner/gat/gat/sampleFiles.py](/Users/cjng96/iner/gat/gat/sampleFiles.py)
- 설치 스크립트: [/Users/cjng96/iner/gat/install.sh](/Users/cjng96/iner/gat/install.sh)

관련 문서:

- 빠른 시작: [gat-quickstart.md](/Users/cjng96/iner/provision/gat-quickstart.md)
- `gat.plugin` 치트시트: [gat-plugin-cheatsheet.md](/Users/cjng96/iner/provision/gat-plugin-cheatsheet.md)

---

## 목차

1. [개요](#개요)
2. [로컬 설치 구조](#로컬-설치-구조)
3. [빠른 시작](#빠른-시작)
4. [CLI 해석 규칙](#cli-해석-규칙)
5. [스크립트 타입: `sys`와 `app`](#스크립트-타입-sys와-app)
6. [스크립트 기본 구조](#스크립트-기본-구조)
7. [config YAML 규칙](#config-yaml-규칙)
8. [실행 시 전달되는 객체](#실행-시-전달되는-객체)
9. [`setup`, `run`, `deploy`의 의미](#setup-run-deploy의-의미)
10. [배포 타입 `app` 상세](#배포-타입-app-상세)
11. [현재 저장소에서 자주 쓰는 `gat.plugin` 패턴](#현재-저장소에서-자주-쓰는-gatplugin-패턴)
12. [실전 예시](#실전-예시)
13. [새 스크립트 작성 절차](#새-스크립트-작성-절차)
14. [트러블슈팅](#트러블슈팅)
15. [주의할 점과 구현 차이](#주의할-점과-구현-차이)
16. [요약](#요약)

---

## 개요

이 저장소에서 `gat`은 Ansible 참고본과 별개로 동작하는 **Python 기반 배포/프로비저닝 런너**다.

핵심 개념은 단순하다.

- 각 `*.py` 파일이 하나의 배포 스크립트다.
- 스크립트 내부의 `config = """..."""` YAML 블록이 설정 원본이다.
- `gat`이 해당 파일을 import해서 `myGat` 클래스를 생성한다.
- 이후 `setupTask()`, `buildTask()`, `deployPreTask()`, `deployPostTask()` 등을 호출한다.
- 실제 SSH 접속, 컨테이너 접속, 이미지 갱신, runit 서비스 작성, DB 계정 생성 등은 주로 `gat.plugin` 헬퍼가 담당한다.

현재 `provision` 폴더의 중심은 `type: sys` 스크립트다. 대표 파일:

- [pg.py](/Users/cjng96/iner/provision/pg.py)
- [web.py](/Users/cjng96/iner/provision/web.py)
- [wikijs.py](/Users/cjng96/iner/provision/wikijs.py)
- [gitea.py](/Users/cjng96/iner/provision/gitea.py)
- [stalwart.py](/Users/cjng96/iner/provision/stalwart.py)

---

## 로컬 설치 구조

현재 로컬에서 잡히는 `gat` 실행기는 다음 wrapper다.

- [/Users/cjng96/bin/gat](/Users/cjng96/bin/gat)

내용:

```bash
#!/bin/bash
P=~/.gat/repo
PYTHONPATH=$P uv run --project $P -m gat.gat $@
```

즉 실제 실행 방식은 다음과 같다.

```bash
PYTHONPATH=~/.gat/repo uv run --project ~/.gat/repo -m gat.gat ...
```

의미:

- `gat`은 파일 직접 실행이 아니라 `python -m gat.gat` 방식으로 실행된다.
- 패키지 루트는 `~/.gat/repo`다.
- `uv`가 전제다.

설치 스크립트는 [/Users/cjng96/iner/gat/install.sh](/Users/cjng96/iner/gat/install.sh)에 있다. 동작은 다음과 같다.

1. `~/.gat/repo` 생성
2. `gat` 저장소 clone
3. `~/bin/gat` wrapper 생성
4. `PATH`에 `~/bin` 추가

`pyproject.toml` 기준 런타임 요구사항:

| 항목 | 값 |
|---|---|
| Python | `>=3.12` |
| 실행기 | `uv` |
| 주요 의존성 | `google-api-python-client`, `google-auth`, `oauth2client`, `paramiko`, `pyyaml`, `requests`, `termcolor`, `watchdog` |

---

## 빠른 시작

### 가장 흔한 사용 패턴

현재 `provision` 저장소 기준으로 실사용 명령은 거의 다음 둘 중 하나다.

```bash
gat FILE SERVER
gat FILE SERVER run
```

예:

```bash
gat pg h4 run
gat web h4 run
gat wikijs bs1 run
gat stalwart h4 run
```

### 기본 의미

| 명령 | 의미 |
|---|---|
| `gat FILE SERVER` | 해당 스크립트의 `setupTask()` 실행 |
| `gat FILE SERVER run` | `setupTask()` 실행 + `remote.runFlag=True` |
| `gat SERVER deploy` | `gat_app.py` 기준 배포 실행 |
| `gat init sys NAME` | `NAME.py` 템플릿 생성 |
| `gat init app` | `gat_app.py` 템플릿 생성 |

### 먼저 확인할 것

```bash
which gat
type gat
```

현재 작업 디렉터리에 `.data.yml`을 요구하는 스크립트가 많으므로, 없는 상태에서 바로 실행하면 예외가 난다.

---

## CLI 해석 규칙

이 부분은 help 문자열보다 [/Users/cjng96/iner/gat/gat/gat.py](/Users/cjng96/iner/gat/gat/gat.py)의 `MyArgv` 구현이 더 중요하다.

### 1. 첫 인자가 파일이면 그 파일을 스크립트로 본다

예:

```bash
gat stalwart h4 run
```

현재 폴더에 `stalwart.py`가 있으면 내부 해석은 다음과 같다.

- `gatName = stalwart.py`
- `serverName = h4`
- `cmd = run`

`.py`는 생략 가능하다.

### 2. 첫 인자가 파일이 아니면 기본 파일은 `gat_app.py`

예:

```bash
gat prod deploy
```

이 경우 대상 스크립트는 `gat_app.py`다.

### 3. 명령을 생략하면 기본값은 `setup`

예:

```bash
gat stalwart h4
```

는 내부적으로 다음과 같다.

```bash
gat stalwart h4 setup
```

### 4. 서버명을 생략하면 서버 개수에 따라 다르다

- 서버가 1개면 자동 선택
- 서버가 2개 이상이면 실패

예:

```bash
gat stalwart run
```

이 형식은 `stalwart.py`에 서버가 하나뿐일 때만 안전하다.

### 5. 현재 구현상 안정적으로 보는 명령

- `help`
- `init`
- `setup`
- `run`
- `deploy`

### 6. 옵션

| 옵션 | 의미 |
|---|---|
| `-v` | 로그 레벨 1 |
| `--vv` | 로그 레벨 2 |
| `-f` | force 플래그 |
| `--git` | deploy 전략을 `git`으로 강제 |
| `--zip` | deploy 전략을 `zip`으로 강제 |
| `--help` | help 출력 |

예:

```bash
gat --vv stalwart h4 run
gat --zip prod deploy
```

---

## 스크립트 타입: `sys`와 `app`

### `type: sys`

서버, 컨테이너, 서비스, 인프라 컴포넌트 구성용이다.
현재 `provision` 저장소의 중심은 이 타입이다.

호출 형식:

```bash
gat FILE SERVER
gat FILE SERVER run
```

대표 예:

```bash
gat pg h4 run
gat web h4 run
gat stalwart h4 run
```

### `type: app`

빌드와 릴리즈 디렉터리 배포 중심의 타입이다. 기본 파일명은 `gat_app.py`다.

호출 형식:

```bash
gat SERVER deploy
gat SERVER setup
gat SERVER run
```

`type: app`은 `buildTask()`, `deployPreTask()`, `deployPostTask()`를 활용하는 구조다.

---

## 스크립트 기본 구조

현재 `provision` 폴더의 실전 패턴은 거의 다음 형태다.

```python
config = """
name: sample
type: sys
podman: true

defaultVars:
  ctrName: sample

servers:
  - name: h4
    host: ph4.mmx.kr
    port: 22
    id: cjng96
    vars:
      pass: 1
"""

import gat.plugin as my
from gat.app_config import GatApp


class myGat(GatApp):
    def __init__(self, helper, **_):
        helper.configStr("yaml", config)
        self.data = helper.loadData(".data.yml")

    def setupTask(self, util, local, remote, **_):
        remote.config.podman = True
        ...
```

핵심 포인트:

1. `helper.configStr("yaml", config)`로 설정 로드
2. 필요하면 `self.data = helper.loadData(".data.yml")`
3. 실제 작업은 `setupTask()`에 둔다
4. 컨테이너 조립과 시스템 작업은 주로 `gat.plugin`을 사용한다

---

## config YAML 규칙

실제 로드는 `Config.configStr()`가 담당한다.

### 자주 쓰는 키

| 키 | 의미 |
|---|---|
| `name` | 서비스 이름 |
| `type` | `sys` 또는 `app` |
| `podman` | podman 사용 여부 |
| `defaultVars` | 서버 공통 기본 변수 |
| `servers` | 대상 서버 목록 |
| `deploy` | `type: app` 배포 설정 |
| `serve` | 앱 개발용 파일 패턴 설정 |
| `test` | 앱 테스트용 파일 패턴 설정 |

### `defaultVars` 병합

`defaultVars`가 있으면 각 `servers[].vars`에 merge된다.

예:

```yaml
defaultVars:
  ctrName: pg
  ctrPorts: 2090:5432

servers:
  - name: h4
    host: h4.mmx.kr
    port: 51022
    id: cjng96
    vars:
      pass: 1
```

실행 시 `h4.vars`에는 다음이 들어간다.

- `ctrName`
- `ctrPorts`
- `pass`

### 문자열 확장

`taskSetup()`과 `taskDeploy()`에서 `expandVar(config)`가 호출된다.

즉 YAML 문자열에는 다음 확장이 들어갈 수 있다.

- 환경 변수 확장
- 내부 딕셔너리 기반 문자열 치환

예시 성격의 문법:

```yaml
- "{{name}}"
```

### `srcPath`

`Config`의 기본 `srcPath`는 `"."`이다.
단, `deploy.strategy == "git"`이면 실행 중 `./clone`으로 바뀐다.

---

## 실행 시 전달되는 객체

`setupTask(self, util, local, remote, **_)`에서 받는 객체를 이해하면 코드 읽기가 쉬워진다.

### `remote`

실제 대상 서버 또는 대상 컨테이너 연결 객체다.

`taskSetup()` 내부 동작:

1. 우선 `Conn(server, config)`로 원격 서버 접속
2. `server.ctrName`이 있으면 그 컨테이너로 다시 래핑
3. `server.dkName`이 있으면 그 컨테이너로 다시 래핑

즉 서버 정의에 `ctrName` 또는 `dkName`이 있으면 `setupTask()`는 곧바로 컨테이너 안에서 실행될 수 있다.

자주 쓰는 패턴:

```python
remote.run("apt update")
remote.runOutput("hostname")
remote.containerConn("pg")
remote.remoteConn("host", 22, "user")
```

### `local`

로컬 머신에서 실행할 작업용 객체다.
앱 빌드나 파일 생성에 쓰인다.

### `util`

전역 유틸과 로드된 데이터 접근용이다.

예:

```python
pw = util.data.apps.wikijs.dbPw
```

---

## `setup`, `run`, `deploy`의 의미

### `setup`

`taskSetup()`가 `setupTask()`를 호출하되:

- `remote.runFlag = False`

즉 보통 이미지 생성, 파일 배치, 설정 작성 같은 준비 작업이 중심이다.

### `run`

`taskSetup()`가 `setupTask()`를 호출하되:

- `remote.runFlag = True`

현재 저장소의 많은 스크립트가 이 값을 보고 실제 실행 단계를 분기한다.

실전 패턴:

```python
if remote.runFlag:
    my.containerUserRun(...)
```

즉 관례상:

- `setup`: 준비만
- `run`: 준비 + 실행

으로 이해하면 된다.

### `deploy`

`type: app`에서만 의미 있는 배포 경로다.
실행 순서는 대략 다음과 같다.

1. `buildTask()` 실행
2. 서버 접속
3. `deployRoot/shared`, `deployRoot/releases` 준비
4. 기존 release 목록 확인 및 초과분 정리
5. 새 release 디렉터리 생성
6. include 파일 수집
7. zip 업로드 또는 git clone 후 zip 업로드
8. shared link 연결
9. `current -> releases/<timestamp>` 갱신
10. `deployPostTask()` 실행

---

## 배포 타입 `app` 상세

현재 저장소는 `sys` 위주지만, `gat` 본체는 `app` 배포 기능도 갖고 있다.

### 기본 템플릿 생성

```bash
gat init app
```

생성 파일:

```text
gat_app.py
```

### 샘플 구조

템플릿은 대략 다음 메서드를 전제로 한다.

```python
from gat.app_config import GatApp


class myGat(GatApp):
    def __init__(self, helper, **_):
        helper.configStr("yaml", config)

    def buildTask(self, util, local, **_):
        ...

    def deployPreTask(self, util, remote, local, **_):
        ...

    def deployPostTask(self, util, remote, local, **_):
        ...
```

### `deploy` 설정에서 실제 의미 있는 키

| 키 | 의미 |
|---|---|
| `strategy` | `zip` 또는 `git` |
| `maxRelease` | 보관할 release 개수 |
| `include` | 업로드 대상 파일/폴더 목록 |
| `exclude` | 업로드 제외 패턴 |
| `sharedLinks` | `shared`에 두고 release에 심볼릭 링크할 경로 |
| `gitRepo` | `git` 전략일 때 clone 대상 |

### 서버 측 필수 성격 키

| 키 | 의미 |
|---|---|
| `deployRoot` | 배포 루트 |
| `gitBranch` | `git` 전략일 때 원격 브랜치 |
| `owner` | 있으면 생성 파일 소유자 조정에 사용 |

### 실제 release 구조

`taskDeploy()` 기준으로 서버에는 대략 이런 구조가 생긴다.

```text
deployRoot/
  current -> releases/YYMMDD_HHMMSS
  releases/
    YYMMDD_HHMMSS/
  shared/
```

### include 형식

구현상 `include`는 두 형식을 받는다.

1. 문자열 경로
2. 객체 경로

문자열 예:

```yaml
include:
  - app
  - config
```

객체 예:

```yaml
include:
  - src: ../build
    dest: build
```

중요: 현재 런타임 코드는 객체 키를 `dest`로 읽는다.
샘플 파일에는 `target`이 남아 있는데, 실제 구현 기준으로는 `dest`를 쓰는 편이 안전하다.

### `strategy: zip`

로컬 파일을 zip으로 묶어 서버의 새 release 디렉터리에 푼다.

### `strategy: git`

원격 저장소를 로컬 `./clone` 아래로 clone한 뒤, 그 결과를 zip 배포한다.

즉 `git` 전략도 결국 업로드 자체는 zip 기반이다.

---

## 현재 저장소에서 자주 쓰는 `gat.plugin` 패턴

여기서는 `provision` 폴더에서 반복적으로 보이는 패턴만 적는다.

### 1. 베이스 이미지 선택

```python
baseName, baseVer = my.containerBaseImage(remote)
baseName, baseVer = my.containerCoImage(remote)
baseName, baseVer = my.dockerBaseImage(remote)
```

용도:

- 공통 베이스 이미지 확보
- 서비스 전용 이미지의 부모 이미지 결정

### 2. 서비스 전용 이미지 생성

```python
my.containerUpdateImage(
    remote,
    baseName=baseName,
    baseVer=baseVer,
    newName=ctrImg,
    newVer=ctrVer,
    hash=None,
    func=update,
)
```

`update(env)` 안에서 보통 하는 일:

- 패키지 설치
- 설정 파일 생성/수정
- 사용자 생성
- runit 서비스 작성
- 앱 바이너리 설치

### 3. runit 서비스 작성

```python
my.writeRunScript(env, "exec ...", targetPath=None)
```

보조 서비스는 `appName`으로 분리한다.

```python
my.writeRunScript(env, "...", appName="bulwark", targetPath=None)
```

현재 `coImage`/baseimage 계열 컨테이너는 runit 기반이므로 이 패턴이 매우 많이 쓰인다.

### 4. 컨테이너 실행

```python
my.containerUserRun(
    env=remote,
    name=remote.vars.ctrName,
    image=f"{ctrImg}:{ctrVer}",
    ports=[...],
)
```

### 5. 다른 컨테이너 접속

```python
db = remote.containerConn("pg")
```

용도:

- 같은 서버의 다른 컨테이너 재사용
- DB 작업
- 웹 프록시 설정

### 6. DB/유저 생성

```python
my.pgDbGen(db, "stalwart")
my.pgUserGen(db, id="stalwart", pw=dbPw, db="stalwart")
```

### 7. 웹 프록시 설정

```python
my.setupWebApp(...)
```

실제 저장소에서는 `web` 컨테이너를 따로 두고, 서비스 컨테이너를 reverse proxy에 연결하는 패턴이 자주 나온다.

---

## 실전 예시

### PostgreSQL 컨테이너

파일:

- [pg.py](/Users/cjng96/iner/provision/pg.py)

핵심 흐름:

1. base image 준비
2. PostgreSQL 패키지 설치
3. 설정 파일 수정
4. runit 실행 스크립트 작성
5. `runFlag`일 때 컨테이너 실행

자주 보는 명령:

```bash
gat pg h4 run
```

### 웹 프록시 컨테이너

파일:

- [web.py](/Users/cjng96/iner/provision/web.py)

핵심 흐름:

1. nginx/dnsmasq 설치
2. runit 서비스 다중 작성
3. podman 네트워크 차이 처리
4. `80/443` 바인딩 정책 반영

자주 보는 명령:

```bash
gat web h4 run
```

### Wiki.js

파일:

- [wikijs.py](/Users/cjng96/iner/provision/wikijs.py)

핵심 흐름:

1. 이미지 생성
2. 앱 설정 수정
3. DB 생성
4. 웹 프록시 연결

자주 보는 명령:

```bash
gat wikijs bs1 run
```

### Stalwart

파일:

- [stalwart.py](/Users/cjng96/iner/provision/stalwart.py)

핵심 흐름:

1. `coImage` 기반 이미지 생성
2. Stalwart 바이너리 설치
3. Bulwark 포함 구성
4. Postgres 연동
5. runit 서비스 2개 이상 작성

자주 보는 명령:

```bash
gat stalwart h4 run
```

---

## 새 스크립트 작성 절차

### 새 `sys` 스크립트

### 1. 템플릿 생성

```bash
gat init sys mysvc
```

생성 파일:

```text
mysvc.py
```

### 2. config 작성

최소한 다음은 정한다.

- `name`
- `type: sys`
- `servers`
- 필요하면 `defaultVars`

### 3. `myGat` 구현

기본 골격:

```python
from gat.app_config import GatApp


class myGat(GatApp):
    def __init__(self, helper, **_):
        helper.configStr("yaml", config)
        self.data = helper.loadData(".data.yml")

    def setupTask(self, util, local, remote, **_):
        ...
```

### 4. 컨테이너형이면 보통 이 순서

1. 베이스 이미지 선택
2. `containerUpdateImage()`로 커스텀 이미지 생성
3. `writeRunScript()`로 실행 스크립트 작성
4. `if remote.runFlag:`에서 `containerUserRun()`
5. 필요하면 DB 생성/프록시 연결

### 새 `app` 스크립트

### 1. 템플릿 생성

```bash
gat init app
```

### 2. `deploy` 섹션 작성

- `strategy`
- `include`
- `exclude`
- `sharedLinks`
- `maxRelease`

### 3. 메서드 구현

- `buildTask()`
- 필요하면 `deployPreTask()`
- 필요하면 `deployPostTask()`

---

## 트러블슈팅

### 1. `ImportError: attempted relative import with no known parent package`

원인:

- `gat/gat.py`를 직접 실행했을 때
- 패키지 모드가 아닌 방식으로 잡혔을 때

정상 실행 형식:

```bash
PYTHONPATH=~/.gat/repo uv run --project ~/.gat/repo -m gat.gat ...
```

확인:

```bash
which gat
type gat
```

즉 wrapper가 깨졌거나, 다른 `gat`가 먼저 잡힌 경우를 먼저 의심하면 된다.

### 2. `.data.yml` 없음

증상:

- 시작 직후 예외

원인:

- `helper.loadData(".data.yml")` 호출

대응:

- 현재 작업 디렉터리에 `.data.yml` 배치

### 3. 서버 이름 누락

증상:

- 서버가 2개 이상일 때 `gat pg run` 같은 명령이 실패

대응:

```bash
gat pg h4 run
```

처럼 서버명을 명시한다.

### 4. `gat FILE run`이 기대대로 안 됨

이 형식은 서버가 하나뿐일 때만 안전하다.

예:

```bash
gat stalwart run
```

현재 `stalwart.py`가 서버 1개일 때는 되지만, 서버를 늘리면 실패한다.

### 5. runit 서비스가 아직 supervise되지 않음

컨테이너가 막 뜬 직후 `sv restart app`를 치면 `/etc/service/.../supervise/ok`가 아직 없어서 경고가 날 수 있다.

실전 대응은 보통 다음 둘 중 하나다.

1. 잠깐 대기 후 `sv restart`
2. `run` 스크립트 자체에서 config 생성/대기 처리

### 6. low port 바인딩 실패

`web.py` 주석처럼 rootless podman에서 `80`, `443` 바인딩이 막힐 수 있다.

이 경우 대표 대응은 다음이다.

```bash
sudo sysctl net.ipv4.ip_unprivileged_port_start=80
```

---

## 주의할 점과 구현 차이

### 1. help 문구와 현재 파서가 완전히 일치하지 않는다

help에는 `gat`, `gat test`, `gat serve`가 남아 있지만, 현재 `MyArgv` 구현만 기준으로 보면 기본 사용 경로는 다음 명령들이다.

- `init`
- `setup`
- `run`
- `deploy`

문서와 실사용은 구현 기준으로 보는 편이 안전하다.

### 2. `sampleFiles.py`의 `target` vs 실제 런타임의 `dest`

샘플 앱 템플릿에는 include 객체 예시가 다음처럼 적혀 있다.

```yaml
- src: ../build
  target: build
```

하지만 현재 `taskDeploy()`의 파일 수집 코드는 객체 키를 `dest`로 읽는다.

따라서 실제 스크립트 작성 시에는 다음처럼 쓰는 편이 맞다.

```yaml
- src: ../build
  dest: build
```

### 3. `.data.yml` 로드는 자동이 아니다

`gat`가 무조건 `.data.yml`을 읽는 구조가 아니라, 각 스크립트의 `__init__()`에서 `helper.loadData(".data.yml")`를 직접 호출해야 한다.

즉 어떤 스크립트는 `.data.yml`이 필수이고, 어떤 스크립트는 아닐 수 있다.

### 4. `sys` 스크립트가 이 저장소의 중심이다

`gat` 본체에는 `app` 배포 기능이 있지만, 현재 `provision` 저장소는 실질적으로 `sys` 중심 구조다.
새 작업을 이 저장소 스타일로 맞출 때도 보통 `type: sys`가 기준이 된다.

---

## 요약

이 저장소의 `gat`은 다음으로 정리된다.

- **스크립트 단위 런너**
- **설정은 inline YAML**
- **실행 로직은 Python**
- **원격 작업은 SSH/컨테이너 connection 객체 기반**
- **공통 시스템 조립은 `gat.plugin` 헬퍼 사용**

현재 `provision` 폴더에서 가장 자주 쓰는 명령 패턴은 다음이다.

```bash
gat FILE SERVER
gat FILE SERVER run
```

새 시스템을 추가할 때도 대체로 이 흐름이면 된다.

1. `gat init sys NAME`
2. `config` 작성
3. `setupTask()` 구현
4. 필요하면 `.data.yml` 사용
5. 필요하면 `containerUpdateImage()` + `writeRunScript()` + `containerUserRun()`
