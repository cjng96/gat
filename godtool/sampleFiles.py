sampleApp = """
# https://
config='''
config:
  name: sample
  type: app	# it's default

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

servers:
  - name: test
    host: test.com
    port: 22
    id: test			# ssh worker user id
    owner: engt   # opt, generated files owner
      # if it's not specified, you don't need sudo right
      # if you need the operation needed sudo right, should specify it.
    targetPath: ~/test	# deployment target path

'''

class myGod:
	def __init__(self, helper, **_):
		helper.configStr("yaml", config)	# helper.configFile("yaml", "god.yaml")

	def buildTask(self, util, local, **_):
		#local.gqlGen()
		local.goBuild()

	# it's default operation and you can override running cmd
	#def runTask(self, util, local, **_):
	#	return [util.config.config.name]

	def deployPreTask(self, util, remote, local, **_):
		#local.run("npm run build")
		pass

	def deployPostTask(self, util, remote, local, **_):
		#remote.pm2Register():
		#local.run("cd %%s/current && echo 'finish'" %% util.deployRoot)
		pass

"""

sampleSys = """
# https://
config='''
config:
  type: sys
  name: test	# hostname
s3:
  key: ${aws_key}
  secret: ${aws_secret}
servers:
  - name: test
    host: test.com
    port: 22
    id: test
	vars:
	  hello: test
'''

class myGod:
	def __init__(self, helper, **_):
		helper.configStr("yaml", config)	# helper.configFile("yaml", "god.yaml")

	def setupTask(self, cfg, util, local, remote, **_):
		#remote.pm2Register():
		#remote.run("cd %%s/current && echo 'finish'" %% remote.vars.deployRoot)

"""