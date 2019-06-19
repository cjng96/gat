sampleApp = """
config='''
config:
  name: test
  type: app

serve:
  patterns:
    - "*.go"
    - "*.json"
    - "*.graphql"

deploy:
  strategy: zip
  #owner: test	# all generated files's owner is set it. if owner is specified, servers/id should be the user who can use sudo command due to sudo cmd
  maxRelease: 3
  include:
	#- "*"
	- {{name}}
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
    id: test
    targetPath: ~/test
'''

class myGod:
	def __init__(self, helper, **kwargs):
		helper.configStr("yaml", config)	# helper.configFile("yaml", "god.yaml")

	def buildTask(self, util, local, **kwargs):
		#local.dbGqlGen():
		#local.goBuild(args)


	def deployPreTask(self, util, local, remote, **kwargs):
		#local.run("npm run build")

	def deployPostTask(self, util, local, remote, **kwargs):
		#remote.pm2Register():
		#local.run("cd %s/current && echo 'finish'" % args.deployRoot)

"""

sampleSys = """
config='''
config:
  type: sys

servers:
  - name: test
    host: test.com
    port: 22
    id: test
    targetPath: ~/test
'''

class myGod:
	def __init__(self, helper, **kwargs):
		helper.configStr("yaml", config)	# helper.configFile("yaml", "god.yaml")

	def setupTask(self, util, local, remote, **kwargs):
		#remote.pm2Register():
		#remote.run("cd %s/current && echo 'finish'" % args.deployRoot)
		
"""