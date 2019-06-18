import os
import boto3

#from myutil import glog

class CoS3:
	def __init__(self):
		self.client = boto3.client('s3')
		self.res = boto3.resource('s3')

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
	