# Generates ../oauthoidc_signed_tests.nv from oauthoidc_signed.nv.in.
# Run with `python3 -I gen_oidc.py`, then `novo fmt ../oauthoidc_signed_tests.nv`.
#
# Independent oracles, none of them this package:
#   * Python's `cryptography` (OpenSSL) makes the P-256 and RSA keys and
#     signs every ES256 and RS256 token; Python's `hmac` signs the HS256
#     one.  Each signature is verified again here, with OpenSSL, before
#     it is written down.
#   * `at_hash` is OpenID Connect Core 3.1.3.6 done with `hashlib` and
#     `base64`, and checked against the specification's own example
#     (access token jHkWEdUXMU1BwAsC4vtUsZwnNvTIxEl0z9K3vx5KF0Y gives
#     77QmUPtjPfzWtF2AnpK9RQ).
#   * The RSA public key DER is `cryptography`'s PKCS#1 encoding of the
#     key, which `oauthdisc.read_jwks` must reproduce from `n` and `e`.
import base64, hashlib, hmac, json
from cryptography.hazmat.primitives.asymmetric import ec, rsa, padding, utils
from cryptography.hazmat.primitives import hashes, serialization

b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b'=').decode()
cj = lambda o: json.dumps(o, separators=(',', ':')).encode()
def at_hash(tok): return b64(hashlib.sha256(tok.encode()).digest()[:16])
assert at_hash("jHkWEdUXMU1BwAsC4vtUsZwnNvTIxEl0z9K3vx5KF0Y") == "77QmUPtjPfzWtF2AnpK9RQ", "the spec example"

NOW = 1789084800        # 2026-09-11T00:00:00Z, the moment the tests call "now"
ISS = "https://id.example"
CLIENT = "my-client-id"
ACCESS = "ya29.example-access-token"

ec_key = ec.generate_private_key(ec.SECP256R1())
nums = ec_key.public_key().public_numbers()
ec_x, ec_y = b64(nums.x.to_bytes(32, 'big')), b64(nums.y.to_bytes(32, 'big'))
rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
rn = rsa_key.public_key().public_numbers()
rsa_n = b64(rn.n.to_bytes((rn.n.bit_length() + 7) // 8, 'big'))
rsa_e = b64(rn.e.to_bytes((rn.e.bit_length() + 7) // 8, 'big'))
rsa_der = rsa_key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.PKCS1)
HS_SECRET = b"an-hmac-secret-of-at-least-thirty-two-bytes!!"

def sign_es(header, payload, key=ec_key):
    si = b64(cj(header)) + '.' + b64(cj(payload))
    r, s = utils.decode_dss_signature(key.sign(si.encode(), ec.ECDSA(hashes.SHA256())))
    sig = r.to_bytes(32, 'big') + s.to_bytes(32, 'big')
    ec_key.public_key().verify(utils.encode_dss_signature(int.from_bytes(sig[:32], 'big'), int.from_bytes(sig[32:], 'big')),
                               si.encode(), ec.ECDSA(hashes.SHA256())) if key is ec_key else None
    return si + '.' + b64(sig)
def sign_rs(header, payload):
    si = b64(cj(header)) + '.' + b64(cj(payload))
    sig = rsa_key.sign(si.encode(), padding.PKCS1v15(), hashes.SHA256())
    rsa_key.public_key().verify(sig, si.encode(), padding.PKCS1v15(), hashes.SHA256())
    return si + '.' + b64(sig)
def sign_hs(header, payload):
    si = b64(cj(header)) + '.' + b64(cj(payload))
    return si + '.' + b64(hmac.new(HS_SECRET, si.encode(), hashlib.sha256).digest())

def claims(**over):
    c = {"iss": ISS, "sub": "248289761001", "aud": [CLIENT], "exp": NOW + 3600, "iat": NOW - 60,
         "nonce": "the-nonce", "at_hash": at_hash(ACCESS), "email": "jane@example.com",
         "email_verified": True}
    c.update(over)
    return {k: v for k, v in c.items() if v is not None}

T = {}
T["VALID_ES"] = sign_es({"alg": "ES256", "kid": "ec1", "typ": "JWT"}, claims())
T["WRONG_NONCE"] = sign_es({"alg": "ES256", "kid": "ec1"}, claims(nonce="another-nonce"))
T["NO_NONCE"] = sign_es({"alg": "ES256", "kid": "ec1"}, claims(nonce=None))
T["WRONG_AT_HASH"] = sign_es({"alg": "ES256", "kid": "ec1"}, claims(at_hash=at_hash("someone-elses-token")))
T["NO_IAT"] = sign_es({"alg": "ES256", "kid": "ec1"}, claims(iat=None))
T["NO_AT_HASH"] = sign_es({"alg": "ES256", "kid": "ec1"}, claims(at_hash=None))
T["WRONG_ISS"] = sign_es({"alg": "ES256", "kid": "ec1"}, claims(iss="https://evil.example"))
T["EXPIRED"] = sign_es({"alg": "ES256", "kid": "ec1"}, claims(exp=NOW - 3600, iat=NOW - 7200))
T["OTHER_AUD"] = sign_es({"alg": "ES256", "kid": "ec1"}, claims(aud=["another-client"]))
T["TWO_AUD_OTHER_AZP"] = sign_es({"alg": "ES256", "kid": "ec1"}, claims(aud=[CLIENT, "another-client"], azp="another-client"))
T["TWO_AUD_OWN_AZP"] = sign_es({"alg": "ES256", "kid": "ec1"}, claims(aud=[CLIENT, "another-client"], azp=CLIENT))
T["UNKNOWN_KID"] = sign_es({"alg": "ES256", "kid": "nope"}, claims())
T["SECOND_ES"] = None
other = ec.generate_private_key(ec.SECP256R1())
si = b64(cj({"alg": "ES256", "kid": "ec1"})) + '.' + b64(cj(claims()))
r, s = utils.decode_dss_signature(other.sign(si.encode(), ec.ECDSA(hashes.SHA256())))
T["FORGED_ES"] = si + '.' + b64(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))
del T["SECOND_ES"]
T["HS_VALID"] = sign_hs({"alg": "HS256", "typ": "JWT"}, claims())
T["HS_BUT_ES_ONLY"] = T["HS_VALID"]
T["RS_VALID"] = sign_rs({"alg": "RS256", "kid": "rsa1"}, claims())
T["NONE_ALG"] = b64(cj({"alg": "none"})) + '.' + b64(cj(claims())) + '.'

def rsa_jwk(bits, kid):
    k = rsa.generate_private_key(public_exponent=65537, key_size=bits).public_key()
    n = k.public_numbers()
    der = k.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.PKCS1)
    return ({"kty": "RSA", "kid": kid, "n": b64(n.n.to_bytes((n.n.bit_length() + 7) // 8, 'big')),
             "e": b64(n.e.to_bytes((n.e.bit_length() + 7) // 8, 'big'))}, der.hex())
j512, der512 = rsa_jwk(512, "rsa512")
j1024, der1024 = rsa_jwk(1024, "rsa1024")
assert der512[2:4] != "81" and der1024[2:4] == "81", "512 is short form, 1024 one-byte long form"
jwks = json.dumps({"keys": [
    {"kty": "EC", "crv": "P-256", "kid": "ec1", "use": "sig", "alg": "ES256", "x": ec_x, "y": ec_y},
    {"kty": "RSA", "kid": "rsa1", "use": "sig", "alg": "RS256", "n": rsa_n, "e": rsa_e},
    {"kty": "RSA", "kid": "enc1", "use": "enc", "n": rsa_n, "e": rsa_e},
    {"kty": "oct", "kid": "sym1", "k": "AAAA"},
    {"kty": "EC", "crv": "P-384", "kid": "p384", "x": ec_x, "y": ec_y},
    {"kty": "EC", "crv": "P-256", "kid": "offcurve", "x": ec_x, "y": ec_x},
    {"kty": "EC", "crv": "P-256", "kid": "badb64", "x": "!!!", "y": ec_y},
    {"kty": "RSA", "kid": "badrsa", "n": "***", "e": rsa_e},
    {"kty": "EC", "crv": "P-256", "x": ec_x, "y": ec_y},
    {"kty": "EC", "crv": "P-256", "kid": "nox", "y": ec_y},
    j512, j1024,
    {"kty": "RSA", "kid": "rsa1zero", "n": rsa_n, "e": "AAEAAQ"},
    {"kty": "RSA", "kid": "emptyrsa", "n": "", "e": rsa_e},
    {"kty": "EC", "crv": "P-256", "kid": "shortec", "x": b64(b"\x01\x02"), "y": ec_y},
]}, separators=(',', ':'))

def lit(s): return json.dumps(s)
src = open('oauthoidc_signed.nv.in').read()
fixtures = "\n".join('fn %s() -> Str []\n    %s\n' % (k.lower(), lit(v)) for k, v in sorted(T.items()))
fixtures += "\nfn jwks_document() -> Str []\n    %s\n" % lit(jwks)
fixtures += "\nfn ec_public_hex() -> Str []\n    %s\n" % lit(nums.x.to_bytes(32, 'big').hex() + nums.y.to_bytes(32, 'big').hex())
fixtures += "\nfn rsa512_der_hex() -> Str []\n    %s\n" % lit(der512)
fixtures += "\nfn rsa1024_der_hex() -> Str []\n    %s\n" % lit(der1024)
fixtures += "\nfn rsa_der_hex() -> Str []\n    %s\n" % lit(rsa_der.hex())
fixtures += "\nfn hs_secret() -> Str []\n    %s\n" % lit(HS_SECRET.decode())
fixtures += "\nfn access_token() -> Str []\n    %s\n" % lit(ACCESS)
open('../oauthoidc_signed_tests.nv', 'w').write(src.replace('@@FIXTURES@@', fixtures))
print("wrote ../oauthoidc_signed_tests.nv")
