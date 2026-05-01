import mimetypes
import socket
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any


class GooglePlayError(RuntimeError):
    pass


class OAuthRedirectServer(HTTPServer):
    query_params: dict[str, str] | None = None


class OAuthRedirectHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parts = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parts.query)
        if "code" in query or "error" in query:
            self.server.query_params = {key: values[0] for key, values in query.items() if values}

        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        message = b"Authentication callback received. You can close this window."
        if not self.server.query_params:
            message = b"Waiting for the OAuth callback with a verification code."
        try:
            self.wfile.write(b"<html><head><title>Authentication Status</title></head><body><p>")
            self.wfile.write(message)
            self.wfile.write(b"</p></body></html>")
        except BrokenPipeError:
            pass

    def log_message(self, format: str, *args: object) -> None:
        pass


def openRedirectServer(host: str, port: int) -> OAuthRedirectServer:
    try:
        return OAuthRedirectServer((host, port), OAuthRedirectHandler)
    except socket.error as exc:
        raise GooglePlayError(f"failed to start google play oauth redirect server on {host}:{port}") from exc


def runAuthFlow(flow: Any, storage: Any, *, host: str, port: int) -> Any:
    server = openRedirectServer(host, port)
    try:
        flow.redirect_uri = f"http://{host}:{port}/"
        authorize_url = flow.step1_get_authorize_url()
        webbrowser.open(authorize_url, new=1, autoraise=True)
        print("\nYour browser has been opened to visit:\n")
        print(f"    {authorize_url}\n")
        deadline = time.time() + 300
        while server.query_params is None and time.time() < deadline:
            server.timeout = max(0.1, deadline - time.time())
            server.handle_request()
        if server.query_params is None:
            raise GooglePlayError("google play oauth timed out waiting for redirect code")
        if "error" in server.query_params:
            raise GooglePlayError(f"google play oauth rejected: {server.query_params['error']}")
        if "code" not in server.query_params:
            raise GooglePlayError("google play oauth redirect did not include a code")
        credential = flow.step2_exchange(server.query_params["code"])
        storage.put(credential)
        credential.set_store(storage)
        print("Authentication successful.")
        return credential
    finally:
        server.server_close()


def buildService(
    *,
    client_secrets_path: Path,
    credential_path: Path,
    scope: str,
    host: str,
    port: int,
) -> Any:
    try:
        from apiclient import discovery
        from googleapiclient.http import build_http
        from oauth2client import client
        from oauth2client import file as oauth_file
        from oauth2client import tools as oauth_tools
    except ImportError as exc:
        raise GooglePlayError("google play publish dependencies are not installed") from exc

    client_secrets = str(client_secrets_path)
    flow = client.flow_from_clientsecrets(
        client_secrets,
        scope=scope,
        message=oauth_tools.message_if_missing(client_secrets),
    )
    storage = oauth_file.Storage(str(credential_path))
    credentials = storage.get()
    if credentials is None or credentials.invalid:
        print(f"publish: google play credentials not found or invalid, writing {credential_path}")
        credentials = runAuthFlow(flow, storage, host=host, port=port)
    http = credentials.authorize(http=build_http())
    return discovery.build("androidpublisher", "v3", http=http)


def publishBundle(*, service: Any, package_name: str, aab_path: Path, track: str) -> None:
    mimetypes.add_type("application/octet-stream", ".aab")
    edit_result = service.edits().insert(body={}, packageName=package_name).execute()
    edit_id = edit_result["id"]
    aab_response = service.edits().bundles().upload(
        editId=edit_id,
        packageName=package_name,
        media_body=str(aab_path),
    ).execute()
    version_code = str(aab_response["versionCode"])
    print(f"publish: version code {version_code} has been uploaded")
    track_response = service.edits().tracks().update(
        editId=edit_id,
        track=track,
        packageName=package_name,
        body={"releases": [{"name": version_code, "versionCodes": [version_code], "status": "completed"}]},
    ).execute()
    print("publish: Track %s is set with releases: %s" % (track_response["track"], str(track_response["releases"])))
    commit_request = service.edits().commit(editId=edit_id, packageName=package_name).execute()
    print('publish: edit "%s" has been committed' % (commit_request["id"]))
