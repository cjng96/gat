import unittest
import tempfile
from pathlib import Path

import yaml

from gat.app_config import (
    Config,
    GatDeployCfg,
    GatApp,
    GatAppCfg,
    GatDeployIncludeCfg,
    GatServeCfg,
    GatServerCfg,
    GatVarsCfg,
)
import gat.gat as gat_runtime
from gat.gat import Helper, Main, newGatScriptInstance, prepareLegacyScriptImports
from gat.sampleFiles import sampleApp, sampleSys
from gat.coCollection import Dict2


class FakeHelper:
    def __init__(self):
        self.cfgType = None
        self.rawConfig = None

    def configStr(self, cfgType, text):
        self.cfgType = cfgType
        self.rawConfig = text


class AppConfigTest(unittest.TestCase):
    def test_runtime_reexports_config_for_legacy_imports(self):
        self.assertIs(gat_runtime.Config, Config)

    def test_typed_config_roundtrips_yaml(self):
        raw = {
            "name": "demo",
            "type": "app",
            "podman": True,
            "serve": {"patterns": ["*.py"], "extraServe": 1},
            "deploy": {
                "strategy": "zip",
                "followLinks": True,
                "maxRelease": 5,
                "include": [{"src": "target/app", "dest": "app"}, "cert"],
                "exclude": ["__pycache__"],
                "sharedLinks": [],
                "extraDeploy": "keep",
            },
            "defaultVars": {"webCtr": "web", "customDefault": "keep"},
            "servers": [
                {
                    "name": "prod",
                    "host": "example.com",
                    "port": 22,
                    "id": "ser",
                    "deployRoot": "/app",
                    "owner": "svc",
                    "vars": {"profile": "prod", "ctrName": "demo", "customVar": "keep"},
                    "extraServer": True,
                }
            ],
            "extraRoot": "keep",
        }

        cfg = GatAppCfg.fromConfigStr("yaml", yaml.safe_dump(raw))

        self.assertEqual(cfg.name, "demo")
        self.assertEqual(cfg.serve.patterns, ["*.py"])
        self.assertEqual(cfg.deploy.include[0].src, "target/app")
        self.assertEqual(cfg.deploy.include[0].dest, "app")
        self.assertEqual(cfg.deploy.include[1], "cert")
        self.assertEqual(cfg.defaultVars.extra["customDefault"], "keep")
        self.assertEqual(cfg.servers[0].vars.extra["customVar"], "keep")
        self.assertEqual(cfg.toDict(), raw)

    def test_class_authored_config_applies_through_helper_configStr(self):
        cfg = GatAppCfg(
            name="demo",
            type="app",
            podman=True,
            serve=GatServeCfg(patterns=["*.rs"]),
            deploy=GatDeployCfg(
                strategy="zip",
                followLinks=True,
                maxRelease=3,
                include=[GatDeployIncludeCfg(src="target/app", dest="app")],
                exclude=[],
                sharedLinks=[],
            ),
            defaultVars=GatVarsCfg(webCtr="web"),
            servers=[
                GatServerCfg(
                    name="dev",
                    host="localhost",
                    port=22,
                    id="me",
                    deployRoot="/app",
                    vars=GatVarsCfg(profile="dev"),
                )
            ],
        )
        helper = FakeHelper()

        cfg.applyTo(helper)
        parsed = yaml.safe_load(helper.rawConfig)

        self.assertEqual(helper.cfgType, "yaml")
        self.assertEqual(parsed["name"], "demo")
        self.assertEqual(parsed["deploy"]["include"][0]["dest"], "app")
        self.assertEqual(parsed["servers"][0]["vars"]["profile"], "dev")

    def test_convenience_config_builders_keep_yaml_shape(self):
        cfg = GatAppCfg(
            name="demo",
            serve=GatServeCfg.watch("*.rs", "*.py"),
            deploy=GatDeployCfg.zip(
                include=[
                    {"src": "target/app", "dest": "app"},
                    "cert",
                ],
                exclude="__pycache__",
                sharedLinks=[],
                extraDeploy="keep",
            ),
            servers=[],
        )

        self.assertEqual(cfg.serve.patterns, ["*.rs", "*.py"])
        self.assertEqual(cfg.deploy.strategy, "zip")
        self.assertFalse(cfg.deploy.followLinks)
        self.assertEqual(cfg.deploy.maxRelease, 3)
        self.assertIsInstance(cfg.deploy.include[0], GatDeployIncludeCfg)
        self.assertEqual(cfg.deploy.include[0].src, "target/app")
        self.assertEqual(cfg.deploy.include[0].dest, "app")
        self.assertEqual(cfg.deploy.include[1], "cert")
        self.assertEqual(cfg.deploy.exclude, ["__pycache__"])
        self.assertEqual(cfg.toDict()["deploy"]["extraDeploy"], "keep")

    def test_include_config_accepts_exclude_member_variable(self):
        cfg = GatAppCfg(
            name="demo",
            deploy=GatDeployCfg.zip(
                include=[
                    GatDeployIncludeCfg("../../coDart", "coDart", exclude=[".git/*"]),
                ],
            ),
        )

        self.assertEqual(cfg.deploy.include[0].src, "../../coDart")
        self.assertEqual(cfg.deploy.include[0].dest, "coDart")
        self.assertEqual(cfg.deploy.include[0].exclude, [".git/*"])
        self.assertEqual(
            cfg.toDict()["deploy"]["include"][0],
            {"src": "../../coDart", "dest": "coDart", "exclude": [".git/*"]},
        )

    def test_zip_builder_can_enable_follow_links_explicitly(self):
        cfg = GatDeployCfg.zip(include=["dist"], followLinks=True)

        self.assertTrue(cfg.followLinks)

    def test_include_target_alias_normalizes_to_dest(self):
        cfg = GatAppCfg.fromDict(
            {
                "name": "demo",
                "deploy": {
                    "include": [
                        {
                            "src": "target/app",
                            "target": "app",
                        }
                    ]
                },
            }
        )

        self.assertEqual(cfg.deploy.include[0].dest, "app")
        self.assertEqual(
            cfg.toDict()["deploy"]["include"][0],
            {"src": "target/app", "dest": "app"},
        )

    def test_gat_app_config_can_assert_yaml_equivalence(self):
        yamlText = """
name: demo
type: app
podman: false
serve:
  patterns: []
deploy:
  strategy: zip
  followLinks: false
  maxRelease: 3
  include:
    - cert
  exclude: []
  sharedLinks: []
defaultVars: {}
servers: []
"""
        cfg = GatAppCfg(
            name="demo",
            type="app",
            podman=False,
            serve=GatServeCfg(),
            deploy=GatDeployCfg.zip(include=["cert"]),
            defaultVars=GatVarsCfg(),
            servers=[],
        )

        self.assertTrue(cfg.matchesYaml(yamlText))
        cfg.assertMatchesYaml(yamlText)

    def test_sys_builder_emits_only_sys_relevant_sections(self):
        cfg = GatAppCfg.sys(
            name="demo",
            servers=[
                GatServerCfg(
                    name="host",
                    host="127.0.0.1",
                    port=22,
                    id="me",
                    vars=GatVarsCfg(hello="test"),
                )
            ],
        )

        data = cfg.toDict()

        self.assertEqual(data["type"], "sys")
        self.assertNotIn("deploy", data)
        self.assertNotIn("serve", data)
        self.assertNotIn("defaultVars", data)
        self.assertEqual(data["servers"][0]["vars"]["hello"], "test")

    def test_gat_app_task_detection_uses_subclass_override(self):
        class DemoApp(GatApp):
            gatConfig = GatAppCfg(name="demo", servers=[])

            def buildTask(self, util, local, remote, **kwargs):
                return "built"

        helper = FakeHelper()
        app = DemoApp(helper)

        self.assertTrue(app.hasTask("buildTask"))
        self.assertFalse(app.hasTask("setupTask"))
        self.assertFalse(app.hasTask("deployPreTask"))
        self.assertFalse(app.hasTask("deployPostTask"))
        self.assertEqual(app.buildTask(None, None, None), "built")
        with self.assertRaises(NotImplementedError):
            app.setupTask(None, None, None)

    def test_gat_app_subclass_applies_class_config(self):
        class DemoApp(GatApp):
            gatConfig = GatAppCfg(
                name="demo",
                type="app",
                podman=True,
                serve=GatServeCfg(patterns=["*.rs"]),
                deploy=GatDeployCfg(),
                defaultVars=GatVarsCfg(webCtr="web"),
                servers=[
                    GatServerCfg(
                        name="dev",
                        host="localhost",
                        port=22,
                        id="me",
                        deployRoot="/app",
                    )
                ],
            )

        helper = FakeHelper()
        app = DemoApp(helper)
        parsed = yaml.safe_load(helper.rawConfig)

        self.assertIs(app.gatConfig, DemoApp.gatConfig)
        self.assertEqual(parsed["name"], "demo")
        self.assertEqual(parsed["defaultVars"]["webCtr"], "web")

    def test_typed_config_applies_directly_to_gat_config(self):
        cfg = GatAppCfg(
            name="demo",
            type="app",
            podman=True,
            serve=GatServeCfg(patterns=["*.rs"]),
            deploy=GatDeployCfg(),
            defaultVars=GatVarsCfg(webCtr="web"),
            servers=[
                GatServerCfg(
                    name="dev",
                    host="localhost",
                    port=22,
                    id="me",
                    deployRoot="/app",
                    vars=GatVarsCfg(profile="dev"),
                )
            ],
        )
        config = Config()
        helper = Helper(config)

        cfg.applyTo(helper)

        self.assertNotIsInstance(config, Dict2)
        self.assertIsInstance(config.gatConfig, GatAppCfg)
        self.assertEqual(config.name, "demo")
        self.assertIsInstance(config.deploy, GatDeployCfg)
        self.assertIsInstance(config.servers[0], GatServerCfg)
        self.assertIsInstance(config.servers[0].vars, GatVarsCfg)
        self.assertEqual(config.gatConfig.servers[0].vars.webCtr, "web")
        self.assertEqual(config.servers[0].vars.webCtr, "web")
        self.assertEqual(config.servers[0].vars.profile, "dev")
        self.assertFalse(config.deploy.followLinks)

    def test_legacy_yaml_configStr_stores_typed_config_inside_gat(self):
        config = Config()

        config.configStr(
            "yaml",
            """
name: yaml-demo
type: app
podman: true
serve:
  patterns: ["*.py"]
deploy:
  strategy: zip
  include: []
defaultVars:
  webCtr: web
servers:
  - name: dev
    host: localhost
    port: 22
    id: me
    deployRoot: /app
    vars:
      profile: dev
""",
        )

        self.assertIsInstance(config.gatConfig, GatAppCfg)
        self.assertEqual(config.gatConfig.name, "yaml-demo")
        self.assertIsInstance(config.deploy, GatDeployCfg)
        self.assertIsInstance(config.servers[0].vars, GatVarsCfg)
        self.assertEqual(config.servers[0].vars.webCtr, "web")
        self.assertEqual(config.servers[0].vars.profile, "dev")

    def test_sys_yaml_configStr_uses_typed_config_without_app_fields(self):
        config = Config()

        config.configStr(
            "yaml",
            """
name: sys-demo
type: sys
servers:
  - name: dev
    host: localhost
    port: 22
    id: me
    vars:
      hello: test
""",
        )

        self.assertIsInstance(config.gatConfig, GatAppCfg)
        self.assertEqual(config.gatConfig.type, "sys")
        self.assertEqual(config.servers[0].vars.hello, "test")
        self.assertNotIn("deploy", config)
        self.assertNotIn("serve", config)
        self.assertNotIn("defaultVars", config)
        self.assertEqual(config.get("deploy.strategy", "missing"), "missing")
        self.assertNotIn("deploy", config.toDict())
        self.assertNotIn("serve", config.toDict())
        self.assertNotIn("defaultVars", config.toDict())
        self.assertNotIn("deployRoot", config.gatConfig.servers[0].toDict())

    def test_default_vars_are_deep_merged_with_server_vars(self):
        config = Config()

        config.configStr(
            "yaml",
            """
name: nested-demo
type: app
defaultVars:
  nested:
    keep: default
    change: default
servers:
  - name: dev
    host: localhost
    port: 22
    id: me
    vars:
      nested:
        change: server
""",
        )

        nested = config.servers[0].vars.nested
        self.assertEqual(nested.keep, "default")
        self.assertEqual(nested.change, "server")

    def test_extra_nested_vars_keep_attribute_access(self):
        config = Config()

        config.configStr(
            "yaml",
            """
name: extra-demo
type: app
servers:
  - name: dev
    host: localhost
    port: 22
    id: me
    vars:
      custom:
        child: value
""",
        )

        self.assertEqual(config.servers[0].vars.custom.child, "value")
        self.assertEqual(config.servers[0].vars.get("custom.child"), "value")

    def test_dic_view_mutates_typed_config(self):
        config = Config()

        config.configStr(
            "yaml",
            """
name: dic-demo
type: app
servers:
  - name: dev
    host: localhost
    port: 22
    id: me
    vars: {}
""",
        )

        server = config.servers[0]
        server.dic["owner"] = "svc"
        server.vars.dic["nested"] = {"child": "value"}

        self.assertEqual(server.owner, "svc")
        self.assertEqual(server.vars.nested.child, "value")
        self.assertEqual(server.toDict()["owner"], "svc")
        self.assertEqual(server.toDict()["vars"]["nested"]["child"], "value")

    def test_dic_assignment_replaces_known_nested_config(self):
        config = Config()

        config.configStr(
            "yaml",
            """
name: dic-replace-demo
type: app
servers:
  - name: dev
    host: localhost
    port: 22
    id: me
    vars:
      profile: dev
      nested:
        keep: value
""",
        )

        server = config.servers[0]
        server.dic["vars"] = {}

        self.assertIsInstance(server.vars, GatVarsCfg)
        self.assertEqual(server.vars.toDict(), {})
        self.assertEqual(server.toDict()["vars"], {})

    def test_dict2_fill_is_normalized_before_to_dict(self):
        varsCfg = GatVarsCfg()

        varsCfg.fill(Dict2({"nested": {"child": "value"}}))

        self.assertEqual(varsCfg.nested.child, "value")
        self.assertEqual(varsCfg.toDict(), {"nested": {"child": "value"}})
        self.assertIn("child", yaml.safe_dump(varsCfg.toDict()))

    def test_vars_cfg_is_dynamic_map(self):
        varsCfg = GatVarsCfg(webCtr="web", sepDk=True, nested={"child": "value"})

        varsCfg["added"] = 1
        varsCfg.dic["fromDic"] = {"enabled": True}
        del varsCfg["sepDk"]
        popped = varsCfg.pop("added")
        dicPopped = varsCfg.dic.pop("fromDic")

        self.assertEqual(popped, 1)
        self.assertEqual(dicPopped.enabled, True)
        self.assertEqual(varsCfg.webCtr, "web")
        self.assertEqual(varsCfg.nested.child, "value")
        self.assertNotIn("fromDic", varsCfg)
        self.assertNotIn("sepDk", varsCfg)
        self.assertEqual(
            varsCfg.toDict(),
            {
                "webCtr": "web",
                "nested": {"child": "value"},
            },
        )

    def test_vars_cfg_preserves_data_key_and_none_values(self):
        varsCfg = GatVarsCfg(data="/data/sftp", net=None)

        self.assertEqual(varsCfg.data, "/data/sftp")
        self.assertIsNone(varsCfg.net)
        self.assertEqual(varsCfg.toDict(), {"data": "/data/sftp", "net": None})

    def test_none_values_override_default_vars(self):
        cfg = GatAppCfg.sys(
            name="demo",
            defaultVars=GatVarsCfg(net="pasta", dbMount="/db"),
            servers=[
                GatServerCfg(
                    name="dev",
                    host="localhost",
                    port=22,
                    id="me",
                    vars=GatVarsCfg(net=None, dbMount=None),
                )
            ],
        )

        varsDict = cfg.normalized().servers[0].vars.toDict()

        self.assertIsNone(varsDict["net"])
        self.assertIsNone(varsDict["dbMount"])

    def test_server_cfg_defaults_port_to_22(self):
        cfg = GatAppCfg.sys(
            name="demo",
            servers=[
                GatServerCfg(name="dev", host="localhost", id="me"),
                GatServerCfg("prod", "example.com", "deploy"),
                GatServerCfg("legacy", "legacy.example.com", 2200, "legacy-user"),
            ],
        )

        servers = cfg.toDict()["servers"]

        self.assertEqual(servers[0]["port"], 22)
        self.assertEqual(servers[0]["id"], "me")
        self.assertEqual(servers[1]["port"], 22)
        self.assertEqual(servers[1]["id"], "deploy")
        self.assertEqual(servers[2]["port"], 2200)
        self.assertEqual(servers[2]["id"], "legacy-user")

    def test_yaml_server_cfg_defaults_port_to_22(self):
        cfg = GatAppCfg.fromYaml(
            """
name: demo
type: sys
servers:
  - name: dev
    host: localhost
    id: me
"""
        )

        self.assertEqual(cfg.servers[0].port, 22)
        self.assertEqual(cfg.toDict()["servers"][0]["port"], 22)

    def test_config_dic_view_keeps_legacy_mutation_access(self):
        config = Config()

        config.dic["custom"] = "value"
        config.dic["nested"] = Dict2({"child": "value"})

        self.assertEqual(config.custom, "value")
        self.assertEqual(config["custom"], "value")
        self.assertEqual(config.toDict()["custom"], "value")
        self.assertEqual(config.toDict()["nested"], {"child": "value"})
        self.assertIn("child", yaml.safe_dump(config.toDict()))

    def test_runtime_mutation_does_not_modify_source_gat_config(self):
        cfg = GatAppCfg(
            name="demo",
            deploy=GatDeployCfg(strategy="zip"),
            servers=[
                GatServerCfg(
                    name="dev",
                    host="localhost",
                    port=22,
                    id="me",
                    deployRoot="/app",
                )
            ],
        )
        config = Config()

        config.configApp(cfg)
        config.deploy.strategy = "git"
        config.srcPath = "./clone"

        self.assertEqual(config.deploy.strategy, "git")
        self.assertEqual(config.srcPath, "./clone")
        self.assertEqual(cfg.deploy.strategy, "zip")
        self.assertEqual(config.toDict()["deploy"]["strategy"], "git")

    def test_gat_app_subclass_can_load_yaml_through_configStr(self):
        class DemoYamlApp(GatApp):
            gatConfig = GatAppCfg(
                name="default",
                type="app",
                podman=True,
                serve=GatServeCfg(),
                deploy=GatDeployCfg(),
                defaultVars=GatVarsCfg(),
                servers=[],
            )

            def loadGatConfig(self):
                return self.configStr(
                    "yaml",
                    """
name: yaml-demo
type: app
podman: true
serve:
  patterns: []
deploy:
  strategy: zip
  include: []
defaultVars:
  webCtr: web
servers: []
""",
                )

        helper = FakeHelper()
        app = DemoYamlApp(helper)
        parsed = yaml.safe_load(helper.rawConfig)

        self.assertIsInstance(app.gatConfig, GatAppCfg)
        self.assertEqual(app.gatConfig.name, "yaml-demo")
        self.assertEqual(parsed["name"], "yaml-demo")

    def test_generated_sample_configs_still_load(self):
        namespace = {}
        exec(sampleApp, namespace)
        appConfig = Config()
        namespace["myGat"](Helper(appConfig))

        namespace = {}
        exec(sampleSys, namespace)
        sysConfig = Config()
        namespace["myGat"](Helper(sysConfig))

        self.assertEqual(appConfig.name, "sample")
        self.assertIn("deploy", appConfig)
        self.assertEqual(sysConfig.type, "sys")
        self.assertNotIn("deploy", sysConfig)

    def test_include_target_alias_still_maps_to_deploy_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "asset.txt"
            src.write_text("asset")
            added = []

            Main().targetFileListProd(
                [{"src": str(src), "target": "build/asset.txt"}],
                [],
                lambda filePath, destPath: added.append((filePath, destPath)),
            )

        self.assertEqual(added, [(str(src), "build/asset.txt")])

    def test_legacy_config_root_is_flattened(self):
        config = Config()

        config.configStr(
            "yaml",
            """
config:
  name: ubuntu
  type: sys
servers:
  - name: local
    host: 127.0.0.1
    port: 22
    id: me
""",
        )

        self.assertEqual(config.name, "ubuntu")
        self.assertEqual(config.type, "sys")
        self.assertEqual(config.servers[0].name, "local")

    def test_legacy_string_vars_are_parsed(self):
        config = Config()

        config.configStr(
            "yaml",
            """
name: legacy-vars
type: sys
servers:
  - name: host
    host: 127.0.0.1
    port: 22
    id: me
    vars:
      test = 1
""",
        )

        self.assertEqual(config.servers[0].vars.test, 1)

    def test_my_gat_must_inherit_gat_app(self):
        class PlainGat:
            def __init__(self, helper, **_):
                self.helper = helper

        helper = FakeHelper()

        with self.assertRaises(AttributeError):
            newGatScriptInstance(type("Module", (), {}), helper)

        with self.assertRaises(TypeError):
            newGatScriptInstance(type("Module", (), {"myGat": PlainGat}), helper)

        class ValidGat(GatApp):
            def __init__(self, helper, **_):
                self.helper = helper

        instance = newGatScriptInstance(type("Module", (), {"myGat": ValidGat}), helper)

        self.assertIsInstance(instance, ValidGat)
        self.assertIs(instance.helper, helper)

    def test_legacy_myutil_import_alias_is_available(self):
        namespace = {}

        prepareLegacyScriptImports()
        exec("import myutil as my\nvalue = hasattr(my, 'scriptDocker')", namespace)

        self.assertTrue(namespace["value"])


if __name__ == "__main__":
    unittest.main()
