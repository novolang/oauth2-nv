# A small authorization server for the network tests: discovery
# documents, a token endpoint with PKCE and client authentication
# checked by Python, the device flow, revocation, introspection, userinfo
# and a few ways to misbehave.  Binds an ephemeral port on 127.0.0.1 and
# prints it as the first line.  Run with `python3 -I oauth_double.py`.
#
# The checks here are the independent oracle for what the client puts on
# the wire: the Basic credential is rebuilt with `urllib.parse.quote_plus`
# and `base64`, and the PKCE challenge is `hashlib.sha256`.
import base64, hashlib, json, os, sys, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote_plus

VERIFIER = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
CHALLENGE = base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest()).rstrip(b"=").decode()
assert CHALLENGE == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM", "RFC 7636 appendix B"
CLIENT, SECRET = "my-client", "s+cr&t"
BASIC = "Basic " + base64.b64encode(("%s:%s" % (quote_plus(CLIENT), quote_plus(SECRET))).encode()).decode()
polls = {}
lock = threading.Lock()

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def send(self, status, body="", ctype="application/json", extra=None):
        data = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        for k, v in (extra or {}).items(): self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def base(self): return "http://127.0.0.1:%d" % self.server.server_port

    def doc(self, issuer):
        b = self.base()
        return json.dumps({"issuer": issuer, "authorization_endpoint": b + "/authorize", "token_endpoint": b + "/token",
                           "device_authorization_endpoint": b + "/device", "userinfo_endpoint": b + "/userinfo",
                           "jwks_uri": b + "/jwks", "revocation_endpoint": b + "/revoke",
                           "introspection_endpoint": b + "/introspect",
                           "code_challenge_methods_supported": ["S256"],
                           "id_token_signing_alg_values_supported": ["ES256"]})

    def do_GET(self):
        p, b = self.path, self.base()
        if p == "/.well-known/openid-configuration": self.send(200, self.doc(b))
        elif p == "/.well-known/oauth-authorization-server/tenant": self.send(200, self.doc(b + "/tenant"))
        elif p == "/.well-known/oauth-authorization-server/skew": self.send(200, self.doc(b + "/other"))
        elif p == "/evil/.well-known/openid-configuration": self.send(200, self.doc("https://elsewhere.example"))
        elif p == "/mirror/oidc.json": self.send(200, self.doc(b))
        elif p == "/jwks": self.send(200, '{"keys":[]}')
        elif p == "/redirect": self.send(302, "", extra={"Location": b + "/jwks"})
        elif p == "/userinfo":
            if self.headers.get("Authorization") == "Bearer good-token":
                self.send(200, '{"sub":"248289761001","email":"jane@example.com"}')
            else: self.send(401, '{"error":"invalid_token"}')
        else: self.send(404, "not found", "text/plain")

    def do_POST(self):
        n = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(n).decode()
        f = {k: v[0] for k, v in parse_qs(raw, keep_blank_values=True).items()}
        auth = self.headers.get("Authorization")
        ctype = self.headers.get("Content-Type", "")
        p = self.path
        if p == "/boom": return self.send(500, "<html>boom</html>", "text/html")
        if p == "/redirect-post": return self.send(307, "", extra={"Location": self.base() + "/token"})
        if "application/x-www-form-urlencoded" not in ctype:
            return self.send(400, '{"error":"invalid_request","error_description":"content type"}')
        authed = (auth == BASIC) or (auth is None and f.get("client_id") == CLIENT and f.get("client_secret") == SECRET)
        public = auth is None and f.get("client_id") == "public-cli" and "client_secret" not in f
        if p == "/token": return self.token(f, authed, public)
        if p == "/device":
            if f.get("client_id") != "public-cli": return self.send(401, '{"error":"invalid_client"}')
            return self.send(200, json.dumps({"device_code": f.get("scope", "") and "dev-" + f["scope"] or "dev-ok-after-2",
                                              "user_code": "WDJB-MJHT", "verification_uri": self.base() + "/activate",
                                              "expires_in": 1800, "interval": 1}))
        if p == "/revoke":
            if not authed: return self.send(401, '{"error":"invalid_client"}')
            return self.send(503 if f.get("token") == "bad" else 200, "")
        if p == "/introspect":
            if not authed: return self.send(401, '{"error":"invalid_client"}')
            return self.send(200, '{"active":true,"scope":"a"}' if f.get("token") == "live" else '{"active":false}')
        self.send(404, "not found", "text/plain")

    def token(self, f, authed, public):
        g = f.get("grant_type")
        if g == "authorization_code":
            if not (authed or public): return self.send(401, '{"error":"invalid_client"}')
            if f.get("code") == "used-code":
                return self.send(400, '{"error":"invalid_grant","error_description":"code already used","error_uri":"https://id.example/e"}')
            expect = "https://client.example.com/cb"
            if f.get("code") != "good-code" or f.get("redirect_uri") != expect:
                return self.send(400, '{"error":"invalid_request"}')
            if base64.urlsafe_b64encode(hashlib.sha256(f.get("code_verifier", "").encode()).digest()).rstrip(b"=").decode() != CHALLENGE:
                return self.send(400, '{"error":"invalid_grant","error_description":"pkce"}')
            return self.send(200, '{"access_token":"AT1","token_type":"Bearer","expires_in":3600,"refresh_token":"RT1","scope":"openid","tenant":"t-9"}')
        if g == "client_credentials":
            if not authed: return self.send(401, '{"error":"invalid_client"}')
            return self.send(200, '{"access_token":"CC","token_type":"bearer","expires_in":300,"scope":"%s"}' % f.get("scope", ""))
        if g == "refresh_token":
            if not (authed or public): return self.send(401, '{"error":"invalid_client"}')
            if f.get("refresh_token") == "RT1":
                return self.send(200, '{"access_token":"AT2","token_type":"Bearer","expires_in":60}')
            if f.get("refresh_token") == "RT-rotating":
                return self.send(200, '{"access_token":"AT3","token_type":"Bearer","expires_in":60,"refresh_token":"RT-next"}')
            if f.get("refresh_token") == "RT-garbage":
                return self.send(200, '{"unexpected":1}')
            return self.send(400, '{"error":"invalid_grant"}')
        if g == "urn:ietf:params:oauth:grant-type:device_code":
            if f.get("client_id") != "public-cli": return self.send(401, '{"error":"invalid_client"}')
            d = f.get("device_code")
            with lock:
                polls[d] = polls.get(d, 0) + 1
                k = polls[d]
            if d == "dev-pending": return self.send(400, '{"error":"authorization_pending"}')
            if d == "dev-denied": return self.send(400, '{"error":"access_denied"}')
            if d == "dev-expired": return self.send(400, '{"error":"expired_token"}')
            if d == "dev-ok-after-2":
                if k < 3: return self.send(400, '{"error":"authorization_pending"}')
                return self.send(200, '{"access_token":"DT","token_type":"Bearer","expires_in":600}')
        self.send(400, '{"error":"unsupported_grant_type"}')

# The server ends itself, so a test that started it never has to stop it.
t = threading.Timer(600, lambda: os._exit(0))
t.daemon = True
t.start()
srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
print(srv.server_port, flush=True)
srv.serve_forever()
