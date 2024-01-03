sampleApp = """
# https://
config='''
type: app	# it's default
name: sample
#cmd: [ python3, sample.py ]

serve:
  patterns: [ "*.go", "*.json", "*.graphql" ]

deploy:
  strategy: zip
  maxRelease: 3
  include:
    #- "*"
    - "{{name}}"
    - config
    - pm2.json
    - src: ../build
      target: build
  exclude:
    - config/my.json
  sharedLinks:
    - config/my.json
  gitRepo: <your remote repo>

servers:
  - name: test
    host: test.com
    port: 22
    id: test      # ssh worker user id
    #dkName: con  #
    #dkId: test
    owner: engt   # opt, generated files owner
      # you don't need sudo right if it's not specified.
      # if you need the operation needed sudo right, should specify it.
    deployRoot: ~/test  # deployment target path
    gitBranch: <your remote repo branch>
'''

class myGod:
	def __init__(self, helper, **_):
		helper.configStr("yaml", config)	# helper.configFile("yaml", "god.yaml")

	def buildTask(self, util, local, **_):
		#local.gqlGen()
		local.goBuild()

	# it's default operation and you can override running cmd
	#def getRunCmd(self, util, local, **_):
	#	return [util.config.config.name]

	def deployPreTask(self, util, remote, local, **_):
		#print('deploy to {{server.name}}) # remote.server.name
		#local.run("npm run build")
		pass

	def deployPostTask(self, util, remote, local, **_):
		#remote.pm2Register():
		#local.run("cd {{deployRoot}}/current && echo 'finish'") # util.dic.deployRoot
		pass

"""

sampleSys = """
# https://
config='''
type: sys
name: test	# hostname

s3:
  key: ${aws_key}
  secret: ${aws_secret}

servers:
  - name: test
    host: test.com
    port: 22
		#dkName: name
    id: test
	vars:
	  hello: test
'''

class myGod:
	def __init__(self, helper, **_):
		helper.configStr("yaml", config)	# helper.configFile("yaml", "god.yaml")

	def setupTask(self, util, local, remote, **_):
		#remote.pm2Register():
		#remote.run("cd %%s/current && echo 'finish'" %% remote.vars.deployRoot)

"""
