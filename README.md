# oauth2-nv

OAuth 2 is the authorization framework that lets a program obtain a
token for an API without handling the account holder's password. It is
specified in
[RFC 6749](https://www.rfc-editor.org/rfc/rfc6749). OpenID Connect adds
an identity layer on top of it, specified in
[OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html).
This package implements the **client** half of both in novo-lang: the
authorization code flow with PKCE, client credentials, the device code
flow, refresh, discovery, revocation, introspection and identity token
validation. It is a port of
[oauth2-rs](https://github.com/ramosbugs/oauth2-rs) and
[Authlib](https://authlib.org)'s client half.

## What the flows are

Four parties appear in RFC 6749 section 1.1. The **resource owner** is
the person. The **client** is the program asking for access, which is
what this package is. The **authorization server** issues tokens. The
**resource server** accepts them.

The **authorization code flow** (section 4.1) is the one that signs a
person in. The client sends the person's browser to the authorization
server's **authorization endpoint** with its `client_id`, a
`redirect_uri` and the **scopes** it wants. The person signs in and
approves. The authorization server redirects the browser back to the
`redirect_uri` with a short-lived **authorization code**. The client
then posts that code to the **token endpoint** and receives an **access
token**, and usually a **refresh token**.

Two unpredictable values travel through that browser round trip. The
**state** is minted by the client, sent to the authorization endpoint
and echoed back in the redirect, so the client can tell that the
callback belongs to a sign-in it started. **PKCE**, specified in
[RFC 7636](https://www.rfc-editor.org/rfc/rfc7636), adds a
**code verifier**, a random string the client keeps, and a **code
challenge**, its SHA-256 digest, which the client sends to the
authorization endpoint. The verifier is presented at the token
endpoint, so a stolen authorization code is useless without it. Under
OpenID Connect a third value, the **nonce**, is sent to the
authorization endpoint and appears in the identity token.

The **client credentials flow** (section 4.4) is a program acting as
itself, with no person involved. The **device code flow**
([RFC 8628](https://www.rfc-editor.org/rfc/rfc8628)) is for a device
with no browser: it displays a short user code and a URL, and polls the
token endpoint while the person signs in elsewhere. **Refresh**
(section 6) exchanges a refresh token for a new access token.

**Discovery** is how a client learns an issuer's endpoints from a
well-known URL, defined by
[RFC 8414](https://www.rfc-editor.org/rfc/rfc8414) for OAuth 2 and by
OpenID Connect Discovery 1.0 for OpenID Connect.

An **identity token** is a JWT the authorization server issues under
OpenID Connect, carrying who signed in. It is verified against the
issuer's published keys, its **JWKS**.

A **confidential client** can keep a secret, such as a server. A
**public client** cannot: a command-line tool, a native application and
a single-page application are all public. PKCE is what protects a
public client's code exchange.

## Install

```
novo pkg add oauth2-nv
```

## Example

```novo
use oauthmsg

fn main() [io]
    // Who this program is, and where the provider sends the person back.
    let client = oauthmsg.with_scopes(
        oauthmsg.client("my-cli", "http://127.0.0.1:8765/callback"),
        ["openid", "email"])

    // The three unpredictable values that must survive the round trip
    // through the browser. Draw them from a random source rather than
    // writing them out as this line does.
    let pending = oauthmsg.pending(client, "st4te", "n0nce", "a-43-byte-code-verifier-goes-right-here-xyz")

    // The address to send the person to.
    match oauthmsg.authorize_url("https://id.example/authorize", client, pending, [])
        Err(f)  => println("that endpoint is not usable: ${f.message()}")
        Ok(url) => println("open: ${url}")

    // What came back on the redirect, and the check that it belongs to
    // the sign-in this program started.
    let cb = oauthmsg.read_callback("code=abc&state=st4te")
    match oauthmsg.check_state(pending, cb)
        Err(f)   => println("refused: ${f.message()}")
        Ok(code) => println("exchange this code: ${code}")
```

`oauthflow.begin` mints those three values from the operating system's
generator, and `oauthflow.exchange_code` performs the whole exchange
over the network. Neither is used above, so this program declares only
`[io]`.

Build with `novo pkg build`. The tests are listed at the end of this page.

## What the package contains

| Module | Contents |
| --- | --- |
| `oautherr` | Every refusal a server or this package can produce, with the retry, back-off and status questions a caller asks of one. |
| `oauthmsg` | The client's configuration, the values that survive the browser round trip, PKCE, and every request and response as arithmetic over strings. |
| `oauthtoken` | A token, its type, its expiry and its scopes, and the `Authorization` header it produces. |
| `oauthdisc` | The two well-known discovery URLs, the provider document, and the key set. |
| `oauthoidc` | OpenID Connect: the identity token's claims and the checks over them. |
| `oauthflow` | The flows: minting the random values, and the requests that reach the network. |

## How to choose an entry point

**`oauthflow.begin` and `exchange_code` are the ordinary path.**
`begin` mints the state, the nonce and the verifier and answers an
`OauthPending`. `exchange_code` takes that value, checks it against the
callback, and posts the code.

**`oauthflow.begin_from` takes the three values from the caller.** It
declares no effects, which is what a test uses.

**`oauthmsg` alone is the whole protocol with no socket.** Build the
request parameters with `authorize_params`, `code_params`,
`refresh_params` and their neighbours, send them however you like, and
read the answer with `read_token_response`. Nothing in that module
touches the network or a clock.

**`oauthflow.device_poll` is one poll and does not sleep.** The loop
stays with the caller, which is what a program with a spinner, a cancel
key or other work to do needs. **`device_wait` is the convenience that
takes the thread** for as long as the person takes.

**`oauthflow.ensure_fresh` refreshes a token if it needs it.** Use
`oauthtoken.needs_refresh` when the decision is yours.

## The rules a user needs

1. **Check the `state`, and let the type make you.** Nothing on the
   wire enforces it. A client that skips it has a login CSRF: an
   attacker starts a sign-in with their own account and sends the
   victim the callback URL, so the victim's client exchanges the
   attacker's code and the victim ends up signed in to the attacker's
   account. `oauthflow.exchange_code` takes the `OauthPending` and
   cannot be called without it. `oauthmsg.check_state` is published
   beside it so a caller can answer a browser sooner, and
   `exchange_code` checks again regardless.
2. **The verifier is a secret and the challenge is not.** Send the
   challenge to the authorization endpoint and the verifier to the
   token endpoint (RFC 7636 section 4).
3. **Use `S256`, not `plain`.** `oauthmsg.pkce_is_weak` answers which
   is which. `plain` is here only for a server that offers nothing
   else.
4. **Mint a verifier with `oauthmsg.verifier_of`, which is base64url.**
   Standard base64's `+` and `/` are outside RFC 7636 section 4.1's
   unreserved alphabet, so a URL builder re-encodes them and the
   verifier presented at the token endpoint is no longer the one the
   challenge was computed from.
5. **A verifier is 43 to 128 characters of `[A-Za-z0-9-._~]`** (RFC
   7636 section 4.1). `oauthmsg.verifier_ok` checks it, and
   `pkce_challenge` refuses one outside the grammar rather than
   producing a challenge that fails at the exchange with
   `invalid_grant` and no explanation.
6. **A callback is one of three things.** `OauthCallback` has a
   success, a server-reported error and an unreadable variant. The
   second is ordinary: it is the person pressing Cancel. A library
   answering an optional code makes "the user declined" and "the server
   sent nonsense" the same absent value.
7. **A callback carrying two `state` parameters is unreadable, not
   half-read.** `read_callback` reads the query with form-nv, which
   sees every occurrence. Taking the first match is exactly the reading
   an attacker would like.
8. **The two discovery URLs are different addresses.** OpenID Connect
   Discovery 1.0 section 4 appends
   `/.well-known/openid-configuration` to the issuer. RFC 8414 section
   3.1 inserts `/.well-known/oauth-authorization-server` between the
   host and the path. For `https://id.example` they agree. For
   `https://id.example/tenant-a`, which is what a multi-tenant
   deployment looks like, they do not. `oauthdisc.openid_url` and
   `oauth_url` are both published, and `fetch` tries both.
9. **An absent `code_challenge_methods_supported` means no PKCE.** RFC
   8414 section 2 says so. A client that reads the silence as "probably
   fine" sends a challenge the server ignores, and the exchange is then
   unprotected with nothing to say so.
   `oauthdisc.supports_pkce` answers `false` for a silent server.
10. **An absent `expires_in` does not mean the token never expires.**
    `OauthToken.expires_at` is optional, and the right reading of the
    absence is to refresh on the first 401.
11. **A token is opaque to a client**, even when it looks like a JWT.
    Its format is between the authorization server and the resource
    server.
12. **A DPoP token is refused by `oauthtoken.authorization_header`.**
    Presenting one needs a proof JWT signed per request with a key this
    package does not hold. Emitting a `Bearer` header for it would
    produce a 401 whose cause is invisible.
13. **Check the nonce and the `azp` on an identity token.**
    `oauthoidc.check_nonce` ties it to the sign-in this client started.
    `check_azp` refuses a token issued for another client.
    `check_at_hash` ties it to the access token that came with it.
14. **`oauthoidc.validate` is a policy over jwt-nv, never a second
    verifier.** `policy_for` builds the policy from the provider
    document and the client identifier. It verifies the algorithms
    jwt-nv verifies, which are ES256 and HS256. An identity token signed
    with RS256, the algorithm OpenID Connect Core section 15.1 makes the
    default, is refused with a signature error, because jwt-nv does not
    yet verify RSA signatures. `oauthdisc.read_jwks` still reads RSA
    keys, so the keys are ready for the day it does.
15. **Client authentication has two spellings and servers differ.**
    `client_secret_basic` puts the credentials in an `Authorization:
    Basic` header, over the form-urlencoded identifier and secret,
    which matters the moment a secret contains a `+` or a `%`. RFC 6749
    section 2.3.1 requires a server to support it, so it is the
    default. `client_secret_post` puts them in the body, and some
    servers accept only that. A persistent `invalid_client` against a
    correctly configured server is the sign to try the other.
16. **A public client has no secret at all.** `OauthAuthNone` is the
    correct setting for a command-line tool, a native application and a
    single-page application, and is why PKCE is not optional here.
17. **`oautherr.is_pending` and `poll_delay` drive the device flow.**
    `authorization_pending` means keep polling, `slow_down` means
    lengthen the interval, and `poll_delay` answers the next wait in
    seconds from the fault and the grant's own interval.

## The effect rows worth knowing

| Function | Row | Why |
| --- | --- | --- |
| `oauthflow.new_state`, `new_nonce`, `new_verifier`, `begin` | `[fs, rand]` | The operating system's generator is a device, and reading a device is `[fs]` |
| `oauthflow.post_form` and every exchange built on it: `exchange_code`, `client_credentials`, `device_begin`, `device_poll`, `refresh`, `ensure_fresh`, `revoke`, `introspect` | `[io, net, time, async]` | The standard library's `HttpClient`, which is the only HTTP client that returns the status and the body of an error reply, costs all four |
| `oauthflow.device_wait` | `[io, net, time, async]` | It sleeps between polls, and it is the only function here that does |
| `oauthdisc.fetch`, `fetch_at`, `fetch_jwks`, `oauthoidc.fetch_userinfo` | `[net, async]` | One `http.client.get`, which follows no redirect |
| Everything else in `oautherr`, `oauthmsg`, `oauthtoken`, `oauthdisc` and `oauthoidc` | `[]` | Arithmetic over strings the caller holds |

The state, the nonce and the verifier exist so that an attacker cannot
predict them, and the standard library's `rand` module is xoshiro256\*\*,
which is a shuffle generator. They go through rand-nv's
`rng.os_bytes` instead, and the `[fs]` is that disclosure.
`oauthflow.begin_from` is the `[]` twin for a caller bringing its own
values, and `begin_from_draws` for a caller bringing the bytes.

## Running on a microcontroller

This package is for a host with an operating system. The exchanges use
the standard library's HTTP client, and the random values are read from
the operating system's generator, neither of which exists on a
microcontroller. The registry shows no microcontroller facet for it.

## What is not included

- **The server side.** The authorization endpoint, the token endpoint,
  consent and the stores behind them are a different package.
- **The implicit grant and the hybrid flows.** OAuth 2.1 removes them
  and the current security best current practice says not to use them.
  A client asking for `response_type=token` is asking for something
  unsafe.
- **The resource owner password grant.** A program that collects
  somebody's password for a third-party service is what OAuth exists to
  avoid.
- **A HTTP client of its own.** The standard library has one, and a
  second would double every program's TLS surface for four requests.
- **A signing key.** RFC 7523 client assertions arrive already signed,
  through `OauthAuthAssertion`. Signing is
  [jwt-nv](https://novo-lang.org/packages/jwt-nv)'s.
- **DPoP proof generation.** See rule 12. The token type is recognised.
- **RSA signature verification.** That is jwt-nv's, and see rule 14.
- **A cache for discovery documents or key sets.** The package holds no
  clock to expire one with, so `fetch` and `fetch_jwks` fetch every time
  and the caller decides how long to keep the answer.

Token exchange (RFC 8693) is reachable through the `extra` parameters
`oauthmsg.authorize_url` and `authorize_params` take.

## Related packages

- [jwt-nv](https://novo-lang.org/packages/jwt-nv) verifies the identity
  token's signature. `oauthoidc` is a policy over it. This package
  depends on it.
- [session-nv](https://novo-lang.org/packages/session-nv) is where an
  `OauthPending` and the resulting sign-in are kept between requests.
- [url-nv](https://novo-lang.org/packages/url-nv) joins the discovery
  URLs and checks an endpoint's scheme. This package depends on it.
- [form-nv](https://novo-lang.org/packages/form-nv) reads the callback
  query and writes the token request body, and keeps every value under
  a repeated key. This package depends on it.
- [base64-nv](https://novo-lang.org/packages/base64-nv) supplies both
  alphabets: base64url without padding for the PKCE challenge, and
  standard base64 for the Basic credential. This package depends on it.
- [crypto-nv](https://novo-lang.org/packages/crypto-nv) supplies the
  SHA-256 under the PKCE challenge and the `at_hash`. This package
  depends on it.
- [rand-nv](https://novo-lang.org/packages/rand-nv) supplies the
  operating system's generator. This package depends on it.
- [calendar-nv](https://novo-lang.org/packages/calendar-nv) is the
  civil datetime an expiry is computed and compared against. This
  package depends on it.
- [paseto-nv](https://novo-lang.org/packages/paseto-nv) is an
  alternative token format, for a system whose tokens you issue
  yourself.

## Tests

```bash
novo test tests/oautherr_tests.nv          # the error codes, retry and back-off
novo test tests/oauthmsg_tests.nv          # PKCE, the callback, and every request shape
novo test tests/oauthtoken_tests.nv        # expiry, scopes, and the header
novo test tests/oauthdisc_tests.nv         # the two well-known URLs and the provider document
novo test tests/oauthoidc_tests.nv         # the identity token's checks
novo test tests/oauthoidc_signed_tests.nv  # signed tokens and key sets, made by OpenSSL
novo test tests/oauthflow_tests.nv         # the flows' refusals before the network
novo test tests/oauthnet_tests.nv          # the flows against a local authorization server
tests/coverage.sh                          # line coverage of src/, merged over every suite
```

The normative sources are RFC 6749 sections 4 and 5 for the flows and
the responses, RFC 7636 for PKCE, RFC 8628 for the device flow, RFC
8414 and OpenID Connect Discovery 1.0 for the two well-known URLs, and
OpenID Connect Core 1.0 for the identity token. The reference
implementations are the Rust crate `oauth2` and Authlib's client half.

The reference data is independent of this package:

- RFC 7636 appendix B gives the PKCE verifier and challenge.
- RFC 6749 section 2.3.1 gives the Basic credential, and sections 5.1
  and 5.2 the token responses. RFC 8628 section 3.2 gives the device
  authorization response.
- OpenID Connect Core appendix A.3 gives an access token and its
  `at_hash`.
- Python's `urllib.parse`, `hashlib`, `base64` and `hmac` produce the
  exact URLs, request bodies and credentials the suites compare against.
- Python's `cryptography` package (OpenSSL) makes the P-256 and RSA keys
  and signs the identity tokens in `tests/oauthoidc_signed_tests.nv`;
  `tests/generate/gen_oidc.py` writes that file.
- `tests/double/oauth_double.py` is a small authorization server that the network suite starts on a free port of 127.0.0.1 and that ends itself after ten minutes. It
  rebuilds the Basic credential and the PKCE challenge itself and refuses
  a request that carries either one wrongly.

The suites assert that a mismatched `state` is refused, that a callback
with two `state` parameters is unreadable, that a verifier outside the
grammar is refused before a challenge is computed, that the two discovery
URLs differ for an issuer with a path, that a provider advertising no
PKCE methods answers `supports_pkce` false, that an absent `expires_in`
is not an infinite lifetime, that a DPoP token does not produce a
`Bearer` header, and that a discovery document for another issuer is
refused.

## Licence

Apache-2.0. See `LICENSE`.

<!-- docs/writing-a-readme.md is the style guide for this page. -->
