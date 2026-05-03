import unittest

from gat import plugin


class FakeEnv:
    def __init__(self):
        self.files = []
        self.runs = []
        self.config = type("Config", (), {"podman": False})()

    def makeFile(self, content, path, sudo=False, mode=None, **_):
        self.files.append(
            {
                "content": content,
                "path": path,
                "sudo": sudo,
                "mode": mode,
            }
        )

    def run(self, cmd, *_, **__):
        self.runs.append(cmd)


class NginxNextcloudTest(unittest.TestCase):
    def test_nginx_nextcloud_uses_runtime_resolver_for_fastcgi_upstream(self):
        env = FakeEnv()

        plugin.nginxNextcloud(
            env,
            domain="next.example.com",
            prot="http",
            proxy="next:9000",
        )

        self.assertEqual(len(env.files), 1)
        content = env.files[0]["content"]
        self.assertIn("resolver 127.0.0.1 valid=30s ipv6=off;", content)
        self.assertIn("set $nextcloud_upstream next:9000;", content)
        self.assertIn("fastcgi_pass $nextcloud_upstream;", content)
        self.assertNotIn("fastcgi_pass next:9000;", content)


if __name__ == "__main__":
    unittest.main()
