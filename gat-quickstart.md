# GAT Quickstart

이 문서는 `/Users/cjng96/iner/provision`에서 `gat`을 바로 쓰기 위한 짧은 실전 요약이다.
상세 설명은 [gat-manual.md](/Users/cjng96/iner/provision/gat-manual.md)를 본다.

## 1. 실행기 확인

먼저 현재 셸에서 어떤 `gat`이 잡히는지 확인한다.

```bash
which gat
type gat
```

현재 로컬 기준 정상 wrapper는 대략 다음 형태다.

```bash
PYTHONPATH=~/.gat/repo uv run --project ~/.gat/repo -m gat.gat ...
```

## 2. 현재 저장소에서 가장 많이 쓰는 명령

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

의미:

- `gat FILE SERVER`: `setupTask()` 실행
- `gat FILE SERVER run`: `setupTask()` 실행, `remote.runFlag=True`

## 3. 새 스크립트 만들기

시스템 스크립트:

```bash
gat init sys mysvc
```

앱 배포 스크립트:

```bash
gat init app
```

## 4. 최소 스크립트 형태

```python
config = """
name: mysvc
type: sys

servers:
  - name: h4
    host: ph4.mmx.kr
    port: 22
    id: cjng96
"""

import gat.plugin as my
from gat.app_config import GatApp


class myGat(GatApp):
    def __init__(self, helper, **_):
        helper.configStr("yaml", config)

    def setupTask(self, util, local, remote, **_):
        remote.run("hostname")
```

## 5. `.data.yml`

현재 저장소의 많은 스크립트는 다음을 쓴다.

```python
self.data = helper.loadData(".data.yml")
```

따라서 `.data.yml`이 없으면 시작 직후 실패할 수 있다.

## 6. 자주 쓰는 패턴

### 컨테이너 이미지 갱신

```python
baseName, baseVer = my.containerBaseImage(remote)

my.containerUpdateImage(
    remote,
    baseName=baseName,
    baseVer=baseVer,
    newName="myapp",
    newVer="1",
    hash=None,
    func=update,
)
```

### runit 실행 스크립트 작성

```python
my.writeRunScript(
    remote,
    "exec /usr/bin/myapp",
    targetPath=None,
)
```

### 컨테이너 실행

```python
if remote.runFlag:
    my.containerUserRun(
        env=remote,
        name=remote.vars.ctrName,
        image="myapp:1",
        ports=["8080:8080"],
    )
```

### 같은 서버의 다른 컨테이너 접속

```python
db = remote.containerConn("pg")
```

## 7. `app` 배포의 핵심

`type: app`은 `gat_app.py` 기준으로 동작한다.

대표 명령:

```bash
gat prod deploy
```

핵심 메서드:

- `buildTask()`
- `deployPreTask()`
- `deployPostTask()`

`deploy.strategy`는 보통 `zip` 또는 `git`이다.

## 8. 자주 막히는 문제

### `ImportError: attempted relative import with no known parent package`

원인:

- `gat.py`를 직접 실행함

정상 실행 방식:

```bash
PYTHONPATH=~/.gat/repo uv run --project ~/.gat/repo -m gat.gat ...
```

### 서버명이 빠짐

서버가 여러 개면 아래처럼 명시해야 한다.

```bash
gat pg h4 run
```

### help 문구와 실제 구현 차이

현재 구현 기준으로 안전하게 보는 명령은 다음이다.

- `init`
- `setup`
- `run`
- `deploy`

## 9. 현재 저장소 기준 추천 흐름

새 시스템 추가 시 보통 다음 순서로 간다.

1. `gat init sys NAME`
2. `config` 작성
3. 필요하면 `.data.yml` 사용
4. `setupTask()` 구현
5. 컨테이너형이면 `containerUpdateImage()` + `writeRunScript()` + `containerUserRun()`
