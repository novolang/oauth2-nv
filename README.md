# oauth2-nv

**Status: NOT IMPLEMENTED — interface only.**

Every public function below is published with its signature and its
effect row, and every body is `todo()`.  Installing this package works;
calling it panics with `not implemented`.

## What this is

OAuth 2 and OpenID Connect, for a **client**.  The four flows a program
actually uses — authorization code with PKCE, client credentials, the
device code flow, and refresh — plus discovery, token revocation,
introspection, and id_token validation.

It is what you reach for when your program has to sign a person in
with somebody else's identity provider, or call an API that wants a
bearer token it did not give you.

It is a port of [`oauth2`](https://github.com/ramosbugs/oauth2-rs) and
[authlib](https://authlib.org)'s client half.  Six modules, and a
reader should know which one they are on.

| surface | module | reach for it when |
| --- | --- | --- |
| the **flows** | `oauthflow` | you are signing somebody in, or fetching a token |
| the **messages** | `oauthmsg` | you are building or reading a request by hand |
| the **token** | `oauthtoken` | you are holding one, and wondering if it is still good |
| the **provider** | `oauthdisc` | you want the endpoints out of `.well-known` |
| OpenID **Connect** | `oauthoidc` | there is an `id_token` in the response |
| the **faults** | `oautherr` | you are deciding whether to retry |

## Adding it, and checking it

```bash
novo pkg add oauth2-nv           # into your novo.toml
novo pkg build                   # type- and effect-check the package
novo test --isolate tests/oauthmsg_tests.nv
```

`novo test` is red today and that is the point of the release: every
assertion fails with `not implemented: oauth2-nv.<module>.<fn>`.  They
turn green one at a time as bodies land.

## The one example that will work

A CLI signing its user in, with PKCE, against a discovered provider:

```novo
use civil
use oauthdisc
use oauthflow
use oauthmsg

fn main() [io, fs, net, rand, async]
    let client = oauthmsg.with_scopes(
        oauthmsg.client("my-cli", "http://127.0.0.1:8765/callback"),
        ["openid", "email"])

    match oauthdisc.fetch("https://id.example")
        Err(_) => println("that issuer has no discovery document")
        Ok(provider) =>
            match oauthflow.begin(client, true)
                Err(_) => println("no generator on this machine")
                Ok(pending) =>
                    // Send the person here, and keep `pending`.
                    match oauthflow.authorize_url(
                            provider.authorization_endpoint, client, pending)
                        Err(_) => println("that endpoint is not usable")
                        Ok(url) =>
                            println("open: ${url}")
                            // …they come back to the loopback listener…
                            let query = wait_for_callback()
                            let cb = oauthmsg.read_callback(query)
                            match oauthflow.exchange_code(
                                    provider.token_endpoint, client,
                                    pending, cb, now())
                                Err(_) => println("sign-in failed")
                                Ok(t)  => println("signed in")
```

The `state` check happens inside `exchange_code`, because `pending` is
an argument it cannot be called without.

## The load-bearing interface

`oauthmsg.OauthPending` — the three values that have to survive the
round trip through the end user's browser.

```novo norun:pseudo
pub struct OauthPending
    state: Str          // the CSRF token, echoed in the callback
    nonce: Str          // the OpenID Connect replay token
    verifier: Str       // the PKCE code_verifier — a SECRET
    redirect_uri: Str
    scopes: [Str]
    issuer: Str
    started_at: ?CivilDateTime
```

That looks like bookkeeping until you ask what happens when a client
skips one of them.

The `state` is a check the client performs **on itself**.  Nothing on
the wire enforces it, no server refuses a client that ignores it, and a
client that ignores it has a **login CSRF**: an attacker starts a sign-in
with their own account, takes the callback URL carrying their own
authorization code, and sends it to a victim.  The victim's browser
completes the callback, the client exchanges the attacker's code, and
the victim is now signed in **to the attacker's account** — where
everything they upload next belongs to the attacker.  It is invisible
from both ends.

The PKCE verifier is the same shape of problem one layer down, and the
`nonce` is the same shape again for the id_token.

So the three of them are one value, and the one function that finishes
the flow takes it:

```novo norun:pseudo
pub fn exchange_code(endpoint: Str, c: OauthClient, p: OauthPending,
                     cb: OauthCallback, arrived_at: CivilDateTime)
    -> Result<OauthToken, OauthFault> [net, async]
```

There is no spelling of that call without the `p`.  The check moves
from a paragraph in a README — which is where every library puts it —
to an argument the compiler asks for.  `oauthmsg.check_state` is
published beside it so a caller can check early and answer a browser
faster, and `exchange_code` checks again anyway: the cheap check is not
the one that has to be trusted.

**`OauthCallback` is an enum for the same reason.**  A redirect back
from an authorization endpoint carries `code` and `state`, **or**
`error` and `state` — and the second is ordinary: it is the person
pressing Cancel.  A library that answered `?Str` for the code makes
"the user declined" and "the server sent nonsense" the same `None`,
and the handler that receives it has a page to render and no way to
know which happened.  Three variants, and the third names what was
wrong.

That third variant is also where a **repeated parameter** lands.
`read_callback` reads the query with form-nv, which sees every
occurrence; a callback carrying two `state` values is
`OauthCallbackUnreadable` rather than half-read.  The standard
library's `http.server.query_get` answers the first match and drops the
rest — and "the first `state`" is exactly the value an attacker would
like a client to check.

## The layer, and why

`host`.  The package opens sockets and reads the operating system's
entropy, so it is not `core` and cannot be.

But four of the six modules are `[]` throughout — `oautherr`,
`oauthmsg`, `oauthtoken` and `oauthoidc` — and the split is the point.
A request is a list of pairs; a response is a string that arrived from
somewhere; an expiry is compared against a time the caller passes in;
an id_token is checked against keys the caller already holds.  Every
RFC 6749 § 4, § 5, RFC 7636 and RFC 8628 vector is a test with no server
running, and "did this client check `state`?" is a question a reader
answers by reading one function.

**Does the `[]` half earn a `core` row of its own?**  Not yet, and the
row that would change that is named: an OAuth **authorization server**.
`oauthmsg`'s request and response shapes are the same shapes a server
parses and emits, and a package that implemented the other end would be
the second consumer that pays for a split.  No such package exists
yet, and a codec whose only consumer is the client beside it is a
second package a reader has to assemble for nothing.  If one is ever
written, `oauthmsg`, `oauthtoken` and `oauthoidc` move out as
`oauth-codec-nv` with no signature change.

### Two rows that are wider than they look

Both are **measured**, not asserted, and both surprise a first-time
reader:

| function | row | why |
| --- | --- | --- |
| `oauthflow.new_state`, `new_nonce`, `new_verifier`, `begin` | `[fs, rand]` | the operating system's generator is `/dev/urandom`, and reading a device is `[fs]` |
| every exchange | `[net, async]` | `http.client.post` costs both — the `[async]` is the client's own deadline task |
| `oauthflow.device_wait` | `[net, time, async]` | it is the one function in the package that sleeps |

The `[fs]` is the interesting one.  `state`, `nonce` and the PKCE
verifier are the three values whose whole purpose is that an attacker
cannot predict them, and the standard library's `rand` module is
xoshiro256\*\* — excellent for a shuffle and not for any of these.  So
they go through rand-nv's `rng.os_bytes`, which reads the entropy
device, and the `[fs]` is the disclosure rather than a surprise to
explain away.  `oauthflow.begin_from` is the `[]` twin for a caller who
brought their own bytes, and it is what every test here uses.

`device_poll` is one poll and does **not** sleep, so the loop stays the
caller's — which is what a program with a spinner, a cancel key, or
other requests to serve needs.  `device_wait` is the convenience that
takes the thread for as long as the end user takes, and its row says so.

## What is out, and why

**The server side, entirely.**  The authorization endpoint, the token
endpoint, consent, and every store behind them.  A different package,
and the grid has no row for one.

**The implicit grant and the hybrid flows.**  OAuth 2.1 removes them
and every current security BCP says not to use them.  A client asking
for `response_type=token` is asking this library to do something
unsafe.

**The resource-owner password grant.**  Same authority.  A program that
collects somebody's password for a third-party service is the thing
OAuth exists to stop.

From `oauth2` that leaves out `ResourceOwnerPasswordCredentials` and
the implicit-flow builders.  From authlib it leaves out the whole
`authlib.oauth2.rfc6749.grants` server side, the JOSE toolkit (that is
jwt-nv), OAuth 1.0a, and the Django and Flask integrations.

**Reachable anyway**: token exchange (RFC 8693) through the `extra`
parameters on `authorize_url`, and JWT client assertions (RFC 7523)
through `OauthAuthAssertion`, which takes an assertion the caller
signed with jwt-nv rather than holding a private key here.

**DPoP (RFC 9449)** is recognised as a token type and refused by
`authorization_header`, because presenting one needs a proof JWT signed
per request with a key this package does not hold.  A library that
emitted a `Bearer` header for a DPoP token would produce a 401 whose
cause is invisible.

## What it depends on, and what it does not

Seven packages, and every one of them is load-bearing:

| | |
| --- | --- |
| base64-nv | RFC 7636's `BASE64URL(SHA256(v))` and RFC 6749 § 2.3.1's Basic credential — two alphabets and two padding rules that `bytes.to_base64` cannot spell |
| calendar-nv | what an expiry **is**: `expires_in` is a duration, and turning it into an instant needs a date to add it to |
| crypto-nv | SHA-256, for the PKCE challenge and for `at_hash` |
| form-nv | both directions of `application/x-www-form-urlencoded` — and the read matters more than the write |
| jwt-nv | the id_token.  `oauthoidc` is a policy over it, never a second verifier |
| rand-nv | the operating system's generator, because `rand` is not one |
| url-nv | RFC 3986 § 5.3 join, and the scheme check |

**Not http-codec-nv**, and not a HTTP client of its own: the standard
library has one, and a client that brought a second would double every
program's TLS surface for four requests.

## Two details worth knowing before you deploy

**The two `.well-known` paths are not the same URL.**  OpenID Connect
Discovery 1.0 § 4 **appends** `/.well-known/openid-configuration` to the
issuer; RFC 8414 § 3.1 **inserts**
`/.well-known/oauth-authorization-server` between the host and the
path.  For `https://id.example` they agree.  For
`https://id.example/tenant-a` — which is what a multi-tenant deployment
looks like — they are different addresses.  `oauthdisc` publishes both
builders by name and `fetch` tries both.

**An empty `code_challenge_methods_supported` means no PKCE.**
RFC 8414 § 2 says so, and a client that reads the absence as "probably
fine" sends a `code_challenge` the server ignores.  The exchange is
then unprotected and nothing says so.  `oauthdisc.supports_pkce`
answers `false` for a silent server, on purpose.

## Related

- [jwt-nv](https://github.com/novolang/jwt-nv) — the id_token's signature
- [session-nv](https://github.com/novolang/session-nv) — where an
  `OauthPending` and the resulting sign-in are kept between requests
- [url-nv](https://github.com/novolang/url-nv),
  [form-nv](https://github.com/novolang/form-nv) — the two halves of a
  request
