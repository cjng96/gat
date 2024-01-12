#!/usr/bin/env python3

import os
import re
import sys
import json
import yaml
import asyncio
import datetime
import subprocess


# dkCmd = "sudo docker"
dkCmd = "docker"


def dockerExec(cmd):
    ret = subprocess.check_output(f"{dkCmd} exec -it {cmd}", shell=True)
    print(ret.decode("utf-8").strip())


def printTable(arr, minWidth=3, minGap=2):
    """
    arr = [[a,b,c], [v1,v2,v3]]
    """
    header = arr[0]
    rows = arr[1:]
    ws = []
    for h in header:
        ws.append(max(len(h), minWidth))

    for row in rows:
        for i, c in enumerate(row):
            sz = len(str(c))
            if sz > ws[i]:
                ws[i] = sz

    for row in arr:
        for i, c in enumerate(row):
            print(f"{c:<{ws[i]+minGap}}", end="")
        print("")


def secs2str(sec):
    """
    uptime용
    """
    td = datetime.timedelta(seconds=sec)
    if td.days > 30:
        return f"{int(td.days/30)}M"

    if td.days > 0:
        return f"{td.days}D"

    if td.seconds > 60 * 60:
        return f"{int(td.seconds/(60*60))}H"

    if td.seconds > 60 * 2:
        return f"{int(td.seconds/60)}m"

    return f"{td.seconds}s"


def pstime2str(tt):
    """
    00:01:02 -> 01:02
    02:01:02 -> 2h 1m
    15-02:01:02 -> 15d 2h
    """
    if tt.startswith("00:"):
        return f"{tt[3:]}"
    if "-" in tt:
        return f"{tt[:-9]}d {int(tt[-8:-6])}h"

    return f"{int(tt[:2])}h {int(tt[3:5])}m"


def test_pstime2str():
    ss = pstime2str("00:01:02")
    print(ss)
    assert ss == "01:02"
    ss = pstime2str("01:02:03")
    print(ss)
    assert ss == "1h 2m"

    ss = pstime2str("15-01:02:03")
    print(ss)
    assert ss == "15d 1h"


def size2str(kb):
    """
    75900 -> 75mb
    275899 -> 275mb
    3275899 -> 3275mb
    """
    mb = kb / 1024
    return f"{mb:.1f}mb"


def test_size2str():
    ss = size2str(75900)
    print(ss)
    assert ss == "74.1mb"

    ss = size2str(275899)
    print(ss)
    assert ss == "269.4mb"

    ss = size2str(3275899)
    print(ss)
    assert ss == "3199.1mb"


# test_pstime2str()
# test_size2str()


def doPrune():
    with open("/etc/sa.yml", "r") as fp:
        info = yaml.safe_load(fp.read())
        deleteTargets = info["prune"]

    cmd = (
        dkCmd
        + """ ps -a --format '{"id":"{{ .ID }}", "img": "{{ .Image }}", "name":"{{ .Names }}"}'"""
    )
    ss = subprocess.check_output(cmd, shell=True).decode("utf-8").strip()
    # print(ss)

    lines = ss.splitlines()
    ids = []
    for line in lines:
        con = json.loads(line)
        # name = con["name"]
        img = con["img"]

        cmd = f"{dkCmd} image history -q {img}"
        ss = subprocess.check_output(cmd, shell=True).decode("utf-8").strip()
        qs = ss.splitlines()
        ids = ids + qs

    cmd = (
        dkCmd
        + """ images --format '{"id":"{{.ID}}", "img":"{{.Repository}}:{{.Tag}}"}' """
    )

    ss = subprocess.check_output(cmd, shell=True).decode("utf-8").strip()
    images = ss.splitlines()
    for node in images:
        img = json.loads(node)
        # print(f'img {img}')
        imgName = img["img"].split(":")[0]
        if img["id"] not in ids:
            print(f"\n{img['img']}({img['id']}) is not used...")
            if imgName in deleteTargets:
                cmd = f"{dkCmd} rmi {img['id']}"
                # print(cmd)
                ss = subprocess.check_output(cmd, shell=True).decode("utf-8").strip()
                print(ss)
            else:
                print("  -> but don't delete it which is not in deleteTarget list")


def parsePs(ss):
    lines = ss.splitlines()
    upcnt = lines[0].strip()
    lines = lines[2:]

    # print(ss)
    # print(f"upcnt:{upcnt}")
    # print(f"line:{lines}")

    # ELAPSED     PID %CPU    VSZ   RSS %MEM     TIME    PPID CMD
    #       0     756  0.0   9524  2832  0.0 00:00:00       0 bash -c cat /var/run/upcnt;ps -awfxo etimes,pid,%cpu,vsz,rss,%mem,time,ppid,
    #       0     763  0.0  11244  1200  0.0 00:00:00     756  \_ ps -awfxo etimes,pid,%cpu,vsz,rss,%mem,time,ppid,cmd
    #  580096     114  0.0  13744  1136  0.0 00:00:00       0 bash -l
    # 8896973       1  0.0  19624    12  0.0 00:00:00       0 /usr/bin/python3 -u /sbin/my_init
    # 8896971      14  0.0 234128   876  0.0 00:00:01       1 /usr/sbin/syslog-ng --pidfile /var/run/syslog-ng.pid -F --no-caps
    # 8896969      22  0.0   1964    92  0.0 00:01:36       1 /usr/bin/runsvdir -P /etc/service
    # 8896969      23  0.0   1812   284  0.0 00:00:00      22  \_ runsv app
    #  580092     421  1.2 497560 15144  0.4 01:59:05      23      \_ python3 -u sermon.py

    # cpu가 166, 소요시간이 날짜 넘어가면 1-04:08:38 형태
    p = re.compile(
        # r"(.+?\s\d\d\d\d)\s+(\d*)\s+(\d+\.\d+)\s+(\d+)\s+(\d+)\s+(\d+\.\d+)\s+(\d+:\d+:\d+)\s+(\d+)\s+(.+)"
        r"\s*(\d+)\s+(\d*)\s+(\d+(\.\d+)?)\s+(\d+)\s+(\d+)\s+(\d+\.\d+)\s+((\d+-)?\d+:\d+:\d+)\s+(\d+)\s+(.+)"
    )
    # 0:elapsed, 1:pid, 2:cpu, 3:cpu1, 4:vsz, 5:rss, 6:mem, 7:time 8:time-day 9:ppid, 10:cmd

    # app number
    apps = []
    for l2 in lines:
        m = p.match(l2)
        if m is None:
            raise Exception(f"invalid dk status - {l2}")

        # container pause상태일때도
        # print(f"match - {m}")
        apps.append(m.groups())

    appPpid = -1
    for idx, node in enumerate(apps):
        # for i,n in enumerate(node):
        #     print(f'{i}: {n}')
        cmd = node[10]
        # print(f"cmd - {cmd} {len(node)}")
        if cmd == "\\_ runsv app":
            # print(f'found - pp - {node[1]}')
            appPpid = node[1]

    app = None
    for idx, node in enumerate(apps):
        ppid = node[9]
        if ppid == appPpid:
            app = node

    return upcnt, app


def outAdd(out, isJson, name, image, uptime, cpu, rss, restart, time, cmd):
    if isJson:
        out[name] = dict(
            image=image,
            uptime=uptime,
            cpu=cpu,
            rss=rss,
            restart=restart,
            time=time,
            cmd=cmd,
        )
    else:
        out.append([name, image, uptime, cpu, rss, restart, time, cmd])


async def asyncRun(*args):
    p = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE)
    stdout, stderr = await p.communicate()
    return stdout


async def asyncShell(cmd):
    p = await asyncio.create_subprocess_shell(cmd, stdout=asyncio.subprocess.PIPE)
    stdout, stderr = await p.communicate()
    return stdout


async def asyncGatherN(n, *coros):
    sem = asyncio.Semaphore(n)

    async def sem_coro(coro):
        async with sem:
            return await coro

    return await asyncio.gather(*(sem_coro(c) for c in coros))


async def doLs(isJson=False):
    # https://stackoverflow.com/questions/61528514/docker-format-with-json-specific-placeholder-syntax-for-multiple-placeholders
    cmd = (
        dkCmd
        + """ ps -a --format '{"id":"{{ .ID }}", "img": "{{ .Image }}", "name":"{{ .Names }}", "status":"{{ .Status }}"}'"""
    )
    ss = subprocess.check_output(cmd, shell=True).decode("utf-8").strip()
    # print(ss)

    lst = ss.splitlines()
    cons = []

    async def _run(ll):
        con = json.loads(ll)
        name = con["name"]
        status = con["status"]

        if status.startswith("Exited ") or status == "Created":
            cons.append([con, -1, "[Container exited]"])
            return

        # lstart, start_time, etimes
        # cmd = f"""docker exec -it {name} ps -awfxo lstart,pid,%cpu,vsz,rss,%mem,time,ppid,cmd"""
        # f가 트리표시, w가 무제한길이, u가 다양한 정보 표시, ax전체 프로세스 표시
        try:
            # https://superuser.com/questions/1326853/docker-exec-messes-up-terminal-line-feeds
            # -it is broken terminal
            cmd = f"""{dkCmd} exec -t {name} bash -c 'cat /var/run/upcnt;ps -awfxo etimes,pid,%cpu,vsz,rss,%mem,time,ppid,cmd' """
            # ss = subprocess.check_output(cmd, shell=True).decode("utf-8").strip()
            ss = (await asyncShell(cmd)).decode("utf-8").strip()
            upcnt, app = parsePs(ss)
            cons.append([con, upcnt, app])
            # print(f"appenmd - {con} , {upcnt} ---{app}")
        except Exception as e:
            if " returned non-zero exit status " in str(e):
                cons.append([con, -1, "[No sa container]"])
                return

            cons.append([con, -1, f"[{e}]"])

    tasks = [_run(ll) for ll in lst]
    await asyncGatherN(5, *tasks)

    # 이름순 정렬 - 생성순이라서 안하는게 나을려나..
    # sorted(cons, key=lambda item: item[0]["name"])

    if isJson:
        out = {}
    else:
        out = []
        out.append(["NAME", "image", "uptime", "%CPU", "RSS", "↺", "TIME", "CMD"])

    for node in cons:
        con, upcnt, app = node
        name = con["name"]
        img = con["img"]
        try:
            restart = int(upcnt)
        except:
            restart = -1

        if app is None:
            outAdd(
                out, isJson, name, img, "-", "-", "-", restart, "-", "No running app"
            )
        elif type(app) is str:
            st = app
            outAdd(out, isJson, name, img, "-", "-", "-", restart, "-", st)

        else:
            # print(app)
            start = int(app[0])  # 초단위 - 이쁘게 바꾸자
            start = secs2str(start)
            # pid = app[1]
            cpu = app[2]
            rss = app[5]
            rss = size2str(int(rss))
            # mem = app[5]
            time = app[7]
            time = pstime2str(time)

            cmd = app[10]
            cmd = cmd[cmd.find(" \\_ ") + 4 :]
            outAdd(out, isJson, name, img, start, cpu, rss, restart, time, cmd)

    if isJson:
        print(json.dumps(out))
    else:
        printTable(out)


def test():
    ss = """\
0
ELAPSED     PID %CPU    VSZ   RSS %MEM     TIME    PPID CMD
       0     756  0.0   9524  2832  0.0 15-00:00:00       0 bash -c cat /var/run/upcnt;ps -awfxo etimes,pid,%cpu,vsz,rss,%mem,time,ppid,
       0     763  0.0  11244  1200  0.0 00:00:00     756  \_ ps -awfxo etimes,pid,%cpu,vsz,rss,%mem,time,ppid,cmd
  580096     114  0.0  13744  1136  0.0 00:00:00       0 bash -l
 8896973       1  0.0  19624    12  0.0 00:00:00       0 /usr/bin/python3 -u /sbin/my_init
 8896971      14  0.0 234128   876  0.0 00:00:01       1 /usr/sbin/syslog-ng --pidfile /var/run/syslog-ng.pid -F --no-caps
 8896969      22  0.0   1964    92  0.0 00:01:36       1 /usr/bin/runsvdir -P /etc/service
 8896969      23  0.0   1812   284  0.0 00:00:00      22  \_ runsv app
  580092     421  1.2 497560 15144  0.4 01:59:05      23      \_ python3 -u sermon.py
"""
    cnt, app = parsePs(ss)
    print(cnt, app)


async def main():
    # test()
    # return

    cnt = len(sys.argv)
    if cnt < 2:
        # print("sa [u,d,s,ls]")
        cmd = "ls"
    else:
        cmd = sys.argv[1]

    if cmd == "h":
        print(
            "sa h(help),u(up),d(down),s(status),r(restart),reset,ls,f(goto log folder),p(prune)"
        )
        return

    elif cmd == "u":
        if cnt < 3:
            print("missing target")
            return

        for con in sys.argv[2:]:
            dockerExec(f"{con} bash -c 'sv u app; sv s app'")
        print()
        await doLs()

    elif cmd == "d":
        if cnt < 3:
            print("missing target")
            return

        for con in sys.argv[2:]:
            dockerExec(f"{con} bash -l -c 'sv d app; test -f /down && /down; sv s app'")
        print()
        await doLs()

    elif cmd == "s":
        if cnt < 3:
            print("missing target")
            return

        con = sys.argv[2]
        dockerExec(f"{con} sv s app")

    elif cmd == "r":
        if cnt < 3:
            print("missing target")
            return

        for con in sys.argv[2:]:
            dockerExec(
                f"{con} bash -c 'sv restart app; echo 0 > /var/run/upcnt; sv s app'"
            )
        await doLs()

    elif cmd == "reset":
        if cnt < 3:
            print("missing target")
            return

        for con in sys.argv[2:]:
            dockerExec(f"{con} bash -c 'echo 0 > /var/run/upcnt'")
        await doLs()

    elif cmd == "ls":
        isJson = False
        if cnt >= 3:
            arg = sys.argv[2]
            if arg == "--json":
                isJson = True

        await doLs(isJson)

    elif cmd == "f":
        if cnt < 3:
            print("missing target")
            return

        con = sys.argv[2]
        # 해당 컨테이너 폴더로 이동
        ret = subprocess.check_output(
            f'{dkCmd} ps --no-trunc -aqf "name=^{con}$"', shell=True
        )
        conId = ret.decode("utf-8").strip()
        print(f"cd /var/lib/docker/containers/{conId}")

    elif cmd == "p":
        # 안쓰이는 도커 이미지 찾아서 제거
        doPrune()
    else:
        print(f"uknown command[{cmd}]")


if __name__ == "__main__":
    # loop = asyncio.get_event_loop()
    # loop.run_until_complete(main())
    # loop.close()

    # asyncio.run(main())
    # py3.6
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
