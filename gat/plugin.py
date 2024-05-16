import os
import re
import json
import time
import yaml
import hashlib
import datetime
import subprocess

# import gattool.coSsh as coSsh
# from .coS3 import CoS3


def loadFile(pp):
    with open(pp, "r") as fp:
        return fp.read()


def installSupervisor(env):
    """
    It's replace start script
    """
    if env.runSafe("test -f /etc/supervisor/supervisord.conf"):
        return False

    env.run("apt update")
    # env.run('apt install -y supervisor sudo')
    # env.run('apt install -y python python-pip python-setuptools python3 python3-pip python3-setuptools')
    env.run("apt install --no-install-recommends -y sudo")
    env.run(
        "apt install --no-install-recommends -y python3 python3-pip python3-setuptools"
    )
    env.run("pip3 install supervisor")
    env.run("mkdir -p /var/log/supervisor")

    env.makeFile(
        path="/start",
        sudo=True,
        content="""\
#!/bin/bash
#/etc/init.d/supervisor starte
mkdir -p /var/log/supervisor
if [ -f /data/no ]; then
	exec /bin/bash
else
	exec /usr/local/bin/supervisord
fi
""",
    )
    env.run("chmod 755 /start")

    env.run("mkdir -p /etc/supervisor/conf.d")
    env.makeFile(
        path="/etc/supervisor/supervisord.conf",
        sudo=True,
        content="""\
[unix_http_server]
file=/var/run/supervisor.sock
chmod=0700
[supervisord]
logfile=/var/log/supervisor/supervisord.log
pidfile=/var/run/supervisord.pid
childlogdir=/var/log/supervisor
nodaemon=true
; no use it due to port conflict
;[inet_http_server]
;#port = 127.0.0.1:9001
[rpcinterface:supervisor]
supervisor.rpcinterface_factory = supervisor.rpcinterface:make_main_rpcinterface
[supervisorctl]
serverurl=unix:///var/run/supervisor.sock
[include]
files = /etc/supervisor/conf.d/*.conf
""",
    )
    return True


def installRunit(env):
    """
    It's replace start script
    https://sourcediver.org/blog/2014/11/17/using-runit-in-a-docker-container/
    """
    if env.runSafe("test -f /sbin/runit"):
        return

    env.run("apt update")
    env.run("apt install -y sudo runit")

    env.makeFile(
        content="""\
#!/bin/bash
export > /etc/envvars
if [ -f /data/no ]; then
	exec /bin/bash
else
	#exec /usr/bin/runsvdir -P /etc/service
	exec /sbin/runit
fi
""",
        path="/start",
        sudo=True,
    )


def installHomebrew(env):
    if not env.runSafe(". ~/.zshrc && command -v brew"):
        env.run(
            'bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
        )


def installSshfsMount(env, name, src, target, port=22, id=None):
    """
    installSshfsMount(remote, 'test', 'account@server.com:', '/tmp/mnt', port=7022)
    """
    if not env.runSafe("command -v sshfs"):
        env.run("sudo apt install --no-install-recommends -y sshfs")

    if id is None:
        home = "~"
    else:
        home = env.runOutput(f"echo ~{id}").strip()

    rsaPath = f"{home}/.ssh/id_rsa"

    rr = re.search(r"@?([\w\.]*?):", src)
    if rr is None:
        raise Exception(f"Can't find host from {src} for installSshfsMount")
    host = rr.group(1)
    # systemd mount는 root로 실행되서
    # -R: remove all from known_hosts
    env.runSafe(f"sudo ssh-keygen -R [{host}]:{port}")
    env.run(f"ssh-keyscan -p {port} -t rsa {host} | sudo tee -a /root/.ssh/known_hosts")

    env.makeFile(
        path=f"/etc/systemd/system/{name}.mount",
        content=f"""\
[Unit]
Description=Mount remote fs with sshfs

[Install]
WantedBy=multi-user.target

[Mount]
What={src}
Where={target}
Type=fuse.sshfs
Options=_netdev,allow_other,Port={port},IdentityFile={rsaPath},reconnect,ServerAliveInterval=30,ServerAliveCountMax=5,x-systemd.automount,uid=1000,gid=1000,StrictHostKeyChecking=no
TimeoutSec=60
""",
        mode=664,
        sudo=True,
    )

    env.run(
        f"sudo systemctl daemon-reload && sudo systemctl restart {name}.mount && sudo systemctl enable {name}.mount"
    )


def installSamba(env):
    if env.runSafe("command -v samba"):
        return
    env.run("sudo apt install -y samba samba-common-bin")
    # 이건 수동으로
    # env.run("sudo smbpasswd -a cjng96")


def installKnock(env, sequence, timeout=10):
    """
    https://linux.die.net/man/1/knockd
    포트 프로토콜도 지정할수 있다. tcp,udp등으로

    knock -d 100 nas.mmx.kr 13571 13598 13573 13582
    """
    env.makeFile(
        path="/etc/default/knockd",
        sudo=True,
        content="""\
START_KNOCKD=1
KNOCKD_OPTS="-i eth0"
""",
    )

    env.makeFile(
        path="/etc/knockd.conf",
        sudo=True,
        content=f"""\
[options]
    UseSyslog

[SSH]
    sequence      = {sequence}
    seq_timeout   = 5
    start_command = ufw insert 1 allow from %IP% to any port 22 comment knockd
    tcpflags      = syn
    cmd_timeout   = {timeout}
    stop_command  = ufw delete allow from %IP% to any port 22
""",
    )

    if not env.runSafe("command -v knock"):
        env.run("sudo apt install -y knockd")
        env.run("sudo systemctl enable knockd")
    env.run("sudo systemctl restart knockd")


def dockerPhotoprism(
    env, url, srcPath, adminPw, dbHost, dbName, dbId, dbPw, name="photo"
):
    """
    앨범추가, 삭제 불편하고
    다음으로 넘어가는것도 gif나 영상에는 안된다

    모바일에서 사진도 작게 나온다
    전체보기도 년도별로 쭈욱 나오는게 아니라 아래로 모어 스크롤 방식 - 앨범에 월별보기, 위치별 보기는 있다

    폴더별 분리하는거, 사람별로 보여주는거 정도만 장점임
    original에 잘 정리해서 넣으면 괜찬을지도..

    todo:
    nginx통해서 전송해야한다
    """

    if containerExists(env, name):
        return

    env.run(
        f"""\
sudo docker run -d --name {name} \
    --restart unless-stopped \
    -p 2342:2342 \
    -e PHOTOPRISM_ADMIN_PASSWORD={adminPw} \
    -e PHOTOPRISM_SITE_URL={url} \
    -e PHOTOPRISM_DATABASE_DRIVER=mysql \
    -e PHOTOPRISM_DATABASE_SERVER=sql \
    -e PHOTOPRISM_DATABASE_NAME={name} \
    -e PHOTOPRISM_DATABASE_USER={name} \
    -e PHOTOPRISM_DATABASE_PASSWORD={dbPw} \
    -e MYSQL_DATABASE={dbName} \
    -e MYSQL_HOST={dbHost} \
    -e MYSQL_USER={dbId} \
    -e MYSQL_PASSWORD={dbPw} \
    -v {srcPath}:/photoprism/originals \
    photoprism/photoprism:latest
    """
    )
    # -v {srcPath}:/photoprism/storage \
    # -v {srcPath}:/photoprism/import \
    env.run(f"docker network connect net {name}")


def dockerSeafile(env):
    # 이거 안된다
    ret = env.runOutput('. ~/.profile && docker ps -qf name="^%s$"' % "seafile")
    if ret.strip() == "":
        if not env.runSafe("test -d seafile-docker-pi"):
            env.run(
                "git clone https://github.com/domenukk/seafile-docker-pi.git && cd ./seafile-docker-pi/image && make base && make server"
            )

        env.run(
            """\
docker run -d --name seafile \
  --restart unless-stopped \
  -e SEAFILE_SERVER_HOSTNAME=nas.mmx.kr \
  -e SEAFILE_ADMIN_EMAIL=cjng96@gmail.com \
  -e SEAFILE_ADMIN_PASSWORD=j56RGfpdXvcwdkBv \
  -v /media/w/seafile:/shared \
  -p 8000:80 \
  -p 8080:8080 \
  seafileltd/seafile:pi
"""
        )

    # 8000:80(web), 8080(webdav), 8082(app) - 어차피 nginx 거쳐서 오므로 사실 export안해도 된다.
    # "seafile-control" (3867) uses depreacted CP15 Barrier instruction at 0xf70bd278
    # sudo vi /etc/rc.local
    # echo 2 >/proc/sys/abi/cp15_barrier
    env.run("docker network connect net seafile")


def nginxSeafile(env, name):
    env.makeFile(
        """\
server {{
    listen 80;
    #listen [::]:80 ipv6only=on;
    server_name {0};
    #rewrite ^ https://$server_name$request_uri? permanent;
    return 301 https://$server_name$request_uri;
}}
server {{
    listen 443 ssl http2;
    #listen [::]:443 http2 ipv6only=on;
    server_name {0};
    #access_log /var/log/nginx/inerauth.access.log;
    error_log /var/log/nginx/{1}.error.log;
    location / {{
        proxy_pass http://{2}:8000;
        proxy_set_header Host $http_host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Scheme $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Host $server_name;
        proxy_read_timeout 1200s;
    }}
    location /seafhttp {{
        rewrite ^/seafhttp(.*)$ $1 break;
        proxy_pass http://{2}:8082;
        client_max_body_size 0;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_request_buffering off;

        proxy_connect_timeout  36000s;
        proxy_read_timeout  36000s;
        proxy_send_timeout  36000s;
        send_timeout  36000s;
    }}
    location /seafdav {{
        rewrite ^/seafdav(.*)$ $1 break;
        proxy_pass http://{2}:8080;
        proxy_buffering off;
        proxy_request_buffering off;
        proxy_redirect off;
        proxy_http_version 1.1;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Scheme $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Accel-Redirect $uri;
        proxy_set_header Host $http_host;
    }}
    location /media {{
        proxy_pass http://{2}:8000;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Host $server_name;
        proxy_read_timeout  1200s;
    }}
}}""".format(
            "sea.mmx.kr", "seaWeb", name
        ),
        path="/data/nginx/seaWeb",
        sudo=True,
        mode=664,
    )
    certbotSetup(env, "sea.mmx.kr", "cjng96@gmail.com")


def nginxNextcloud(
    env,
    domain,
    prot="https",
    port=80,
    name="next",
    proxy="next:9000",
    nginxCfgPath="/data/nginx",
    localBind=False,
    selfSign=False,  # true: 사설 인증서 사용
    selfSignPort=443,
):
    # https://www.reddit.com/r/selfhosted/comments/rvqv3l/nextcloud_behind_nginx_proxy_manager_nextcloud
    # https://github.com/nextcloud/docker/blob/master/.examples/docker-compose/insecure/mariadb/fpm/web/nginx.conf

    listen = port
    # if localBind:
    #     listen = f'127.0.0.1:{port}'
    extra1 = ""
    extra2 = ""

    if selfSign:
        env.run("apt install -y openssl")
        env.run("mkdir -p /data/ssl")
        if not env.runSafe("test -f /data/ssl/nginx.key"):
            env.run(
                "openssl req -x509 -nodes -days 3650 -newkey rsa:2048 -keyout /data/ssl/nginx.key -out /data/ssl/nginx.crt  -subj '/C=KR'"
            )

        listen = f"{selfSignPort} ssl"
        extra1 = """
ssl_certificate /data/ssl/nginx.crt;
ssl_certificate_key /data/ssl/nginx.key;
"""
        extra2 = f"""
server {{
    listen 80;
    server_name {domain};
    return 301 https://$host$request_uri;
}}
"""

    env.makeFile(
        f"""\
server {{
	listen			{listen};
	server_name		{domain};
	root			/data/{name};

    {extra1}

	#access_log		/var/log/nginx/{name}.log;
	error_log		/var/log/nginx/error.log;

	# index			index.php index.html index.htm;
    index           index.php index.html /index.php$request_uri;
	# fastcgi_index	index.php;
	# fastcgi_param	SCRIPT_FILENAME $document_root$fastcgi_script_name;
	# include			fastcgi.conf;

    location ~ \.php(?:$|/) {{
        # Required for legacy support
        rewrite ^/(?!index|remote|public|cron|core\/ajax\/update|status|ocs\/v[12]|updater\/.+|oc[ms]-provider\/.+|.+\/richdocumentscode\/proxy) /index.php$request_uri;

        fastcgi_split_path_info ^(.+?\.php)(/.*)$;
        set $path_info $fastcgi_path_info;

        try_files $fastcgi_script_name =404;

        client_max_body_size 0;
        # client_body_buffer_size 128m;

        include fastcgi_params;
        # fastcgi_param SCRIPT_FILENAME $document_root$fastcgi_script_name;
        fastcgi_param SCRIPT_FILENAME /var/www/html/$fastcgi_script_name;
        fastcgi_param PATH_INFO $path_info;
        #fastcgi_param HTTPS on;

        fastcgi_param modHeadersAvailable true;         # Avoid sending the security headers twice
        fastcgi_param front_controller_active true;     # Enable pretty urls
        fastcgi_pass {proxy};

        fastcgi_intercept_errors on;
        fastcgi_request_buffering off;

        # 추가한거
        # fastcgi_buffering off;
    }}

    location ~ \.(?:css|js|svg|gif)$ {{
        try_files $uri /index.php$request_uri;
        expires 6M;         # Cache-Control policy borrowed from `.htaccess`
        access_log off;     # Optional: Don't log access to assets
    }}

    location ~ \.woff2?$ {{
        try_files $uri /index.php$request_uri;
        expires 7d;         # Cache-Control policy borrowed from `.htaccess`
        access_log off;     # Optional: Don't log access to assets
    }}

    # Rule borrowed from `.htaccess`
    location /remote {{
        return 301 /remote.php$request_uri;
    }}

    location / {{
        try_files $uri $uri/ /index.php$request_uri;
    }}
}}
{extra2}
""",
        path=f"{nginxCfgPath}/{name}",
        sudo=True,
        mode=664,
    )

    if prot == "https" and not selfSign:
        certbotSetup(
            env,
            domainStr=domain,
            email="cjng96@gmail.com",
            name=name,
            nginxCfgPath=nginxCfgPath,
            localBind=localBind,
        )


def dockerNextcloudFpm(
    env,
    dataPath,
    name="next",
    overwriteProt="https",
    overwriteDomain=None,  # None이면 overwrite안한다
    dbHost="sql",
    dbName="next",
    dbId="next",
    dbPw="1234",
    publishPort=0,
    restart="unless-stopped",
    imgTag="fpm",
):
    """
    sudo docker exec -ti --user www-data next /var/www/html/occ files:scan --all
    sudo docker exec -ti --user www-data next /var/www/html/occ files:cleanup

    파일 락 걸린거 찾기 - 락 안풀리면 위에 scan --all하라네
    SELECT FROM_UNIXTIME( oc_file_locks.ttl, '%Y-%m-%d %h' ) AS DATE, oc_file_locks.lock, COUNT(*) AS LOCKS FROM oc_file_locks GROUP BY DATE, oc_file_locks.lock ORDER BY LOCKS DESC

    아래껄로 lock 0으로 강제로 풀수 있다
    SELECT * FROM oc_file_locks WHERE `lock`<>0;

    5분마다 이거 해줘야한다
    https://docs.nextcloud.com/server/23/admin_manual/configuration_server/background_jobs_configuration.html
    docker exec -u www-data next php -f /var/www/html/cron.php

    https://help.nextcloud.com/t/docker-setup-cron/78547/7
    그냥 인스턴스 하나 더 띄우자

    """

    # https://hub.docker.com/_/nextcloud#running-this-image-with-docker-compose
    if containerExists(env, name):
        # TODO: next가 만들다 실패했을도 있으니 더 검사해야 한다
        return

    # bind mount도 안먹힌다
    # env.run(f'sudo mount --bind {srcPath} /data/web/{name}')
    env.run(f"sudo mkdir -p /data/web/{name}")

    # 어차피 web통해서 접근해서 이거 필요없는거 같은데..
    publishPortCmd = "" if publishPort == 0 else f"-p {publishPort}:9000"
    # publishPortCmd = ""

    # web쪽에 /data/next로 별도로 마운팅하지 않으려면 web쪽꺼를 가져다 쓸수밖에 없다
    overwrite = ""
    if overwriteDomain is not None:
        overwrite = f"""\
  -e OVERWRITEPROTOCOL={overwriteProt} \
  -e OVERWRITEHOST={overwriteDomain} \
  -e OVERWRITECLIURL={overwriteProt}://{overwriteDomain} \
  """

    env.run(
        f"""\
sudo docker run -d --name {name} \
  --restart {restart} \
  {publishPortCmd} \
  -e MYSQL_DATABASE={dbName} \
  -e MYSQL_HOST={dbHost} \
  -e MYSQL_USER={dbId} \
  -e MYSQL_PASSWORD={dbPw} \
  {overwrite} \
  -v /data/web/{name}:/var/www/html \
  -v {dataPath}:/var/www/html/data \
  nextcloud:{imgTag}
"""
    )
    env.run(f"docker network connect net {name}")

    env.runSafe(f"sudo docker rm -f {name}Cron")
    env.run(
        f"""\
sudo docker run -d --name {name}Cron \
  --restart {restart} \
  --entrypoint /cron.sh \
  -e MYSQL_DATABASE={dbName} \
  -e MYSQL_HOST={dbHost} \
  -e MYSQL_USER={dbId} \
  -e MYSQL_PASSWORD={dbPw} \
  -v /data/web/{name}:/var/www/html \
  -v {dataPath}:/var/www/html/data \
  nextcloud:{imgTag}
"""
    )
    env.run(f"docker network connect net {name}Cron")


def dockerNextcloud(
    env,
    domain,
    srcPath,
    name="next",
    prot="https",
    dbHost="sql",
    dbName="next",
    dbId="next",
    dbPw="1234",
):
    # https://hub.docker.com/_/nextcloud#running-this-image-with-docker-compose
    if containerExists(env, name):
        # TODO: next가 만들다 실패했을도 있으니 더 검사해야 한다
        return

    env.run(
        f"""\
sudo docker run -d --name {name} \
  --restart unless-stopped \
  -e MYSQL_DATABASE={dbName} \
  -e MYSQL_HOST={dbHost} \
  -e MYSQL_USER={dbId} \
  -e MYSQL_PASSWORD={dbPw} \
  -e OVERWRITEPROTOCOL={prot} \
  -e OVERWRITEHOST={domain} \
  -e OVERWRITECLIURL={prot}://{domain} \
  -v {srcPath}:/var/www/html \
  nextcloud
"""
    )
    # -e APACHE_DISABLE_REWRITE_IP=1 \
    # -e TRUSTED_PROXIES=web \

    env.run(f"docker network connect net {name}")

    # web에서 /media/w/nextcloud에 접근이 가능해야한다 - static files
    # 이게 좀 어렵다 그냥 fpm대신 아파치 쓰자

    web = env.dockerConn("web")
    web.makeFile(
        f"""\
server {{
    listen 80;
    #listen 443 ssl http2;
    #listen [::]:443 http2 ipv6only=on;
    server_name {domain};
    #access_log /var/log/nginx/inerauth.access.log;
    error_log /var/log/nginx/{name}.error.log;
    location / {{
        proxy_pass http://{name}:80;
        proxy_set_header Host $http_host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Scheme $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Host $server_name;
        proxy_read_timeout 1200s;
        client_max_body_size 0;
    }}
}}""",
        path=f"/data/nginx/{name}",
        sudo=True,
        mode=664,
    )
    if prot == "https":
        certbotSetup(web, domainStr=domain, email="cjng96@gmail.com", name=name)


def installRclone(env):
    if env.runSafe("command -v rclone"):
        return
    env.run("curl https://rclone.org/install.sh | sudo bash")
    env.run("rclone config touch")


def installRcloneMount(env, name, target, src=None, rclone="/usr/bin/rclone"):
    """
    installRcloneMount(remote, 'n2', src='n2:data', target='/n2', rclone='/usr/local/bin/rclone')
    """
    if src is None:
        src = f"{name}:"

    env.run(f"sudo mkdir -p {target}")

    # /usr/bin/rclone, /usr/local/bin/rclone
    env.makeFile(
        path=f"/etc/systemd/system/{name}.service",
        content=f"""\
[Unit]
Description={name} rclone mount
AssertPathIsDirectory={target}
After=network-online.target

[Service]
Type=simple
ExecStart={rclone} mount \
--config=/home/cjng96/.config/rclone/rclone.conf \
--allow-other \
--uid=1000 --gid=1000 \
--cache-tmp-upload-path=/tmp/rclone/upload \
--cache-chunk-path=/tmp/rclone/chunks \
--cache-workers=8 \
--cache-writes \
--cache-dir=/tmp/rclone/vfs \
--cache-db-path=/tmp/rclone/db \
--no-modtime \
--drive-use-trash \
--stats=0 \
--checkers=16 \
--bwlimit=40M \
--dir-cache-time=60m \
--cache-info-age=60m {src} {target}
ExecStop=/bin/fusermount -u {target}
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
""",
        sudo=True,
    )

    env.run(
        f"sudo systemctl daemon-reload && sudo systemctl restart {name} && sudo systemctl enable {name}"
    )


def installRedis(env, memSize="1G", memPolicy="allkeys-lru", port=None):
    """
    memSize: 1G, 512M
    memPolicy
    """
    if env.runSafe("command -v redis-cli"):
        return

    env.run("sudo apt install --no-install-recommends -y redis-server")
    env.configLine(
        "/etc/redis/redis.conf",
        regexp="^# maxmemory ",
        line=f"maxmemory {memSize}",
        sudo=True,
    )
    env.configLine(
        "/etc/redis/redis.conf",
        regexp="^# maxmemory-policy",
        line=f"maxmemory-policy {memPolicy}",
        sudo=True,
    )

    if port is not None:
        env.configLine(
            "/etc/redis/redis.conf", regexp="^port ", line=f"port {port}", sudo=True
        )

    env.run("sudo service redis-server start")


def installRabbitMq(env, account="admin", pw=""):
    """
    localhost:15672
    """
    if env.runSafe("command -v rabbitmqctl"):
        return

    env.run(
        "sudo apt install --no-install-recommends -y rabbitmq-server && sudo service rabbitmq-server start"
    )
    env.run("sudo rabbitmq-plugins enable rabbitmq_management")
    env.run(f'sudo rabbitmqctl add_user {account} "{env.util.str2arg(pw)}"')  # TODO: pw
    env.run(f"sudo rabbitmqctl set_user_tags {account} administrator")
    env.run("sudo service rabbitmq-server restart")


def installDart(env, ver="latest"):
    """
    version: lastest, 3.0.7...
    dart sdk: 400MB
    pub-cache: 80MB

    E: Unable to locate package dart오류 나면 - n2에서 나온다
    https://storage.googleapis.com/dart-archive/channels/stable/release/2.15.0/sdk/dartsdk-linux-arm64-release.zip
    arm64는 아래 경로에서 받을수 있다
    https://storage.googleapis.com/dart-archive/channels/stable/release/2.15.0/sdk/dartsdk-linux-arm64-release.zip
    """
    if env.runSafe("command -v dart"):
        return

    def _install(pt):
        # pt: arm64, x64
        env.run(
            # 'wget -qO /tmp/dart.zip "https://storage.googleapis.com/dart-archive/channels/stable/release/latest/sdk/dartsdk-linux-arm64-release.zip"'
            # 'curl -L -o /tmp/dart.zip "https://storage.googleapis.com/dart-archive/channels/stable/release/latest/sdk/dartsdk-linux-arm64-release.zip"'
            f'curl -L -o /tmp/dart.zip "https://storage.googleapis.com/dart-archive/channels/stable/release/{ver}/sdk/dartsdk-linux-{pt}-release.zip"'
        )
        env.run("sudo unzip -d /usr/lib/ /tmp/dart.zip")
        env.run("sudo mv /usr/lib/dart-sdk /usr/lib/dart")
        env.run("sudo ln -sf /usr/lib/dart/bin/dart /usr/bin/dart")
        env.run("sudo ln -sf /usr/lib/dart/bin/pub /usr/bin/pub")

    # arch = env.runOutput("dpkg --print-architecture").strip()
    arch = getArch(env)
    if arch == "arm64":
        _install(arch)

    elif arch == "amd64":
        # env.run(
        #     "sudo apt-get install --no-install-recommends -y apt-transport-https wget gnupg2"
        # )
        # env.run(
        #     "sudo sh -c 'wget -qO- https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add -'"
        # )
        # env.run(
        #     "sudo sh -c 'wget -qO- https://storage.googleapis.com/download.dartlang.org/linux/debian/dart_stable.list > /etc/apt/sources.list.d/dart_stable.list'"
        # )
        # env.run("sudo apt-get update")
        # env.run("sudo apt-get install --no-install-recommends -y dart")
        # env.run("sudo ln -sf /usr/lib/dart/bin/pub /usr/bin/pub")
        _install("x64")
    else:
        raise Exception(f"unknown arch[{arch}]")


def setupRclone(env, name, type, host, port, user, id=None, keyFile=None):
    """
    sftp용임
    
    이걸 해놓으면 rclone sync를 쓸수가 있다. sshfs+rsync는 빠르게 안된다(ssh는 가능하지만 좀..)
    pub = dk.runOutput('cat ~/.ssh/id_rsa.pub')
	backup = remote.remoteConn(host='backup.com', port=7022, id='cjng96')
	#backup.strEnsure("/jail/%s/.ssh/authorized_keys" % 'b_engdb', pub, sudo=True)
	my.makeSftpUser(backup, 'b_colldb', '/jail', 'data', [pub])

	my.installRclone(dk)
    my.setupRclone(dk, name='n2', type='sftp', host='backup.com', port=7022, 
	    user='b_colldb', keyFile='~/.ssh/id_rsa')

	dk.makeFile('''\
#!/bin/bash
sudo -iu cjng96 rclone sync -P --stats-one-line /data/db n2:/data/db
''', '/etc/cron.daily/n2-db', sudo=True)
    """
    if id is None:
        id = env.runOutput("whoami").strip()

    home = env.runOutput(f"echo ~{id}").strip()

    env.run(
        f"sudo mkdir -p {home}/.config/rclone && sudo touch {home}/.config/rclone/rclone.conf"
    )
    env.run(f"sudo chown {id}: {home}/.config -R")  # 일단은

    content = f"""\
[{name}]
type = {type}
host = {host}
port = {port}
user = {user}
md5sum_command = md5sum
sha1sum_command = sha1sum
"""
    if keyFile is not None:
        env.run(f"openssl rsa -in {keyFile} -outform pem > {keyFile}.pem")
        keyFile2 = env.runOutput(f"realpath {keyFile}").strip()
        content += f"key_file = {keyFile2}.pem\n"
    else:
        content += "ask_password = true"

    env.configBlock(
        path=f"{home}/.config/rclone/rclone.conf",
        marker=f"# {{mark}} server {name} config",
        block=content,
        sudo=True,
    )


def setupRunitService(env, name, cmd):
    env.run(f"mkdir -p /var/log/{name}")
    env.run(f"sudo mkdir -p /etc/service/{name}/log")
    env.makeFile(
        f"""\
#!/bin/bash
exec 2>&1
#set -e
exec {cmd}
""",
        f"/etc/service/{name}/run",
        sudo=True,
    )
    env.makeFile(
        f"""\
#!/bin/bash
#[ -d /var/log/{name} ] || mkdir -p /var/log/{name}
exec chpst -u root:adm svlogd -t /var/log/{name}
""",
        f"/etc/service/{name}/log/run",
        sudo=True,
    )


def setupInternalSftp(env):
    env.configLine(
        path="/etc/ssh/sshd_config",
        regexp="Subsystem\s+sftp\s+",
        line="Subsystem sftp internal-sftp",
        sudo=True,
    )
    env.configBlock(
        path="/etc/ssh/sshd_config",
        marker="# {mark} sftponly",
        block="""\
Match Group sftponly
    ChrootDirectory %h
    X11Forwarding no
    AllowTcpForwarding no
    ForceCommand internal-sftp
""",
        sudo=True,
    )


def makeSftpUser(env, id, rootPath="/home", dataFolderName="data", authPubs=None):
    home = f"{rootPath}/{id}"
    makeUser(
        env,
        id,
        home=home,
        # shell='/usr/bin/rssh',
        authPubs=authPubs,
    )
    # env.run('sudo adduser {0} sftponly'.format(id))
    env.run(f"sudo groupadd -f sftponly && sudo usermod -a -G sftponly {id}")
    env.run(f"sudo chown root: {home} && sudo chmod 755 {home}")
    env.run(
        f"\
sudo mkdir -p {home}/{dataFolderName} && \
sudo chmod 775 {home}/{dataFolderName} && \
sudo chown {id}: {home}/{dataFolderName}"
    )


def mountFolder(env, src, dest):
    env.run("sudo mkdir -p {0}".format(dest))
    if not env.runSafe(f"mountpoint -q {dest}".format()):
        env.run(f"sudo mount -o bind {src} {dest}")
    env.strEnsure(
        f"/etc/fstab", f"{src} {dest} none defaults,nofail,bind 0 0\n", sudo=True
    )


# centos 호환 여부 : O
def installRssh(env, home, useChroot=True):
    """
    rssh이용해서 rsyn를 쓸수 있게.
    단점은 루트가 보여서 조금 지저분하다
    **** 이거.. 지금 또 chroot 안된다..ㅜ.ㅜ

    sftp만이면 internal-sftp설정 쓰면 된다.
    internal-sftp써도
    home을 root로 설정, 데이터용 폴더 따로 만들어줘야 함
    또 문제가, internal-sftp는 /media/ssd1/users/b_test2를 쓰려고 하면 /media/ssd1..등의 부모 폴더도
    다 root owned and 755여야 한다. mount bind할수 있지만 치명적
    """
    # https://www.cyberciti.biz/tips/howto-linux-unix-rssh-chroot-jail-setup.html"
    if env.runSafe(f"test -f {home}/ok"):
        return

    os = env.getOS()
    print(f"========== install rssh on {os} ==========")
    if os == "ubuntu":
        env.run("sudo apt install --no-install-recommends -y rssh")
    elif os == "centos":
        env.run("sudo yum install -y rssh")

    env.run(f"mkdir -p {home}/{{dev,etc,lib,usr,bin}}")
    env.run(f"mkdir -p {home}/usr/bin")
    # env.run(f'mkdir -p {home}/usr/libexec/openssh'.format(home))
    env.run(f"mkdir -p {home}/usr/lib/openssh")
    env.run(f"mkdir -p {home}/usr/lib/rssh")
    env.run(f"mkdir -p {home}/lib/aarch64-linux-gnu")

    # unknown user problem
    # env.configLine('/etc/nsswitch.conf', '^passwd:\s*compat', 'passwd: files', sudo=True)
    env.run(f"cp -f /lib/aarch64-linux-gnu/libnss* {home}/lib/aarch64-linux-gnu/")

    env.run(f"[ -e {home}/dev/null ] || mknod -m 666 {home}/dev/null c 1 3")
    # ubuntu는 없다
    # env.run('cp -avr /etc/ld.so.cache.d/ {0}/etc/'.format(home))
    arr = [
        "/etc/ld.so.cache",
        "/etc/ld.so.conf",
        "/etc/nsswitch.conf",
        #'/etc/passwd',
        #'/etc/group',
        "/etc/hosts",
        "/etc/resolv.conf",
    ]
    for item in arr:
        env.run(f"cp -f {item} {home}/etc/")
    env.run(f"touch {home}/etc/passwd && touch {home}/etc/group")

    # TODO: remove root and other account for group, passwd
    # env.run(cp )

    env.run("sudo chmod u+s /usr/lib/rssh/rssh_chroot_helper")

    # bash만 sh, rssh_chroot_helper복사등 방법이 여러가지
    env.run(f"cp -f /bin/sh {home}/bin/")
    # env.run(f'cp -f /bin/bash {home}/bin/')
    env.run(f"cp -f /usr/bin/rssh {home}/usr/bin/")
    env.run(f"cp -f /usr/bin/scp {home}/usr/bin/")
    env.run(f"cp -f /usr/bin/sftp {home}/usr/bin/")
    env.run(f"cp -f /usr/bin/rsync {home}/usr/bin/")
    # env.run(f'cp /usr/lib/rssh/rssh_chroot_helper {home}/usr/libexec/')
    env.run(f"cp -f /usr/lib/openssh/sftp-server {home}/usr/lib/openssh/")
    env.run(f"sudo cp -f /usr/lib/rssh/rssh_chroot_helper {home}/usr/lib/rssh/")
    env.run(f"sudo chown root: {home}/usr/lib/rssh/rssh_chroot_helper")

    env.run(
        "cd /sbin && sudo wget -O l2chroot http://www.cyberciti.biz/files/lighttpd/l2chroot.txt && sudo chmod +x l2chroot"
    )
    env.configLine("/sbin/l2chroot", "BASE=", f"BASE={home}", sudo=True)

    env.run("l2chroot /bin/sh")
    # env.run('l2chroot /bin/bash')
    env.run("l2chroot /usr/bin/rssh")
    env.run("l2chroot /usr/bin/scp")
    env.run("l2chroot /usr/bin/sftp")
    env.run("l2chroot /usr/bin/rsync")
    env.run("l2chroot /usr/lib/openssh/sftp-server")
    env.run("l2chroot /usr/lib/rssh/rssh_chroot_helper")

    env.configLine("/etc/rssh.conf", "^#allowscp", "allowrscp", sudo=True)
    env.configLine("/etc/rssh.conf", "^#allowsftp", "allowsftp", sudo=True)
    env.configLine("/etc/rssh.conf", "^#allowrsync", "allowrsync", sudo=True)
    env.configLine(
        "/etc/rssh.conf", "^#chrootpath\s*=", f"chrootpath={home}", sudo=True
    )
    # env.run('sudo /etc/init.d/sshd restart')

    # https://unix.stackexchange.com/questions/341501/setting-up-logging-of-chroot-users
    # /etc/rsyslog.conf
    # input(type="imuxsock" Socket="/media/ssd1/users/dev/log" CreatePath="on")
    ####local3.*                                                /var/log/sftp.log

    # limit his home only
    # 요거 아직 안된다. 해당 라인이 없으면 추가가 기본이여야 한다.
    env.configLine(
        "/etc/pam.d/common-session",
        "session required pam_mkhomedir",
        "session required pam_mkhomedir.so debug skel=/etc/skel umask=0077",
        sudo=True,
    )

    env.run(f"echo ok > {home}/ok2")


def makeRsshUser(env, id, rootPath, authPubs):
    makeUser(env, id, home=f"{rootPath}/{id}", shell="/usr/bin/rssh", authPubs=authPubs)


def registerAuthPubs(env, authPubs, id=None):
    env.log(f">> registerAuthPubs - id:{id} pubs:{authPubs}")
    if id is None:
        home = "~"
    else:
        home = env.runOutput(f"echo ~{id}").strip()
        if home == "":
            raise Exception(f"registerAuthPubs: failed to get home folder for {id}")

    for key in authPubs:
        print(f"home - {home}")
        env.strEnsure(f"{home}/.ssh/authorized_keys", key, sudo=True)


def registerAuthPub(env, pub, id=None):
    registerAuthPubs(env, [pub], id)


def userDel(env, id):
    env.log(f">> userDel - id:{id}")
    cmd = f"sudo deluser {id}"
    env.run(cmd)


def userAddRaw(
    env,
    id,
    genHome=True,
    shell=None,
    uid=None,
    gid=None,
    unique=True,
    system=False,
):
    env.log(f">> userAdd - id:{id} system:{system} shell:{shell}")

    # if env.runSafe('cat /etc/passwd | grep -e "^%s:"' % id):
    if env.runSafe(f'grep -c "^{id}:" /etc/passwd'):
        print(f"  -> userAdd - exist user[{id}]")
        return

    # if not existOk or runRet("id -u %s" % name) != 0:
    # 	run("useradd %s -m -s /bin/bash" % (name))
    cmd = "sudo useradd -M "
    if shell is not None:
        cmd += f" --shell {shell}"

    if system:
        cmd += " --system"

    if genHome:
        cmd += " -m"
    else:
        cmd += " -M -d /nonexistent"

    if uid is not None:
        cmd += f" --uid {uid}"
    if gid is not None:
        cmd += f" --gid {gid}"
    if unique is False:
        cmd += " -o"

    cmd += f" {id}"
    print(f"gen user - {cmd}")
    env.run(cmd)


def userAdd(
    env,
    id,
    home=None,
    shell=None,
    genSshKey=True,
    grantSudo=False,
    authPubs=None,
    uid=None,
    gid=None,
    unique=True,
    system=False,
):
    env.log(
        f">> userMake - id:{id} home:{home} shell:{shell} genKey:{genSshKey} grantSudo:{grantSudo} authPubs:{authPubs}"
    )

    # if env.runSafe('cat /etc/passwd | grep -e "^%s:"' % id):
    if env.runSafe(f'grep -c "^{id}:" /etc/passwd'):
        # 이 경우도 등록은 갱신한다.
        print(f"  -> makeUser - exist user[{id}]")
        if authPubs is not None:
            registerAuthPubs(env, authPubs=authPubs, id=id)
        return

    # if not existOk or runRet("id -u %s" % name) != 0:
    # 	run("useradd %s -m -s /bin/bash" % (name))
    cmd = 'sudo adduser --disabled-password --gecos ""'
    if home is not None:
        cmd += f" --home {home}"
    if shell is not None:
        cmd += f" --shell {shell}"

    if system:
        cmd += " --system"

    if uid is not None:
        cmd += f" --uid {uid}"
    if gid is not None:
        cmd += f" --gid {gid}"
    if unique is False:
        cmd += " -o"

    cmd += f" {id}"
    # print(f"gen user - {cmd}")
    env.run(cmd)

    if grantSudo:
        env.run(
            f'sudo adduser {id} sudo && \
      sudo echo "{id} ALL=(ALL:ALL) NOPASSWD:ALL" > /etc/sudoers.d/{id} && \
      sudo chmod 0440 /etc/sudoers.d/{id}'
        )

    # 이미 해당 폴더가 있엇을 경우 권한문제가 생길수있으므로 변경
    home = env.runOutput(f"echo ~{id}").strip()
    env.run(f"sudo chown {id}: {home} -R")

    if genSshKey:
        sshKeyGen(env, id, authPubs)


makeUser = userAdd


def sshKeyGen(env, id, authPubs=None):
    home = env.runOutput(f"echo ~{id}").strip()

    # 자기파일이라 sudo가 필요없어야하는데, 이미 존재했을 경우 위에서 chown을 해주는데도 안되는 경우가 있음
    if not env.runSafe(f"sudo test -e {home}/.ssh/id_rsa"):
        env.run("sudo apt update")  # openssh-client설치에서 404오류 나는 경우가
        env.run("sudo apt install --no-install-recommends -y openssh-client")
        env.run(
            f'sudo -u {id} ssh-keygen -b 2048 -q -t ed25519 -N "" -f {home}/.ssh/id_rsa'
        )

    pp = f"{home}/.ssh/authorized_keys"
    env.run(f"sudo touch {pp} && sudo chmod 700 {pp} && sudo chown {id}: {pp}")

    # TODO: local id_rsa.pub을 등록해야하는데 local...
    # env.uploadFile('~/.ssh/id_rsa.pub', '{0}/.ssh/authorized_keys'.format(home))
    # env.strEnsure("%s/.ssh/authorized_keys" % home, key, sudo=True)

    if authPubs is not None:
        registerAuthPubs(env, authPubs=authPubs, id=id)


def buildImagePre(env):
    buildImage = env.server.get("buildImage", False)
    if buildImage:
        env.runSafe(
            "sudo docker rm -f {0}; sudo docker rmi {0}".format(env.vars.dkName)
        )

        # ret = env.runOutput('. ~/.profile && docker inspect --format="ok" %s; echo' % name)
        # ret = env.runOutput('. ~/.profile && docker ps -qf name="^%s$"' % name)
        # if ret.strip() != '':
        # 	return

    return buildImage


def buildImagePost(env):
    buildImage = env.server.get("buildImage", False)
    if not buildImage:
        return

    # env.run('docker stop {0}'.format(env.vars.dkName))
    env.run("sudo docker commit {0} {0}".format(env.vars.dkName))
    # env.run('docker rm {0}'.format(env.vars.dkName))

    writeBuildSh(env)


def writeBuildSh(env):
    ss = dockerRunCmd("$1", env.vars.dkName, env.vars.get("dkPort", ""))
    env.makeFile(
        f"""\
#!/bin/bash
{ss}
""",
        f"docker_{env.vars.dkName}.sh",
    )


def verStr(version):
    if type(version) is int:
        v1 = int(version / 10000)
        v2 = int((version - (v1 * 10000)) / 100)
        v3 = int((version - (v1 * 10000) - (v2 * 100)))
        # print(f"{v1} --- {v2} ,,, {v3}")
        return f"{v1}.{v2}.{v3}"
    return version


def _skipSameVersion(env, prefix, ver):
    """
    prefix: "{name}:{baseVer}" 문자열
    """
    firstVer = ver
    for i in range(100):
        ver += 1
        # 다음버젼이 존재하면 더 넘기기
        # cmdBash = ""
        # if env.remoteOs == 'centos':
        #     cmdBash = "bash_"
        # ret = env.runOutput(
        #     f". ~/.{cmdBash}profile && sudo docker images -q {prefix}{ver}"
        # ).strip()

        cmd = f"podman images -q {prefix}{ver}"
        if not env.config.podman:
            cmd = f"sudo docker images -q {prefix}{ver}"

        ret = env.runOutputProf(cmd).strip()
        if ret == "":
            okFlag = True
            break

        print(f"{prefix}{ver} - version exists...")

    if not okFlag:
        raise Exception(f"Failed to found next new version - {prefix}{firstVer}")

    return ver


def _getVersionYaml(env, fn, component, imgName, prefix, hash):
    """
    component이름의 hash를 얻어와서 비교하고 다르면 버젼 업후, 버젼 반환
    """
    firstVer = 1
    nowStr = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    fn2 = f"{fn}.yml"
    if os.path.isfile(fn2):
        with open(fn2, "r") as fp:
            infos = yaml.safe_load(fp.read())
    else:
        infos = {component: dict(version=firstVer, hash=hash, date=nowStr)}
        with open(fn2, "w") as fp:
            fp.write(yaml.dump(infos))

        print(f"{fn}/{component}: created - version:{firstVer}, hash={hash}")
        return firstVer

    info = infos.get(component)
    if info is None:
        info = dict(version=firstVer, hash="", date=nowStr)
        infos[component] = info

    infoHash = info["hash"]
    infoVer = info["version"]
    if infoHash == hash:
        print(f"{fn}/{component}: content is not changed.")
        return infoVer

    print(f"{fn}/{component}: content is updated - old:{infoHash}, now:{hash}")

    okFlag = False
    # ver = infoVer
    # for i in range(100):
    #     ver += 1
    #     # 다음버젼이 존재하면 더 넘기기
    #     ret = env.runOutput(f". ~/.profile && sudo docker images -q {imgName}:{prefix}{ver}").strip()
    #     if ret == "":
    #         okFlag = True
    #         break

    #     print(f"{fn}/{component}: {ver} version exists...")

    # if not okFlag:
    #     raise Exception(f"Failed to found next new version - {imgName}:{prefix}{infoVer}")
    ver = _skipSameVersion(env, f"{imgName}:{prefix}", infoVer)

    print(f"{fn}/{component}: new version - {ver}")
    info["version"] = ver
    info["hash"] = hash
    info["date"] = nowStr
    with open(fn2, "w") as fp:
        fp.write(yaml.dump(infos))

    return ver


def baseCheckVersion(env, files, imgName, prefix):
    sha = hashlib.sha256()
    for fn in files:
        with open(fn, "rb") as fp:
            # sha.update(fp.read().encode("utf8"))
            sha.update(fp.read())

    hash = sha.hexdigest()
    ver = _getVersionYaml(env, "version", "base", imgName, prefix, hash)
    return f"{prefix}{ver}", hash


def deployCheckVersion(env, util, imgName, prefix):
    sha = hashlib.sha256()

    def doProd(src, dest):
        # print(f"deployCheckVersion: file - {src}")
        if src == "./version.yml":
            print("deployCheckVersion: skip version.yml file")
            return

        with open(src, "rb") as fp:
            sha.update(fp.read())

    util.deployFileListProd(env, doProd)

    hash = sha.hexdigest()
    # print(f"hash - {hash}")
    ver = _getVersionYaml(env, "version", "app", imgName, prefix, hash)
    return f"{prefix}{ver}", hash


def containerUpdateImage(
    env,
    baseName,
    baseVer,
    newName,
    newVer,
    hash,
    func,
    net=None,
    userId=None,
):
    """
    return: true(created new one), false(already exists)
    """
    print(f"containerUpdateImage: {newName}:{newVer} from {baseName}:{baseVer}")
    # baseVer = verStr(baseVer)
    # newVer = verStr(newVer)

    prog = "podman"
    if not env.config.podman:
        prog = "sudo docker"

    # 해당 버젼이 이미 있으면 생략
    ret = env.runOutputProf(f"{prog} images -q {newName}:{newVer}").strip()
    if ret != "":
        # 기존 이미지와 hash label이 동일한지 확인 - 다르면 다시 생성
        def checkParentRev():
            # 해당부모가 동일한지 확인
            baseHash = env.runOutputProf(
                f"{prog} images -q {baseName}:{baseVer}"
            ).strip()

            ret = env.runOutputProf(f"{prog} image history -q {newName}:{newVer}")
            lst = ret.split()
            if baseHash not in lst:
                raise Exception(f"no matched parent[bashHash:{baseHash}]")

        if hash is None:
            checkParentRev()
            return False

        # we should use sudo for docker?
        ret = env.runOutput(
            f"""{prog} image inspect -f '{{{{index .Config.Labels "hash"}}}}' {newName}:{newVer}"""
        ).strip()
        # print(f"hash - {hash} {ret}")
        if ret != hash:
            print(f"Regenerated image[{newName}:{newVer} whose hash is not match.")
            env.run(f"docker rmi -f {newName}:{newVer}")
        else:
            checkParentRev()
            return False

    if env.config.podman:
        env.run(f"{prog} rm -if {newName}-con")
    else:
        env.run(f"{prog} rm -f {newName}-con")

    # Dockerfile에 직접 명시해도 되지만, 편의를 위해서 다시 이미지를 만든다
    extra = ""
    if net is not None:
        extra = f"--network {net}"

    env.run(f"{prog} run -itd {extra} --name {newName}-con {baseName}:{baseVer}")
    dk = env.dockerConn(f"{newName}-con", dkId=userId)

    func(dk)
    dk.clearConn()

    # 이미지 생성 및 리소스 제거
    extra = ""
    if hash is not None:
        extra = f"""-c 'LABEL hash="{hash}"'"""

    env.run(f"{prog} commit {extra} {newName}-con {newName}:{newVer}")
    # env.run(f"sudo docker tag {newName}:{newVer} {newName}:latest")
    env.run(f"{prog} rm -f {newName}-con")
    return True


dockerUpdateImage = containerUpdateImage


# nodeVer는 coimg에 포함된거라 매번 바뀌지 않는다
def containerCoImage(env, nodeVer="16.13.1", dartVer="3.2.3"):
    baseName, baseVer = containerBaseImage(env)

    newName = "coimg"
    newVer = 7
    newVer = f"{baseVer}{newVer}"
    # 1~9, a~z까지 쓰자
    # 최악으로 coImg와 baseImg버젼이 겹쳐져도 1 11과 11 1처럼 중복되도, 부모가 다르기때문에 오류난다

    def update(env):
        baseimgInitScript(env)
        env.run(f"echo {newName}:{newVer} >> /version-{newName}-{newVer}")

        env.run("apt update")
        env.run("apt install -y --no-install-recommends libmysqlclient-dev git")
        # env.run("sudo apt remove -y python3-pip")
        # 풀설치- 200메가정도 늘어남. mysqlclient같은거 빌드할때 필요하다
        env.run("apt install -y python3-pip python3-pyxattr")
        # env.run("ln -sf /usr/bin/python3 /usr/bin/python")
        # env.run("apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*")

        # 이거 공용 컴포넌트는 별도로 층을 나눌것인가
        env.run(
            "pip3 install setuptools aiomysql aiohttp aiohttp-cors aiosmtplib multidict"
        )
        env.run("pip3 install bcrypt requests google-auth google-auth-oauthlib")
        env.run("pip3 install pyyaml pyOpenSSL")

        # 280 - base
        # 435 - python 150m정도
        # 480 - node추가 34m정도
        # 1002 - dart 520m - 이거는 빌드할때만 설치하고 지워도 될수도.. 시간이 오래 걸림
        # nodeApp는 node_modules때문에 300메가정도 늘어난다

        # 크론은 새벽 2시에 동작하도록 - 기본은 6시
        env.configLine(
            path="/etc/crontab",
            regexp=r"^25\s6\s+",
            line=f"25 2    * * *   root    test -x /usr/sbin/anacron || ( cd / && run-parts --report /etc/cron.daily )",
            sudo=True,
        )

        # nvmInstall(env, account="root", nodeVer=nodeVer)
        # # env.run("/opt/nvm/nvm-exec npm install -g gulp")
        # env.run(". /etc/profile && . /opt/nvm/nvm.sh && npm install -g gulp")
        fnmInstall(env, nodeVer=nodeVer)
        # env.run(". /etc/profile && fnm exec npm install -g gulp")
        # env.run(f". /etc/profile && fnm exec --using {nodeVer} npm install -g gulp")
        env.run(f". /etc/profile && npm install -g gulp")

        # lastest가 3.1.0인데 컴포넌트들이 아직 지원이 안된다
        installDart(env, ver=dartVer)

    containerUpdateImage(
        env,
        baseName=baseName,
        baseVer=baseVer,
        newName=newName,
        newVer=newVer,
        hash=None,
        func=update,
    )
    return newName, newVer


dockerCoImage = containerCoImage


def containerBaseImage(env):
    name = "baseimg"
    version = 1
    # 이게 서버에 동일한 버젼이 있었던 경우가 유일한 취약점이다
    # version = _skipSameVersion(env, f"{name}:", version)

    # version = verStr(version)
    prog = "podman"
    if not env.config.podman:
        prog = "sudo docker"

    # 해당 버젼이 이미 있으면 생략
    ret = env.runOutputProf(f"{prog} images -q {name}:{version}")
    if ret.strip() != "":
        return name, version

    # 이미지가 지정되어 있지 않으면 기본 이미지로 같은 이름으로 만든다.
    installDocker(env, arch="amd64")

    # make docker image
    env.run("rm -rf /tmp/docker && mkdir /tmp/docker")
    # https://github.com/phusion/baseimage-docker/releases
    origin = "docker.io/"
    if not env.config.podman:
        origin = ""
    env.makeFile(
        f"""\
# FROM phusion/baseimage:focal-1.0.0
FROM {origin}phusion/baseimage:jammy-1.0.4
LABEL title="gattool"
CMD ["/sbin/my_init"]
RUN mkdir -p /data && mkdir -p /work
RUN apt update && \\
    apt upgrade -y -o Dpkg::Options::="--force-confold" && \\
    apt purge -y vim-tiny && \\
    apt install -y sudo vim net-tools inetutils-ping rsync unzip zstd
# RUN apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*
""",
        "/tmp/docker/Dockerfile",
    )
    # upgrade -> add 110MB

    env.runProf(f"{prog} build -t {name}:{version} /tmp/docker && rm -rf /tmp/docker")
    # --squash --no-cache
    # env.run(f"sudo docker tag {name}:{version} {name}:latest")

    return name, version


dockerBaseImage = containerBaseImage


def dockerImageForSupervisor(env, name, version, userId, func):
    """
    기본용 이미지만 만들어놓고, FROM으로 여기서부터 생성한다 - 빠름
    업그레이드가 필요하면 직접해도 되고 이미지를 다시 만들면 새로 만들어진다 - 이걸 추천
    """
    version = verStr(version)

    # 해당 버젼이 이미 있으면 생략
    ret = env.runOutput(f". ~/.profile && sudo docker images -q {name}:{version}")
    if ret.strip() != "":
        return

    # 이미지가 지정되어 있지 않으면 기본 이미지로 같은 이름으로 만든다.
    installDocker(env, arch="amd64")

    env.run(f"sudo docker rm -f {name}-con && sudo docker rmi {name}-work")

    # make docker image
    env.run("rm -rf /tmp/docker && mkdir /tmp/docker")
    env.makeFile(
        """\
FROM ubuntu:20.04
#LABEL maintainer="cjng96@gmail.com"
LABEL title="gattool"
RUN echo "#!/bin/bash\\\\nexec /bin/bash" > /start && chmod 755 /start
RUN mkdir -p /data && mkdir -p /work/log && ln -sf /work/log /var/log
CMD ["/start"]
""",
        "/tmp/docker/Dockerfile",
    )
    env.run(
        f". ~/.profile && sudo docker build -t {name}-work /tmp/docker && rm -rf /tmp/docker"
    )  # --no-cache

    # Dockerfile에 직접 명시해도 되지만, 편의를 위해서 다시 이미지를 만든다
    env.run(f"sudo docker run -itd --name {name}-con {name}-work")
    dk = env.dockerConn(f"{name}-con")

    ret = installSupervisor(dk)
    if userId is not None:
        makeUser(dk, userId, grantSudo=True)
    # supervisor설치한 경우만 재시작
    if ret:
        env.run(f"sudo docker restart {name}-con")

    dk = env.dockerConn(f"{name}-con", dkId=userId)
    supervisorBasic(dk, serverName=name)

    if func is not None:
        func(dk)

    # 이미지 생성 및 리소스 제거
    env.run(f"sudo docker commit {name}-con {name}:{version}")
    env.run(f"sudo docker tag {name}:{version} {name}:latest")
    env.run(f"sudo docker rm -f {name}-con")
    env.run(f"sudo docker rmi {name}-work")


def makeDockerContainerForSupervisor(
    env, name, image=None, port=None, dkId=None, mountBase=True
):
    """
    이제, dockerImageForSupervisor,dockerUpdateImage 시리즈를 쓰라
    port=1000-1010:1000-1010
    """
    buildImage = env.vars.get("buildImage", False)
    if buildImage:
        port = ""
        mountBase = not buildImage
        name += "_img"

    # image를 쓰면 68초, 직접 생성하면 241초 한 4배
    makeDockerContainer(env, name=name, port=port, image=image, mountBase=mountBase)

    dk = env.dockerConn(name)
    ret = installSupervisor(dk)
    if dkId is not None:
        makeUser(dk, dkId, grantSudo=True)
    # supervisor설치한 경우만 재시작
    if ret:
        env.run(f"sudo docker restart {env.vars.dkName}")

    dk = env.dockerConn(name, dkId=dkId)
    supervisorBasic(dk, serverName=name)
    return dk


def makeDockerContainerForRunit(
    env, name, image=None, port=None, dkId=None, mountBase=True
):
    buildImage = env.server.get("buildImage", False)
    if buildImage:
        port = ""
        mountBase = not buildImage
        name += "_img"

    makeDockerContainer(env, name=name, port=port, image=image, mountBase=mountBase)

    dk = env.dockerConn(name)
    installRunit(dk)
    if dkId is not None:
        makeUser(dk, dkId, grantSudo=True)
    env.run(f"sudo docker restart {env.vars.dkName}")

    dk = env.dockerConn(name, dkId=dkId)
    # supervisorBasic(dk, serverName=name)
    return dk


def cloudWatchInit(conn, accessKey, secretKey):
    conn.run("sudo mkdir -p /etc/systemd/system/docker.service.d/")
    conn.run("sudo touch /etc/systemd/system/docker.service.d/aws-credentials.conf")

    conn.configBlock(
        "/etc/systemd/system/docker.service.d/aws-credentials.conf",
        "### {mark} cloud watch",
        f'''\
[Service]
Environment="AWS_ACCESS_KEY_ID={accessKey}"  
Environment="AWS_SECRET_ACCESS_KEY={secretKey}"''',
        sudo=True,
    )

    conn.run("sudo systemctl daemon-reload")
    conn.run("sudo systemctl restart docker")


def containerRunCmd(
    name,
    image,
    port=None,
    mountBase=True,
    net=None,
    env=None,
    extra="",
    useHost=True,
    awsLogsGroup=None,
    awsLogsStream=None,
    awsLogsRegion=None,
):
    """
    port: "3306:3306", "9018-9019:9018-9019", ["9018-9019:9018-9019"]
    """
    # print("port", port)

    prog = "podman"
    if not env.config.podman:
        prog = "sudo docker"

    # if portCnt != 1:
    # 	portCmd = '-p {0}-{1}:{0}-{1}'.format(port, port+portCnt-1)
    # else:
    # 	portCmd = '-p {0}:{0}'.format(port)

    cmd = f"{prog} run -itd --restart unless-stopped --name {name} --hostname {name} "

    if net is not None:
        # host, bridge(default)
        # 첫 시작시에 net이 없다는 오류가 뜸 -> sudo docker network create net -> 나중에 손 봐야함
        # print(f"=================== net : {net} ==============================")
        # env.run(f"sudo docker network create net")
        # print(f"=================== ret : {ret} ==============================")
        cmd += f"--network {net} "

    if port is not None:
        portCmd = ""
        if type(port) is str:
            if port != "":
                portCmd += f"-p {port} "
        elif type(port) is int:
            portCmd += f"-p {port} "
        elif type(port) is list:
            for p in port:
                portCmd += f"-p {p} "
        else:
            raise Exception(f"******** invalid port type is {type(port)}")

        cmd += f"{portCmd} "

    if mountBase:
        cmd += (
            # "-v /data/common:/common "	일단은 common도 없애자 - eweb설정등은 god레벨에서 직접 올리자
            f"-v /data/{name}:/data -v /work/{name}:/work "
        )

    if awsLogsGroup is not None:
        awsLogsRegion = awsLogsRegion or "us-west-1"
        awsLogsStream = awsLogsStream or name

        cmd += f"--log-driver=awslogs "
        cmd += f"--log-opt awslogs-region={awsLogsRegion} "
        cmd += f"--log-opt awslogs-group={awsLogsGroup} "
        cmd += f"--log-opt awslogs-stream={awsLogsStream} "
    else:
        cmd += "--log-opt max-size=30m --log-opt max-file=3 "

    if useHost and not env.config.podman:
        cmd += "--add-host=host.docker.internal:host-gateway "

    cmd += extra
    cmd += f" {image}"

    if env is not None:
        # if dockerContainerExists(env, env.vars.dkName):
        if containerExists(env, name):
            env.run(f"{prog} start {name}")
            dk = env.dockerConn(name)
            # 이 부분에서도 에러 발생
            dk.run("! test -f /update || /update")

            # env.run(f"sudo docker rm -f {env.vars.dkName}")
            env.run(f"{prog} rm -f {name}")

        # env.run(f"sudo mkdir -p /data/{name}/tmp")
        env.run(cmd)
        dk = env.dockerConn(name)
        dk.makeFile(cmd, "/cmd")

    return cmd


dockerRunCmd = containerRunCmd


def containerExists(env, name):
    prog = "podman"
    if not env.config.podman:
        prog = "sudo docker"

    ret = env.runOutputProf(f'{prog} ps -aqf name="^{name}$"')
    return ret.strip() != ""


def makeDockerContainer(env, name, image=None, port=None, mountBase=True):
    """
    image: None(create image directly), string(using that image)
    """
    prog = "podman"
    if not env.config.podman:
        prog = "sudo docker"

    print(f"makeDockerContainer: name:{name}, image:{image}, port:{port}")
    # 이건 image도 나온다.
    # ret = env.runOutput('. ~/.profile && docker inspect --format="ok" %s; echo' % name)
    # ret = env.runOutput(f'. ~/.profile && sudo docker ps -qf name="^{name}$"')
    # if ret.strip() != "":
    #     return
    if containerExists(env, name):
        return

    if image is None:
        # 이미지가 지정되어 있지 않으면 기본 이미지로 같은 이름으로 만든다.
        image = name
        if env.config.podman:
            installPodman(env)
        else:
            installDocker(env, arch="amd64")

        # make docker image
        env.run("rm -rf /tmp/container-sv && mkdir /tmp/container-sv")
        env.makeFile(
            """\
FROM ubuntu:18.04
#LABEL maintainer="cjng96@gmail.com"
RUN echo "#!/bin/bash\\\\nexec /bin/bash" > /start && chmod 755 /start
RUN mkdir -p /data && mkdir -p /work/log && ln -sf /work/log /var/log
CMD ["/start"]
""",
            "/tmp/container-sv/Dockerfile",
        )
        env.runProf(
            f"{prog} build -t {image} /tmp/container-sv && rm -rf /tmp/container-sv"
        )  # --no-cache

    cmd = dockerRunCmd(name, image, port, mountBase)
    env.runProf(cmd)

    # leave cmd as a file
    env.makeFile(cmd, "/tmp/dockerCmd")
    env.runProf(f"{prog} cp /tmp/dockerCmd {name}:/cmd")


def writeRunScript(env, cmd, targetPath="/app/current", appName="app"):
    env.log(f">> writeRunScript: {cmd}")

    pp = f"/etc/service/{appName}" if targetPath is None else targetPath

    env.run(f"mkdir -p /etc/service/{appName}")
    env.makeFile(
        f"""\
#!/bin/sh
{upcntRunStr()}
{cmd}
""",
        f"{pp}/run",
    )
    if targetPath is not None:
        env.run(f"ln -sf {pp}/run /etc/service/{appName}/run")

    writeSvHelper(env)


def writeSvHelper(env):
    env.log(f">> writeSvHelper")

    help = "shortcuts - c(app),s(status),r(run),d(stop),re(restart),e(exit)"
    env.configBlock(
        path="~/.bashrc",
        marker="# {mark} alias",
        block=f"""
function readlinks() {{ readlink "$@" || echo "$@"; }}
alias d="sv d app; test -f /down && /down; sv s app"
alias re="echo -1 > /var/run/upcnt; sv restart app; ps aux; sv s app"
alias c="cd $(dirname $(readlinks /etc/service/app/run))"
alias s="ps aux && sv s app"
alias r="sv d app; ENV=test $(dirname $(readlinks /etc/service/app/run))/run"
alias e="exit"
alias h="echo '{help}'"
echo "{help}"
""",
    )


def promptSet(env, name):
    env.configBlock(
        path="~/.bashrc",
        marker="# {mark} PS1",
        block=f'PS1="{name} $PS1"',
    )


def supervisorBasic(env, serverName):
    if env.runSafe("test -f /etc/profile.d/sv.sh"):
        return

    # env.configBlock(path="~/.bashrc", marker="# {mark} PS1 CHANGED BLOCK", block='PS1="dk_%s $PS1"' % serverName)
    promptSet(env, f"dk_{serverName}")
    # env.run("sudo ln -sf /usr/local/bin/supervisorctl /usr/bin/sv")

    env.makeFile(
        """\
alias sv='sudo supervisorctl'
alias sstart='sudo supervisorctl start'
alias sstop='sudo supervisorctl stop'
alias sre='sudo supervisorctl restart'
alias sst='sudo supervisorctl status'
alias slog='sudo supervisorctl tail -f'
""",
        path="/etc/profile.d/sv.sh",
        sudo=True,
    )


def localeSet(env):
    env.run("sudo apt install --no-install-recommends -y locales")
    env.run(
        "sudo locale-gen en_US en_US.UTF-8 && sudo update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8"
    )


def registerSshPubsFromS3(env, local, bucket, prefix, account):
    local.run("mkdir -p work/%s" % prefix)
    lst = local.s3List(bucket=bucket, prefix=prefix)
    local.s3DownloadFiles(
        bucket=bucket, prefix=prefix, nameList=lst, targetFolder="./work/"
    )

    # pp = "~/.ssh/authorized_keys"
    home = env.runOutput("echo ~%s" % account).strip()
    pp = "%s/.ssh/authorized_keys" % home

    pubs = []
    for name in lst:
        with open(os.path.join("./work", name), "r") as fp:
            key = fp.read()
            key = key.strip()
            pubs.append(key)

    registerSshPubs(env, local=local, pubs=pubs, account=account)


def registerSshPubs(env, local, pubs, account):
    # pp = "~/.ssh/authorized_keys"
    home = env.runOutput("echo ~%s" % account).strip()
    pp = "%s/.ssh/authorized_keys" % home
    for pub in pubs:
        # TODO: 추가 보장하는거?
        env.run(
            """K="%s" && grep -q -F "$K" %s 2>/dev/null || echo "$K" >> %s"""
            % (pub.key, pp, pp)
        )


def supervisorSshServer(env, port, denyUsers=None):
    env.run("sudo apt install --no-install-recommends -y openssh-server")
    env.configLine(
        path="/etc/ssh/sshd_config",
        regexp="#PasswordAuthtication yes",
        line="PasswordAuthtication no",
        sudo=True,
    )
    if denyUsers is not None:
        env.configBlock(
            path="/etc/ssh/sshd_config",
            marker="# {mark} DenyUsers",
            block="DenyUsers " + denyUsers,
            sudo=True,
        )

    env.run("sudo mkdir -p /var/run/sshd")
    env.makeFile(
        """\
[program:sshd]
command=/usr/sbin/sshd -D -p {0}
stderr_logfile=/var/log/supervisor/%(program_name)s_err.log
stdout_logfile=/var/log/supervisor/%(program_name)s_out.log
""".format(
            port
        ),
        "/etc/supervisor/conf.d/ssh.conf",
        sudo=True,
    )
    env.run("sudo supervisorctl reread && sudo supervisorctl update")


def cronForSupervisor(env):
    env.run("sudo apt install --no-install-recommends -y cron anacron")
    # env.uploadFileTo("./files/cron.conf", "/tmp/efile/")
    env.makeFile(
        content="""\
[program:cron]
command=/usr/sbin/cron -f
autostart=true
autorestart=true
stdout_logfile=/var/log/cron.err
stderr_logfile=/var/log/cron.log
""",
        path="/etc/supervisor/conf.d/cron.conf",
        sudo=True,
    )
    # invoke-rc.d anacron start is failed because of it
    env.makeFile(
        content="""\
#!/bin/sh
exit 0
""",
        path="/usr/sbin/policy-rc.d",
        sudo=True,
    )


def rsyslogForSupervisor(env):
    env.run("sudo apt install --no-install-recommends -y rsyslog")
    env.makeFile(
        content="""\
[program:rsyslogd]
command=/usr/sbin/rsyslogd -n
autostart=true
autorestart=true
stderr_logfile=/var/log/supervisor/%(program_name)s_err.log
stdout_logfile=/var/log/supervisor/%(program_name)s_out.log
""",
        path="/etc/supervisor/conf.d/rsyslogd.conf",
        sudo=True,
    )
    env.run("sleep 1 && sudo kill $(pidof rsyslogd)")
    env.run("sudo supervisorctl reread && sudo supervisorctl update")


def logrotateForSupervisor(env):
    env.run("sudo apt install --no-install-recommends -y logrotate")
    env.makeFile(
        content="""\
/var/log/supervisor/*.log {
	daily
	rotate 90
	missingok
	dateext
	#create
	copytruncate
}""",
        path="/etc/logrotate.d/supervisor",
        sudo=True,
    )
    # env.run("sudo sv reread && sudo sv add cron && sudo sv restart cron")
    env.run("sudo supervisorctl reread && sudo supervisorctl update")


def setupTz(env):
    # mongodb설치할때 time zone물어본다 그거 회피용
    # https://stackoverflow.com/questions/44331836/apt-get-install-tzdata-noninteractive
    env.run(
        "export DEBIAN_FRONTEND=noninteractive && "
        "sudo ln -fs /usr/share/zoneinfo/Asia/Seoul /etc/localtime && "
        "sudo apt install -y tzdata && "
        "sudo dpkg-reconfigure --frontend noninteractive tzdata"
    )


# TODO: mysql, goBuild, gqlGen, dbXorm, pm2Register등은 기본 task에서 빼야할듯
def mysqlUserDel(env, id, host):
    hr = env.runOutput(
        f"""sudo mysql -e "SELECT 'exist' FROM mysql.user where user='{id}' AND host='{host}'";"""
    )
    if hr == "":
        return

    env.run('''sudo mysql -e "DROP USER '%s'@'%s';"''' % (id, host))


def mysqlUserGen(env, id, pw, host, priv, unixSocket=False):
    """
    priv: "*.*:ALL,GRANT", "*.*:RELOAD,PROCESS,LOCK TABLES,REPLICATION CLIENT"
    앞에께 ON 대상, 뒤에껀 권한인데 - ALL PRIVILEGES를 주면 전체 권한이 된다

    """
    # pw = str2arg(pw).replace(';', '\\;').replace('`', '``').replace("'", "\\'")
    pw = env.str2arg(pw).replace("'", "''")
    # 이게 좀 웃긴데, mysql 통해서 실행하는거기 때문에 \\는 \\\\로 바꿔야한다.
    pw = pw.replace("\\\\", "\\\\\\\\")
    host = env.str2arg(host)
    if unixSocket:
        env.run(
            f'''sudo mysql -e "CREATE USER '{id}'@'{host}' IDENTIFIED VIA unix_socket;"'''
        )
    else:
        env.run(
            f'''sudo mysql -e "CREATE USER '{id}'@'{host}' IDENTIFIED BY '{pw}';"'''
        )

    privList = priv.split("/")
    for priv in privList:
        priv2, oper = priv.split(":")

        grantOper = ""
        lst = list(map(lambda x: x.strip().upper(), oper.split(",")))
        if "GRANT" in lst:
            lst.remove("GRANT")
            grantOper = "WITH GRANT OPTION"
        oper = ",".join(lst)

        env.run(
            f'''sudo mysql -e "GRANT {oper} ON {priv2} TO '{id}'@'{host}' {grantOper};"'''
        )


def goBuild(env, targetOs="", targetArch=""):
    """
    os: windows, darwin, linux
    arch: amd64, arm64
    """
    print("task: goBuild as [%s]..." % env.config.name)

    env.onlyLocal()

    cmd = ["go", "build", "-o", env.config.name]
    env = os.environ.copy()
    if targetOs != "":
        env["GOOS"] = targetOs
    if targetArch != "":
        env["GOARCH"] = targetArch

    print(f"goBuild: {cmd}")
    ret = subprocess.run(cmd, env=env)
    if ret.returncode != 0:
        raise Exception("task.goBuild: build failed")


def gqlGen(env):
    print("task: gql gen...")
    env.onlyLocal()

    # run only it's changed
    t1 = os.path.getmtime("schema.graphql")
    t2 = 0
    if os.path.exists("models_gen.go"):
        t2 = os.path.getmtime("models_gen.go")

    if t1 != t2:
        print("task: gql - graphql schema is updated... re-generate it.")
        cmd = ["go", "run", "github.com/99designs/gqlgen"]
        ret = subprocess.run(cmd)
        if ret.returncode != 0:
            raise Exception("task.gqlGen: failed to build graphql")

        os.utime("models_gen.go", (t1, t1))
    else:
        print("task: gql - skip because of no modification.")


def dbXormReverse(env):
    print("task: xorm reverse...")
    env.onlyLocal()

    # load from config
    with open("./config/base.json") as f:
        cfg = json.load(f)

    with open("./config/my.json") as f:
        cfg2 = json.load(f)
        cfg = dictMerge(cfg, cfg2)

    print("run: ", cfg)

    db = cfg["db"]
    uri = "%s:%s@tcp(%s:%d)/%s?charset=utf8" % (
        db["id"],
        db["pw"],
        db["host"],
        db["port"],
        db["name"],
    )
    cmd = [
        "xorm",
        "reverse",
        "mysql",
        uri,
        "/home/cjng96/go/src/github.com/go-xorm/cmd/xorm/templates/goxorm",
    ]
    env.run(cmd)


def installMongodb(
    env,
    dataDir="/var/lib/mongodb",
    bindIp="127.0.0.1",
    cacheSizeGB=None,
    authEnable=True,
):
    if env.runSafe("command -v mongo"):
        return False

    setupTz(env)

    # env.run('sudo apt install --no-install-recommends -y libcurl3 openssl gnupg2')
    # env.run("sudo apt-key adv --keyserver hkp://keyserver.ubuntu.com:80 --recv 9DA31620334BD75D9DCB49F368818C72E52529D4")
    # env.run("echo 'deb [ arch=amd64 ] https://repo.mongodb.org/apt/ubuntu bionic/mongodb-org/4.0 multiverse' | sudo tee /etc/apt/sources.list.d/mongodb-org-4.0.list")
    # env.run("sudo apt install --no-install-recommends -y openssl gnupg2")
    env.run("sudo apt install --no-install-recommends -y gnupg")

    # env.run("wget -qO - https://www.mongodb.org/static/pgp/server-4.2.asc | sudo apt-key add -")
    # env.run("curl https://www.mongodb.org/static/pgp/server-4.2.asc | sudo apt-key add -")
    # env.run(
    #     "curl https://www.mongodb.org/static/pgp/server-5.0.asc | sudo apt-key add -"
    # )
    env.run(
        "curl -fsSL https://pgp.mongodb.com/server-6.0.asc | \
sudo gpg -o /usr/share/keyrings/mongodb-server-6.0.gpg --dearmor"
    )

    # env.run(
    #     'echo "deb [ arch=amd64 ] https://repo.mongodb.org/apt/ubuntu bionic/mongodb-org/4.2 multiverse" | sudo tee /etc/apt/sources.list.d/mongodb-org-4.2.list'
    # )
    # env.run(
    #     'echo "deb [ arch=amd64,arm64 ] https://repo.mongodb.org/apt/ubuntu focal/mongodb-org/5.0 multiverse" | sudo tee /etc/apt/sources.list.d/mongodb-org-5.0.list'
    # )
    # 22.04
    env.run(
        'echo "deb [ arch=amd64,arm64 signed-by=/usr/share/keyrings/mongodb-server-6.0.gpg ] https://repo.mongodb.org/apt/ubuntu jammy/mongodb-org/6.0 multiverse" | sudo tee /etc/apt/sources.list.d/mongodb-org-6.0.list'
    )
    # 20.04
    # env.run(
    #     'echo "deb [ arch=amd64,arm64 signed-by=/usr/share/keyrings/mongodb-server-6.0.gpg ] https://repo.mongodb.org/apt/ubuntu focal/mongodb-org/6.0 multiverse" | sudo tee /etc/apt/sources.list.d/mongodb-org-6.0.list'
    # )

    env.run("sudo apt update")
    # env.run("sudo apt install --no-install-recommends -y mongodb-org")
    env.run("sudo apt install -y mongodb-org")

    cfg = dict(
        storage=dict(dbPath=dataDir, journal=dict(enabled=True)),
        systemLog=dict(
            destination="file", logAppend=True, path="/var/log/mongodb/mongod.log"
        ),
        net=dict(port=27017, bindIp=bindIp),
        processManagement=dict(timeZoneInfo="/usr/share/zoneinfo", fork=False),
    )
    # fork:false는 안해줘도 기본값인듯..

    if authEnable:
        cfg["security"] = dict(authorization="enabled")

    if cacheSizeGB is not None:
        cfg["storage"]["wiredTiger"] = dict(engineConfig=dict(cacheSizeGB=cacheSizeGB))

    ss = yaml.dump(cfg)
    env.makeFile(ss, "/etc/mongod.conf")


def mongodbForSupervisor(env, dataDir, cacheSizeGB=None, admin=None, pw=None):
    if env.runSafe("command -v mongo"):
        return False

    installMongodb(env, dataDir, cacheSizeGB=cacheSizeGB, authEnable=True)

    env.makeFile(
        content=f"""\
[program:mongodb]
command=/usr/bin/mongod --config /etc/mongod.conf
#command=/usr/bin/mongod --dbpath {dataDir}
priority=999
username=mongodb
#stdout_logfile=/tmp/%(program_name)s.stdout
#stderr_logfile=/tmp/%(program_name)s.stderr
autostart=true
""",
        path="/etc/supervisor/conf.d/mongodb.conf",
        sudo=True,
    )
    env.run(
        "sudo supervisorctl reread && sudo supervisorctl update && sudo supervisorctl restart mongodb"
    )

    if admin is None:
        return

    # https://stackoverflow.com/questions/22682891/create-a-mongodb-user-from-commandline
    # dropUser('cjng96')
    # ss = "db.getSiblingDB('admin').createUser({user: '{0}', pwd:'{1}', roles:['dbAdminAnyDatabase']})".format(util.data.mongo.user, util.data.mongo.pw)
    # dk.run('mongo admin --eval "%s"' % util.str2arg(ss))
    env.runSafe(f'''mongo admin --eval "db.dropUser('{admin}')"''')
    ss = f"db.createUser({{user: '{admin}', pwd:'{pw}', roles:['root']}})"
    env.run(f'mongo admin --eval "{env.util.str2arg(ss)}"')

    env.configLine(
        path="/etc/mongod.conf",
        regexp="^#security:",
        line="security:\n  authorization: enabled",
        sudo=True,
    )
    env.run("sudo supervisorctl restart mongodb")


def installGitea(env):
    # cmd = "sudo apt install git"
    # env.run(cmd)

    # https://docs.gitea.com/installation/install-from-binary
    # cmd = "wget -O gitea https://dl.gitea.com/gitea/1.21.7/gitea-1.21.7-linux-amd64 && chmod +x gitea"
    if not env.runSafe("command -v gitea"):
        cmd = "curl -L -o gitea https://dl.gitea.com/gitea/1.21.7/gitea-1.21.7-linux-amd64 && chmod +x gitea"
        env.run(cmd)
        env.run("mv gitea /usr/local/bin/gitea")


def initGitea(env, dataDir="/var/lib/gitea"):
    env.run(f"mkdir -p {dataDir}/{{custom,data,log}}")
    env.run(f"chown -R git:git {dataDir}/")
    env.run(f"chmod -R 750 {dataDir}/")

    env.run("mkdir -p /etc/gitea")
    env.run("chown root:git /etc/gitea")
    env.run("chmod 770 /etc/gitea")

    # env.run('chmod 750 /etc/gitea')
    # env.run('chmod 640 /etc/gitea/app.ini')


def installMariaDb(env, dataDir="/var/lib/mysql", port=3306, repo=None):
    """
    repo = "deb [arch=amd64,arm64,ppc64el,s390x] https://mirror.yongbok.net/mariadb/repo/10.5/ubuntu focal main"
    """
    # hr = env.runOutput('pidof mysqld; echo').strip()
    # if len(hr) > 0:
    if env.runSafe("command -v mysqld"):
        return

    if repo is not None:
        env.run(
            "sudo apt-get install software-properties-common dirmngr apt-transport-https"
        )
        env.run(
            'sudo apt-key adv --fetch-keys "https://mariadb.org/mariadb_release_signing_key.asc"'
        )
        env.run(f'sudo add-apt-repository "{repo}"')

    env.run("sudo apt install --no-install-recommends -y mariadb-server")
    # python-mysqldb")
    # env.run("pip3 install mysql-python") # not support python3

    # 아래 이게 필요한가...
    # env.run("sudo apt install --no-install-recommends -y libmysqlclient-dev python3-pip")
    # env.run("pip3 install mysqlclient")
    env.run("sudo mkdir -p -m 755 /run/mysqld && sudo chown mysql: /run/mysqld")
    env.configLine(
        "/etc/mysql/mariadb.conf.d/50-server.cnf",
        regexp="^datadir\s*=\s*",
        line=f"datadir={dataDir}",
        appendAfterRe=r"^\[mysqld\]$",
        sudo=True,
    )
    env.configLine(
        "/etc/mysql/mariadb.conf.d/50-server.cnf",
        regexp="^port\s*=\s*[0-9]",
        line=f"port={port}",
        appendAfterRe=r"^\[mysqld\]$",
        sudo=True,
    )
    env.configLine(
        "/etc/mysql/mariadb.conf.d/50-server.cnf",
        regexp="^bind-address\s*=",
        line="#bind-address =",
        ignore=True,
        sudo=True,
    )
    # env.run("[ ! -d {0}/mysql ] && sudo mysql_install_db --ldata='{0}'".format(dataDir))
    # 이제 initMariaDb를 따로 호출해야한다
    # if not env.runSafe(f"test -d {dataDir}/mysql"):
    # env.run(f"sudo mysql_install_db --ldata='{dataDir}'")

    # dk.uploadFileTo("./files/mariadb.conf", "/tmp/efile")
    # dk.run("sudo mv /tmp/efile/mariadb.conf /etc/supervisor/conf.d/")
    # /usr/bin/mysql_secure_installation'
    env.run(
        "sudo killall mysqld_safe; sleep 3"
    )  # it runs when apt install. baseimage에서는 실행이 안된다


def mariadbInit(env, binlog, galera, galeraIps, galeraSstPw):
    """
    ips: 192.168.1.100,192.168.1.101
    binlog: true, false
    """
    ss = ""

    if galera:
        ss += f"""\
[galera]
wsrep_on=ON
wsrep_provider=/usr/lib/libgalera_smm.so
wsrep_cluster_name=iner-cluster
wsrep_cluster_address=gcomm://{galeraIps}

# 강제사항 아닌듯
#wsrep_node_name=
#wsrep_node_address=

wsrep_sst_method=mariabackup
wsrep_sst_auth=sstuser:{galeraSstPw}
binlog_format=ROW
default_storage_engine=InnoDB
innodb_autoinc_lock_mode=2
wsrep_provider_options="pc.ignore_sb=TRUE"
innodb_flush_log_at_trx_commit=0
"""

    if binlog:
        ss += """
log_bin=binlog
#max_binlog_size=100M
expire_logs_days=7
log_slave_updates=1
"""

    # /usr/lib/libgalera_smm.so
    # https://jsonobject.tistory.com/510
    env.configBlock(
        path="/etc/mysql/mariadb.conf.d/50-server.cnf",
        marker="# {mark} mariadb config",
        block=ss,
        sudo=True,
    )
    # ignore_sb=true는 split brain상태일때도 쓰기가 가능함, 한개만 쓰기일때는 안전하다
    # https://whitekeyboard.tistory.com/620?category=881248


def upcntRunStr():
    # return "test -f /var/opt/upcnt || echo 0 > /var/opt/upcnt; awk -F, '{$1=$1+1}1' /var/opt/upcnt > /tmp/upt && mv /tmp/upt /var/opt/upcnt"
    # centos에서 docker exec -i dxm bash -c "echo '1'"하면 안된다
    # 'awk -F, "{$1=$1+1}1" /var/run/upcnt > /tmp/upt && mv /tmp/upt /var/run/upcnt'
    return (
        "awk -F, '{$1=$1+1}1' /var/run/upcnt > /tmp/upt && mv /tmp/upt /var/run/upcnt"
    )


def baseimgInitScript(env):
    env.makeFile(
        content="#!/bin/bash\necho -1 > /var/run/upcnt",
        path="/etc/my_init.d/01_upcnt-init",
    )
    env.makeFile(
        content="#!/bin/bash\n! test -d /data/init.d || run-parts /data/init.d",
        path="/etc/my_init.d/02_data-init",
    )


def mariaDbForSupervisor(env, dataDir="/var/lib/mysql", port=3306):
    # hr = env.runOutput('pidof mysqld; echo').strip()
    # if len(hr) > 0:
    if env.runSafe("command -v mysqld"):
        return

    installMariaDb(env, port=port, dataDir=dataDir)
    initMariaDb(env, dataDir=dataDir)

    env.makeFile(
        content="""\
[program:mariadb]
command=/usr/sbin/mysqld
priority=999
username=mysql
#stdout_logfile=/tmp/%(program_name)s.stdout
#stderr_logfile=/tmp/%(program_name)s.stderr
autostart=true
""",
        path="/etc/supervisor/conf.d/mariadb.conf",
        sudo=True,
    )
    # dk.run("sudo sv reread && sudo sv add mariadb && sudo sv restart mariadb")
    env.run(
        "sudo supervisorctl reread && sudo supervisorctl update && sudo supervisorctl restart mariadb"
    )


def mysqlCreateUsersFromS3(env, local, bucket, key):
    # local.run("mkdir -p ./work")
    dbUserList = local.s3DownloadFile(bucket=bucket, key=key, dest=None).decode()
    dbUserList = json.loads(dbUserList)
    # mysqlCreateUsers(env, dbUserList=dbUserList['mariadb'])
    for user in dbUserList["mariadb"]:
        env.mysqlUserGen(
            id=user["name"], pw=user["password"], host=user["host"], priv=user["priv"]
        )


def mysqlWaitReady(env):
    print("wait mysql to be ready...")
    for i in range(30):
        # hr = env.runSafe(f"mysql -e 'select 1' > /dev/null 2>&1")
        hr = env.runSafe(f"mysql -e 'select 1'", printLog=False)
        if hr is False:
            print(".", end="", flush=True)
            time.sleep(1)
            continue

        print("")
        return

    raise Exception("mysql not ready. check mysql container logs.")


# mariabackup과 비교해서 복구시 1:15 vs 15초 정도로 5배 정도 느리다
# 빽업은 37 vs 11 3.5배정도 느리다
def mysqlSqlDump(env, cron):
    env.makeFile(
        """\
#!/bin/bash
if [ "$1" == "" ]; then
    FN=full-$(date +"%Y-%m%d-%H%M").sql.zst

    echo dump sql...
    time mysqldump -A --master-data=2 --flush-logs --events --routines --triggers --single-transaction -R -uroot | zstd -o $FN

    echo move file...
    mkdir -p /work/dump
    mv $FN /work/dump/

    echo remove old file...
    find /work/dump/ -mtime +10 -type f -delete
elif [ "$1" == "restore" ]; then
    echo Restore sql from "$2"
    read -p "Are you sure[y|N]? " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi

    time zstd -c -d $2 | mysql
fi
""",
        path="/usr/local/bin/db-dump",
        mode=760,
        sudo=True,
    )

    if cron:
        env.run("ln -sf /usr/local/bin/db-dump /etc/cron.daily/db-dump")


def mysqlBinDump(env, cron, desync):
    # 이제 이거만 쓴다
    # 증분빽업은 이렇게
    # 10, 1
    # time mariabackup --prepare --target-dir=/data/backup
    # time mariabackup --backup --user=root --slave-info --target-dir=/data/inc --incremental-basedir=/data/backup
    # time mariabackup --prepare --incremental-dir=/data/inc --target-dir=/data/backup
    # rm -rf /data/inc

    # backup: 20,1 - 2.5
    # restore: 16
    # dump backup: 32s
    # 스트림시에 복구할때 9초 딜레이가 있지만 무시할만. 2.5GB vs 59mb
    # backup stream: 15s - 59mb
    # restore stream: 8s(unzip), 16s(restore)

    desyncOff = ""
    desyncOn = ""
    if desync:
        # 확인은 이걸로 SHOW GLOBAL STATUS LIKE 'wsrep_local_state_comment';
        desyncOff = 'mysql -e "SET GLOBAL wsrep_desync=OFF;"'
        desyncOn = 'mysql -e "SET GLOBAL wsrep_desync=ON;"'

    env.makeFile(
        f"""\
#!/bin/bash
if [ -z "$1" ]; then
    cmt = ''
    if [ -n "$2" ]; then
        cmt = '-$2'
    fi

    echo -e "\\nBackup sql..."
    #time mariabackup --backup --user=root --slave-info --target-dir=/work/bdump
    #rm -f /work/backup.zst
    VER=$(mysql --version | sed -E "s/.*Distrib (.*)-M.*/\\1/")
    FN=bdump-$(date +"%Y-%m%d-%H%M")-$VER$cmt.sql.zst

    mkdir -p /work/bdump
    
    {desyncOff}
    time mariabackup --backup --user=root --slave-info --stream=xbstream | zstd -o /work/bdump/$FN
    {desyncOn}

    #chmod 644 /work/bdump/$FN

    echo remove old file...
    find /work/bdump/ -mtime +10 -type f -delete

    # for bup
    cp -a /work/bdump/$FN /work/bdump.zst

    touch /work/bdump/new.flag

elif [ "$1" == "restore" ]; then
    if [ ! -f "$2" ]; then
        echo invalid maria backup target[$2]
        exit 1
    fi

    echo -e "\\nRestore sql from [$2]"
    read -p "Are you sure[y|N]? " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi

    # unzip
    rm -rf /work/_restore
    mkdir -p /work/_restore
    time zstd -c -d $2 | mbstream -x -C /work/_restore

    # restore
    sv d app
    rm -rf /data/mysql
    time mariabackup --prepare --target-dir=/work/_restore
    time mariabackup --copy-back --target-dir=/work/_restore
    chown -R mysql.mysql /data/mysql
    sv u app
    #rm -rf /work/_restore
fi
""",
        path="/usr/local/bin/db-bdump2",
        mode=760,
        sudo=True,
    )
    # 동작 테스트 필요함
    env.makeFile(
        f"""\
#!/usr/bin/env python3
import subprocess, datetime, re, shutil, os, sys

bupFolder = '/work/bupOnline'
os.environ['BUP_DIR'] = bupFolder

def isMysqlLive():
    return subprocess.run('pidof mysqld', stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, shell=True).returncode == 0


def backup(cmt=''):
    cmt = f'-{{cmt}}' if cmt else ''

    print("\\nBackup sql...")
    ver = subprocess.check_output(["mysql", "--version"])
    m = re.search(r'Distrib (.*)-M.*', str(ver))
    ver = m.group(1)

    timestamp = datetime.datetime.now().strftime("%Y-%m%d-%H%M")
    filename = f"bdump-{{timestamp}}-{{ver}}{{cmt}}.sql.zst"

    backupDir = "/work/bdump"
    backupFile = os.path.join(backupDir, filename)
    os.makedirs(backupDir, exist_ok=True)

    # bup
    print(f'Bup backup starts to {{bupFolder}}...')
    if not os.path.exists(bupFolder):
        subprocess.check_call('bup init', shell=True)

    # subprocess.check_call(['bup', 'index', '/data/mysql'])
    # subprocess.check_call('time bup save -n db /data/mysql', shell=True, executable='/bin/bash')
    # subprocess.check_call(f'time zstd -c -d {{backupFile}} | bup split -n db', shell=True, executable='/bin/bash')
    
    # cmd = f"time mariabackup --backup --user=root --slave-info --stream=xbstream | zstd -o {{backupFile}}"
    # zstd만 할때 1분 30초, bup까지 하니까 3분. 두번째부터는 1분 51초
    cmd = (
        f"time mariabackup --backup --user=root --slave-info --stream=xbstream | "
        f"tee >(zstd -o {{backupFile}}) | bup split -n db"
    )
    subprocess.check_call(cmd,shell=True,executable="/bin/bash")

    # shutil.copy(backupFile, "/work/bdump.zst")
    #subprocess.check_call('ln -sf {{backupFile}} /work/bdump.zst', shell=True)

    print("Remove old files...")
    subprocess.check_call(["find", backupDir, "-mtime", "+10", "-type", "f", "-delete"])

    open(os.path.join(backupDir, f"{{filename}}.flag"), "w").close()

def restoreFile(backupFile):
    if isMysqlLive():
        print("Stop mysql service first")
        sys.exit(1)

    if not os.path.isfile(backupFile):
        print(f"Invalid maria backup target [{{backupFile}}]")
        return
    
    print(f"\\nRestore sql from [{{backupFile}}]")
    ss = input("Are you sure [y|N]? ").lower()
    if ss != "y":
        return
    
    restoreDir = "/work/_restore"
    shutil.rmtree(restoreDir, ignore_errors=True)
    os.makedirs(restoreDir)
    
    print(f'Prepare restore folder[{{restoreDir}}] from backup file[{{backupFile}}]...')
    cmd = f'time zstd -c -d {{backupFile}} | mbstream -x -C {{restoreDir}}'
    subprocess.check_call(cmd,shell=True,executable="/bin/bash")

    print('Delete old mysql data folder...')
    shutil.rmtree("/data/mysql", ignore_errors=True)

    print('Restore mysql data...')
    subprocess.check_call(["mariabackup", "--prepare", f"--target-dir={{restoreDir}}"])
    subprocess.check_call(["mariabackup", "--copy-back", f"--target-dir={{restoreDir}}"])
    subprocess.check_call("chown -R mysql.mysql /data/mysql")
    shutil.rmtree(restoreDir)

    print('restore is finished successfully.')

def restoreBup(target):
    if isMysqlLive():
        print("Stop mysql service first")
        sys.exit(1)

    # target is hash or name
    print(f"\\nRestore sql from bup[{{target}}]")
    ss = input("Are you sure [y|N]? ").lower()
    if ss != "y":
        return
    
    restoreDir = "/work/_restoreBup"
    shutil.rmtree(restoreDir, ignore_errors=True)
    os.makedirs(restoreDir)
    
    print(f'Prepare restore folder[{{restoreDir}}] from bup[{{target}}]...')
    cmd = f'time bup join db {{target}} | mbstream -x -C {{restoreDir}}'
    subprocess.check_call(cmd,shell=True,executable="/bin/bash")

    print('Delete old mysql data folder...')
    shutil.rmtree("/data/mysql", ignore_errors=True)

    print('Restore mysql data...')
    subprocess.check_call(["mariabackup", "--prepare", f"--target-dir={{restoreDir}}"])
    subprocess.check_call(["mariabackup", "--copy-back", f"--target-dir={{restoreDir}}"])
    subprocess.check_call("chown -R mysql.mysql /data/mysql", shell=True)
    shutil.rmtree(restoreDir)

    print('restore is finished successfully.')
    
def main():
    argv = sys.argv
    if len(argv) < 2:
        print("Please provide a command [backup|restoreFile|ls|restoreBup]")
        return

    cmd = argv[1]
    if cmd == "backup":
        comment = argv[2] if len(argv) > 2 else ''
        backup(comment)
    elif cmd == "restoreFile":
        if len(argv) < 3:
            print("Please provide a backup file path.")
            return
        restoreFile(argv[2])
    elif cmd == 'ls':
        print(f'bup repo is {{bupFolder}}..')
        subprocess.check_call('bup ls -l db', shell=True)
    elif cmd == 'restoreBup':
        print(f'bup repo is {{bupFolder}}..')
        restoreBup(argv[2])
    else:
        print(f"Unknown command [{{cmd}}]")
        return

if __name__ == "__main__":
    main()
""",
        path="/usr/local/bin/db-online",
        mode=760,
        sudo=True,
    )

    if cron:
        env.run("ln -sf /usr/local/bin/db-online /etc/cron.daily/db-online")


def dockerForceNetwork(env, name):
    env.run(f"docker network inspect {name} || docker network create {name}")
    # -f {{.Name}}


def getArch(env):
    os = env.getOS()
    arch = None

    if os == "ubuntu":
        arch = env.runOutput("dpkg --print-architecture").strip()
    elif os == "centos":
        arch = env.runOutput("uname -m").strip()
    else:
        raise Exception("Unsupported Operating System")

    return arch


def installDocker(env, arch=None):
    """
    arch: amd64 | arm64
    """
    if arch is None:
        arch = getArch(env)

    # if env.runRet('which docker > /dev/null') != 0:
    if env.runSafe("command -v docker"):
        return

    os = env.getOS()

    if os == "ubuntu":
        # docker.io로 설치가 더 편한데, 좀 애매하다...
        env.run(
            "sudo apt install --no-install-recommends -y apt-transport-https ca-certificates curl gnupg-agent software-properties-common"
        )
        env.run(
            "curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add -"
        )
        # sudo apt-key fingerprint 0EBFCD88
        env.run(
            f'sudo add-apt-repository "deb [arch={arch}] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable"'
        )
        env.run("sudo apt update")
        env.run("apt-cache policy docker-ce")
        env.run("sudo apt install --no-install-recommends -y docker-ce")

        env.run("sudo usermod -aG docker $USER")
        # env.run("sudo adduser {{server.id}} docker")	# remote.server.id
        # env.run("sudo service docker restart")	# /etc/init.d/docker restart
    elif os == "centos":
        env.run("sudo yum install -y yum-utils device-mapper-persistent-data lvm2")
        env.run(
            "sudo yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo"
        )
        # env.run("sudo yum makecache fast")
        env.run("sudo yum makecache")
        env.run("yum list docker-ce --showduplicates | sort -r")
        env.run("sudo yum install -y docker-ce docker-ce-cli containerd.io")
        env.run("sudo systemctl start docker")
        env.run("sudo systemctl enable docker")
        # 여기 명령어가 이상한것 같은데?
        env.run("sudo usermod -aG docker $USER")
    else:
        raise Exception(f"Unsupported Operating System - {os}")

    time.sleep(3)  # boot up


def installPodman(env, arch=None):
    """
    arch: amd64 | arm64
    """
    if arch is None:
        arch = getArch(env)

    # if env.runRet('which docker > /dev/null') != 0:
    if env.runSafe("command -v podman"):
        return

    os = env.getOS()
    if os == "ubuntu":
        env.run("sudo apt update")
        env.run("sudo apt install -y podman")
    elif os == "centos":
        env.run("sudo dnf update")
        env.run("sudo dnf install -y podman")
    else:
        raise Exception(f"Unsupported Operating System - {os}")

    time.sleep(3)  # boot up


def installRestic(env, version, arch=None):
    """
    version: 0.16.4(0.12.1)
    arch: amd64 | arm64
    """
    if arch is None:
        arch = getArch(env)

    # if env.runRet('[ -f /usr/local/bin/restic ]') != 0:
    # if not env.runSafe("test -f /usr/local/bin/restic"):
    if not env.runSafe("command -v restic"):
        env.run("sudo apt install --no-install-recommends -y bzip2")
        env.run(
            f"curl -L -o restic.bz2 https://github.com/restic/restic/releases/download/v{version}/restic_{version}_linux_{arch}.bz2"
        )
        env.run(
            "bzip2 -df restic.bz2 && chmod 755 restic && sudo mv restic /usr/local/bin/"
        )
        # env.run("rm -rf restic")


def supervisorNginxInstall(env):
    if env.runSafe("command -v nginx"):
        return

    env.run("sudo apt install --no-install-recommends -y nginx")
    env.run("sudo rm /etc/nginx/sites-enabled/default")
    env.run("sudo /etc/init.d/nginx stop")
    env.run("sudo mkdir -p /data/nginx")

    # TODO:
    # http {  client_max_body_size 100M;

    env.makeFile(
        """\
include /data/nginx/*;
""",
        "/etc/nginx/sites-available/include-data",
        sudo=True,
    )
    env.run(
        "sudo ln -sf /etc/nginx/sites-available/include-data /etc/nginx/sites-enabled/include-data"
    )

    env.makeFile(
        content="""\
[program:nginx]
command=/usr/sbin/nginx -g "daemon off;"
username=www-data
priority=900
#stdout_events_enabled=true
#stderr_events_enabled=true
#stdout_logfile= /dev/stdout
#stdout_logfile_maxbytes=0
#stderr_logfile=/dev/stderr
#stderr_logfile_maxbytes=0
autostart=true
autorestart=true
""",
        path="/etc/supervisor/conf.d/nginx.conf",
        sudo=True,
    )
    env.run(
        "sudo supervisorctl reread && sudo supervisorctl update && sudo supervisorctl restart nginx"
    )


def certbotInstall(env):
    if env.runSafe("command -v certbot"):
        return

    setupTz(env)

    # env.run("sudo apt install --no-install-recommends -y software-properties-common")
    # env.run("sudo add-apt-repository universe")
    # env.run("sudo add-apt-repository ppa:certbot/certbot")
    # env.run("sudo apt-get update")
    # env.run("sudo apt-get install --no-install-recommends -y certbot python-certbot-nginx")
    # snap설치가 기본인데, docker라서 설치가 어렵고,
    # docker로 실행하는것도 경로가 달라서 어렵다
    env.run("sudo apt update")
    env.run("sudo apt install -y python3-venv libaugeas0")
    env.run("sudo python3 -m venv /opt/certbot/")
    env.run("sudo /opt/certbot/bin/pip install --upgrade pip")
    env.run("sudo /opt/certbot/bin/pip install certbot certbot-nginx")
    env.run("sudo ln -s /opt/certbot/bin/certbot /usr/bin/certbot")

    # /etc/cron.d/certbot 자동 생성 안되면 만들어줘야한다
    # SHELL=/bin/sh
    # PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin
    # 0 */12 * * * root test -x /usr/bin/certbot -a \! -d /run/systemd/system && perl -e 'sleep int(rand(43200))' && certbot -q renew
    env.makeFile(
        content="""\
#!/bin/bash
test -x /usr/bin/certbot -a \! -d /run/systemd/system && perl -e 'sleep int(rand(43200))' && certbot -q renew
""",
        path="/etc/cron.weekly/certbot",
        sudo=True,
    )


def certbotCopy(pubWeb, web, domain, cfgName):
    # 일단 d21 proxy, direct 둘다 지원한다
    # cron으로 주기적으로 가져와야한다
    # ssh root@192.168.1.204
    full = pubWeb.loadFile(f"/etc/letsencrypt/live/{domain}/fullchain.pem", sudo=True)
    priv = pubWeb.loadFile(f"/etc/letsencrypt/live/{domain}/privkey.pem", sudo=True)

    web.run(
        f"mkdir -p /data/letsencrypt/remote/{domain}; chmod 700 /data/letsencrypt/remote"
    )
    web.makeFile(
        full,
        f"/data/letsencrypt/remote/{domain}/fullchain.pem",
        sudo=True,
        makeFolder=True,
    )
    web.makeFile(priv, f"/data/letsencrypt/remote/{domain}/privkey.pem", sudo=True)

    nextCfg = web.loadFile(f"/data/nginx/{cfgName}", sudo=True)
    if "443 ssl" not in nextCfg:
        nextCfg = nextCfg.replace(
            "server {",
            f"""server {{
  listen 443 ssl http2;
  ssl_certificate /etc/letsencrypt/remote/{domain}/fullchain.pem;
  ssl_certificate_key /etc/letsencrypt/remote/{domain}/privkey.pem;
  include /etc/letsencrypt/options-ssl-nginx.conf;
  ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;
""",
        )
        web.makeFile(nextCfg, path=f"/data/nginx/{cfgName}", sudo=True)
        web.run("nginx -s reload")


def bupInstall(env, bupPath):
    env.run(
        "sudo add-apt-repository -y ppa:ulikoehler/bup && sudo apt update && sudo apt -y install bup git"
    )

    # bup 준비
    # profile에 놓으면 de sql로 들어갔을때 못찾고(bash -l 해야만 함), .bashrc로 하면 sh에서는 못쓴다
    # sh해도 .profile은 안 읽는다. 그냥 bashrc를 쓰자
    # bash로 호출할때도 -i를 줘야만 bashrc가 동작한다 - 즉 경로나 이런건 profile에 적고 -l하는게 맞다
    if bupPath is not None:
        env.configBlock(
            path=f"/root/.profile",
            marker=f"# {{mark}} bup config",
            block=f"""\
export BUP_DIR={bupPath}
""",
        )


def certbotSetup(
    env,
    domainStr,
    email,
    name,
    httpRedirect=True,
    nginxCfgPath="/data/nginx",
    localBind=False,
    proxyProtocol=False,
):
    """
    domainStr: "a1.com a2.com"처럼 문자열 나열을 지원한다.
    """
    lst = domainStr.split(" ")
    dd = ""
    for domain in lst:
        dd += " -d %s" % domain

    extra = ""
    # run시 redicect가 기본값이다
    if httpRedirect:
        extra = "--redirect"
    else:
        extra = "--no-redirect"

    env.run(
        f"sudo certbot --nginx {dd} {extra} --non-interactive --agree-tos --email {email} --keep-until-expiring"
    )

    # http2 적용
    # listen 443 ssl; # managed by Certbot
    # env.run(f"cat /data/nginx/{name}")
    port = "443"
    if localBind:
        port = "127.0.0.1:443"

    proxyStr = ""
    if proxyProtocol:
        proxyStr = "proxy_protocol"

    env.configLine(
        path=f"{nginxCfgPath}/{name}",
        regexp=r"^ *listen +443 +ssl;",
        line=f"  listen {port} ssl http2 {proxyStr}; # managed by Certbot",
        sudo=True,
    )
    # env.run(f"cat /data/nginx/{name}")

    env.run("sudo nginx -s reload")


def nginxWebSite(
    env,
    name,
    domain,
    certAdminEmail,
    root,
    defaultServer=False,
    cacheOn=False,
    localBind=False,
    certSetup=True,
):
    ss = "default_server" if defaultServer else ""

    cache = ""
    if cacheOn:
        cache = """\
location ~* \.(?:manifest|appcache|html?|xml|json)$ {
  expires -1;
}
location ~* \.(?:jpg|jpeg|gif|png|ico|cur|gz|svg|svgz|mp4|ogg|ogv|webm|htc)$ {
  expires 1M;
  access_log off;
  add_header Cache-Control "public";
}
location ~* \.(?:css|js)$ {
  expires 1M;
  access_log off;
  add_header Cache-Control "public";
}"""

    env.makeFile(
        f"""\
# server {{
#   listen 80 {ss};
#   #listen [::]:80 ipv6only=on;
#   #listen [::]:80 default_server;
#   server_name {domain};
#   #rewrite ^ https://$server_name$request_uri? permanent;
#   return 301 https://$server_name$request_uri;
# }}
server {{
  #listen 443 ssl http2 {ss};
  listen 80 {ss};
  #listen [::]:443 ssl http2 {ss};

  server_name {domain};
  #ssl_certificate {{ssl_cert_path}}/fullchain.pem;
  #ssl_certificate_key {{ssl_cert_path}}/privkey.pem;

  root {root};
  index index.html index.htm index.nginx-debian.html;

  location / {{
    # First attempt to serve request as file, then
    # as directory, then fall back to displaying a 404.
    #try_files $uri $uri/ =404;
    try_files $uri $uri/ @rewrites;
  }}

  location @rewrites {{
    rewrite ^(.*)$ /index.html last;
  }}

  {cache}
}}
""",
        f"/data/nginx/{name}",
        sudo=True,
    )

    if certSetup:
        certbotSetup(
            env,
            domainStr=domain,
            email=certAdminEmail,
            name=name,
            localBind=localBind,
        )


# deprecated - setupWebApp을 privateApi, root없이 쓰자. publicApi는 '/'
def setupProxyForNginx(
    env,
    name,
    domain,
    certAdminEmail,
    proxyUrl,
    httpRedirect=True,
    certBot=True,
    nginxCfgPath="/data/nginx",
    buffering=True,
):
    """
    proxyUrl: http://192.168.1.105
    httpRedirect: True(all traffic from 80 to https), False(allow 80, 443 both)
    """

    print(
        "\n\n\nusing setupWebApp without privateApi parameter. setupProxyForNginxWithPrivate is deprecated...\n\n\n"
    )
    time.sleep(10)

    extra = (
        ""
        if buffering
        else """
# client_body_buffer_size 128m;
# client_body_buffer_size 0;
proxy_request_buffering off;
client_max_body_size 0;

proxy_max_temp_file_size 0;
"""
    )

    env.makeFile(
        f"""\
server {{
  listen 80;
  server_name {domain};
  #access_log /var/log/nginx/inerauth.access.log;
  error_log /var/log/nginx/{name}.error.log;
  location / {{
    # set $upstream {proxyUrl};
    # resolver 127.0.0.11 ipv6=off;
    # proxy_pass $upstream;
    proxy_pass {proxyUrl};
    proxy_buffering off;
    proxy_redirect off;
    proxy_http_version 1.1;
    #proxy_set_header Connection "";
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Scheme $scheme;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Accel-Redirect $uri;
    proxy_set_header Host $http_host;
    proxy_set_header Upgrade $http_upgrade;  # web socket
    proxy_set_header Connection upgrade;
    {extra} 
  }}
}}""",
        f"{nginxCfgPath}/{name}",
        sudo=True,
        mode=664,
    )
    if certBot:
        # env.run('sudo ln -sf /etc/nginx/sites-available/{0} /etc/nginx/sites-enabled/{0}'.format(name))
        certbotSetup(
            env,
            domainStr=domain,
            email=certAdminEmail,
            name=name,
            httpRedirect=httpRedirect,
            nginxCfgPath=nginxCfgPath,
        )
    else:
        env.run("sudo nginx -s reload")


# deprecated - setupWebApp을 root=null로 사용하라
def setupProxyForNginxWithPrivate(
    env,
    name,
    domain,
    certAdminEmail,
    proxyUrl,
    privateApi,
    publicApi="/",
    privateFilter="",
    maxBodySize="1m",
    certSetup=True,
):
    print(
        "\n\n\nusing setupWebApp without root parameter. setupProxyForNginxWithPrivate is deprecated...\n\n\n"
    )
    time.sleep(10)

    privPath = f"/data/nginx/{name}.priv"
    env.makeFile(
        f"""\
# server {{
#   listen 80;
#   #listen [::]:80 ipv6only=on;
#   server_name {domain};
#   #rewrite ^ https://$server_name$request_uri? permanent;
#   return 301 https://$server_name$request_uri;
# }}
server {{
  listen 80;
  server_name {domain};
  #access_log /var/log/nginx/inerauth.access.log;
  error_log /var/log/nginx/{name}.error.log;
  client_max_body_size {maxBodySize};

  location {privateApi} {{
    include {privPath};
    deny all;
    try_files $uri $uri @proxy;
  }}
  location {publicApi} {{
    try_files $uri $uri @proxy;
  }}
  location @proxy {{
    set $upstream {proxyUrl};
    resolver 127.0.0.11 ipv6=off;
    proxy_pass $upstream;
    proxy_buffering off;
    proxy_redirect off;
    proxy_http_version 1.1;
    #proxy_set_header Connection "";
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Scheme $scheme;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Accel-Redirect $uri;
    proxy_set_header Host $http_host;
  }}
}}""",
        f"/data/nginx/{name}",
        sudo=True,
        mode=664,
    )
    env.makeFile(privateFilter, privPath, sudo=True, mode=664)

    if certSetup:
        certbotSetup(env, domainStr=domain, email=certAdminEmail, name=name)
    else:
        env.run("sudo nginx -s reload")


# 단순 proxy로 쓰려면 privateApi, root없이 쓰자. publicApi는 '/'
# proxyUrl: http://192.168.1.105
def setupWebApp(
    env,
    name,
    domain,
    proxyUrl,
    publicApi,
    root=None,
    privateApi=None,
    privateFilter=None,
    wsPath=None,
    maxBodySize="1m",
    buffering=True,
    certSetup=True,
    certAdminEmail=None,
    httpRedirect=True,
    localBind=False,
    proxyProtocol=False,
    customConfig="",
):
    """
    root를 None하면 setupProxyForNginxWithPrivate랑 동일
    apiPath -> publicApi

    privateContent=
    allow 172.0.0.0/8; # docker
    allow 45.77.21.99; # tk1
    allow 115.178.67.152; # rt
    """

    privPath = f"/data/nginx/{name}.priv"
    if privateFilter is not None:
        env.makeFile(privateFilter, privPath, sudo=True, mode=664)

    extra = (
        ""
        if buffering
        else """
# client_body_buffer_size 128m;
# client_body_buffer_size 0;
proxy_request_buffering off;
client_max_body_size 0;

proxy_max_temp_file_size 0;
"""
    )

    proxyContent = f"""
    set $upstream {proxyUrl};
    resolver 127.0.0.11 ipv6=off;
    proxy_pass $upstream;
    proxy_buffering off;
    proxy_redirect off;
    proxy_http_version 1.1;
    #proxy_set_header Connection "";
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Scheme $scheme;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Accel-Redirect $uri;
    proxy_set_header Host $http_host;
    {extra}
"""

    wsContent = ""
    if wsPath is not None:
        wsContent = f"""location {wsPath} {{
    {proxyContent}
    proxy_set_header Upgrade $http_upgrade; # for ws2
    proxy_set_header Connection upgrade;
    proxy_read_timeout 1d;
  }}"""

    rootContent = ""
    if root is not None:
        rootContent = f"""root {root};
  index index.html;
  location / {{
    # First attempt to serve request as file, then
    # as directory, then fall back to displaying a 404.
    #try_files $uri $uri/ =404;
    try_files $uri $uri/ @rewrites;
  }}
  location @rewrites {{
    rewrite ^(.*)$ /index.html last;
  }}"""

    # server {{
    #   listen 80;
    #   #listen [::]:80 ipv6only=on;
    #   server_name {domain};
    #   #rewrite ^ https://$server_name$request_uri? permanent;
    #   return 301 https://$server_name$request_uri;
    # }}

    privateContent = ""
    if privateApi is not None:
        privateContent = f"""location {privateApi} {{
    include {privPath};
    deny all;
    try_files $uri $uri @proxy;
  }}
"""

    env.makeFile(
        f"""\
server {{
  listen 80;
  server_name {domain};
  #access_log /var/log/nginx/{name}.access.log;
  error_log /var/log/nginx/{name}.error.log;
  client_max_body_size {maxBodySize};
  resolver 127.0.0.11 valid=30s;

  location {publicApi} {{
    try_files $uri $uri @proxy;
  }}
  {privateContent}
  {wsContent}
  {rootContent}
  location @proxy {{
    {proxyContent}
  }}
  {customConfig}
}}""",
        f"/data/nginx/{name}",
        sudo=True,
        mode=664,
    )

    if certSetup:
        if certAdminEmail is None:
            raise Exception("should specify [certAdminEmail] for certSetup")

        certbotSetup(
            env,
            domainStr=domain,
            name=name,
            email=certAdminEmail,
            httpRedirect=httpRedirect,
            localBind=localBind,
            proxyProtocol=proxyProtocol,
        )
    else:
        env.run("sudo nginx -s reload")


def cronResticB2BackupFromS3(env, local, bucket, key, b2Repo, pw, dirs):
    if env.runSafe("test -f /etc/cron.daily/restic-sync"):
        return
    b2Info = local.s3DownloadFile(bucket=bucket, key=key, dest=None).decode()
    b2Info = json.loads(b2Info)
    cronResticB2Backup(env, "restic-backup", b2Info.id, b2Info.secret, b2Repo, pw, dirs)


def cronResticB2Backup(env, name, b2id, b2secret, b2repo, pw, dirs, baseDir=None):
    pp = f"/etc/cron.daily/{name}"
    # if env.runSafe(f"test -f {pp}"):
    #    return

    cdCmd = ""
    if baseDir is not None:
        cdCmd = f"cd {baseDir};"

    env.makeFile(
        content=f"""\
#!/bin/bash
export B2_ACCOUNT_ID="{b2id}"
export B2_ACCOUNT_KEY="{b2secret}"
export RESTIC_REPOSITORY="b2:{b2repo}"
export RESTIC_PASSWORD="{env.util.str2arg(pw)}"
if [ "x$1" == "x" ]; then
  {cdCmd}restic backup {dirs}
  (( RANDOM%30 == 0)) && restic forget --keep-last 10 --keep-daily 60 --keep-weekly 42 --keep-monthly 24 --prune
else
  # restore latest --target . --path /media/jail
  restic "$@"
fi
""",
        path=pp,
        sudo=True,
        mode=770,
    )
    try:
        env.runOutputAll(f"sudo {pp} init")
    except coSsh.MyCalledProcessError as e:
        # 이미 설정되어 있으면 무시
        if "failed: config already exists" in e.output:
            return

        raise e


def installGolang(env, version, arch):
    """
    version=1.13.5
    arch=linux-arm64|linux-armv6l|windows-amd64|darwin-amd64(mac)
    """
    if env.runSafe(". ~/.profile && command -v go"):
        return

    env.run(f"curl -o go.tar.gz https://dl.google.com/go/go{version}.{arch}.tar.gz")
    env.run("sudo rm -rf /usr/local/go && sudo tar -C /usr/local -xzf go.tar.gz")
    env.configBlock(
        path="~/.profile",
        marker="### {mark} golang path",
        block="export PATH=$PATH:/usr/local/go/bin",
    )


def installGocryptfs(env, withOpenssl=False):
    if env.runSafe(". ~/.profile && command -v gocryptfs"):
        return

    # env.run(". ~/.profile && go get -d github.com/rfjakob/gocryptfs")
    # buildScript = "build.bash" if withOpenssl else "build-without-openssl.bash"
    # env.run(f". ~/.profile && cd $(go env GOPATH)/pkg/mod/github.com/rfjakob/gocryptfs@v1.8.0 && ./{buildScript}")
    env.run(". ~/.profile && git clone https://github.com/rfjakob/gocryptfs.git")
    env.run(". ~/.profile && cd gocryptfs && ./build-without-openssl.bash")
    env.run("rm -rf gocryptfs")

    env.configBlock(
        path="~/.profile",
        marker="### {mark} gocryptfs path",
        block="export PATH=$PATH:~/go/bin",
    )
    env.configLine(
        path="/etc/fuse.conf",
        sudo=True,
        append=True,
        regexp="user_allow_other",
        line="user_allow_other",
    )


def installTransmission(env, port, userName, pw, downDir, incompleteDir, watchDir):
    if port == "":
        raise Exception("transmission - specify port")
    if userName == "":
        raise Exception("transmission - specify userName")
    if pw == "":
        raise Exception("transmission - specify pw")
    if downDir == "":
        raise Exception("transmission - specify downDir")
    if incompleteDir == "":
        raise Exception("transmission - specify incompletedir")

    if env.runSafe("command -v transmission-cli1"):
        return

    env.run("sudo apt install -y transmission-daemon")
    env.run("sudo /etc/init.d/transmission-daemon stop")

    env.run(
        f"sudo mkdir -p {downDir} && sudo chmod 775 {downDir} -R && sudo chown debian-transmission: {downDir}"
    )
    env.run(
        f"sudo mkdir -p {incompleteDir} && sudo chmod 775 {incompleteDir} -R && sudo chown debian-transmission: {incompleteDir}"
    )
    # env.run('sudo mkdir -p %s' % watchDir)

    pp = "/etc/transmission-daemon/settings.json"
    # env.configLine(path=pp, regexp=r'^\s*"rpc-username":', sudo=True, line=f'"rpc-username": "{userName}",')
    # env.configLine(path=pp, regexp=r'^\s*"rpc-password":', sudo=True, line=f'"rpc-password": "{pw}",')
    # env.configLine(path=pp, regexp=r'^\s*"rpc-port":', sudo=True, line=f'"rpc-port": {port},')
    # env.configLine(path=pp, regexp=r'^\s*"rpc-whitelist-enabled":', sudo=True, line='"rpc-whitelist-enabled": false,')
    # env.configLine(path=pp, regexp=r'^\s*"download-dir":', sudo=True, line=f'"download-dir": "{downDir}",')
    # env.configLine(path=pp, regexp=r'^\s*"incomplete-dir":', sudo=True, line=f'"incomplete-dir": "{incompleteDir}",')
    # env.configLine(path=pp, regexp=r'^\s*"incomplete-dir-enabled":', sudo=True, line='"incomplete-dir-enabled": true,')
    # env.configLine(
    #     path=pp, regexp=r'^\s*"trash-original-torrent-files":', sudo=True, line='"trash-original-torrent-files": true,'
    # )
    # env.configLine(path=pp, regexp=r'^\s*"umask":', sudo=True, line='"umask": 2,')  # other에게는 write권한 안주는거

    ss = env.loadFile(pp, sudo=True)
    dic = json.loads(ss)
    dic["rpc-username"] = userName
    dic["rpc-password"] = pw
    dic["rpc-port"] = port
    dic['rpc-whitelist-enabled"'] = False
    dic["download-dir"] = downDir
    dic["incomplete-dir"] = incompleteDir
    dic["incomplete-dir-enabled"] = True
    dic["trash-original-torrent-files"] = True
    dic["umask"] = 2

    if watchDir is not None:
        # 이거 해당 파라미터가 없으면 마지막에 추가되서 깨진다 - 이거 json로드해서 하도록 해야겠다
        # env.configLine(path=pp, regexp=r'^\s*"watch-dir":', sudo=True, append=True, line=f'"watch-dir": "{watchDir}",')
        # env.configLine(
        #     path=pp, regexp=r'^\s*"watch-dir-enabled":', sudo=True, append=True, line='"watch-dir-enabled": true,'
        # )
        dic["watch-dir"] = watchDir
        dic["watch-dir-enabled"] = True

    ss = json.dumps(dic)
    env.makeFile(ss, path=pp, sudo=True)

    env.run("sudo /etc/init.d/transmission-daemon start")


def pm2Register(env, nvmPath="~/.nvm", useNvm=True):
    print("task: pm2 register...")
    env.onlyRemote()

    cmd = ""
    if useNvm:
        cmd += ". %s/nvm.sh && " % nvmPath
    cmd += f"cd {env.server.deployPath} && pm2 delete pm2.json && pm2 start pm2.json"
    env.run(cmd)


def pm2Install(env):
    env.run(
        f". ~/.profile && cd {env.server.deployPath} && /opt/nvm/nvm-exec npm i -g pm2"
    )


def nvmInstall(env, account=None, nodeVer=None):
    """
    node는 추가시 34m정도
    """
    if env.runSafe("type -f /opt/nvm/nvm-exec"):
        return

    env.run(
        "curl -o- https://raw.githubusercontent.com/creationix/nvm/master/install.sh | bash"
    )
    env.run("sudo rm -rf /opt/nvm && sudo mv -f ~/.nvm /opt/nvm")
    # env.run('sudo rm -rf /opt/nvm && sudo ln -sf ~/.nvm /opt/nvm') # 링크하면 오류난다.
    env.configLine(
        "~/.bashrc", regexp="^export NVM_DIR=", line="export NVM_DIR=/opt/nvm"
    )
    # env.run('echo \'export NVM_DIR=/opt/nvm\' | sudo dd of=/etc/profile.d/nvm_path.sh')

    # nvm.apply_users
    if account is not None:
        home = env.runOutput(f"echo ~{account}").strip()

        env.configBlock(
            f"{home}/.bashrc",
            "### {mark} NVM env",
            '''\
export NVM_DIR=/opt/nvm
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
[ -s "$NVM_DIR/bash_completion" ] && . "$NVM_DIR/bash_completion"''',
        )

    if nodeVer is not None:
        env.run(f". /etc/profile && . /opt/nvm/nvm.sh && nvm install {nodeVer}")


def fnmInstall(env, nodeVer=None):
    if env.runSafe("command -v fnm"):
        return

    env.run("curl -fsSL https://fnm.vercel.app/install | bash")

    # env.run("sudo rm -rf /opt/nvm && sudo mv -f ~/.nvm /opt/nvm")
    # env.configLine(
    #     "~/.bashrc", regexp="^export NVM_DIR=", line="export NVM_DIR=/opt/nvm"
    # )
    env.configBlock(
        "/etc/profile",
        "### {mark} fnm path",
        '''export PATH=/root/.local/share/fnm:$PATH\neval "`fnm env`"''',
        sudo=True,
    )

    if nodeVer is not None:
        env.run(f". /etc/profile && fnm install {nodeVer}")


def pnpmAndGulp(env):
    # 이거 의미 없다. 쓰면 안된다.
    env.run(". /etc/profile && . /opt/nvm/nvm.sh && npm install -g pnpm")
    env.run(". /etc/profile && . /opt/nvm/nvm.sh && pnpm install -g gulp")


def installYarnGulp(env):
    # . /opt/nvm.sh --install 이거는 .nvmrc를 인스톨을 못한다.
    env.run(
        f". ~/.profile && . /opt/nvm/nvm.sh && cd {env.server.deployPath} && nvm install"
    )

    # env.run("curl -sS https://dl.yarnpkg.com/debian/pubkey.gpg | sudo apt-key add -")
    # env.run('echo "deb https://dl.yarnpkg.com/debian/ stable main" | sudo tee /etc/apt/sources.list.d/yarn.list')
    # env.run("sudo apt update && sudo apt install -y yarn")
    env.run("npm install --global yarn")

    env.run(
        f". ~/.profile && cd {env.server.deployPath} && /opt/nvm/nvm-exec npm i -g gulp"
    )


def installNvmPnpmGulp(env, gulpBuild=True):
    """
    pnpm 이제 쓰지말자, node_modules link폴더 인식 안되고,
    자꾸 global설치 위치 잘못됬다고 오류난다.ㅜㅜ
    """
    # . /opt/nvm.sh --install 이거는 .nvmrc를 인스톨을 못한다.
    env.run(
        f". ~/.profile && . /opt/nvm/nvm.sh && cd {env.server.deployPath} && nvm install"
    )
    env.run(
        f". ~/.profile && cd {env.server.deployPath} && /opt/nvm/nvm-exec npm install -g pnpm"
    )
    env.run(
        f". ~/.profile && cd {env.server.deployPath} && sudo -l -u cjng96 /opt/nvm/nvm-exec pnpm install -g gulp"
    )
    env.run(
        f". ~/.profile && cd {env.server.deployPath} && /opt/nvm/nvm-exec pnpm install"
    )
    if gulpBuild:
        env.run(
            f". ~/.profile && cd {env.server.deployPath} && /opt/nvm/nvm-exec gulp build"
        )


def installNvmGulp(env, installGulp=True, gulpBuild=True, path=None):
    if path is None:
        path = env.util.cfg.deployPath

    # . /opt/nvm.sh --install 이거는 .nvmrc를 인스톨을 못한다.
    env.run(f". ~/.profile && . /opt/nvm/nvm.sh && cd {path} && nvm install")
    if installGulp:
        env.run(f". ~/.profile && cd {path} && /opt/nvm/nvm-exec npm install -g gulp")

    env.run(f". ~/.profile && cd {path} && /opt/nvm/nvm-exec npm install")
    if gulpBuild:
        env.run(f". ~/.profile && cd {path} && /opt/nvm/nvm-exec gulp build")


def installFail2ban(env, action="iptables-multiport", blockType=None, ignoreIps=""):
    """
    ignoreIps: '1.1.1.1 2.2.2.2' or [ '1.1.1.1', '2.2.2.2' ]
    """
    if isinstance(ignoreIps, list):
        ignoreIps = " ".join(ignoreIps)

    def _gen():
        env.makeFile(
            path="/etc/fail2ban/jail.local",
            content=f"""\
[DEFAULT]
ignoreip = 127.0.0.1/8 {ignoreIps}
# 30m
bantime  = 1800
findtime  = 300
maxretry = 5
destemail = cjng96@gmail.com
sender = fail2ban@n2.com
mta = sendmail
# action = %(action_mwl)s
banaction = {action}

[sshd]
enabled = true
port     = 22
""",
            sudo=True,
        )
        if blockType is not None:
            env.configLine(
                path="/etc/fail2ban/action.d/iptables-common.conf",
                regexp="blocktype\s*=",
                line=f"blocktype = {blockType}",
                sudo=True,
            )

    if env.runSafe("command -v fail2ban-client"):
        _gen()
        return

    env.run("sudo apt install --no-install-recommends -y fail2ban")
    env.run("sudo systemctl enable fail2ban")

    _gen()
    env.run("sudo systemctl restart fail2ban")


def rcloneSetupForN2(env, accountName, pubs):
    # backup.strEnsure("/jail/%s/.ssh/authorized_keys" % 'b_engdb', pub, sudo=True)
    backup = env.remoteConn(host="backup.mmx.kr", port=7022, id="cjng96")
    makeSftpUser(backup, accountName, "/jail", "data", pubs)

    installRclone(env)
    setupRclone(
        env,
        name="n2",
        type="sftp",
        host="backup.mmx.kr",
        port=7022,
        user=accountName,
        keyFile="~/.ssh/id_rsa",
    )


def sshTunneling(env, runUser, name, host, user, local, remote, port=22):
    """
    sudo systemctl status secure-tunnel@dkreg
    local포트를 remote로 연결하는거 - docker registry에서 사용한다.

    """
    # https://gist.github.com/drmalex07/c0f9304deea566842490
    env.makeFile(
        f"""\
[Unit]
Description=Setup a secure tunnel to %I
After=network.target

[Service]
ExecStart=/usr/bin/ssh -F /etc/default/secure-tunnel.config -NT %i

# Restart every >2 seconds to avoid StartLimitInterval failure
RestartSec=5
Restart=always
User={runUser}

[Install]
WantedBy=multi-user.target
""",
        path="/etc/systemd/system/secure-tunnel@.service",
        sudo=True,
    )

    env.run("sudo touch /etc/default/secure-tunnel.config")
    env.configBlock(
        "/etc/default/secure-tunnel.config",
        f"### {{mark}} {name}",
        f"""\
Host {name}
   HostName {host}
   Port {port}
   User {user}
   #IdentityFile /etc/some_folder/id_rsa.some-user.examle.com
   LocalForward {local} {remote}
   ServerAliveInterval 60
   ExitOnForwardFailure yes
""",
        sudo=True,
    )

    # systemd mount는 root로 실행된다
    env.run(f"ssh-keygen -R [{host}]:{port}")
    env.run(
        f"ssh-keyscan -p {port} -t rsa {host} | sudo tee -a /home/{runUser}/.ssh/known_hosts"
    )

    env.run(f"sudo systemctl enable --now secure-tunnel@{name}")


def scriptBasic(env):
    env.configBlock(
        path="~/.bashrc",
        marker="# {mark} basic script",
        block=f"""
alias sz="sudo du -hd1 | sort -h"
""",
    )


def scriptDocker(env, saYml="./resource/sa.yml"):
    env.makeFile(
        path="/usr/local/bin/de", content="""docker exec -it "$@" bash -l """, sudo=True
    )
    env.makeFile(
        path="/usr/local/bin/dl", content="""docker logs --tail 3000 "$@" """, sudo=True
    )
    env.makeFile(
        path="/usr/local/bin/dlf",
        content="""docker logs ---tail 500 -f "$@" """,
        sudo=True,
    )
    env.makeFile(
        path="/usr/local/bin/dlg",
        content="""A=`docker inspect --format '{{.LogPath}}' "$@"`\necho $A\nvi $A""",
        sudo=True,
    )

    # https://www.jorgeanaya.dev/en/bin/docker-ps-prettify/
    # 위에꺼 이름이 길거나 하면 잘 안된다. 보기 안좋다
    env.makeFile(
        path="/usr/local/bin/dp",
        content="""
#docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Networks}}\t{{.Ports}}' "$@" | less -N -S
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}({{.RunningFor}})\t{{.ID}} {{.Networks}}' -a "$@" """,
        sudo=True,
    )
    env.makeFile(path="/usr/local/bin/di", content="""docker images """, sudo=True)

    env.makeFile(path="/usr/local/bin/dr", content="""docker rm -f "$@" """, sudo=True)
    # dri bsone:*
    env.makeFile(
        path="/usr/local/bin/dri",
        content="""docker rmi $(docker images -q "$@") """,
        sudo=True,
    )
    # env.makeFile(path="/usr/local/bin/dri", content="""docker rmi "$@" """, sudo=True)

    # docker backup script - 잘 안쓴다
    env.makeFile(
        """\
#!/bin/bash
if [ "$#" -ne 1 ]; then
  echo 'Please docker_backup CONTAINER_NAME'
  exit 1
fi
name=$1
mkdir -p ~/backup
time nice docker export $(docker inspect --format="\{{.Id}}" $name) | zstd -o ~/backup/$name-$(date +%y-%m%d_%H%M%S).zst
""",
        "/usr/local/bin/docker_backup",
        sudo=True,
    )

    # run할때 쓰는 cmd, port, volumes를 잃어버린다. run할때 해야 함
    env.makeFile(
        """\
#!/bin/bash
if [ "$#" -ne 2 ]; then
  echo 'Please docker_restore BACKUP_FILE IMAGE_NAME'
  exit 1
fi
fn=$1
image=$2
time zstd -d $fn -c | docker import --change 'CMD ["/start"]' - $image
""",
        "/usr/local/bin/docker_restore",
        sudo=True,
    )

    pp = os.path.dirname(os.path.abspath(__file__))
    env.copyFile(
        srcPath=f"{pp}/sa.py",
        targetPath="/usr/local/bin/sa",
        sudo=True,
    )

    env.copyFile(
        srcPath=saYml,
        targetPath="/etc/sa.yml",
        sudo=True,
    )


def scriptPodman(env, saYml="./resource/sa.yml"):
    env.run("mkdir -p ~/.local/bin")
    env.makeFile(path="~/.local/bin/pe", content="""podman exec -it "$@" bash -l """)
    env.makeFile(path="~/.local/bin/pl", content="""podman logs --tail 3000 "$@" """)
    env.makeFile(
        path="~/.local/bin/plf",
        content="""podman logs ---tail 500 -f "$@" """,
    )
    env.makeFile(
        path="~/.local/bin/plg",
        content="""A=`podman inspect --format '{{.LogPath}}' "$@"`\necho $A\nvi $A""",
    )

    # https://www.jorgeanaya.dev/en/bin/docker-ps-prettify/
    # 위에꺼 이름이 길거나 하면 잘 안된다. 보기 안좋다
    env.makeFile(
        path="~/.local/bin/dp",
        content="""
#docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Networks}}\t{{.Ports}}' "$@" | less -N -S
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}({{.RunningFor}})\t{{.ID}} {{.Networks}}' -a "$@" """,
    )
    env.makeFile(path="~/.local/bindi", content="""docker images """)

    env.makeFile(path="~/.local/bin/dr", content="""docker rm -f "$@" """)
    # dri bsone:*
    env.makeFile(
        path="~/.local/bin/dri",
        content="""docker rmi $(docker images -q "$@") """,
    )
    # env.makeFile(path="/usr/local/bin/dri", content="""docker rmi "$@" """, sudo=True)

    # docker backup script - 잘 안쓴다
    env.makeFile(
        """\
#!/bin/bash
if [ "$#" -ne 1 ]; then
  echo 'Please docker_backup CONTAINER_NAME'
  exit 1
fi
name=$1
mkdir -p ~/backup
time nice docker export $(docker inspect --format="\{{.Id}}" $name) | zstd -o ~/backup/$name-$(date +%y-%m%d_%H%M%S).zst
""",
        "~/.local/bin/docker_backup",
    )

    # run할때 쓰는 cmd, port, volumes를 잃어버린다. run할때 해야 함
    env.makeFile(
        """\
#!/bin/bash
if [ "$#" -ne 2 ]; then
  echo 'Please docker_restore BACKUP_FILE IMAGE_NAME'
  exit 1
fi
fn=$1
image=$2
time zstd -d $fn -c | docker import --change 'CMD ["/start"]' - $image
""",
        "~/.local/bin/docker_restore",
    )

    pp = os.path.dirname(os.path.abspath(__file__))
    env.copyFile(
        srcPath=f"{pp}/sa.py",
        targetPath="~/.local/bin/sa",
    )

    env.copyFile(
        srcPath=saYml,
        targetPath="~/.local/share/sa.yml",
    )
