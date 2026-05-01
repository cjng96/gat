from __future__ import annotations

from collections.abc import ItemsView, Iterator, KeysView, Mapping, ValuesView
from dataclasses import dataclass, field, fields, replace
from pathlib import Path
from typing import Any, Self

import yaml


_MISSING = object()

JsonDict = dict[str, Any]
JsonMap = Mapping[str, Any]


class GatCfgDictView:
    def __init__(self, owner: Any) -> None:
        self.owner = owner

    def __contains__(self, key: str) -> bool:
        return key in self.owner

    def __getitem__(self, key: str) -> Any:
        return self.owner[key]

    def __setitem__(self, key: str, value: Any) -> None:
        if hasattr(self.owner, "_setValue"):
            self.owner._setValue(key, value, mergeKnown=False)
        else:
            self.owner[key] = value

    def __delitem__(self, key: str) -> None:
        del self.owner[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.owner)

    def __len__(self) -> int:
        return len(self.owner.toDict())

    def get(self, key: str, default: Any = None) -> Any:
        return self.owner.get(key, default)

    def items(self) -> ItemsView[str, Any]:
        return self.owner.items()

    def keys(self) -> KeysView[str]:
        return self.owner.toDict().keys()

    def values(self) -> ValuesView[Any]:
        return self.owner.toDict().values()

    def pop(self, key: str, default: Any = _MISSING) -> Any:
        try:
            value = self.owner[key]
        except KeyError:
            if default is _MISSING:
                raise
            return default
        del self.owner[key]
        return value

    def update(self, data: JsonMap | None = None, **kwargs: Any) -> None:
        for key, value in (data or {}).items():
            self[key] = value
        for key, value in kwargs.items():
            self[key] = value

    def toDict(self) -> JsonDict:
        return self.owner.toDict()


class GatDynamicCfg:
    def __init__(self, data: Any = None) -> None:
        object.__setattr__(self, "_data", {})
        self.fill(data or {})

    def __getattr__(self, name: str) -> Any:
        data = object.__getattribute__(self, "_data")
        if name in data:
            return data[name]
        raise AttributeError(name)

    def __setattr__(self, name: str, value: Any) -> None:
        self._data[name] = _runtimeValue(value)

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._data[key] = _runtimeValue(value)

    def __delitem__(self, key: str) -> None:
        del self._data[key]

    def __delattr__(self, name: str) -> None:
        data = object.__getattribute__(self, "_data")
        if name in data:
            del data[name]
            return
        raise AttributeError(name)

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __repr__(self) -> str:
        return str(self.toDict())

    @property
    def dic(self) -> GatCfgDictView:
        return GatCfgDictView(self)

    @property
    def extra(self) -> JsonDict:
        return self._data

    def get(self, name: str, default: Any = None) -> Any:
        current = self
        for item in name.split("."):
            current = _getPathItem(current, item, _MISSING)
            if current is _MISSING:
                return default
        return current

    def fill(self, data: Any) -> None:
        if isinstance(data, GatDynamicCfg):
            data = data.toDict()
        elif _hasJsonValue(data):
            data = data.toJson()
        for key, value in (data or {}).items():
            self._data[key] = _runtimeValue(value)

    def items(self) -> ItemsView[str, Any]:
        return self._data.items()

    def keys(self) -> KeysView[str]:
        return self._data.keys()

    def values(self) -> ValuesView[Any]:
        return self._data.values()

    def pop(self, key: str, default: Any = _MISSING) -> Any:
        if default is _MISSING:
            return self._data.pop(key)
        return self._data.pop(key, default)

    def update(self, data: Any = None, **kwargs: Any) -> None:
        self.fill(data or {})
        self.fill(kwargs)

    def clear(self) -> None:
        self._data.clear()

    def setdefault(self, key: str, default: Any = None) -> Any:
        if key not in self._data:
            self._data[key] = _runtimeValue(default)
        return self._data[key]

    def toDict(self) -> JsonDict:
        return {key: _toDictValue(value) for key, value in self._data.items()}

    def toJson(self) -> JsonDict:
        return self.toDict()


def _knownExtra(data: JsonMap, names: set[str]) -> JsonDict:
    return {key: _runtimeValue(value) for key, value in data.items() if key not in names}


def _putIfNotNone(data: JsonDict, key: str, value: Any) -> None:
    if value is not None:
        data[key] = value


def _listValue(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _toDictValue(value: Any) -> Any:
    if isinstance(value, GatCfgMixin):
        return value.toDict()
    if isinstance(value, GatDynamicCfg):
        return value.toDict()
    if _hasJsonValue(value):
        return _toDictValue(value.toJson())
    if isinstance(value, list):
        return [_toDictValue(item) for item in value]
    if isinstance(value, dict):
        return {key: _toDictValue(item) for key, item in value.items()}
    return value


def _runtimeValue(value: Any) -> Any:
    if isinstance(value, (GatCfgMixin, GatDynamicCfg)):
        return value
    if _hasJsonValue(value):
        value = value.toJson()
    if isinstance(value, dict):
        return GatDynamicCfg(value)
    if isinstance(value, list):
        return [_runtimeValue(item) for item in value]
    return value


def _hasJsonValue(value: Any) -> bool:
    return hasattr(value, "toJson") and not isinstance(value, (str, bytes))


def _deepMerge(base: JsonMap | None, override: JsonMap | None) -> JsonDict:
    merged = {key: _toDictValue(value) for key, value in (base or {}).items()}
    for key, value in (override or {}).items():
        value = _toDictValue(value)
        if isinstance(merged.get(key), dict) and isinstance(value, dict):
            merged[key] = _deepMerge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _yamlSafeLoadConfig(text: str) -> JsonDict:
    try:
        return yaml.safe_load(text) or {}
    except yaml.YAMLError:
        if "\t" not in text:
            raise
        return yaml.safe_load(text.replace("\t", "  ")) or {}


def _flattenLegacyConfigRoot(data: Any) -> Any:
    if isinstance(data, dict) and isinstance(data.get("config"), dict):
        nested = dict(data["config"])
        nested.update({key: value for key, value in data.items() if key != "config"})
        return nested
    return data


def _dictFromLegacyVarsString(text: str) -> JsonDict:
    data = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line and ":" not in line.split("=", 1)[0]:
            key, value = line.split("=", 1)
        elif ":" in line:
            key, value = line.split(":", 1)
        else:
            continue
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        try:
            data[key] = yaml.safe_load(value) if value else ""
        except yaml.YAMLError:
            data[key] = value
    return data


class GatCfgMixin:
    @classmethod
    def _fieldNames(cls: type[Any]) -> set[str]:
        return {item.name for item in fields(cls)}

    def _knownFieldNames(self) -> set[str]:
        return self._fieldNames() - {"extra", "_presentKeys"}

    def __getattr__(self, name: str) -> Any:
        extra = self.__dict__.get("extra")
        if isinstance(extra, dict) and name in extra:
            return extra[name]
        raise AttributeError(name)

    def _isFieldPresent(self, key: str) -> bool:
        presentKeys = getattr(self, "_presentKeys", None)
        return presentKeys is None or key in presentKeys

    def _markPresent(self, key: str) -> None:
        presentKeys = getattr(self, "_presentKeys", None)
        if presentKeys is not None:
            presentKeys.add(key)

    @property
    def dic(self) -> GatCfgDictView:
        return GatCfgDictView(self)

    def __contains__(self, key: str) -> bool:
        return self.get(key, _MISSING) is not _MISSING

    def __getitem__(self, key: str) -> Any:
        value = self.get(key, _MISSING)
        if value is _MISSING:
            raise KeyError(key)
        return value

    def __setitem__(self, key: str, value: Any) -> None:
        self._setValue(key, value, mergeKnown=False)

    def __delitem__(self, key: str) -> None:
        if key in self._knownFieldNames():
            setattr(self, key, None)
        elif key in self.extra:
            del self.extra[key]
        else:
            raise KeyError(key)
        presentKeys = getattr(self, "_presentKeys", None)
        if presentKeys is not None:
            presentKeys.discard(key)

    def __iter__(self) -> Iterator[str]:
        return iter(self.toDict())

    def items(self) -> ItemsView[str, Any]:
        return self.toDict().items()

    def toJson(self) -> JsonDict:
        return self.toDict()

    def get(self, name: str, default: Any = None) -> Any:
        current = self
        for item in name.split("."):
            current = _getPathItem(current, item, _MISSING)
            if current is _MISSING:
                return default
        return current

    def fill(self, data: Any) -> None:
        if isinstance(data, GatCfgMixin):
            data = data.toDict()
        elif _hasJsonValue(data):
            data = data.toJson()
        for key, value in (data or {}).items():
            self._setValue(key, value, mergeKnown=True)

    def _setValue(self, key: str, value: Any, mergeKnown: bool = True) -> None:
        if key in self._knownFieldNames():
            current = getattr(self, key, None)
            if mergeKnown and isinstance(current, GatCfgMixin) and isinstance(value, dict):
                current.fill(value)
            else:
                setattr(self, key, self._coerceFieldValue(key, value))
        else:
            self.extra[key] = _runtimeValue(value)
        self._markPresent(key)

    def _coerceFieldValue(self, _key: str, value: Any) -> Any:
        return _runtimeValue(value)


def _getPathItem(current: Any, key: str, default: Any) -> Any:
    if isinstance(current, Config):
        if key not in current._presentKeys:
            return default
        if hasattr(current, key):
            return getattr(current, key)
        return current.extra.get(key, default)
    if isinstance(current, GatCfgMixin):
        if key in current._knownFieldNames():
            if not current._isFieldPresent(key):
                return default
            value = getattr(current, key)
            return value if value is not None else default
        return current.extra.get(key, default)
    if isinstance(current, GatDynamicCfg):
        return current._data.get(key, default)
    if isinstance(current, dict):
        return current.get(key, default)
    if hasattr(current, "__contains__") and hasattr(current, "__getitem__"):
        try:
            return current[key] if key in current else default
        except (KeyError, TypeError):
            return default
    return getattr(current, key, default)


class Config:
    def __init__(self) -> None:
        object.__setattr__(self, "_trackPresent", False)
        object.__setattr__(self, "gatConfig", None)
        object.__setattr__(self, "srcPath", ".")
        object.__setattr__(self, "extra", {})
        object.__setattr__(self, "_presentKeys", {"srcPath"})
        object.__setattr__(self, "_trackPresent", True)

    @property
    def dic(self) -> GatCfgDictView:
        return GatCfgDictView(self)

    def configStr(self, cfgType: str, text: str) -> None:
        self.configApp(GatAppCfg.fromConfigStr(cfgType, text))

    def configFile(self, cfgType: str, path: str | Path) -> None:
        with open(path, "r") as fp:
            self.configStr(cfgType, fp.read())

    def configApp(self, cfg: "GatAppCfg") -> None:
        if not isinstance(cfg, GatAppCfg):
            raise TypeError("configApp requires GatAppCfg")

        object.__setattr__(self, "gatConfig", cfg.normalized())
        self._loadConfig(self.gatConfig)
        self._postProcess()

    def configServerGet(self, name: str) -> "GatServerCfg":
        for server in self.servers:
            if server.name == name:
                print("deploy: selected server - ", server)
                return server

        print(self)
        raise Exception(f"Not found server[{name}]")

    def configGet(self) -> Self:
        return self

    def _loadConfig(self, cfg: "GatAppCfg") -> None:
        object.__setattr__(self, "_trackPresent", False)
        object.__setattr__(self, "name", cfg.name)
        object.__setattr__(self, "type", cfg.type)
        object.__setattr__(self, "podman", cfg.podman)
        object.__setattr__(self, "serve", cfg.serve)
        object.__setattr__(self, "deploy", cfg.deploy)
        object.__setattr__(self, "defaultVars", cfg.defaultVars)
        object.__setattr__(self, "servers", cfg.servers)
        object.__setattr__(self, "extra", {})
        for key, value in cfg.extra.items():
            value = _runtimeValue(value)
            self.extra[key] = value
            object.__setattr__(self, key, value)
        presentKeys = cfg.presentKeys()
        presentKeys.add("srcPath")
        object.__setattr__(self, "_presentKeys", presentKeys)
        object.__setattr__(self, "_trackPresent", True)

    def _postProcess(self) -> None:
        if "deploy" in self and self.type == "app" and self.deploy.followLinks is None:
            self.deploy.followLinks = False

    def get(self, name: str, default: Any = None) -> Any:
        current = self
        for item in name.split("."):
            current = _getPathItem(current, item, _MISSING)
            if current is _MISSING:
                return default
        return current

    def toDict(self) -> JsonDict:
        data = {key: _toDictValue(value) for key, value in self.extra.items()}
        if self.gatConfig is not None:
            data.update(self.gatConfig.toDict())
        data["srcPath"] = self.srcPath
        for key, value in self.__dict__.items():
            if key in {"gatConfig", "extra"} or key.startswith("_"):
                continue
            if key not in self._presentKeys:
                continue
            data[key] = _toDictValue(value)
        return data

    def items(self) -> ItemsView[str, Any]:
        return self.toDict().items()

    def __contains__(self, key: str) -> bool:
        return key in self._presentKeys

    def __getitem__(self, key: str) -> Any:
        value = self.get(key, _MISSING)
        if value is _MISSING:
            raise KeyError(key)
        return value

    def __setitem__(self, key: str, value: Any) -> None:
        setattr(self, key, _runtimeValue(value))
        if key in self.extra:
            self.extra[key] = getattr(self, key)

    def __delitem__(self, key: str) -> None:
        if key not in self._presentKeys:
            raise KeyError(key)
        self._presentKeys.remove(key)
        self.extra.pop(key, None)
        if key in self.__dict__:
            object.__delattr__(self, key)

    def __setattr__(self, key: str, value: Any) -> None:
        object.__setattr__(self, key, value)
        if (
            self.__dict__.get("_trackPresent", False)
            and not key.startswith("_")
            and key not in {"gatConfig", "extra"}
        ):
            self._presentKeys.add(key)

    def __getattr__(self, key: str) -> Any:
        if "extra" in self.__dict__ and key in self.extra:
            return self.extra[key]
        raise AttributeError(key)

    def __iter__(self) -> Iterator[str]:
        return iter(self.toDict())

    def __repr__(self) -> str:
        return str(self.toDict())


class GatVarsCfg(GatDynamicCfg):
    def __init__(self, data: Any = None, **kwargs: Any) -> None:
        object.__setattr__(self, "_data", {})
        self.fill(data or {})
        self.fill({key: value for key, value in kwargs.items() if value is not None})

    @classmethod
    def fromDict(cls: type[Self], data: Any) -> Self:
        if isinstance(data, cls):
            return data
        if isinstance(data, str):
            data = _dictFromLegacyVarsString(data)
        return cls(data or {})

    def fill(self, data: Any) -> None:
        if isinstance(data, str):
            data = _dictFromLegacyVarsString(data)
        super().fill(data)


@dataclass
class GatServeCfg(GatCfgMixin):
    patterns: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def watch(cls: type[Self], *patterns: str | list[str] | tuple[str, ...], **kwargs: Any) -> Self:
        if len(patterns) == 1 and isinstance(patterns[0], (list, tuple)):
            patterns = tuple(patterns[0])
        data = {"patterns": list(patterns)}
        data.update(kwargs)
        return cls.fromDict(data)

    @classmethod
    def fromDict(cls: type[Self], data: Any) -> Self:
        if isinstance(data, cls):
            return data
        data = data or {}
        return cls(
            patterns=list(data.get("patterns", [])),
            extra=_knownExtra(data, {"patterns"}),
        )

    def toDict(self) -> JsonDict:
        return {**_toDictValue(self.extra), "patterns": list(self.patterns)}


@dataclass
class GatDeployIncludeCfg(GatCfgMixin):
    src: str
    dest: str | None = None
    exclude: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def fromDict(cls: type[Self], data: Any) -> Self:
        if isinstance(data, cls):
            return data
        return cls(
            src=data["src"],
            dest=data.get("dest", data.get("target")),
            exclude=list(data.get("exclude", [])),
            extra=_knownExtra(data, {"src", "dest", "target", "exclude"}),
        )

    def toDict(self) -> JsonDict:
        data = _toDictValue(self.extra)
        data["src"] = self.src
        _putIfNotNone(data, "dest", self.dest)
        if self.exclude:
            data["exclude"] = list(self.exclude)
        return data

    def _coerceFieldValue(self, key: str, value: Any) -> Any:
        if key == "exclude":
            return list(value or [])
        return _runtimeValue(value)


@dataclass
class GatDeployCfg(GatCfgMixin):
    strategy: str = "zip"
    followLinks: bool = False
    maxRelease: int = 3
    include: list[str | GatDeployIncludeCfg] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    sharedLinks: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def zip(
        cls: type[Self],
        include: Any = None,
        exclude: Any = None,
        sharedLinks: Any = None,
        followLinks: bool = False,
        maxRelease: int = 3,
        **kwargs: Any,
    ) -> Self:
        data = dict(kwargs)
        data.update(
            {
                "strategy": "zip",
                "followLinks": followLinks,
                "maxRelease": maxRelease,
                "include": _listValue(include),
                "exclude": _listValue(exclude),
                "sharedLinks": _listValue(sharedLinks),
            }
        )
        return cls.fromDict(data)

    @classmethod
    def fromDict(cls: type[Self], data: Any) -> Self:
        if isinstance(data, cls):
            return data
        data = data or {}
        include = []
        for item in data.get("include", []):
            include.append(GatDeployIncludeCfg.fromDict(item) if isinstance(item, dict) else item)
        names = {"strategy", "followLinks", "maxRelease", "include", "exclude", "sharedLinks"}
        return cls(
            strategy=data.get("strategy", "zip"),
            followLinks=data.get("followLinks", False),
            maxRelease=data.get("maxRelease", 3),
            include=include,
            exclude=list(data.get("exclude", [])),
            sharedLinks=list(data.get("sharedLinks", [])),
            extra=_knownExtra(data, names),
        )

    def toDict(self) -> JsonDict:
        data = _toDictValue(self.extra)
        data.update(
            {
                "strategy": self.strategy,
                "followLinks": self.followLinks,
                "maxRelease": self.maxRelease,
                "include": [
                    item.toDict() if isinstance(item, GatDeployIncludeCfg) else item
                    for item in self.include
                ],
                "exclude": list(self.exclude),
                "sharedLinks": list(self.sharedLinks),
            }
        )
        return data

    def _coerceFieldValue(self, key: str, value: Any) -> Any:
        if key == "include":
            return [
                GatDeployIncludeCfg.fromDict(item) if isinstance(item, dict) else item
                for item in value
            ]
        if key in {"exclude", "sharedLinks"}:
            return list(value or [])
        return _runtimeValue(value)


@dataclass
class GatServerCfg(GatCfgMixin):
    name: str
    host: str
    port: int
    id: str
    deployRoot: str | None = None
    vars: GatVarsCfg = field(default_factory=GatVarsCfg)
    dkName: str | None = None
    dkId: str | None = None
    owner: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def fromDict(cls: type[Self], data: Any) -> Self:
        if isinstance(data, cls):
            return data
        names = {"name", "host", "port", "id", "deployRoot", "vars", "dkName", "dkId", "owner"}
        return cls(
            name=data["name"],
            host=data["host"],
            port=data["port"],
            id=data["id"],
            deployRoot=data.get("deployRoot"),
            vars=GatVarsCfg.fromDict(data.get("vars", {})),
            dkName=data.get("dkName"),
            dkId=data.get("dkId"),
            owner=data.get("owner"),
            extra=_knownExtra(data, names),
        )

    def toDict(self) -> JsonDict:
        data = _toDictValue(self.extra)
        data.update(
            {
                "name": self.name,
                "host": self.host,
                "port": self.port,
                "id": self.id,
                "vars": self.vars.toDict(),
            }
        )
        _putIfNotNone(data, "deployRoot", self.deployRoot)
        _putIfNotNone(data, "dkName", self.dkName)
        _putIfNotNone(data, "dkId", self.dkId)
        _putIfNotNone(data, "owner", self.owner)
        return data

    def _coerceFieldValue(self, key: str, value: Any) -> Any:
        if key == "vars":
            return GatVarsCfg.fromDict(value)
        return _runtimeValue(value)


@dataclass
class GatAppCfg(GatCfgMixin):
    name: str
    type: str = "app"
    podman: bool = False
    serve: GatServeCfg = field(default_factory=GatServeCfg)
    deploy: GatDeployCfg = field(default_factory=GatDeployCfg)
    defaultVars: GatVarsCfg = field(default_factory=GatVarsCfg)
    servers: list[GatServerCfg] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)
    _presentKeys: set[str] | None = field(default=None, repr=False, compare=False)

    @classmethod
    def fromDict(cls: type[Self], data: Any) -> Self:
        if isinstance(data, cls):
            return data
        data = _flattenLegacyConfigRoot(data)
        names = {"name", "type", "podman", "serve", "deploy", "defaultVars", "servers"}
        return cls(
            name=data["name"],
            type=data.get("type", "app"),
            podman=data.get("podman", False),
            serve=GatServeCfg.fromDict(data.get("serve", {})),
            deploy=GatDeployCfg.fromDict(data.get("deploy", {})),
            defaultVars=GatVarsCfg.fromDict(data.get("defaultVars", {})),
            servers=[GatServerCfg.fromDict(item) for item in data.get("servers", [])],
            extra=_knownExtra(data, names),
            _presentKeys=set(data.keys()),
        )

    @classmethod
    def fromConfigStr(cls: type[Self], cfgType: str, text: str) -> Self:
        if cfgType != "yaml":
            raise ValueError(f"unknown config type[{cfgType}]")
        return cls.fromDict(_yamlSafeLoadConfig(text))

    @classmethod
    def fromYaml(cls: type[Self], text: str) -> Self:
        return cls.fromConfigStr("yaml", text)

    @classmethod
    def sys(
        cls: type[Self],
        name: str,
        servers: list["GatServerCfg"] | list[JsonMap] | None = None,
        **kwargs: Any,
    ) -> Self:
        data = dict(kwargs)
        data.update({"name": name, "type": "sys", "servers": servers or []})
        return cls.fromDict(data)

    def toDict(self) -> JsonDict:
        data = _toDictValue(self.extra)
        data["name"] = self.name
        if self._shouldEmit("type"):
            data["type"] = self.type
        if self._shouldEmit("podman"):
            data["podman"] = self.podman
        if self._shouldEmit("serve"):
            data["serve"] = self.serve.toDict()
        if self._shouldEmit("deploy"):
            data["deploy"] = self.deploy.toDict()
        if self._shouldEmit("defaultVars"):
            data["defaultVars"] = self.defaultVars.toDict()
        if self._shouldEmit("servers"):
            data["servers"] = [server.toDict() for server in self.servers]
        return data

    def toYaml(self) -> str:
        return yaml.safe_dump(self.toDict(), sort_keys=False, allow_unicode=True)

    def matchesYaml(self, text: str) -> bool:
        return self.toDict() == self.fromYaml(text).toDict()

    def assertMatchesYaml(self, text: str) -> None:
        if not self.matchesYaml(text):
            raise AssertionError("GatAppCfg does not match yaml config")

    def normalized(self) -> Self:
        cfg = GatAppCfg.fromDict(self.toDict())
        servers = []
        for server in cfg.servers:
            mergedVars = _deepMerge(cfg.defaultVars.toDict(), server.vars.toDict())
            servers.append(replace(server, vars=GatVarsCfg.fromDict(mergedVars)))
        return replace(cfg, servers=servers)

    def presentKeys(self) -> set[str]:
        if self._presentKeys is None:
            return set(self.toDict().keys())
        return set(self._presentKeys)

    def _shouldEmit(self, key: str) -> bool:
        return self._presentKeys is None or key in self._presentKeys

    def _coerceFieldValue(self, key: str, value: Any) -> Any:
        if key == "serve":
            return GatServeCfg.fromDict(value)
        if key == "deploy":
            return GatDeployCfg.fromDict(value)
        if key == "defaultVars":
            return GatVarsCfg.fromDict(value)
        if key == "servers":
            return [GatServerCfg.fromDict(item) for item in value]
        return _runtimeValue(value)

    def applyTo(self, helper: Any) -> None:
        if hasattr(helper, "configApp"):
            helper.configApp(self)
        else:
            helper.configStr("yaml", self.toYaml())


class GatApp:
    gatConfig: GatAppCfg | None = None

    def __init__(self, helper: Any, **_: Any) -> None:
        self.helper = helper
        self.gatConfig = self.loadGatConfig()
        self.applyConfig()

    def loadGatConfig(self) -> GatAppCfg:
        if self.__class__.gatConfig is None:
            raise ValueError(f"{self.__class__.__name__}.gatConfig is required")
        return self.__class__.gatConfig

    def configStr(self, cfgType: str, text: str) -> GatAppCfg:
        self.gatConfig = GatAppCfg.fromConfigStr(cfgType, text)
        return self.gatConfig

    def applyConfig(self, helper: Any = None) -> None:
        if helper is not None:
            self.helper = helper
        self.gatConfig.applyTo(self.helper)

    def hasTask(self, name: str) -> bool:
        return getattr(type(self), name, None) is not getattr(GatApp, name, None)

    def getRunCmd(self, util: Any, local: Any, remote: Any, **kwargs: Any) -> None:
        return None

    def buildTask(self, util: Any, local: Any, remote: Any, **kwargs: Any) -> None:
        raise NotImplementedError("buildTask must be overridden in myGat")

    def setupTask(self, util: Any, local: Any, remote: Any, **kwargs: Any) -> None:
        raise NotImplementedError("setupTask must be overridden in myGat")

    def deployPreTask(self, util: Any, local: Any, remote: Any, **kwargs: Any) -> None:
        pass

    def deployPostTask(self, util: Any, local: Any, remote: Any, **kwargs: Any) -> None:
        pass
