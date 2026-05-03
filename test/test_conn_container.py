import unittest
from contextlib import redirect_stdout
from io import StringIO

from gat import gat


class FakeParentConn:
    def __init__(self):
        self.calls = []

    def run(self, cmd, printLog=True, nosudo=False, logOutput=None):
        self.calls.append(("run", cmd, printLog, nosudo, logOutput))
        return "run-ok"

    def runOutput(self, cmd, printLog=True, nosudo=False):
        self.calls.append(("runOutput", cmd, printLog, nosudo))
        return "output-ok"

    def runOutputAll(self, cmd, printLog=True, nosudo=False):
        self.calls.append(("runOutputAll", cmd, printLog, nosudo))
        return "all-ok"


class FakeSsh:
    def __init__(self):
        self.calls = []

    def run(self, cmd, logCmd=None, log=False):
        self.calls.append((cmd, logCmd, log))
        return "ssh-run-ok"

    def close(self):
        pass


def make_container_conn(parent):
    conn = gat.Conn.__new__(gat.Conn)
    conn.ctrTunnel = parent
    conn.ctrName = "haproxy"
    conn.ctrId = None
    conn.ctrType = "podmanRoot"
    conn.logName = "host/haproxy"
    conn.ssh = None
    conn._uploadHelper = False
    conn.tempPath = None
    conn.ctrCmdGet = lambda: "sudo podman"
    return conn


def make_ssh_conn(ssh):
    conn = gat.Conn.__new__(gat.Conn)
    conn.ctrTunnel = None
    conn.ssh = ssh
    conn.logName = "host"
    conn._uploadHelper = False
    conn.tempPath = None
    return conn


class ConnContainerTest(unittest.TestCase):
    def test_container_run_delegates_rootful_podman_sudo_to_parent_conn(self):
        parent = FakeParentConn()
        conn = make_container_conn(parent)

        ret = conn.run("! test -f /update || /update", printLog=False)

        self.assertEqual(ret, "run-ok")
        self.assertEqual(len(parent.calls), 1)
        kind, cmd, print_log, nosudo, log_output = parent.calls[0]
        self.assertEqual(kind, "run")
        self.assertFalse(print_log)
        self.assertFalse(nosudo)
        self.assertFalse(log_output)
        self.assertIn("sudo podman exec -i", cmd)
        self.assertIn("haproxy", cmd)
        self.assertIn("/update", cmd)

    def test_container_run_keeps_verbose_output_when_parent_command_log_is_hidden(self):
        parent = FakeParentConn()
        conn = make_container_conn(parent)

        with redirect_stdout(StringIO()):
            conn.run("apt update", printLog=True)

        kind, _, print_log, _, log_output = parent.calls[0]
        self.assertEqual(kind, "run")
        self.assertFalse(print_log)
        self.assertTrue(log_output)

    def test_container_output_helpers_delegate_to_parent_conn(self):
        parent = FakeParentConn()
        conn = make_container_conn(parent)

        self.assertEqual(conn.runOutput("id", printLog=False), "output-ok")
        self.assertEqual(conn.runOutputAll("id", printLog=False), "all-ok")

        self.assertEqual([call[0] for call in parent.calls], ["runOutput", "runOutputAll"])
        for _, cmd, print_log, nosudo in parent.calls:
            self.assertFalse(print_log)
            self.assertFalse(nosudo)
            self.assertIn("sudo podman exec -i", cmd)
            self.assertIn("haproxy", cmd)

    def test_container_output_does_not_prepare_sudo_for_inner_container_command(self):
        parent = FakeParentConn()
        conn = make_container_conn(parent)
        conn.ctrCmdGet = lambda: "podman"

        def fail_prepare_sudo(_cmd):
            raise AssertionError("container inner sudo must not trigger Conn sudo setup")

        conn.prepareSudoWithAskPass = fail_prepare_sudo

        self.assertEqual(
            conn.runOutput('sudo mysql -e "select 1"', printLog=False),
            "output-ok",
        )

        _, cmd, print_log, nosudo = parent.calls[0]
        self.assertFalse(print_log)
        self.assertFalse(nosudo)
        self.assertIn("podman exec -i", cmd)
        self.assertIn("bash -c", cmd)
        self.assertIn("sudo mysql", cmd)

    def test_ssh_run_streams_output_in_verbose_mode(self):
        old_log_lv = gat.g_logLv
        gat.g_logLv = 1
        try:
            ssh = FakeSsh()
            conn = make_ssh_conn(ssh)

            with redirect_stdout(StringIO()):
                self.assertEqual(conn.run("apt update", printLog=True), "ssh-run-ok")

            _, _, log = ssh.calls[0]
            self.assertTrue(log)
        finally:
            gat.g_logLv = old_log_lv

    def test_ssh_run_does_not_stream_output_when_command_log_is_hidden(self):
        old_log_lv = gat.g_logLv
        gat.g_logLv = 1
        try:
            ssh = FakeSsh()
            conn = make_ssh_conn(ssh)

            conn.run("apt update", printLog=False)

            _, _, log = ssh.calls[0]
            self.assertFalse(log)
        finally:
            gat.g_logLv = old_log_lv


if __name__ == "__main__":
    unittest.main()
