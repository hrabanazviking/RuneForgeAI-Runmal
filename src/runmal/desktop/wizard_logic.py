"""First-Run Setup wizard logic (R-05) — Qt-free view-model layer.

The wizard *widgets* live in ``runmal.desktop.wizard``; everything
they decide lives here, so the whole flow is unit-testable on hosts
with no PySide6 (the R-04 client-layer pattern). This module talks
to the engine ONLY through ``RunmalClient`` — no engine imports, no
SQL, no prompt logic.

The flow (plan §2.3, four steps):

1. **Connect a mind** — one of five backend kinds, described in plain
   words (:data:`BACKEND_OPTIONS`). Ollama detection runs through the
   R-02 roads: a draft Ollama profile is created (or an existing one
   reused), then its health + model list are read — the same probe
   any later screen uses, never a private side channel. Creating the
   chosen profile goes through the R-02 client; an API key, when one
   is given, is set afterwards via the write-only secret route and is
   never stored on this object, never logged, and never echoed back
   (INV-023).
2. **Prove it** — the profile's health probe + model list, rendered
   as plain words (:func:`health_words`): reachable or not, how many
   models, how long the answer took, or a plain-language failure
   reason. Raw JSON is never shown to the user.
3. **Meet someone** — create a first character from a few lines, or
   import a card file (JSON/PNG) through the library import road;
   then open a chat with that character (the engine seeds the
   greeting) and pin the chosen profile to it, so the first chat
   answers through the mind step 1 connected.
4. **Your name** — the persisted ``{{user}}`` name via the R-03 road.

Demo mode honesty: the ``fake`` backend is labelled Demo everywhere
it can appear — it is a canned responder, never disguised as a model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from runmal.desktop.client import RunmalClient
from runmal.desktop.client.errors import ClientError
from runmal.desktop.client.models import (
    BackendProfile,
    CharacterSummary,
    ChatSummary,
)

#: The Ollama address the wizard probes unless the user edits it.
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"

#: Profile name used for the wizard's Ollama draft (step 1 detection
#: creates it through the R-02 roads; finishing keeps it as the
#: user's Ollama profile, with the picked model written back).
OLLAMA_PROFILE_NAME = "Ollama (local)"


@dataclass(frozen=True)
class BackendOption:
    """One step-1 choice, in plain words."""

    kind: str  # the engine's chat_backend key (R-02 CHAT_BACKENDS)
    title: str
    blurb: str
    profile_name: str
    needs_api_key: bool = False
    needs_base_url: bool = False
    default_base_url: str = ""
    default_model: str = ""


BACKEND_OPTIONS: tuple[BackendOption, ...] = (
    BackendOption(
        kind="ollama",
        title="Ollama — on this computer",
        blurb=(
            "Runs models locally, free and private, if Ollama is "
            "installed. Rúnmál can look for it and list its models."
        ),
        profile_name=OLLAMA_PROFILE_NAME,
        needs_base_url=True,
        default_base_url=DEFAULT_OLLAMA_URL,
    ),
    BackendOption(
        kind="openrouter",
        title="OpenRouter — online, many models",
        blurb=(
            "One API key opens many hosted models. You paste the key "
            "once; Rúnmál stores it in its secret store and never "
            "shows it back."
        ),
        profile_name="OpenRouter",
        needs_api_key=True,
    ),
    BackendOption(
        kind="openai",
        title="OpenAI-compatible — your own server address",
        blurb=(
            "Any server that speaks the OpenAI chat shape: its "
            "address, its API key if it has one, and a model name."
        ),
        profile_name="OpenAI-compatible",
        needs_api_key=True,
        needs_base_url=True,
    ),
    BackendOption(
        kind="aesir",
        title="Aesir — Rúnmál's own local engine",
        blurb=(
            "The project's own inference engine, when it is running "
            "on this machine. No key needed."
        ),
        profile_name="Aesir (local)",
    ),
    BackendOption(
        kind="fake",
        title="Demo mode — not a real model",
        blurb=(
            "Honestly: this is not a model at all. It is a canned "
            "responder that always says the same line, so you can "
            "see how Rúnmál feels before connecting a real mind. "
            "You can switch to a real backend later."
        ),
        profile_name="Demo mode",
        default_model="fake-1",
    ),
)

_OPTIONS_BY_KIND = {option.kind: option for option in BACKEND_OPTIONS}


def backend_option(kind: str) -> BackendOption:
    """The plain-words option for one engine backend kind."""
    try:
        return _OPTIONS_BY_KIND[kind]
    except KeyError:
        raise ValueError(f"unknown backend kind: {kind}") from None


def plain_reason(text: str) -> str:
    """Render an engine/backend detail string as plain words.

    Health details are already short taxonomy strings (the adapters
    sanitize them, INV-001/023); this only guards the user against a
    raw JSON blob or an empty string ever reaching the wizard.
    """
    cleaned = " ".join(str(text or "").split())
    if not cleaned:
        return "the backend gave no reason"
    if cleaned.startswith("{") or cleaned.startswith("["):
        return "the backend answered with something Rúnmál could not read"
    return cleaned


def health_words(
    label: str,
    health: dict[str, Any],
    models: list[dict[str, Any]] | None = None,
    models_error: str = "",
) -> str:
    """Step 2's report, in words — never raw JSON.

    ``label`` names the profile/backend in human terms ("Demo mode",
    "Ollama (local)"); ``health`` is the R-02 health payload;
    ``models`` the R-02 model list when it could be read.
    """
    ok = bool(health.get("ok"))
    latency = health.get("latency_ms")
    latency_words = ""
    if isinstance(latency, (int, float)):
        latency_words = f" It answered in {latency:.0f} milliseconds."
    if not ok:
        reason = plain_reason(str(health.get("detail") or ""))
        return (
            f"Not reachable — {label} did not answer properly: "
            f"{reason}. You can go back and check the address or "
            f"key, try a different mind, or continue anyway and "
            f"fix it later in Connections."
        )
    words = f"Reachable — {label} answered.{latency_words}"
    if models is not None:
        names = [
            str(m.get("model_id") or m.get("display_name") or "")
            for m in models
        ]
        names = [n for n in names if n]
        if names:
            shown = ", ".join(names[:5])
            extra = f" (and {len(names) - 5} more)" if len(names) > 5 else ""
            words += f" It reports {len(names)} model(s): {shown}{extra}."
        else:
            words += " It reports no models yet."
    elif models_error:
        words += (
            " Its model list could not be read ("
            + plain_reason(models_error)
            + "), but the connection itself works."
        )
    return words


@dataclass(frozen=True)
class DetectResult:
    """Step 1's Ollama detection verdict."""

    reachable: bool
    models: list[str] = field(default_factory=list)
    words: str = ""
    profile: BackendProfile | None = None


@dataclass(frozen=True)
class ProveResult:
    """Step 2's verdict for the chosen profile."""

    ok: bool
    words: str
    model_count: int = 0
    latency_ms: float | None = None
    models: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class GreetedChat:
    """Step 3's landing: the opened chat + its seeded greeting."""

    chat: ChatSummary
    character: CharacterSummary
    greeting: str = ""
    message_count: int = 0


class WizardFlow:
    """Stateful driver for one wizard run, over one client.

    Holds only ids and the chosen profile/character/chat objects —
    never a secret value: an API key passes through
    :meth:`create_chosen_profile` as an argument, goes straight to
    the write-only secret route, and is not retained (INV-023).
    """

    def __init__(self, client: RunmalClient) -> None:
        self._client = client
        self.profile: BackendProfile | None = None
        self.character: CharacterSummary | None = None
        self.greeted_chat: GreetedChat | None = None
        # The profile detection created speculatively (step 1). If
        # the user finishes with a different kind, the draft is
        # deleted again — detection must not leave litter behind.
        self._draft_profile_id: str | None = None

    # -------------------------------------------------------- step 1

    def detect_ollama(self, base_url: str = "") -> DetectResult:
        """Look for Ollama through the R-02 health/models roads.

        Creates the draft Ollama profile on first use (or reuses an
        existing Ollama profile), probes it, and — when reachable —
        lists its models for the user to pick from. An unreachable
        Ollama is a plain-words result, not an exception.
        """
        url = (base_url or "").strip() or DEFAULT_OLLAMA_URL
        profile = self._ollama_profile(url)
        self.profile = profile
        self._draft_profile_id = profile.id
        health = self._client.profile_health(profile.id)
        if not health.get("ok"):
            return DetectResult(
                reachable=False,
                words=(
                    "No Ollama answered at "
                    f"{url} — {plain_reason(str(health.get('detail') or ''))}. "
                    "If Ollama is installed, start it and look again; "
                    "otherwise pick another mind, or Demo mode."
                ),
                profile=profile,
            )
        models: list[str] = []
        models_error = ""
        try:
            models = [
                str(m.get("model_id") or "")
                for m in self._client.profile_models(profile.id)
            ]
            models = [m for m in models if m]
        except ClientError as exc:
            models_error = str(exc)
        if models:
            words = (
                f"Ollama is running at {url} with {len(models)} "
                f"model(s): {', '.join(models[:5])}. Pick one below."
            )
        elif models_error:
            words = (
                f"Ollama answered at {url}, but its model list could "
                f"not be read ({plain_reason(models_error)}). You "
                "can type a model name instead."
            )
        else:
            words = (
                f"Ollama is running at {url}, but it has no models "
                "yet. Pull one in Ollama first (for example "
                "'ollama pull llama3'), or type its name if you are "
                "about to."
            )
        return DetectResult(
            reachable=True, models=models, words=words, profile=profile
        )

    def _ollama_profile(self, base_url: str) -> BackendProfile:
        profiles = self._client.list_backend_profiles()
        for existing in profiles:
            if existing.chat_backend == "ollama":
                if (existing.config or {}).get("base_url") != base_url:
                    return self._client.update_backend_profile(
                        existing.id, config={"base_url": base_url}
                    )
                return existing
        return self._client.create_backend_profile(
            OLLAMA_PROFILE_NAME,
            "ollama",
            config={"base_url": base_url},
        )

    def create_chosen_profile(
        self,
        kind: str,
        *,
        chat_model: str = "",
        base_url: str = "",
        api_key: str = "",
    ) -> BackendProfile:
        """Create (or finish) the step-1 profile via the R-02 client.

        When detection already created a draft of the same kind, the
        draft is updated with the picked model/address instead of
        creating a second profile. A non-empty ``api_key`` is stored
        via the write-only secret route after creation and is never
        retained by this object.
        """
        option = backend_option(kind)
        model = (chat_model or "").strip() or option.default_model
        url = (base_url or "").strip() or option.default_base_url
        config = {"base_url": url} if url else None

        profile: BackendProfile | None = None
        if self.profile is not None and self.profile.chat_backend == kind:
            profile = self.profile
            updates: dict[str, Any] = {}
            if model != profile.chat_model:
                updates["chat_model"] = model
            if config is not None and config != (profile.config or {}):
                updates["config"] = config
            if updates:
                profile = self._client.update_backend_profile(
                    profile.id, **updates
                )
        else:
            profile = self._client.create_backend_profile(
                option.profile_name,
                kind,
                chat_model=model,
                config=config,
            )
        if api_key:
            profile = self._client.set_chat_secret(profile.id, api_key)
        if self._draft_profile_id is not None:
            draft_id, self._draft_profile_id = self._draft_profile_id, None
            if draft_id != profile.id:
                try:
                    self._client.delete_backend_profile(draft_id)
                except ClientError:
                    pass  # tidy-up only; the chosen profile stands
        self.profile = profile
        return profile

    # -------------------------------------------------------- step 2

    def prove(self, profile_id: str | None = None) -> ProveResult:
        """Run the R-02 health probe + model list and word the result."""
        profile = self.profile
        if profile_id is not None:
            profile = self._client.get_backend_profile(profile_id)
            self.profile = profile
        if profile is None:
            raise ClientError("no backend profile to prove yet")
        option = _OPTIONS_BY_KIND.get(profile.chat_backend)
        label = option.profile_name if option else profile.label
        health = self._client.profile_health(profile.id)
        models: list[dict[str, Any]] | None = None
        models_error = ""
        if health.get("ok"):
            try:
                models = self._client.profile_models(profile.id)
            except ClientError as exc:
                models_error = str(exc)
        names = [
            str(m.get("model_id") or "") for m in (models or [])
        ]
        latency = health.get("latency_ms")
        return ProveResult(
            ok=bool(health.get("ok")),
            words=health_words(label, health, models, models_error),
            model_count=len([n for n in names if n]),
            latency_ms=latency if isinstance(latency, (int, float)) else None,
            models=[n for n in names if n],
        )

    # -------------------------------------------------------- step 3

    def create_character(
        self,
        *,
        name: str,
        description: str = "",
        personality: str = "",
        first_greeting: str = "",
        scenario: str = "",
    ) -> CharacterSummary:
        """Create the first character from a few plain lines."""
        clean_name = name.strip()
        if not clean_name:
            raise ClientError("the character needs a name")
        card: dict[str, Any] = {
            "name": clean_name,
            "description": description.strip(),
            "personality": personality.strip(),
            "scenario": scenario.strip(),
            "first_mes": first_greeting.strip(),
        }
        self.character = self._client.create_character(card, name=clean_name)
        return self.character

    def import_character(
        self, filename: str, data: bytes
    ) -> CharacterSummary:
        """Import a card file (JSON/PNG) via the library road and
        resolve the character it landed."""
        outcome = self._client.import_character_file(filename, data)
        if not outcome.ok:
            raise ClientError(
                "that file did not import as a character: "
                + plain_reason(outcome.reason)
            )
        characters = self._client.list_characters()
        for character in characters:
            if character.id == outcome.character_id:
                self.character = character
                return character
        # The report named a character the list does not show (a
        # repaired import can land under a normalized id) — fall back
        # to the report's own identity rather than failing the step.
        self.character = CharacterSummary(
            id=outcome.character_id, name=outcome.character_name
        )
        return self.character

    def open_greeted_chat(
        self,
        character_id: str | None = None,
        *,
        profile_id: str | None = None,
    ) -> GreetedChat:
        """Open the first chat: create it with the character (the
        engine seeds the greeting), pin the chosen profile to it so
        its answers come from the connected mind, and read the
        greeting back."""
        character = self.character
        if character_id is not None:
            for listed in self._client.list_characters():
                if listed.id == character_id:
                    character = listed
                    break
            else:
                character = CharacterSummary(id=character_id)
        if character is None:
            raise ClientError("no character to open a chat with yet")
        chat = self._client.create_chat(
            title=f"First chat with {character.name or 'your character'}",
            character_id=character.id,
        )
        pin = profile_id
        if pin is None and self.profile is not None:
            pin = self.profile.id
        if pin:
            try:
                chat = self._client.set_chat_backend_profile(chat.id, pin)
            except ClientError:
                # Pinning is a refinement; the chat itself already
                # exists and is greeted. A failed pin must not strand
                # the user at the last step — generation still
                # resolves an explicit profile at send time.
                pass
        messages = self._client.list_chat_messages(chat.id)
        greeting = ""
        for message in messages:
            if message.role == "assistant" and message.content:
                greeting = message.content
                break
        self.greeted_chat = GreetedChat(
            chat=chat,
            character=character,
            greeting=greeting,
            message_count=len(messages),
        )
        return self.greeted_chat

    # -------------------------------------------------------- step 4

    def get_user_name(self) -> str:
        """The effective persisted user name (default "User")."""
        payload = self._client.get_user_name()
        name = payload.get("user_name")
        return name if isinstance(name, str) and name else "User"

    def set_user_name(self, name: str) -> str:
        """Persist the user's name via the R-03 road; an empty field
        keeps the current/default name instead of clearing it."""
        cleaned = (name or "").strip()
        if not cleaned:
            return self.get_user_name()
        payload = self._client.set_user_name(cleaned)
        stored = payload.get("user_name")
        return stored if isinstance(stored, str) and stored else cleaned


__all__ = [
    "BACKEND_OPTIONS",
    "DEFAULT_OLLAMA_URL",
    "OLLAMA_PROFILE_NAME",
    "BackendOption",
    "DetectResult",
    "GreetedChat",
    "ProveResult",
    "WizardFlow",
    "backend_option",
    "health_words",
    "plain_reason",
]
