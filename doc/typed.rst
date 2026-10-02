Typed Configuration
===================

.. currentmodule:: donfig.typed

Donfig stores configuration as an untyped nested ``dict`` and surfaces it
through ``Config.get(key) -> Any``. That is flexible, but it means static type
checkers cannot verify configuration access: a typo in a key or a wrong
assumption about a value's type is only discovered at runtime.

The :mod:`donfig.typed` module adds an optional, statically-typed
representation on top of donfig. Instead of a nested ``dict``, the
configuration is modeled as a tree of frozen dataclasses. This typed,
nested ``dict`` (i.e., the *schema*) is also the single source of truth for defaults.
Reads and writes still go through the familiar dotted-string API
(``config.get("a.b")``, ``config.set({"a.b": value})``), but they are
backed by immutable snapshots, and typed attribute access (``config.a.b``)
carries precise static types all the way down.

Donfig's `typed` module provides the engine for downstream libraries to use
typed schemas, but is schema-agnostic itself. The schema, typed
attribute accessors, and per-key ``get`` overloads, live in the consuming
application.

Donfig's YAML and environment variable ingestion is available when using the
typed module. The untyped :class:`donfig.Config` collection
machinery feeds the typed snapshot through :func:`apply_overrides`.

Defining a schema
-----------------

A schema is a tree of frozen dataclasses whose nodes subclass
:class:`ConfigNode`. Field defaults are the configuration defaults:

.. code-block:: python

    # mypkg/_config.py
    from dataclasses import dataclass, field

    from donfig.typed import ConfigNode


    @dataclass(frozen=True, slots=True)
    class SchedulerConfig(ConfigNode):
        work_stealing: bool = False
        allowed_failures: int = 5


    @dataclass(frozen=True, slots=True)
    class MypkgConfig(ConfigNode):
        logging_level: str = "info"
        scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)

:class:`ConfigNode` is a mixin that restores dict-style item access on the
dataclass nodes, so ``node["allowed_failures"]`` and dotted
``node["scheduler.allowed_failures"]`` work alongside typed attribute access
(``node.scheduler.allowed_failures``). Unknown keys raise ``KeyError``.

Key aliases
~~~~~~~~~~~

Serialized key segments (from YAML files, environment variables, or
dotted-string keys) must map to dataclass field names, which are Python
identifiers. When a serialized key is not a legal identifier (.e.g, a reserved word
like ``async``, or a hyphenated key like ``work-stealing``), attach a
``__key_aliases__`` mapping (serialized segment to Python field name) to the
node:

.. code-block:: python

    @dataclass(frozen=True, slots=True)
    class SchedulerConfig(ConfigNode):
        __key_aliases__ = {"work-stealing": "work_stealing"}

        work_stealing: bool = False

Both ``config.get("scheduler.work-stealing")`` and the
``scheduler.work_stealing`` attribute then resolve to the same field.

Creating the manager
--------------------

The application subclasses :class:`TypedConfigManager`, which is generic over
the root schema class. The subclass is where typed attribute accessors (and,
optionally, per-key ``get`` overloads) are defined:

.. code-block:: python

    # mypkg/_config.py  (continued)
    from donfig import Config
    from donfig.typed import TypedConfigManager, apply_overrides, flatten_mapping

    # Untyped donfig object: collects YAML files and MYPKG_* env vars as usual.
    _ingest = Config("mypkg")


    def _build_base() -> MypkgConfig:
        return apply_overrides(MypkgConfig(), flatten_mapping(_ingest.config))


    class MypkgTypedConfig(TypedConfigManager[MypkgConfig]):
        @property
        def logging_level(self) -> str:
            return self._current().logging_level

        @property
        def scheduler(self) -> SchedulerConfig:
            return self._current().scheduler


    config = MypkgTypedConfig(default_factory=MypkgConfig, build_base=_build_base)

Two callables parameterize the manager:

``default_factory``
    Constructs the pure-defaults snapshot (typically the root schema class
    itself). Exposed as the ``defaults`` property, mirroring
    ``donfig.Config.defaults``.

``build_base``
    Constructs the process-global base snapshot: the defaults overlaid with
    whatever was ingested from YAML files and environment variables.
    :func:`flatten_mapping` flattens the nested ``dict`` collected by
    :class:`donfig.Config` into a flat dotted-key mapping, and
    :func:`apply_overrides` applies that mapping to a snapshot. Unknown keys
    are skipped with a warning rather than raising, so a stray environment
    variable or an extra YAML key never prevents import.

Reading configuration
---------------------

Both access styles read from the same state:

.. code-block:: python

    >>> from mypkg._config import config

    >>> config.scheduler.allowed_failures        # typed: int
    5
    >>> config.get("scheduler.allowed_failures")  # dotted string
    5
    >>> config.get("scheduler.retries", default=3)
    3

``get`` raises an informative ``KeyError`` for unknown keys, suggesting the
closest match at the deepest level that resolved:

.. code-block:: python

    >>> config.get("scheduler.allowed_failure")
    Traceback (most recent call last):
        ...
    KeyError: "'scheduler.allowed_failure' is not a valid configuration key. Did you mean 'scheduler.allowed_failures'?"

For interoperability with code expecting the untyped interface, ``to_dict()``
converts the current snapshot back to a nested ``dict`` keyed by serialized
names, and ``pprint()`` prints it.

Per-key ``get`` overloads
~~~~~~~~~~~~~~~~~~~~~~~~~

``TypedConfigManager.get`` returns ``Any``, like ``donfig.Config.get``. To
give the dotted-string API precise static types too, the subclass can add
``@overload`` declarations per key:

.. code-block:: python

    from typing import Any, Literal, overload

    class MypkgTypedConfig(TypedConfigManager[MypkgConfig]):
        @overload
        def get(self, key: Literal["scheduler.allowed-failures"]) -> int: ...
        @overload
        def get(self, key: Literal["scheduler.work-stealing"]) -> bool: ...
        @overload
        def get(self, key: str, default: Any = ...) -> Any: ...
        def get(self, key: str, default: Any = MISSING) -> Any:
            return super().get(key, default)

Setting configuration
---------------------

``set`` matches the semantics of ``donfig.Config.set``. Called bare, the
override is permanent, meaning it is applied immediately to the process-global base
and is visible from every thread:

.. code-block:: python

    config.set({"scheduler.work-stealing": True})
    config.set(logging_level="debug")  # keyword form

Used as a context manager, the override is *scoped*, meaning it is isolated to the
calling context (thread or async task, via :class:`contextvars.ContextVar`)
and unwound on exit:

.. code-block:: python

    with config.set({"scheduler.allowed-failures": 10}):
        assert config.scheduler.allowed_failures == 10
    assert config.scheduler.allowed_failures == 5

Because snapshots are immutable frozen dataclasses, each ``set`` produces a
new snapshot; concurrent readers always see a consistent view and there is no
partially-applied state. Unlike a plain ``with config.set(...)`` on the
untyped object, the scoped form does not leak into other threads or async
tasks running concurrently. Note one asymmetry inherited from donfig's
last-writer-wins semantics: a bare ``set`` *is* visible everywhere, including
inside ``ThreadPoolExecutor`` workers, which do not copy context variables.

``reset()`` and ``refresh()`` rebuild the base snapshot via ``build_base``,
re-reading YAML files and environment variables — the typed analog of
``donfig.Config.refresh``.

Deprecating keys
----------------

Like :class:`donfig.Config`, the manager accepts a ``deprecations`` mapping
from old key name to new name, or to ``None`` for keys that were removed:

.. code-block:: python

    config = MypkgTypedConfig(
        default_factory=MypkgConfig,
        build_base=_build_base,
        deprecations={"sched.failures": "scheduler.allowed-failures", "old-flag": None},
    )

Reading or setting a renamed key warns (``DeprecationWarning`` by default —
customizable via ``deprecation_warning``) and redirects to the new key.
Setting a removed key raises; reading one honors an explicit ``default`` and
otherwise raises ``KeyError``. The exception for removed keys can be
customized via ``removed_error``.

API
---

The full API is documented in the :doc:`API reference <api/donfig>`.

.. autosummary::
    ConfigNode
    TypedConfigManager
    apply_overrides
    flatten_mapping
    get_path
    replace_path
    to_nested_dict
    unknown_key_error
