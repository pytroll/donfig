"""
Generic engine for statically-typed, dataclass-backed configuration.

donfig historically stored configuration as an untyped nested ``dict`` and
surfaced it through ``Config.get(key) -> Any``.  This module adds an optional,
*typed* representation that any donfig consumer can adopt without giving up
donfig's env-var / YAML ingestion: model the configuration as a tree of frozen
dataclasses (the schema, and the single source of truth for defaults) and drive
it through the familiar dotted-string API, but backed by immutable snapshots and
a context-local overlay for scoped ``with`` blocks.

To adopt it an application:

* defines its schema as frozen ``@dataclass`` nodes subclassing `ConfigNode`.
  Attach ``__key_aliases__`` (serialized-segment -> Python-field-name) to a node
  when a serialized key is not a legal identifier, e.g. ``{"async": "async_"}``;
* subclasses `TypedConfigManager`, passing ``default_factory`` (the root schema
  class) and ``build_base`` (defaults overlaid with env/YAML ingest, typically
  via :func:`apply_overrides` fed from ``donfig.Config(...).config``);
* adds per-key ``get`` overloads and typed attribute ``@property`` accessors so
  that both ``config.get("a.b")`` and ``config.a.b`` carry precise static types.

Everything in this module is schema-agnostic; the schema, the overloads, and the
typed accessors live in the consuming application.
"""

from __future__ import annotations

import difflib
import threading
import warnings
from collections.abc import Callable, Mapping
from contextvars import ContextVar, Token
from dataclasses import fields, is_dataclass, replace
from typing import TYPE_CHECKING, Any, Generic, Literal, TypeVar, overload

if TYPE_CHECKING:
    from typing_extensions import Self

#: A frozen-dataclass config snapshot type (the application's root schema).
ConfigT = TypeVar("ConfigT")

__all__ = [
    "MISSING",
    "ConfigNode",
    "TypedConfigManager",
    "apply_overrides",
    "flatten_mapping",
    "get_path",
    "replace_path",
    "to_nested_dict",
    "unknown_key_error",
]

#: Sentinel distinguishing "no default supplied" from an explicit ``None`` default.
MISSING: Any = object()

_ROSTER_LIMIT = 10


# --- key-alias helpers ----------------------------------------------------
def _key_aliases(obj: object) -> Mapping[str, str]:
    """Serialized-segment -> Python-field-name overrides for a config node."""
    return getattr(type(obj), "__key_aliases__", {})


def _serialized_names(obj: object) -> Mapping[str, str]:
    """Python-field-name -> serialized-segment (the reverse of ``__key_aliases__``)."""
    return {field_name: serialized for serialized, field_name in _key_aliases(obj).items()}


def _resolve_field(obj: object, segment: str) -> str:
    """Translate a serialized key segment to the dataclass field name."""
    return _key_aliases(obj).get(segment, segment)


# --- dotted-key traversal -------------------------------------------------
def get_path(cfg: object, key: str) -> object:
    """Read a dotted-string key from a frozen-dataclass config snapshot.

    Raises
    ------
    KeyError
        If the key does not resolve to a value.
    """
    obj: object = cfg
    segments = key.split(".")
    for i, segment in enumerate(segments):
        if isinstance(obj, Mapping):
            # remaining segments index into an open mapping (e.g. codecs.*)
            remainder = ".".join(segments[i:])
            try:
                return obj[remainder]
            except KeyError:
                raise KeyError(key) from None
        # A prior segment resolved to a scalar leaf, but the key has more
        # segments — descend no further. Without this guard, `hasattr` would
        # match ordinary Python attributes/methods (e.g. `logging_level.upper`
        # returning `str.upper`) instead of raising for the invalid key.
        if not is_dataclass(obj):
            raise KeyError(key)
        field_name = _resolve_field(obj, segment)
        if field_name not in {f.name for f in fields(obj)}:
            raise KeyError(key)
        obj = getattr(obj, field_name)
    return obj


def replace_path(cfg: ConfigT, key: str, value: object) -> ConfigT:
    """Return a new snapshot with the dotted-string key set to ``value``.

    The return type mirrors the input: replacing a value produces a new snapshot of
    the same schema type, so callers keep their precise static type without a cast.
    """
    segments = key.split(".")
    return _replace_recursive(cfg, segments, value, key)  # type: ignore[return-value]


# `obj: Any` is load-bearing here: the function dispatches dynamically between a
# `Mapping` (open subtree) and a dataclass instance, and `dataclasses.replace`
# requires a dataclass-typed argument that `object` would reject.
def _replace_recursive(obj: Any, segments: list[str], value: object, key: str) -> object:
    segment = segments[0]
    if isinstance(obj, Mapping):
        remainder = ".".join(segments)
        return {**obj, remainder: value}
    # See the scalar-leaf guard in `get_path`: never descend past a non-node.
    if not is_dataclass(obj):
        raise KeyError(key)
    field_name = _resolve_field(obj, segment)
    if field_name not in {f.name for f in fields(obj)}:
        raise KeyError(key)
    # `is_dataclass` narrows `obj` to `... | type[...]`, which `replace` rejects;
    # at runtime `obj` is always a dataclass *instance* here, so re-widen to Any.
    node: Any = obj
    if len(segments) == 1:
        return replace(node, **{field_name: value})
    child = getattr(node, field_name)
    new_child = _replace_recursive(child, segments[1:], value, key)
    return replace(node, **{field_name: new_child})


# --- typo suggestions -----------------------------------------------------
def _children(obj: object) -> list[str]:
    """Return the immediate child key names of a config node (else an empty list)."""
    if isinstance(obj, Mapping):
        return list(obj)
    if is_dataclass(obj):
        names = _serialized_names(obj)
        return [names.get(f.name, f.name) for f in fields(obj)]
    return []


def _resolve_for_suggestion(cfg: object, key: str) -> tuple[str, list[str], str]:
    """Walk ``key`` as far as it resolves.

    Returns the deepest resolvable dotted prefix, that node's child key names, and
    the first segment that failed to resolve (the remainder is treated as a single
    key once an open mapping is reached).
    """
    obj: object = cfg
    prefix = ""
    segments = key.split(".")
    for i, segment in enumerate(segments):
        if isinstance(obj, Mapping):
            # the remainder indexes into an open mapping as a single key
            return prefix, _children(obj), ".".join(segments[i:])
        if not is_dataclass(obj):
            # the key descends below a scalar leaf: nothing to suggest there
            return prefix, [], segment
        field_name = _resolve_field(obj, segment)
        if field_name not in {f.name for f in fields(obj)}:
            return prefix, _children(obj), segment
        obj = getattr(obj, field_name)
        prefix = f"{prefix}.{segment}" if prefix else segment
    return prefix, _children(obj), ""


def unknown_key_error(key: str, cfg: object) -> KeyError:
    """Build a `KeyError` for an unknown config key.

    Resolves ``key`` to the deepest valid level, then suggests the closest child
    key there if one is similar enough; otherwise lists the available keys at that
    level (capped at ``_ROSTER_LIMIT``).
    """
    msg = f"{key!r} is not a valid configuration key."
    prefix, children, failed = _resolve_for_suggestion(cfg, key)
    matches = difflib.get_close_matches(failed, children, n=1) if failed != "" else []
    if len(matches) > 0:
        suggestion = f"{prefix}.{matches[0]}" if prefix != "" else matches[0]
        return KeyError(f"{msg} Did you mean {suggestion!r}?")
    if len(children) > 0:
        shown = sorted(children)
        roster = ", ".join(shown[:_ROSTER_LIMIT])
        if len(shown) > _ROSTER_LIMIT:
            roster += f", ... ({len(shown) - _ROSTER_LIMIT} more)"
        where = f" under {prefix!r}" if prefix != "" else ""
        msg = f"{msg} Valid keys{where}: {roster}."
    return KeyError(msg)


# --- (de)serialization ----------------------------------------------------
def to_nested_dict(cfg: object) -> dict[str, Any]:
    """Convert a config snapshot to a nested dict keyed by serialized names.

    Returns a heterogeneous, JSON-like tree (nested dicts and scalars) that
    callers navigate by key, so `Any` values are appropriate here.
    """

    # `obj: Any` is also load-bearing: `dataclasses.fields` requires a
    # dataclass-typed argument that `object` would reject.
    def convert(obj: Any) -> Any:
        if isinstance(obj, Mapping):
            return dict(obj)
        if hasattr(type(obj), "__dataclass_fields__"):
            names = _serialized_names(obj)
            out: dict[str, Any] = {}
            for f in fields(obj):
                out[names.get(f.name, f.name)] = convert(getattr(obj, f.name))
            return out
        return obj

    return convert(cfg)  # type: ignore[no-any-return]


def flatten_mapping(data: Mapping[str, object], prefix: str = "") -> dict[str, object]:
    """Flatten a nested mapping into a single dotted-key mapping."""
    out: dict[str, object] = {}
    for k, v in data.items():
        key = f"{prefix}{k}" if not prefix else f"{prefix}.{k}"
        if isinstance(v, Mapping):
            out.update(flatten_mapping(v, key))
        else:
            out[key] = v
    return out


def apply_overrides(
    cfg: ConfigT,
    overrides: Mapping[str, object],
    *,
    warning_category: type[Warning] = UserWarning,
) -> ConfigT:
    """Apply a flat dotted-key override map to a snapshot.

    Unknown keys are skipped with a warning rather than raising, so a stray
    environment variable or extra YAML key never prevents import.
    """
    for key, value in overrides.items():
        try:
            cfg = replace_path(cfg, key, value)
        except KeyError:
            warnings.warn(
                f"Unrecognized config key {key!r} from environment or YAML — ignoring.",
                warning_category,
                stacklevel=2,
            )
    return cfg


# --- item-access mixin ----------------------------------------------------
class ConfigNode:
    """Mixin giving frozen config dataclasses dict-style item access.

    A typed config returns dataclass instances for subtrees; this mixin restores
    subscripting (``node["order"]`` and dotted ``node["a.b"]``) alongside typed
    attribute access (``node.order``), raising `KeyError` for unknown keys.

    ``__slots__ = ()`` keeps subclasses fully slotted (no ``__dict__``).
    """

    __slots__ = ()

    def __getitem__(self, key: str) -> object:
        return get_path(self, key)


# --- scoped-set context manager -------------------------------------------
class _ConfigSet:
    """Context manager returned by ``TypedConfigManager.set``.

    ``set`` applies the override immediately to the process-global base, so a bare
    ``config.set(...)`` is permanent and visible from every thread (matching
    donfig's last-writer-wins semantics, including inside ``ThreadPoolExecutor``
    workers, which do not copy context variables).

    Using the result as a ``with`` block *promotes* the override to a
    context-local scope: ``__enter__`` undoes the global apply and re-applies the
    new snapshot through a `ContextVar`, so the change is isolated to the calling
    context (thread / async task) and unwound on ``__exit__``.
    """

    def __init__(self, manager: TypedConfigManager[Any], prev_base: object, new: object) -> None:
        self._manager = manager
        self._prev_base = prev_base
        self._new = new
        self._token: Token[Any] | None = None

    def __enter__(self) -> Self:
        self._token = self._manager._enter_scope(self._prev_base, self._new)
        return self

    def __exit__(self, *exc: object) -> None:
        if self._token is not None:
            self._manager._exit_scope(self._token)


def _default_removed_error(key: str) -> Exception:
    return ValueError(f"Configuration key {key!r} has been removed and no longer has any effect.")


# --- the manager ----------------------------------------------------------
class TypedConfigManager(Generic[ConfigT]):
    """Schema-agnostic base for a typed, donfig-compatible configuration object.

    Generic over ``ConfigT``, the application's root schema dataclass. Holds
    immutable ``ConfigT`` snapshots and resolves reads through a process-global
    base plus a context-local overlay, so `_current` (and therefore the subclass's
    typed attribute properties) carries the precise schema type. Subclasses add
    per-key ``get`` overloads and typed attribute properties over `_current`.
    """

    def __init__(
        self,
        *,
        default_factory: Callable[[], ConfigT],
        build_base: Callable[[], ConfigT],
        deprecations: Mapping[str, str | None] | None = None,
        removed_error: Callable[[str], Exception] = _default_removed_error,
        deprecation_warning: type[Warning] = DeprecationWarning,
    ) -> None:
        self._default_factory = default_factory
        self._build_base = build_base
        self._deprecations: Mapping[str, str | None] = dict(deprecations or {})
        self._removed_error = removed_error
        self._deprecation_warning = deprecation_warning
        self._base: ConfigT = build_base()
        self._scope: ContextVar[ConfigT] = ContextVar("typed_config_scope")
        # Serializes read-modify-write of the process-global `_base` so
        # concurrent `set`s to different keys don't lose updates (each rebuilds
        # a whole immutable snapshot from `_base`).
        self._lock = threading.Lock()

    # --- state resolution -------------------------------------------------
    def _current(self) -> ConfigT:
        return self._scope.get(self._base)

    def _enter_scope(self, prev_base: ConfigT, new: ConfigT) -> Token[ConfigT]:
        with self._lock:
            self._base = prev_base
        return self._scope.set(new)

    def _exit_scope(self, token: Token[ConfigT]) -> None:
        self._scope.reset(token)

    # --- string API -------------------------------------------------------
    def get(self, key: str, default: Any = MISSING) -> Any:
        resolved = self._apply_deprecation(key, raise_on_removed=False)
        if resolved is None:
            # Key was removed; treat as absent — honour the caller's default.
            if default is MISSING:
                raise KeyError(key)
            return default
        current = self._current()
        try:
            return get_path(current, resolved)
        except KeyError:
            if default is MISSING:
                raise unknown_key_error(key, current) from None
            return default

    def set(self, updates: Mapping[str, object] | None = None, **kwargs: object) -> _ConfigSet:
        """Apply one or more config overrides (permanent, or scoped as a ``with``)."""
        all_updates: dict[str, object] = {}
        if updates:
            all_updates.update(updates)
        all_updates.update(kwargs)
        with self._lock:
            prev_base = self._base
            # `scoped` layers on the current view (any active `with` overlay); it is
            # what a `with config.set(...)` pins as its context-local scope. `permanent`
            # layers on the global base, so a bare `set` nested inside a `with` block
            # does not leak that block's overlay into the base.
            scoped = self._current()
            permanent = prev_base
            for key, value in all_updates.items():
                resolved = self._apply_deprecation(key, raise_on_removed=True)
                try:
                    scoped = replace_path(scoped, resolved, value)
                    permanent = replace_path(permanent, resolved, value)
                except KeyError:
                    raise unknown_key_error(key, permanent) from None
            self._base = permanent
        return _ConfigSet(self, prev_base, scoped)

    # --- lifecycle --------------------------------------------------------
    def reset(self) -> None:
        # Rebuild outside the lock (`build_base` may read env/YAML) and swap
        # atomically under it.
        new_base = self._build_base()
        with self._lock:
            self._base = new_base

    def refresh(self) -> None:
        self.reset()

    # --- compat / introspection ------------------------------------------
    @property
    def defaults(self) -> dict[str, Any]:
        return to_nested_dict(self._default_factory())

    def to_dict(self) -> dict[str, Any]:
        return to_nested_dict(self._current())

    def update(self, updates: Mapping[str, object]) -> None:
        self.set(updates)

    def pprint(self) -> None:
        import pprint as _pp

        _pp.pprint(self.to_dict())

    # --- deprecations -----------------------------------------------------
    @overload
    def _apply_deprecation(self, key: str, *, raise_on_removed: Literal[True]) -> str: ...
    @overload
    def _apply_deprecation(self, key: str, *, raise_on_removed: Literal[False]) -> str | None: ...
    def _apply_deprecation(self, key: str, *, raise_on_removed: bool) -> str | None:
        """Resolve a possibly-deprecated config key to its canonical name.

        Returns the (possibly redirected) key, or ``None`` when the key was
        removed and ``raise_on_removed`` is ``False`` (so the caller can honour a
        default). Raises ``removed_error(key)`` when removed and
        ``raise_on_removed`` is ``True``.
        """
        if key not in self._deprecations:
            return key
        new_key = self._deprecations[key]
        if new_key is None:
            if raise_on_removed:
                raise self._removed_error(key)
            return None
        warnings.warn(
            f"Configuration key {key!r} has been renamed to {new_key!r}.",
            self._deprecation_warning,
            stacklevel=3,
        )
        return new_key
