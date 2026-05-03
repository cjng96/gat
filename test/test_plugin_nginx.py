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


class SetupWebAppTest(unittest.TestCase):
    def test_setup_web_app_omits_access_rules_by_default(self):
        env = FakeEnv()

        plugin.setupWebApp(
            env,
            name="git",
            domain="git.example.com",
            proxyUrl="http://git:3000",
            publicApi="/api",
            certSetup=False,
        )

        self.assertEqual(len(env.files), 1)
        content = env.files[0]["content"]
        self.assertNotIn("deny all;", content)
        self.assertNotIn("allow 10.0.0.0/8;", content)

    def test_setup_web_app_adds_access_rules_to_entry_locations(self):
        env = FakeEnv()

        plugin.setupWebApp(
            env,
            name="git",
            domain="git.example.com",
            proxyUrl="http://git:3000",
            publicApi="/api",
            wsPath="/ws",
            root="/data/www",
            proxyTrustedIp="172.18.0.0/16",
            accessIpRanges=["1.2.3.4", "10.0.0.0/8"],
            certSetup=False,
        )

        self.assertEqual(len(env.files), 1)
        content = env.files[0]["content"]
        self.assertIn("real_ip_header proxy_protocol;", content)
        self.assertIn("set_real_ip_from 172.18.0.0/16;", content)
        self.assertIn("allow 1.2.3.4;", content)
        self.assertIn("allow 10.0.0.0/8;", content)
        self.assertGreaterEqual(content.count("deny all;"), 2)
        self.assertIn("location /api {", content)
        self.assertIn("location /ws {", content)
        self.assertIn("location / {", content)


if __name__ == "__main__":
    unittest.main()
