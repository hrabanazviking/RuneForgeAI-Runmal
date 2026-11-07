"""Web Search plugin (P-088): opt-in, per-chat, cited results.

Roadmap line: "Web Search plugin: opt-in, per-chat, with
results cited into context (off by default -- sovereignty is
the default state)." Built from the roadmap line and Runmal's
own contracts only -- the P-081 Plugin API v1, the P-082
sandbox policy, and the banked citizen pattern (P-084 first,
P-086 for per-chat configuration). See
docs/WEB_SEARCH_PLUGIN_2026-11-07.md.

Sovereignty contract (the slice's heart): web search is OFF
by default for every chat. The only road that can invoke a
search provider is the explicit :meth:`WebSearchPlugin.search`
action, and it refuses -- before any provider or transport
call -- unless that chat has explicitly opted in through
:meth:`WebSearchPlugin.set_chat_config`. The prompt hook
never searches and never touches a network-shaped seam: it
only offers an already-fetched result set back to the
composer, and it abstains the moment a chat's opt-in is off.
No event triggers a search; ``message.*`` events are not
even declared.

Citations: results enter context only through
:func:`format_result_set`, which renders every result with
its title and URL, and :meth:`SearchResultSet.to_dict`
exposes the same title + URL pairs as inspectable citation
data. There is no rendering path that emits a snippet
without its source.

Provider seam: a provider is any object with a
``search(query, *, max_results)`` method (sync or async) or
any plain callable of that shape, returning
:class:`SearchResult` rows, mappings, or ``(title, url,
snippet)`` tuples. The shipped default is
:class:`DeterministicSearchProvider` -- deterministic,
labelled ``deterministic-1``, minting its URLs on the
RFC 2606 reserved ``example.invalid`` domain: a placeholder
that is never disguised as a real search result.
:class:`HttpJsonSearchProvider` is the real-web shape: it
calls an endpoint template through an INJECTED transport
callable, so tests (and any deployment) supply the actual
network road; this module itself opens no socket.

Sandbox stance (P-082): the manifest declares only v1
surface permissions, so the derived resource grant set is
EMPTY (:func:`sandbox_grants` proves it). ``network.access``
is deliberately not part of the v1 manifest vocabulary, so
no v1 manifest can declare it; like P-086's model access,
the provider/transport is host wiring handed to trusted
in-tree registration code, and the per-chat opt-in above is
the gate that wiring is exercised through.

Wiring: :func:`register_plugin` is the one-call trusted
registration road. ``build_registry`` / ``create_app`` are
unchanged -- P-081's battery pins the empty boot registry;
the keeper reconciles liveness at banking. No migration:
per-chat config and the latest result sets live in memory
on the plugin instance and are lost on restart (the P-086
stance, stated plainly).
"""

from __future__ import annotations

import dataclasses
import hashlib
import inspect
import urllib.parse
from dataclasses import dataclass, field

from runmal.plugins.manifest import PluginManifest, manifest_from_data, manifest_to_data
from runmal.plugins.registry import PluginHandlers, PluginRecord, PluginRegistry
from runmal.prompt.slots import Slot
from runmal.sandbox.policy import GrantSet, grants_from_manifest

PLUGIN_ID = "runmal.web-search"
PLUGIN_VERSION = "1.0.0"
HOOK_ID = "web-search-slot"
SLOT_LOCAL_ID = "web-search"
UI_LOCAL_ID = "web-search-panel"
DETERMINISTIC_VERSION = "deterministic-1"
DEFAULT_MAX_RESULTS = 5
MAX_RESULTS = 10
MAX_QUERY_CHARS = 500
DECLARED_EVENTS = ("chat.created", "chat.deleted")


class WebSearchError(RuntimeError):
    """A search could not be performed or its results were
    malformed. Nothing new is stored when this raises."""


class WebSearchDisabledError(WebSearchError):
    """The chat has not opted in. Raised BEFORE any provider
    or transport call: sovereignty is the default state."""


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _check_max_results(value, *, what: str = "max_results") -> int:
    if not _is_int(value) or not 1 <= value <= MAX_RESULTS:
        raise ValueError(
            f"{what} must be an int in 1..{MAX_RESULTS}: {value!r}")
    return value


def _check_chat_id(chat_id) -> str:
    if not isinstance(chat_id, str) or not chat_id:
        raise ValueError(f"chat_id must be a non-empty string: {chat_id!r}")
    return chat_id


def _check_query(query) -> str:
    if not isinstance(query, str):
        raise ValueError(f"query must be a string: {query!r}")
    cleaned = query.strip()
    if not cleaned:
        raise ValueError("query must be non-empty")
    if len(cleaned) > MAX_QUERY_CHARS:
        raise ValueError(
            f"query exceeds {MAX_QUERY_CHARS} chars: {len(cleaned)}")
    return cleaned


@dataclass(frozen=True)
class SearchResult:
    """One cited result: a snippet is never carried without
    its title + URL source."""

    title: str
    url: str
    snippet: str = ""
    provider: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.title, str) or not self.title.strip():
            raise ValueError(f"result title must be non-empty: {self.title!r}")
        if not isinstance(self.url, str) or not (
            self.url.startswith("https://") or self.url.startswith("http://")
        ):
            raise ValueError(
                f"result url must start http:// or https://: {self.url!r}")
        if not isinstance(self.snippet, str):
            raise ValueError(f"result snippet must be a string: {self.snippet!r}")
        if not isinstance(self.provider, str):
            raise ValueError(f"result provider must be a string: {self.provider!r}")

    def to_dict(self) -> dict:
        return {"title": self.title, "url": self.url,
                "snippet": self.snippet, "provider": self.provider}


@dataclass(frozen=True)
class SearchResultSet:
    """One performed search: the query, its provenance, and
    its cited results as inspectable data."""

    query: str
    chat_id: str
    provider: str
    road: str
    results: tuple[SearchResult, ...] = ()

    def citations(self) -> list[dict]:
        """1-based citation rows, aligned with the rendering
        in :func:`format_result_set`."""
        return [
            {"index": i + 1, "title": r.title, "url": r.url,
             "snippet": r.snippet, "provider": r.provider or self.provider}
            for i, r in enumerate(self.results)
        ]

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "chat_id": self.chat_id,
            "provider": self.provider,
            "road": self.road,
            "results": [r.to_dict() for r in self.results],
            "citations": self.citations(),
        }


def format_result_set(result_set: SearchResultSet) -> str:
    """Render a result set for context: header naming the
    provider + road, then every result WITH its citation.
    This is the only text rendering of results in the slice."""
    header = (
        f"Web search results for \"{result_set.query}\" "
        f"(provider: {result_set.provider}; road: {result_set.road}; "
        f"cited sources):"
    )
    lines = [header]
    for citation in result_set.citations():
        lines.append(f"[{citation['index']}] {citation['title']} -- {citation['url']}")
        if citation["snippet"]:
            lines.append(citation["snippet"])
    return "\n".join(lines)


class DeterministicSearchProvider:
    """The default provider: deterministic and honestly
    labelled. Pure hash/string work derived from the query;
    URLs live on the reserved ``example.invalid`` domain and
    snippets say plainly that they are deterministic
    placeholders. Never a real search, never disguised."""

    provider = DETERMINISTIC_VERSION
    version = DETERMINISTIC_VERSION
    road = "deterministic"

    async def search(self, query: str, *, max_results: int = DEFAULT_MAX_RESULTS) -> list[SearchResult]:
        query = _check_query(query)
        _check_max_results(max_results)
        digest = hashlib.sha256(query.encode("utf-8")).hexdigest()
        slug = "-".join(query.lower().split())[:48].strip("-") or "query"
        out: list[SearchResult] = []
        for i in range(max_results):
            tag = hashlib.sha256(f"{digest}:{i}".encode("utf-8")).hexdigest()[:10]
            out.append(SearchResult(
                title=f"{query} -- deterministic result {i + 1}",
                url=f"https://example.invalid/search/{slug}/{tag}",
                snippet=(
                    "Deterministic placeholder result "
                    f"{i + 1} for \"{query}\" (provider "
                    "deterministic-1; not a real web source)."
                ),
                provider=self.provider,
            ))
        return out


class HttpJsonSearchProvider:
    """The real-web shape, through an INJECTED transport.

    ``endpoint_template`` must contain ``{query}`` (the query
    is URL-quoted into it) and may contain ``{max_results}``.
    ``transport`` is a callable taking the final URL and
    returning a mapping with a ``results`` list of
    ``{title, url, snippet?}`` mappings (sync or async).
    This provider opens no socket itself: the transport IS
    the network road, supplied by the host.
    """

    provider = "http-json"
    road = "web"

    def __init__(self, endpoint_template: str, transport) -> None:
        if not isinstance(endpoint_template, str) or "{query}" not in endpoint_template:
            raise ValueError(
                "endpoint_template must be a string containing {query}: "
                f"{endpoint_template!r}")
        if not callable(transport):
            raise ValueError("transport must be callable")
        self.endpoint_template = endpoint_template
        self.transport = transport

    def build_url(self, query: str, *, max_results: int) -> str:
        url = self.endpoint_template.replace(
            "{query}", urllib.parse.quote(query, safe=""))
        return url.replace("{max_results}", str(max_results))

    async def search(self, query: str, *, max_results: int = DEFAULT_MAX_RESULTS) -> list[SearchResult]:
        query = _check_query(query)
        _check_max_results(max_results)
        url = self.build_url(query, max_results=max_results)
        try:
            payload = self.transport(url)
            if inspect.isawaitable(payload):
                payload = await payload
        except WebSearchError:
            raise
        except Exception as exc:
            raise WebSearchError(f"search transport failed: {exc}") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
            raise WebSearchError(
                "search payload must be a mapping with a results list")
        try:
            return [_coerce_result(row, provider=self.provider)
                    for row in payload["results"]]
        except ValueError as exc:
            raise WebSearchError(f"search provider returned an invalid result: {exc}") from exc


class _CallableProvider:
    """Wrap a plain callable as a provider (road ``custom``)."""

    road = "custom"
    provider = "callable"

    def __init__(self, func) -> None:
        self._func = func

    async def search(self, query: str, *, max_results: int = DEFAULT_MAX_RESULTS):
        result = self._func(query, max_results=max_results)
        if inspect.isawaitable(result):
            result = await result
        return result


def _coerce_result(row, *, provider: str) -> SearchResult:
    if isinstance(row, SearchResult):
        if row.provider:
            return row
        return dataclasses.replace(row, provider=provider)
    if isinstance(row, dict):
        return SearchResult(
            title=row.get("title"), url=row.get("url"),
            snippet=row.get("snippet", "") or "",
            provider=row.get("provider") or provider)
    if isinstance(row, (tuple, list)) and len(row) in (2, 3):
        return SearchResult(
            title=row[0], url=row[1],
            snippet=row[2] if len(row) == 3 else "", provider=provider)
    raise WebSearchError(
        f"search provider returned an unsupported result row: {type(row).__name__}")


async def _invoke_provider(provider, query: str, *, max_results: int) -> SearchResultSet:
    """Call any provider shape; stamp honest provenance."""
    search_attr = getattr(provider, "search", None)
    if callable(search_attr):
        road = str(getattr(provider, "road", "custom"))
        provider_name = str(getattr(
            provider, "provider", getattr(provider, "version", "callable")))
        try:
            raw = search_attr(query, max_results=max_results)
            if inspect.isawaitable(raw):
                raw = await raw
        except WebSearchError:
            raise
        except Exception as exc:
            raise WebSearchError(f"search provider failed: {exc}") from exc
    elif callable(provider):
        wrapped = _CallableProvider(provider)
        road, provider_name = wrapped.road, wrapped.provider
        try:
            raw = await wrapped.search(query, max_results=max_results)
        except WebSearchError:
            raise
        except Exception as exc:
            raise WebSearchError(f"search provider failed: {exc}") from exc
    else:
        raise ValueError("provider must expose .search or be callable")
    if isinstance(raw, SearchResultSet):
        try:
            results = tuple(_coerce_result(r, provider=provider_name) for r in raw.results)
        except ValueError as exc:
            raise WebSearchError(f"search provider returned an invalid result: {exc}") from exc
        return SearchResultSet(query=raw.query, chat_id=raw.chat_id,
                               provider=raw.provider or provider_name,
                               road=raw.road or road, results=results)
    if isinstance(raw, (str, bytes)) or not hasattr(raw, "__iter__"):
        raise WebSearchError(
            f"search provider returned a non-iterable result: {type(raw).__name__}")
    try:
        results = tuple(_coerce_result(r, provider=provider_name) for r in raw)
    except ValueError as exc:
        raise WebSearchError(f"search provider returned an invalid result: {exc}") from exc
    return SearchResultSet(query=query, chat_id="", provider=provider_name,
                           road=road, results=results)


@dataclass(frozen=True)
class WebSearchConfig:
    """Plugin-global config: the provider seam + result cap.

    ``provider=None`` selects :class:`DeterministicSearchProvider`.
    A provider object or plain callable is used as handed in
    (host wiring); provenance labels come from the provider.
    """

    provider: object = None
    max_results: int = DEFAULT_MAX_RESULTS

    def __post_init__(self) -> None:
        _check_max_results(self.max_results)
        if self.provider is not None:
            if not callable(getattr(self.provider, "search", None)) and not callable(self.provider):
                raise ValueError("provider must expose .search or be callable")

    @property
    def effective_provider(self):
        return self.provider or DeterministicSearchProvider()


@dataclass(frozen=True)
class ChatWebSearchConfig:
    """Per-chat opt-in. ``enabled=False`` is the default for
    every chat: sovereignty is the default state."""

    enabled: bool = False
    max_results: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise ValueError(f"enabled must be a bool: {self.enabled!r}")
        if self.max_results is not None:
            _check_max_results(self.max_results)

    def to_dict(self) -> dict:
        return {"enabled": self.enabled, "max_results": self.max_results}


def manifest_data() -> dict:
    """The citizen's manifest as plain data (PLG-02)."""
    return {
        "id": PLUGIN_ID,
        "name": "Web Search",
        "version": PLUGIN_VERSION,
        "api_version": 1,
        "description": "Opt-in per-chat web search: explicit searches only when a chat has opted in (off by default), with results cited into context by title and URL.",
        "author": "Runmal",
        "capabilities": ["chat.events", "prompt.hooks", "ui.slots"],
        "permissions": ["chat.read", "prompt.inject", "ui.contribute"],
        "events": list(DECLARED_EVENTS),
        "prompt_hooks": [{"id": HOOK_ID, "stage": "slots", "priority": 80}],
        "ui_slots": [{"id": UI_LOCAL_ID, "slot": "chat.sidebar", "label": "Web Search", "order": 80, "payload": {"kind": "panel", "route": "web-search"}}],
        "settings": {
            "schema": {"max_results": {"type": "integer", "minimum": 1, "maximum": MAX_RESULTS}},
            "defaults": {"max_results": DEFAULT_MAX_RESULTS},
        },
        "enabled_by_default": False,
    }


def build_manifest() -> PluginManifest:
    """The validated manifest, built through the strict parser."""
    return manifest_from_data(manifest_data())


def config_from_manifest(manifest) -> WebSearchConfig:
    """Config from the manifest's settings defaults.

    Lenient by design (the P-084 pattern): a missing or
    invalid value falls back to the module constant. A
    manifest can never carry a provider (data only, PLG-02),
    so the provider always comes from explicit config.
    """
    defaults: dict = {}
    settings = manifest.get("settings") if isinstance(manifest, dict) else getattr(manifest, "settings", None)
    if isinstance(settings, dict):
        raw = settings.get("defaults")
        if isinstance(raw, dict):
            defaults = raw
    max_results = defaults.get("max_results", DEFAULT_MAX_RESULTS)
    if not _is_int(max_results) or not 1 <= max_results <= MAX_RESULTS:
        max_results = DEFAULT_MAX_RESULTS
    return WebSearchConfig(max_results=max_results)


def sandbox_grants() -> GrantSet:
    """The citizen's P-082 resource grants: empty, by construction."""
    return grants_from_manifest(manifest_to_data(build_manifest()))


class WebSearchPlugin:
    """The citizen: opt-in search action + cited-results slot.

    Per-chat config and the latest result set per chat live
    on the instance (in memory; lost on restart). With no
    explicit provider the deterministic default answers --
    labelled, never disguised.
    """

    def __init__(self, config: WebSearchConfig | None = None) -> None:
        self.config = config or config_from_manifest(build_manifest())
        self._chat_configs: dict[str, ChatWebSearchConfig] = {}
        self._results: dict[str, SearchResultSet] = {}

    @property
    def manifest(self) -> PluginManifest:
        return build_manifest()

    def handlers(self) -> PluginHandlers:
        return PluginHandlers(
            on_event=self.on_event,
            prompt_hooks={HOOK_ID: self.web_search_slot},
        )

    # -- per-chat opt-in --------------------------------------
    def set_chat_config(self, chat_id, cfg: ChatWebSearchConfig | None = None, **overrides) -> ChatWebSearchConfig:
        chat_id = _check_chat_id(chat_id)
        if cfg is None and "config" in overrides:
            cfg = overrides.pop("config")
        if cfg is None:
            cfg = ChatWebSearchConfig(**overrides) if overrides else ChatWebSearchConfig()
        elif isinstance(cfg, dict):
            cfg = ChatWebSearchConfig(**{**cfg, **overrides})
        elif overrides:
            cfg = dataclasses.replace(cfg, **overrides)
        self._chat_configs[chat_id] = cfg
        return cfg

    def get_chat_config(self, chat_id) -> ChatWebSearchConfig:
        return self._chat_configs.get(str(chat_id), ChatWebSearchConfig())

    def clear_chat_config(self, chat_id) -> None:
        key = str(chat_id)
        self._chat_configs.pop(key, None)
        self._results.pop(key, None)

    def is_enabled(self, chat_id) -> bool:
        return self.get_chat_config(chat_id).enabled

    # -- inspect -----------------------------------------------
    def results_for(self, chat_id) -> SearchResultSet | None:
        return self._results.get(str(chat_id))

    def clear_results(self, chat_id) -> None:
        self._results.pop(str(chat_id), None)

    def search_status(self, chat_id) -> dict:
        chat_id = str(chat_id)
        latest = self._results.get(chat_id)
        return {
            "plugin_id": PLUGIN_ID,
            "chat_id": chat_id,
            "config": self.get_chat_config(chat_id).to_dict(),
            "has_results": latest is not None,
            "latest": latest.to_dict() if latest is not None else None,
        }

    # -- the explicit search action -----------------------------
    async def search(self, chat_id, query, *, max_results: int | None = None) -> dict:
        """Search for one chat -- ONLY when it has opted in.

        The opt-in check runs first: a chat that has not
        enabled web search raises :class:`WebSearchDisabledError`
        before the provider is touched and before the query is
        even validated, so a disabled chat causes no provider
        call, no transport call and no stored state. On success
        the result set becomes the chat's latest (inspectable
        via :meth:`search_status`) and the status dict is
        returned with ``performed=True``. A provider failure
        raises :class:`WebSearchError` and stores nothing new.
        """
        chat_id = _check_chat_id(chat_id)
        cfg = self.get_chat_config(chat_id)
        if not cfg.enabled:
            raise WebSearchDisabledError(
                f"web search is not enabled for chat {chat_id!r} "
                "(off by default; per-chat opt-in required)")
        query = _check_query(query)
        if max_results is not None:
            _check_max_results(max_results)
        effective = max_results or cfg.max_results or self.config.max_results
        result_set = await _invoke_provider(
            self.config.effective_provider, query, max_results=effective)
        results = tuple(result_set.results[:effective])
        stored = SearchResultSet(
            query=query, chat_id=chat_id, provider=result_set.provider,
            road=result_set.road, results=results)
        self._results[chat_id] = stored
        status = self.search_status(chat_id)
        status["performed"] = True
        return status

    # -- events --------------------------------------------------
    async def on_event(self, event) -> None:
        """Housekeeping only: chat.deleted drops that chat's
        opt-in and stored results. chat.created (declared) is
        a deliberate no-op. No event ever triggers a search."""
        name = getattr(event, "name", None)
        if name == "chat.deleted":
            chat_id = getattr(event, "chat_id", None)
            if not chat_id and isinstance(getattr(event, "data", None), dict):
                chat_id = event.data.get("chat_id")
            if chat_id:
                self.clear_chat_config(chat_id)

    # -- prompt hook ----------------------------------------------
    async def web_search_slot(self, ctx, slots):
        """The slots-stage hook: offer the latest cited results.

        Abstains (None) unless the chat is CURRENTLY opted in
        and a stored result set with at least one result
        exists. Never calls a provider: context changes only
        from an explicit, opted-in search that already ran.
        """
        chat_id = getattr(ctx, "chat_id", None)
        if chat_id is None:
            return None
        if not self.is_enabled(chat_id):
            return None
        result_set = self._results.get(str(chat_id))
        if result_set is None or not result_set.results:
            return None
        return [
            Slot(
                id=SLOT_LOCAL_ID,
                kind="web_search",
                role="system",
                content=format_result_set(result_set),
                order=4,
                priority=80,
                trigger="web-search",
            )
        ]


def register_plugin(
    registry: PluginRegistry,
    provider=None,
    *,
    config: WebSearchConfig | None = None,
    enable: bool = False,
) -> tuple[PluginRecord, WebSearchPlugin]:
    """Register the citizen into ``registry`` (trusted code only).

    ``provider`` is host wiring: a provider object or plain
    callable handed in by trusted registration code; when both
    ``provider`` and ``config`` are given the explicit provider
    wins. Returns the record and the plugin instance.
    ``enable=True`` performs the owner's enable verb
    immediately; the default leaves the plugin REGISTERED.
    Note the two distinct switches: registry enablement makes
    the citizen live at all; per-chat opt-in (default OFF)
    is what allows any search.
    """
    if config is None:
        config = WebSearchConfig(provider=provider)
    elif provider is not None:
        config = dataclasses.replace(config, provider=provider)
    plugin = WebSearchPlugin(config)
    record = registry.register(plugin.manifest, plugin.handlers())
    if enable:
        registry.enable(PLUGIN_ID)
        record = registry.get(PLUGIN_ID)
    return record, plugin


__all__ = [
    "DECLARED_EVENTS",
    "DEFAULT_MAX_RESULTS",
    "DETERMINISTIC_VERSION",
    "HOOK_ID",
    "MAX_QUERY_CHARS",
    "MAX_RESULTS",
    "PLUGIN_ID",
    "PLUGIN_VERSION",
    "SLOT_LOCAL_ID",
    "UI_LOCAL_ID",
    "ChatWebSearchConfig",
    "DeterministicSearchProvider",
    "HttpJsonSearchProvider",
    "SearchResult",
    "SearchResultSet",
    "WebSearchConfig",
    "WebSearchDisabledError",
    "WebSearchError",
    "WebSearchPlugin",
    "build_manifest",
    "config_from_manifest",
    "format_result_set",
    "manifest_data",
    "register_plugin",
    "sandbox_grants",
]
