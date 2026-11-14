"""Desktop session establishment (R-04).

Two proven roads into the engine's local auth (``runmal.auth`` /
``runmal.app.require_local_auth``):

1. **Local credential (desktop default).** The shell runs in-process
   as the same OS user as the engine, so it may read the owner-only
   credential file via ``get_or_create_credential()`` and present it
   as ``Authorization: Bearer …``. The value lives only in this
   object's private field: ``repr`` shows the mode, never the value,
   and nothing in the client layer logs it (INV-023).

2. **Bootstrap nonce → session cookie (browser road).** The launcher
   mints a one-use nonce (``create_bootstrap_nonce``); exchanging it
   at ``GET /launcher/bootstrap`` sets the signed ``runmal_session``
   cookie, which the engine also accepts. Implemented here so the
   client layer can serve future out-of-process shells that cannot
   read the credential file; not the in-process default.
"""

from __future__ import annotations

import httpx

from runmal.auth import SESSION_COOKIE_NAME, create_bootstrap_nonce
from runmal.desktop.client.errors import AuthError, TransportError


class DesktopSession:
    """An established (or establishable) engine session.

    Construct via :meth:`from_local_credential` or
    :meth:`from_bootstrap`; the plain constructor takes an explicit
    bearer token and exists for tests.
    """

    def __init__(self, base_url: str, *, bearer_token: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        self._bearer_token = bearer_token
        self._cookies: dict[str, str] = {}

    def __repr__(self) -> str:  # never the credential (INV-023)
        mode = "bearer" if self._bearer_token else (
            "cookie" if self._cookies else "anonymous"
        )
        return f"DesktopSession(base_url={self.base_url!r}, mode={mode!r})"

    # ------------------------------------------------------------ roads

    @classmethod
    def from_local_credential(cls, base_url: str) -> DesktopSession:
        """Read the owner-only local credential in-process (default)."""
        from runmal.auth import get_or_create_credential

        return cls(base_url, bearer_token=get_or_create_credential())

    @classmethod
    def from_bootstrap(
        cls, base_url: str, *, http: httpx.Client | None = None
    ) -> DesktopSession:
        """Exchange a fresh launcher bootstrap nonce for the signed
        session cookie, exactly as a browser launched by
        ``launcher.core.bootstrap_url`` would."""
        session = cls(base_url)
        nonce = create_bootstrap_nonce()
        owns_client = http is None
        client = http or httpx.Client(
            base_url=session.base_url, timeout=10.0, trust_env=False
        )
        try:
            try:
                response = client.get(
                    "/launcher/bootstrap",
                    params={"nonce": nonce},
                    follow_redirects=False,
                )
            except httpx.HTTPError as exc:
                raise TransportError(
                    f"bootstrap exchange unreachable: {exc.__class__.__name__}"
                ) from exc
        finally:
            if owns_client:
                client.close()
        if response.status_code not in (200, 303, 307, 308):
            raise AuthError(
                response.status_code, "launcher bootstrap was refused"
            )
        cookie = response.cookies.get(SESSION_COOKIE_NAME, "")
        if not cookie:
            # httpx surfaces Set-Cookie via the jar on the client when
            # the caller shared one; fall back to the raw header.
            raw = response.headers.get("set-cookie", "")
            for part in raw.split(";"):
                name, _, value = part.strip().partition("=")
                if name == SESSION_COOKIE_NAME and value:
                    cookie = value
                    break
        if not cookie:
            raise AuthError(
                response.status_code,
                "bootstrap answered without a session cookie",
            )
        session._cookies[SESSION_COOKIE_NAME] = cookie
        return session

    # -------------------------------------------------------- application

    def apply(self, client: httpx.Client) -> None:
        """Attach this session's auth material to an httpx client."""
        if self._bearer_token:
            client.headers["Authorization"] = f"Bearer {self._bearer_token}"
        for name, value in self._cookies.items():
            client.cookies.set(name, value)

    @property
    def authenticated(self) -> bool:
        return bool(self._bearer_token or self._cookies)
