import os
import boto3
import botocore
#from myutil import glog

class CoS3:
	def __init__(self, key=None, secret=None):
		if key is None:
			self.client = boto3.client('s3')
			self.res = boto3.resource('s3')
		else:
			self.client = boto3.client("s3", aws_access_key_id=key, aws_secret_access_key=secret)
			session = boto3.Session(
				aws_access_key_id=key,
				aws_secret_access_key=secret,
			)
			self.res = session.resource("s3")

	def bucketAllName(self):
		lst = []
		for bucket in self.res.buckets.all():
			lst.append(bucket.name)

		return lst

	# name: 'ucount-it.stage'
	def bucketGet(self, name):
		return CoBucket(self, self.res.Bucket(name))


class CoBucket:
	def __init__(self, s3, bucket):
		self.s3 = s3
		self.bucket = bucket
		self.name = bucket.name

	# for file in bucket.objectList('aging.ucount.it/export/565c04166fb69292224594d1/20170323'):
	#   glog(file.key)
	def objectList(self, prefix=None):
		return self.bucket.objects.filter(Prefix=prefix).all()

	# key: test.jpg -- targetPath
	def upload(self, key, pp):
		#with open(pp, "rb") as fp:
		#	self.bucket.put_object(Key=key, Body=fp)
		self.bucket.upload_file(pp, key)

	def temp(self):
		result = self.s3.res.meta.client.list_objects(Bucket='test', Delimiter='/')
		for o in result.get('CommonPrefixes'):
			print(o.get('Prefix'))

	# 
	def existFile(self, key):
		try:
			self.s3.res.Object(self.name, key).load()
			return True
		except botocore.exceptions.ClientError as e:
			if e.response['Error']['Code'] == '404':
				return False
			else:
				raise

	# can be slow
	def existFolder(self, key):
		result = self.s3.client.list_objects(Bucket=self.name, Prefix=key)
		if "Contents" in result:
			return True

		return False			

	# 이건 하위 폴더 이름 목록만 얻기
	def folderList(self, pp):
		lst = []
		paginator = self.s3.client.get_paginator('list_objects')
		for result in paginator.paginate(Bucket=self.name, Delimiter='/', Prefix=pp):
			if result.get('CommonPrefixes') is not None:
				for subdir in result.get('CommonPrefixes'):
					prefix = subdir.get('Prefix')
					prefix = prefix[len(pp):]	# 20170401/
					prefix = prefix.rstrip("/")
					lst.append(prefix)

		return lst

	def fileList(self, pp):
		lst = []
		paginator = self.s3.client.get_paginator('list_objects')
		for result in paginator.paginate(Bucket=self.name, Delimiter='/', Prefix=pp):
			if result.get('Contents') is not None:
				for ff in result.get('Contents'):
					key = ff.get('Key')
					key = key[len(pp):]	# 20170401/
					if key == "":
						continue
					#key = key.rstrip("/")
					lst.append(key)

		return lst


	def downloadDir(self, prefix, localPath='/tmp'):
		if not prefix.endswith('/'):
			prefix += "/"

		paginator = self.s3.client.get_paginator('list_objects')
		for result in paginator.paginate(Bucket=self.name, Delimiter='/', Prefix=prefix):
			if result.get('CommonPrefixes') is not None:
				for subdir in result.get('CommonPrefixes'):
					self.downloadDir(subdir.get('Prefix'), localPath)

			if result.get('Contents') is not None:
				for file in result.get('Contents'):
					key = file.get('Key')

					# remove prefix
					name = key[len(prefix):]
					if len(name) == 0:
						continue

					target = os.path.join(localPath, name)
					targetDir = os.path.dirname(target)

					os.makedirs(targetDir, exist_ok=True)
					#self.s3.res.meta.client.download_file(self.name, key, target)
					self.bucket.download_file(key, target)


	#'ucount-it.stage', 'aging.ucount.it/config/report.csv', "c:\\work\\pbi\\"
	def downloadFile(self, key, target):
		if target.endswith(os.path.sep):
			name = os.path.basename(key)
			target = os.path.join(target, name)

		#f1 = self.s3.res.Object(self.name, key)
		#f1.download_file(target)
		self.bucket.download_file(key, target)
		return target
	