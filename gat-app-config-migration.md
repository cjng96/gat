# gat_app.py GatAppCfg Migration Guide

이 문서는 기존 YAML 기반 `gat_app.py`를 `GatAppCfg` 클래스 설정 방식으로 옮기는 절차를 정리한다.

목표는 세 가지다.

- 설정 자동완성과 타입 힌트를 얻는다.
- 기존 YAML 설정과 실행 결과를 유지한다.
- 문제가 생기면 YAML 방식으로 바로 되돌릴 수 있게 한다.

## 1. 기존 구조

기존 `gat_app.py`는 보통 다음 형태다.

```python
config = """
name: myapp
type: app

serve:
  patterns: ["*.py"]

deploy:
  strategy: zip
  include:
    - src: target/release/myapp
      dest: myapp

defaultVars:
  ctrName: myapp

servers:
  - name: prod
    host: example.com
    port: 22
    id: ser
    deployRoot: /app
    vars:
      profile: prod
"""


class myGat:
    def __init__(self, helper, **_):
        helper.configStr("yaml", config)
```

새 구조에서는 `myGat`가 `GatApp`을 상속하고, 설정은 `gatConfig` 클래스 멤버에 둔다.

## 2. import 추가

`gat_app.py` 상단에 필요한 타입을 import한다.

```python
from gat.app_config import (
    GatAppCfg,
    GatDeployCfg,
    GatApp,
    GatDeployIncludeCfg,
    GatServeCfg,
    GatServerCfg,
    GatVarsCfg,
)
```

짧은 alias(`AppCfg`, `Deploy`, `Inc`, `Serve`, `Server`, `Vars`)는 제공하지 않는다. 새 설정 파일은 위처럼 `GatAppCfg`, `GatDeployCfg`, `GatDeployIncludeCfg`, `GatServeCfg`, `GatServerCfg`, `GatVarsCfg` 풀 클래스명을 사용한다.

`GatVarsCfg`는 동적 map 성격의 설정이다. 프로젝트별 임의 키를 계속 사용할 수 있다.

```python
GatVarsCfg(
    ctrName="myapp",
    profile="prod",
    sepDk=True,
    customValue="anything",
)
```

## 3. myGat 상속 변경

기존:

```python
class myGat:
    def __init__(self, helper, **_):
        helper.configStr("yaml", config)
```

변경:

```python
class myGat(GatApp):
    gatConfig = GatAppCfg(
        name="myapp",
        type="app",
        # ...
    )

    def __init__(self, helper, **kwargs):
        super().__init__(helper, **kwargs)
```

`super().__init__()`이 `gatConfig`를 gat 런타임 설정으로 적용한다. 기존처럼 `helper.loadData(...)`가 필요하면 `super()` 호출 뒤에 둔다.

```python
class myGat(GatApp):
    gatConfig = GatAppCfg(...)

    def __init__(self, helper, **kwargs):
        super().__init__(helper, **kwargs)
        self.data = helper.loadData(".data.yml")
```

`buildTask`, `setupTask`, `deployPreTask`, `deployPostTask`, `getRunCmd`는 `GatApp`에 원형이 정의되어 있다. 필요한 메서드만 override한다.

```python
class myGat(GatApp):
    gatConfig = GatAppCfg(...)

    def buildTask(self, util, local, remote, **_):
        local.run("make build")

    def deployPostTask(self, util, local, remote, **_):
        remote.run("systemctl restart myapp")
```

런타임은 `hasTask()`로 override 여부를 확인한다. 따라서 base class에 원형이 있어도 subclass에서 구현한 hook만 실행된다.

## 4. YAML 필드 매핑

### root

YAML:

```yaml
name: myapp
type: app
podman: true
```

`GatAppCfg`:

```python
GatAppCfg(
    name="myapp",
    type="app",
    podman=True,
)
```

### serve

YAML:

```yaml
serve:
  patterns: ["*.rs", "*.py", "*.yml"]
```

`GatServeCfg.watch()`:

```python
serve=GatServeCfg.watch("*.rs", "*.py", "*.yml")
```

### deploy

YAML:

```yaml
deploy:
  strategy: zip
  followLinks: true
  maxRelease: 3
  include:
    - src: target/release/myapp
      dest: myapp
      exclude:
        - .git/*
    - cert
  exclude:
    - __pycache__
  sharedLinks: []
```

`GatDeployCfg.zip()`:

```python
deploy=GatDeployCfg.zip(
    include=[
        GatDeployIncludeCfg("target/release/myapp", "myapp", exclude=[".git/*"]),
        "cert",
    ],
    followLinks=True,
    exclude=["__pycache__"],
)
```

include 항목의 `exclude`도 `GatDeployIncludeCfg.fromDict(...)` 대신 생성자 인자로 표현한다.

```python
GatDeployIncludeCfg("../../coDart", "coDart", exclude=[".git/*"])
```

`GatDeployCfg.zip()`은 `strategy="zip"`, `followLinks=False`, `maxRelease=3`, `sharedLinks=[]`를 기본값으로 둔다. 기존 YAML의 `followLinks: true`를 유지해야 하면 명시한다.

```python
deploy=GatDeployCfg.zip(
    include=["dist"],
    followLinks=True,
    maxRelease=5,
)
```

### defaultVars

YAML:

```yaml
defaultVars:
  webCtr: web
  dbCtr: pg
  profile: dev
```

`GatVarsCfg`:

```python
defaultVars=GatVarsCfg(
    webCtr="web",
    dbCtr="pg",
    profile="dev",
)
```

`defaultVars`는 서버별 `vars`와 deep merge된다. 중첩 dict도 유지된다.

### servers

YAML:

```yaml
servers:
  - name: prod
    host: example.com
    port: 22
    id: ser
    deployRoot: /app
    vars:
      profile: prod
      ctrName: myapp
```

`GatServerCfg`:

```python
servers=[
    GatServerCfg(
        name="prod",
        host="example.com",
        port=22,
        id="ser",
        deployRoot="/app",
        vars=GatVarsCfg(
            profile="prod",
            ctrName="myapp",
        ),
    ),
]
```

`type: sys` 스크립트는 app 전용 섹션을 출력하지 않도록 `GatAppCfg.sys(...)`를 사용한다.

```python
class myGat(GatApp):
    gatConfig = GatAppCfg.sys(
        name="myhost",
        servers=[
            GatServerCfg(
                name="prod",
                host="example.com",
                port=22,
                id="ser",
                vars=GatVarsCfg(profile="prod"),
            ),
        ],
    )
```

## 5. 전체 예시

```python
config = """
name: myapp
type: app
podman: true

serve:
  patterns: ["*.py"]

deploy:
  strategy: zip
  followLinks: true
  maxRelease: 3
  include:
    - src: target/release/myapp
      dest: myapp
    - cert
  exclude:
    - __pycache__
  sharedLinks: []

defaultVars:
  webCtr: web
  profile: dev

servers:
  - name: prod
    host: example.com
    port: 22
    id: ser
    deployRoot: /app
    vars:
      profile: prod
      ctrName: myapp
"""

from gat.app_config import (
    GatAppCfg,
    GatDeployCfg,
    GatApp,
    GatDeployIncludeCfg,
    GatServeCfg,
    GatServerCfg,
    GatVarsCfg,
)


class myGat(GatApp):
    gatConfig = GatAppCfg(
        name="myapp",
        type="app",
        podman=True,
        serve=GatServeCfg.watch("*.py"),
        deploy=GatDeployCfg.zip(
            include=[
                GatDeployIncludeCfg("target/release/myapp", "myapp"),
                "cert",
            ],
            followLinks=True,
            exclude=["__pycache__"],
        ),
        defaultVars=GatVarsCfg(
            webCtr="web",
            profile="dev",
        ),
        servers=[
            GatServerCfg(
                name="prod",
                host="example.com",
                port=22,
                id="ser",
                deployRoot="/app",
                vars=GatVarsCfg(
                    profile="prod",
                    ctrName="myapp",
                ),
            ),
        ],
    )

    def __init__(self, helper, **kwargs):
        super().__init__(helper, **kwargs)
```

## 6. YAML fallback 유지

마이그레이션 중에는 기존 `config = """..."""`를 바로 지우지 말고 남겨둔다. 비교 테스트와 긴급 fallback에 사용한다.

YAML 방식으로 되돌리고 싶으면 `loadGatConfig()`를 override한다.

```python
class myGat(GatApp):
    gatConfig = GatAppCfg(...)

    def loadGatConfig(self):
        return self.configStr("yaml", config)
```

`self.configStr("yaml", config)`는 YAML을 `GatAppCfg`로 변환한 뒤 기존 gat 설정 적용 경로를 사용한다. 따라서 `defaultVars` 병합, `deploy.followLinks` 기본값 같은 후처리가 동일하게 적용된다.

기본 상태에서는 `loadGatConfig()` override를 두지 않는다. `gatConfig` 클래스 멤버만 사용하면 된다.

## 7. 검증 방법

### 1. YAML과 typed config 결과 비교

```python
myGat.gatConfig.assertMatchesYaml(config)
```

### 2. gat 런타임 적용 확인

```python
from gat.gat import Config, Helper

cfg = Config()
myGat(Helper(cfg))

assert cfg.name == "myapp"
assert cfg.servers[0].vars.ctrName == "myapp"
```

### 3. 서버별 defaultVars 병합 확인

```python
assert cfg.servers[0].vars.webCtr == "web"
assert cfg.servers[0].vars.profile == "prod"
```

### 4. 문법 확인

```bash
python3 -m py_compile gat_app.py
```

## 8. 마이그레이션 체크리스트

- [ ] `myGat`가 `GatApp`을 상속한다.
- [ ] `__init__()`에서 `super().__init__(helper, **kwargs)`를 먼저 호출한다.
- [ ] 기존 YAML `config`는 비교와 fallback용으로 남겨둔다.
- [ ] `myGat.gatConfig.assertMatchesYaml(config)`로 YAML과 typed config 결과가 같은지 확인한다.
- [ ] `defaultVars` 값이 각 서버 `vars`에 병합되는지 확인한다.
- [ ] `GatVarsCfg`의 프로젝트별 임의 키가 유지되는지 확인한다.
- [ ] 기존 `buildTask`, `setupTask`, `deployPreTask`, `deployPostTask`는 그대로 둔다.
- [ ] 직접 실행하지 말고 기존처럼 `gat SERVER deploy` 또는 `gat FILE SERVER run`으로 실행한다.

## 9. 주의할 점

### 설정 객체 역할

- `GatAppCfg`: gat_app.py에서 작성하는 typed 설정 원본
- `Config`: gat 런타임이 사용하는 실행 설정
- `GatVarsCfg`: 서버별 동적 변수 map
- `dic`: 기존 스크립트 호환용 mutable view

일반 gat_app.py에서는 `GatAppCfg`, `GatDeployCfg`, `GatDeployIncludeCfg`, `GatServeCfg`, `GatServerCfg`, `GatVarsCfg`만 직접 사용하면 된다. `Config`와 `dic`는 런타임/하위호환 영역이다.

### GatVarsCfg는 고정 스키마가 아니다

`GatVarsCfg`는 서버별 변수 map이다. 다음처럼 프로젝트마다 다른 키를 넣어도 된다.

```python
GatVarsCfg(
    ctrName="ec",
    httpApi="ec.inertry.com",
    sepDk=True,
    customNested={"enabled": True},
)
```

실행 중에도 map처럼 접근할 수 있다.

```python
remote.vars["newKey"] = "value"
del remote.vars["newKey"]
remote.vars.get("customNested.enabled")
```

### deploy include의 target alias

기존 YAML에서 `target`을 쓴 경우 새 설정에서는 가능하면 `dest`로 바꾼다.

```python
GatDeployIncludeCfg("../build", "build")
```

현재 런타임은 `target` alias도 읽지만, 새 코드에서는 `dest`가 명확하다.

include별 제외 패턴은 `exclude` 인자를 사용한다. dict를 직접 넘기는 `GatDeployIncludeCfg.fromDict(...)`는 YAML fallback을 파싱할 때만 필요하고, 새 typed 설정에서는 사용하지 않는다.

```python
GatDeployIncludeCfg("../coDart", "coDart", exclude=[".git/*"])
```

### 알 수 없는 필드

`GatAppCfg`, `GatDeployCfg`, `GatServerCfg`는 알 수 없는 필드를 `extra`로 유지한다. 즉 기존 YAML에 프로젝트 전용 필드가 있어도 roundtrip에서 보존된다.

```python
server = GatServerCfg(
    name="prod",
    host="example.com",
    port=22,
    id="ser",
    extra={"customServerFlag": True},
)
```

일반적으로는 known 필드로 표현할 수 없는 값만 `extra`에 둔다.

## 10. 권장 순서

1. 기존 `config` YAML을 그대로 둔다.
2. `GatApp` import와 상속만 먼저 적용한다.
3. YAML을 보고 `gatConfig = GatAppCfg(...)`를 작성한다.
4. `legacy.toDict() == myGat.gatConfig.toDict()` 테스트를 추가한다.
5. `super().__init__()` 이후 기존 데이터 로딩과 초기화 코드를 붙인다.
6. `py_compile`과 관련 unittest를 실행한다.
7. 실제 deploy/run 전에 dev 서버 대상으로 한 번 실행한다.
