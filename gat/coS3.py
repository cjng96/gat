import os
import io
from typing import Any
#from myutil import glog

class CoS3:
  def __init__(self, key: str | None = None, secret: str | None = None) -> None:
    import boto3
    import botocore
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

  def bucketAllName(self) -> list[str]:
    lst = []
    for bucket in self.res.buckets.all():
      lst.append(bucket.name)

    return lst

  # name: 'ucount-it.stage'
  def bucketGet(self, name: str) -> "CoBucket":
    return CoBucket(self, self.res.Bucket(name))


class CoBucket:
  def __init__(self, s3: CoS3, bucket: Any) -> None:
    self.s3 = s3
    self.bucket = bucket
    self.name = bucket.name

  # for file in bucket.objectList('aging.ucount.it/export/565c04166fb69292224594d1/20170323'):
  #   glog(file.key)
  def objectList(self, prefix: str | None = None) -> Any:
    return self.bucket.objects.filter(Prefix=prefix).all()

  # key: test.jpg -- targetPath
  def upload(self, key: str, pp: str) -> None:
    #with open(pp, "rb") as fp:
    #	self.bucket.put_object(Key=key, Body=fp)
    self.bucket.upload_file(pp, key)

  def temp(self) -> None:
    result = self.s3.res.meta.client.list_objects(Bucket='test', Delimiter='/')
    for o in result.get('CommonPrefixes'):
      print(o.get('Prefix'))

  # 
  def existFile(self, key: str) -> bool:
    try:
      self.s3.res.Object(self.name, key).load()
      return True
    except botocore.exceptions.ClientError as e:
      if e.response['Error']['Code'] == '404':
        return False
      else:
        raise

  # can be slow
  def existFolder(self, key: str) -> bool:
    result = self.s3.client.list_objects(Bucket=self.name, Prefix=key)
    if "Contents" in result:
      return True

    return False			

  # 이건 하위 폴더 이름 목록만 얻기
  def folderList(self, pp: str) -> list[str]:
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

  def fileList(self, pp: str) -> list[str]:
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


  def downloadDir(self, prefix: str, localPath: str = '/tmp') -> None:
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
  def downloadFile(self, key: str, target: str | None) -> bytes | str:
    if target is None:
      #with io.BytesIO() as f:
      #	self.bucket.download_fileobj(key, f)
      #	return f.read()
      obj = self.s3.client.get_object(Bucket=self.name, Key=key)
      return obj['Body'].read()

    if target.endswith(os.path.sep):
      name = os.path.basename(key)
      target = os.path.join(target, name)

    #f1 = self.s3.res.Object(self.name, key)
    #f1.download_file(target)
    self.bucket.download_file(key, target)
    return target

  def deleteFile(self, bucketName: str, key: str) -> None:
    obj = self.res.Object(bucketName, key)
    obj.delete()

  def deleteFolder(self, bucketName: str, key: str) -> None:
    bucket = self.res.Bucket(bucketName)
    bucket.objects.filter(Prefix=key+'/').delete()

