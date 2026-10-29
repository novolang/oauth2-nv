# Changelog

All notable changes to oauth2-nv are recorded here. The format is
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
package follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
with the pre-1.0 rule that a breaking change bumps the MINOR number.

## 0.1.0 — 2026-10-29

Every body is implemented; the stability is `experimental`.

### Changed (breaking)

- The network functions' effect rows widen from `[net, async]` to
  `[io, net, time, async]`: `oauthflow.post_form`, `exchange_code`,
  `client_credentials`, `device_begin`, `device_poll`, `refresh`,
  `ensure_fresh`, `revoke` and `introspect`; `device_wait` gains `io`.
  The standard library's one-shot `http.client.post` answers only the
  body of a 2xx reply and cannot carry an `Authorization` header, so it
  cannot read an `invalid_grant` or send `client_secret_basic`. The
  connection client can, and costs `[io, net, time, async]`.
- `oautherr.OauthSlowDown(interval_secs)` carries a floor on the new
  wait and not the new interval. `poll_delay` answers the larger of
  that floor and the grant's interval plus five seconds. The wire never
  names an interval, so `fault_named` builds `OauthSlowDown(0)`.
- `oauthflow.post_form` and `oauthmsg.authorize_url` accept an `http`
  endpoint only when the host is a loopback address (127.0.0.0/8 or
  `::1`), the exception RFC 8252 section 8.3 makes for redirects.
  `oauthdisc` applies the same rule to an issuer and to the addresses
  it fetches.
- `oauthflow.post_form` takes parameters that already carry the
  client's body credentials (the `oauthmsg.*_params` functions add
  them) and adds only the `Authorization` header, so a credential is
  never sent twice.
- A device authorization response without `expires_in` reads as 900
  seconds, and an `interval` below one reads as five.
- A redirect from a token, device, revocation or introspection endpoint
  is not followed, so credentials are never replayed to another address.

### Added

- `oauthtoken.unix_seconds`, the unit the JWT claims are written in.
- `oauthflow.begin_from_draws`, `begin` over three byte draws already
  made, which treats an absent draw as `OauthNoEntropy`.
- The dependency ranges move to the registry's latest releases:
  base64-nv ^0.1.1, calendar-nv ^0.2.1, crypto-nv ^0.1.7, form-nv ^0.1.1,
  rand-nv ^0.1.9, url-nv ^0.1.4. jwt-nv and p256-nv are paths while
  jwt-nv 0.1.0 and p256-nv 0.1.0 are not on the registry; they become
  `^0.1.0` at publish.
- Readers accept what providers send: `expires_in` as a string of
  digits, a 200 reply that carries an `error` member (GitHub), and
  `verification_url` for `verification_uri` (Google).
- `read_jwks` reads P-256 and RSA signature keys and lists the others,
  with the reason, in `jwks_skipped`.

### Limitations

- `oauthoidc.validate` verifies ES256 and HS256 identity tokens. jwt-nv
  does not yet verify RSA signatures, so an RS256 token is refused with a
  signature error.
- The unreachable result of `claims_of_verified` after jwt-nv has
  verified a token is excused from coverage with its reason at the site.

### Tests

Seven suites, a local authorization server for the network functions
(`tests/oauthnet_tests.nv`), and `tests/coverage.sh`, which reports 100% of the
lines under `src/`.

## 0.0.3 — 2026-09-25

The package builds with novo 0.11.  Every body is still `todo()`.

- The lock file moves crypto-nv 0.1.3 to 0.1.6, rand-nv 0.1.5 to 0.1.6
  and url-nv 0.1.1 to 0.1.3.  crypto-nv 0.1.3 and url-nv 0.1.1 write
  into lists through names that are not declared `var`, which novo 0.11
  refuses (E2038), so this package did not build with novo 0.11 against
  them.  No requirement in the manifest changed.

## 0.0.2 — 2026-09-15

README rewritten to the package README style guide (docs/writing-a-readme.md); no change to the interface.

## 0.0.1 — 2026-09-12

The **interface**: every signature and every effect row, and no bodies.
`stability = "draft"`, and the release is recorded `implemented = false`.

### Added

- `oauthmsg` — the message arithmetic, `[]` throughout.  `OauthPending`
  (the state, the nonce and the PKCE verifier as one value),
  `OauthClient`, `OauthClientAuth`, `OauthPkceMethod`, `OauthCallback`
  and `OauthDeviceGrant`; the authorization URL builder with RFC 8252
  § 8.3's loopback exception; RFC 7636's verifier grammar and challenge
  derivation; the parameter list of every flow's token request;
  RFC 6749 § 2.3.1's Basic header, urlencoded before it is base64ed;
  and the readers for a token response, an error response and a device
  authorization response.
- `oauthtoken` — `OauthToken`, `OauthTokenType`, and the expiry
  arithmetic with the clock as an argument at both ends.  `covers`
  reads an absent `scope` member as § 5.1 does; `authorization_header`
  refuses a token type it cannot build a header for; `redacted` is
  published so no caller writes its own and logs a credential.
- `oauthflow` — the four flows performed, over one `post_form`.
  `begin`/`begin_from` are the minting pair, `device_poll` is one poll
  and `device_wait` is the loop that sleeps, `ensure_fresh` is the
  refresh that leaves a live token alone, and `revoke`/`introspect`
  are RFC 7009 and RFC 7662.
- `oauthdisc` — `OauthProvider`, both `.well-known` builders (they are
  different URLs for an issuer with a path), the issuer check
  OpenID Connect Discovery § 4.3 requires, `missing_for` as the
  per-flow gap list, and the JWKS reader that skips what it cannot read
  and says what it skipped.
- `oauthoidc` — `OauthIdClaims` and `policy_for`, which takes the
  allowed algorithms from the discovery document rather than from the
  token's header; the three checks OpenID Connect adds (`nonce`, `azp`,
  `at_hash`); `identity`, which is the issuer and the subject together;
  and `check_userinfo_sub` for § 5.3.4.
- `oautherr` — `OauthFault` over RFC 6749 § 5.2, § 4.1.2.1 and
  RFC 8628 § 3.5, plus this client's own refusals.  `is_pending`,
  `poll_delay`, `is_retryable`, `needs_user_action`,
  `is_configuration_fault`, `is_client_safe` and `status_for` are the
  questions a caller has; `known_codes` is the contract.
- `tests/` — 82 API tests against the signatures, red until the bodies
  land.  The vectors are the specifications' own: RFC 7636 Appendix B's
  verifier and challenge, RFC 6749 § 2.3.1's Basic credential and
  § 5.1's token response, RFC 8628 § 3.2's device response.

### Known

- Every body is `todo()`.  `novo test` is red, `novo pkg build` is
  green, and the shard rows that measure the design — `effect-budget`,
  `dep-layer`, `no-discharge-in-core` — pass.
- No `tests/embedded_probe.nv`, and the absence is a claim not made
  rather than a claim skipped: this is a `host` package, so it makes no
  device claim to check.

### Design notes

Four of the six modules — `oautherr`, `oauthmsg`, `oauthtoken` and
`oauthoidc` — declare no effects, so a `oauth-codec-nv` split would be
a file move with no signature change. It is not made, because the
second consumer that would pay for it is an OAuth authorization server,
and none exists. A codec whose only consumer is the client beside it is
a second package a reader has to assemble for nothing.

Left out of the ported surface: from oauth2-rs, the resource owner
password credentials grant and the implicit-flow builders; from
Authlib, the whole `authlib.oauth2.rfc6749.grants` server side, the
JOSE toolkit, OAuth 1.0a, and the Django and Flask integrations.
