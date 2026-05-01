# GAT Plugin Cheatsheet

이 문서는 `/Users/cjng96/iner/gat/gat/plugin.py` 중에서
`/Users/cjng96/iner/provision`에서 자주 쓰는 함수만 추려 정리한 치트시트다.

상세 배경은 [gat-manual.md](/Users/cjng96/iner/provision/gat-manual.md)를 본다.

## 1. 기본 전제

대부분 함수는 `setupTask(self, util, local, remote, **_)` 안에서 `remote` 또는 `env` 객체와 함께 사용한다.

예:

```python
import gat.plugin as my
from gat.app_config import GatApp


class myGat(GatApp):
    def __init__(self, helper, **_):
        helper.configStr("yaml", config)

    def setupTask(self, util, local, remote, **_):
        ...
```

## 2. 베이스 이미지 계열

### `my.containerBaseImage(remote)`

용도:

- phusion/baseimage 기반 기본 이미지 확보

반환:

```python
baseName, baseVer = my.containerBaseImage(remote)
```

특징:

- 기본 이미지 이름은 `baseimg`
- 없으면 새로 빌드
- 있으면 재사용

### `my.containerCoImage(remote, nodeVer="lts-gallium", dartVer="3.10.7")`

용도:

- `baseimg` 위에 Python/Node/Dart 등의 공용 빌드 환경을 얹은 `coimg` 생성

반환:

```python
baseName, baseVer = my.containerCoImage(remote)
```

현재 저장소 예:

- [stalwart.py](/Users/cjng96/iner/provision/stalwart.py)

### `my.dockerBaseImage(remote)`

이름은 `dockerBaseImage`지만 현재 구현은 `containerBaseImage` alias다.

```python
baseName, baseVer = my.dockerBaseImage(remote)
```

## 3. 이미지 갱신

### `my.containerUpdateImage(...)`

대표 형태:

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

의미:

- `baseName:baseVer`를 부모로 컨테이너를 띄움
- `func(update_env)` 안에서 패키지 설치/파일 생성/설정 변경 수행
- 마지막에 commit해서 `newName:newVer` 이미지 생성

`update(env)` 안에서 자주 하는 일:

- `env.run("apt update")`
- `env.run("apt install ...")`
- `env.makeFile(...)`
- `env.configLine(...)`
- `my.writeRunScript(...)`

주의:

- 해당 태그 이미지가 이미 있고 부모 이미지 조건이 맞으면 재생성을 생략할 수 있다
- `hash`를 쓰면 label 기반 재생성 판단도 가능하다

## 4. 컨테이너 실행

### `my.containerUserRun(...)`

대표 형태:

```python
my.containerUserRun(
    env=remote,
    name=remote.vars.ctrName,
    image=f"{ctrImg}:{ctrVer}",
    ports=["8080:8080"],
)
```

자주 쓰는 인자:

| 인자 | 의미 |
|---|---|
| `name` | 컨테이너 이름 |
| `image` | 실행할 이미지 |
| `ports` | 포트 매핑 |
| `net` | 네트워크 설정 |
| `volumes` | 볼륨 마운트 |
| `envs` | 환경 변수 |
| `runAsCmd` | true면 systemd/quadlet 대신 즉시 실행 커맨드 방식 |
| `rootfull` | rootfull podman 여부 |

특징:

- `podman`이면 기본적으로 user systemd/quadlet 흐름을 탄다
- `docker`면 내부적으로 커맨드 실행 방식으로 간다

실전 예:

```python
if remote.runFlag:
    my.containerUserRun(
        env=remote,
        name=remote.vars.ctrName,
        image=f"{ctrImg}:{ctrVer}",
        ports=remote.vars.ctrPorts,
    )
```

## 5. runit 실행 스크립트

### `my.writeRunScript(env, cmd, appName="app", targetPath="/app/current")`

대표 형태:

```python
my.writeRunScript(
    env,
    "exec /usr/bin/myapp",
    targetPath=None,
)
```

중요한 동작:

- `/etc/service/{appName}/run` 생성
- phusion/baseimage runit 서비스로 등록
- `targetPath=None`이면 곧바로 `/etc/service/app/run`을 쓴다

보조 서비스 추가 예:

```python
my.writeRunScript(
    env,
    "exec npm start",
    appName="bulwark",
    targetPath=None,
)
```

현재 저장소 예:

- [pg.py](/Users/cjng96/iner/provision/pg.py)
- [web.py](/Users/cjng96/iner/provision/web.py)
- [stalwart.py](/Users/cjng96/iner/provision/stalwart.py)

### `my.writeSvHelper(env)`

용도:

- runit용 shell alias/helper를 `.bashrc` 쪽에 써준다

보통 `writeRunScript()`가 내부에서 호출하므로 직접 쓸 일은 많지 않다.

## 6. 사용자 생성

### `my.userAddRaw(...)`

실전에서는 system user 생성 시 이쪽이 더 안전한 경우가 있다.

예:

```python
my.userAddRaw(
    env,
    "stalwart",
    genHome=False,
    shell="/usr/sbin/nologin",
    system=True,
)
```

용도:

- home 경로 자동 처리 부작용을 피하고 싶을 때
- system user를 명시적으로 만들고 싶을 때

## 7. DB 관련

### `my.pgDbGen(env, name)`

용도:

- PostgreSQL DB가 없으면 생성
- 생성 후 `pg_trgm` extension도 추가

예:

```python
my.pgDbGen(db, "stalwart")
```

### `my.pgUserGen(env, id, pw, db)`

용도:

- PostgreSQL role이 없으면 생성
- DB connect 및 schema/database privilege 부여

예:

```python
my.pgUserGen(db, id="stalwart", pw=dbPw, db="stalwart")
```

주의:

- **role이 이미 있으면 바로 return한다**
- 즉 기존 비밀번호를 바꾸지 않는다
- 비밀번호 회전이 필요하면 별도 `ALTER USER` 또는 삭제 후 재생성이 필요하다

### `my.pgUserDel(env, id, db)`

용도:

- role 권한 revoke 후 삭제

예:

```python
my.pgUserDel(db, id="stalwart", db="stalwart")
```

## 8. 웹 프록시

### `my.setupWebApp(...)`

대표 형태:

```python
my.setupWebApp(
    env=web,
    name="stalwart",
    domain="stalwart.mmx.kr",
    proxyUrl="http://host.containers.internal:8080",
    publicApi="/",
)
```

주요 인자:

| 인자 | 의미 |
|---|---|
| `name` | nginx 설정 이름 |
| `domain` | 서비스 도메인 |
| `proxyUrl` | upstream 주소 |
| `publicApi` | public path prefix |
| `root` | 정적 파일 root |
| `privateApi` | private path |
| `wsPath` | websocket path |
| `maxBodySize` | 업로드 크기 제한 |
| `httpRedirect` | HTTP -> HTTPS redirect |
| `customConfig` | nginx 추가 설정 |

용도:

- `web` 컨테이너에 reverse proxy 설정 생성

## 9. 연결 객체 패턴

### `remote.containerConn("pg")`

같은 서버의 다른 컨테이너 접속

```python
db = remote.containerConn("pg")
```

### `remote.remoteConn(host, port, id, ...)`

다른 서버나 다른 접속 대상을 직접 연결

```python
web = remote.remoteConn("192.168.15.210", 22, "jychoi", ctrName="web")
```

## 10. 최소 컨테이너형 패턴

```python
import gat.plugin as my
from gat.app_config import GatApp


class myGat(GatApp):
    def __init__(self, helper, **_):
        helper.configStr("yaml", config)
        self.data = helper.loadData(".data.yml")

    def setupTask(self, util, local, remote, **_):
        baseName, baseVer = my.containerBaseImage(remote)

        ctrImg = remote.config.name
        ctrVer = "1"

        def update(env):
            my.baseimgInitScript(env)
            env.run("apt update")
            env.run("apt install -y curl")
            my.writeRunScript(
                env,
                "exec /usr/bin/python3 -m http.server 8080",
                targetPath=None,
            )

        my.containerUpdateImage(
            remote,
            baseName=baseName,
            baseVer=baseVer,
            newName=ctrImg,
            newVer=ctrVer,
            hash=None,
            func=update,
        )

        if remote.runFlag:
            my.containerUserRun(
                env=remote,
                name=remote.vars.ctrName,
                image=f"{ctrImg}:{ctrVer}",
                ports=["8080:8080"],
            )
```

## 11. 실무 팁

1. `setupTask()`에서 `remote.runFlag`를 기준으로 build/run을 분리한다.
2. system user는 `userAddRaw()`가 더 예측 가능한 경우가 있다.
3. DB 비밀번호 변경이 가능해야 하면 `pgUserGen()`만 믿지 않는다.
4. `writeRunScript()`는 runit 기반 컨테이너에 맞춰 쓴다.
5. `setupWebApp()`의 `proxyUrl`은 실제 런타임 포트 기준으로 잡는다.
