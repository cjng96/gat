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
	def __init__(self, tasks, helper, **kwargs):
		self.tasks = tasks
		self.helper = helper
		helper.configStr("yaml", config)	# helper.configFile("yaml", "god.yaml")

	def buildTask(self, args, **kwargs):
		#if not self.tasks.dbGqlGen():
		#	return False
		#return self.tasks.goBuild(args)
		return True

	def deployPreTask(self, ssh, args, **kwargs):
		#subprocess.check_output("npm run build", shell=True)
		return True

	def deployPostTask(self, ssh, args, **kwargs):
		#if not self.tasks.pm2Register():
		#	return False
		#ssh.run("cd %s/current && echo 'finish'" % args.deployRoot)
		return True
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
	def __init__(self, tasks, helper, **kwargs):
		self.tasks = tasks
		self.helper = helper
		helper.configStr("yaml", config)	# helper.configFile("yaml", "god.yaml")

	def setupTask(self, ssh, args, **kwargs):
		#if not self.tasks.pm2Register():
		#	return False
		#ssh.run("cd %s/current && echo 'finish'" % args.deployRoot)
		return True
"""