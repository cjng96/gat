from pathlib import Path
from typing import Any


class SshDeployError(RuntimeError):
    pass


def openCoSsh(*, host: str | None, port: int, user: str | None) -> Any:
    if host is None or user is None:
        raise SshDeployError("ssh deploy host/user is not configured")
    from coPy.coSsh import CoSsh
    ssh = CoSsh()
    ssh.init(host, port, user)
    return ssh


def uploadFile(*, ssh: Any, local_path: Path, remote_path: str) -> None:
    ssh.uploadFile(str(local_path), remote_path)


def runRemote(*, ssh: Any, command: str) -> None:
    ssh.run(command)


def runRemoteOutput(*, ssh: Any, command: str) -> None:
    ssh.runOutput(command)
