sampleApp = '''
from gat.app_config import GatApp, GatAppCfg, GatDeployCfg, GatDeployIncludeCfg, GatServeCfg, GatServerCfg


class myGat(GatApp):
    gatConfig = GatAppCfg(
        name="sample",
        type="app",
        # cmd=["python3", "sample.py"],
        serve=GatServeCfg.watch("*.go", "*.json", "*.graphql"),
        deploy=GatDeployCfg.zip(
            include=[
                # "*",
                "{{name}}",
                "config",
                "pm2.json",
                GatDeployIncludeCfg("../build", "build"),
            ],
            exclude=["config/my.json"],
            sharedLinks=["config/my.json"],
            gitRepo="<your remote repo>",
        ),
        servers=[
            GatServerCfg(
                name="test",
                host="test.com",
                port=22,
                id="test",  # ssh worker user id
                # dkName="con",
                # dkId="test",
                owner="engt",  # opt, generated files owner
                # you don't need sudo right if it's not specified.
                # if you need the operation needed sudo right, should specify it.
                deployRoot="~/test",  # deployment target path
                extra={"gitBranch": "<your remote repo branch>"},
            ),
        ],
    )

    def buildTask(self, util, local, **_):
        #local.gqlGen()
        local.goBuild()

    # it's default operation and you can override running cmd
    #def getRunCmd(self, util, local, **_):
    #    return [util.config.config.name]

    def deployPreTask(self, util, remote, local, **_):
        #print('deploy to {{server.name}}) # remote.server.name
        #local.run("npm run build")
        pass

    def deployPostTask(self, util, remote, local, **_):
        #remote.pm2Register():
        #local.run("cd {{deployRoot}}/current && echo 'finish'") # util.dic.deployRoot
        pass
'''

sampleSys = '''
from gat.app_config import GatApp, GatAppCfg, GatServerCfg, GatVarsCfg


class myGat(GatApp):
    gatConfig = GatAppCfg.sys(
        name="sample",
        # s3={"key": "${aws_key}", "secret": "${aws_secret}"},
        servers=[
            GatServerCfg(
                name="test",
                host="test.com",
                port=22,
                id="test",  # ssh worker user id
                # dkName="name",
                vars=GatVarsCfg(hello="test"),
            ),
        ],
    )

    def setupTask(self, util, local, remote, **_):
        #remote.pm2Register():
        #remote.run("cd %%s/current && echo 'finish'" %% remote.vars.deployRoot)
        pass

'''
