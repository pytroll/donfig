#!/usr/bin/env python
# Copyright (c) 2018- Donfig Developers
"""Tests for the generic typed-config engine in :mod:`donfig.typed`."""

from __future__ import annotations

import copy
import pickle
import sys
import threading
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, dataclass, field
from typing import Any

import pytest

from donfig.typed import (
    MISSING,
    ConfigNode,
    TypedConfigManager,
    apply_overrides,
    flatten_mapping,
    get_path,
    replace_path,
    to_nested_dict,
    unknown_key_error,
)


@dataclass(frozen=True, slots=True)
class SchedulerConfig(ConfigNode):
    __key_aliases__ = {"work-stealing": "work_stealing", "async": "async_"}

    work_stealing: bool = False
    allowed_failures: int = 5
    async_: bool = False


@dataclass(frozen=True, slots=True)
class RootConfig(ConfigNode):
    logging_level: str = "info"
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)
    codecs: Mapping[str, Any] = field(default_factory=dict)


class TypedTestConfig(TypedConfigManager[RootConfig]):
    @property
    def logging_level(self) -> str:
        return self._current().logging_level

    @property
    def scheduler(self) -> SchedulerConfig:
        return self._current().scheduler


def make_config(**kwargs: Any) -> TypedTestConfig:
    return TypedTestConfig(default_factory=RootConfig, build_base=RootConfig, **kwargs)


# --- dotted-key traversal -------------------------------------------------
def test_get_path() -> None:
    cfg = RootConfig()
    assert get_path(cfg, "logging_level") == "info"
    assert get_path(cfg, "scheduler") is cfg.scheduler
    assert get_path(cfg, "scheduler.allowed_failures") == 5


def test_get_path_aliases() -> None:
    cfg = RootConfig()
    assert get_path(cfg, "scheduler.work-stealing") is False
    assert get_path(cfg, "scheduler.async") is False


def test_get_path_open_mapping() -> None:
    cfg = RootConfig(codecs={"blosc.shuffle": "bit"})
    # The remainder below the mapping indexes it as a single dotted key.
    assert get_path(cfg, "codecs.blosc.shuffle") == "bit"
    with pytest.raises(KeyError):
        get_path(cfg, "codecs.zstd.level")


def test_get_path_unknown() -> None:
    cfg = RootConfig()
    with pytest.raises(KeyError):
        get_path(cfg, "nope")
    with pytest.raises(KeyError):
        get_path(cfg, "scheduler.nope")


def test_replace_path() -> None:
    cfg = RootConfig()
    new = replace_path(cfg, "scheduler.allowed_failures", 10)
    assert new.scheduler.allowed_failures == 10
    # Snapshots are immutable: the original is untouched.
    assert cfg.scheduler.allowed_failures == 5
    assert replace_path(cfg, "scheduler.work-stealing", True).scheduler.work_stealing is True


def test_replace_path_open_mapping() -> None:
    cfg = RootConfig(codecs={"a": 1})
    new = replace_path(cfg, "codecs.blosc.shuffle", "bit")
    assert new.codecs == {"a": 1, "blosc.shuffle": "bit"}
    assert cfg.codecs == {"a": 1}


def test_replace_path_unknown() -> None:
    with pytest.raises(KeyError):
        replace_path(RootConfig(), "scheduler.nope", 1)


# Ported from zarr-python#4101: a dotted key that walks past a scalar leaf must
# raise, not resolve a stray Python attribute (e.g. `str.upper`).
@pytest.mark.parametrize("key", ["logging_level.upper", "scheduler.allowed_failures.numerator"])
def test_traversal_does_not_descend_into_scalar_attributes(key: str) -> None:
    cfg = RootConfig()
    with pytest.raises(KeyError):
        get_path(cfg, key)
    with pytest.raises(KeyError):
        replace_path(cfg, key, "X")


def test_snapshot_is_picklable_and_deepcopyable() -> None:
    cfg = replace_path(RootConfig(), "codecs.x", "pkg.X")
    assert pickle.loads(pickle.dumps(cfg)) == cfg
    assert copy.deepcopy(cfg) == cfg


def test_snapshots_are_frozen() -> None:
    cfg = RootConfig()
    with pytest.raises(FrozenInstanceError):
        cfg.logging_level = "debug"  # type: ignore[misc]


# --- ConfigNode item access -----------------------------------------------
def test_config_node_getitem() -> None:
    cfg = RootConfig()
    assert cfg["logging_level"] == "info"
    assert cfg["scheduler.allowed_failures"] == 5
    assert cfg["scheduler"] is cfg.scheduler
    assert cfg.scheduler["work-stealing"] is False
    with pytest.raises(KeyError):
        cfg["nope"]


# --- typo suggestions -----------------------------------------------------
def test_unknown_key_error_suggests_close_match() -> None:
    err = unknown_key_error("scheduler.allowed_failure", RootConfig())
    assert "Did you mean 'scheduler.allowed_failures'?" in err.args[0]


def test_unknown_key_error_suggests_top_level() -> None:
    err = unknown_key_error("logging", RootConfig())
    assert "Did you mean 'logging_level'?" in err.args[0]


def test_unknown_key_error_lists_valid_keys() -> None:
    err = unknown_key_error("scheduler.zzz", RootConfig())
    msg = err.args[0]
    assert "Valid keys under 'scheduler'" in msg
    assert "allowed_failures" in msg
    assert "work-stealing" in msg


def test_unknown_key_error_below_scalar_has_no_roster() -> None:
    # The key dead-ends below a scalar leaf: nothing to suggest, no roster.
    err = unknown_key_error("logging_level.x", RootConfig())
    assert err.args[0] == "'logging_level.x' is not a valid configuration key."


def test_unknown_key_error_resolvable_key_lists_children() -> None:
    # Misuse tolerance: a key that fully resolves still yields a usable error.
    err = unknown_key_error("scheduler", RootConfig())
    assert "Valid keys under 'scheduler'" in err.args[0]
    # ... and one resolving to a scalar leaf has no children to list.
    err = unknown_key_error("logging_level", RootConfig())
    assert err.args[0] == "'logging_level' is not a valid configuration key."


def test_unknown_key_error_roster_is_capped() -> None:
    codecs = {f"codec{i:02d}": i for i in range(12)}
    err = unknown_key_error("codecs.zzz", RootConfig(codecs=codecs))
    msg = err.args[0]
    assert "codec00" in msg
    assert "... (2 more)" in msg
    assert "codec11" not in msg


# --- (de)serialization ----------------------------------------------------
def test_to_nested_dict_uses_serialized_names() -> None:
    assert to_nested_dict(RootConfig()) == {
        "logging_level": "info",
        "scheduler": {"work-stealing": False, "allowed_failures": 5, "async": False},
        "codecs": {},
    }


def test_flatten_mapping() -> None:
    nested = {"a": {"b": 1, "c": {"d": 2}}, "e": 3}
    assert flatten_mapping(nested) == {"a.b": 1, "a.c.d": 2, "e": 3}


def test_apply_overrides() -> None:
    cfg = apply_overrides(RootConfig(), {"scheduler.work-stealing": True, "logging_level": "debug"})
    assert cfg.scheduler.work_stealing is True
    assert cfg.logging_level == "debug"


def test_apply_overrides_skips_unknown_with_warning() -> None:
    with pytest.warns(UserWarning, match="Unrecognized config key 'nope'"):
        cfg = apply_overrides(RootConfig(), {"nope": 1, "logging_level": "debug"})
    # The unknown key is skipped; the valid one still applies.
    assert cfg.logging_level == "debug"


def test_apply_overrides_custom_warning_category() -> None:
    class IngestWarning(UserWarning):
        pass

    with pytest.warns(IngestWarning):
        apply_overrides(RootConfig(), {"nope": 1}, warning_category=IngestWarning)


# --- the manager: reads ---------------------------------------------------
def test_manager_get() -> None:
    config = make_config()
    assert config.get("logging_level") == "info"
    assert config.get("scheduler.allowed_failures") == 5
    assert config.get("scheduler.work-stealing") is False


def test_manager_typed_attribute_access() -> None:
    config = make_config()
    assert config.logging_level == "info"
    assert config.scheduler.allowed_failures == 5


def test_manager_get_default() -> None:
    config = make_config()
    assert config.get("nope", default=3) == 3
    # An explicit None default is distinct from "no default supplied".
    assert config.get("nope", default=None) is None


def test_manager_get_unknown_raises_with_suggestion() -> None:
    config = make_config()
    with pytest.raises(KeyError, match="allowed_failures"):
        config.get("scheduler.allowed_failure")


def test_manager_to_dict_and_defaults() -> None:
    config = make_config()
    assert config.defaults == to_nested_dict(RootConfig())
    config.set(logging_level="debug")
    assert config.to_dict()["logging_level"] == "debug"
    # `defaults` still reflects the pure schema defaults.
    assert config.defaults["logging_level"] == "info"


def test_manager_pprint(capsys: pytest.CaptureFixture[str]) -> None:
    make_config().pprint()
    assert "logging_level" in capsys.readouterr().out


# --- the manager: writes --------------------------------------------------
def test_manager_bare_set_is_permanent() -> None:
    config = make_config()
    config.set({"scheduler.allowed_failures": 7})
    config.set(logging_level="debug")  # keyword form
    assert config.scheduler.allowed_failures == 7
    assert config.logging_level == "debug"


def test_manager_bare_set_visible_across_threads() -> None:
    config = make_config()
    config.set({"scheduler.allowed_failures": 7})
    with ThreadPoolExecutor(1) as pool:
        assert pool.submit(config.get, "scheduler.allowed_failures").result() == 7


def test_manager_set_unknown_key_raises() -> None:
    config = make_config()
    with pytest.raises(KeyError, match="allowed_failures"):
        config.set({"scheduler.allowed_failure": 1})


def test_manager_get_and_set_reject_descending_into_scalar() -> None:
    config = make_config()
    with pytest.raises(KeyError):
        config.get("logging_level.upper")
    with pytest.raises(KeyError):
        config.set({"logging_level.upper": "X"})


def test_manager_permanent_set_cross_thread_last_writer_wins() -> None:
    # A permanent `set` from any thread updates the shared global base, so a
    # later permanent `set` in another thread is visible everywhere.
    config = make_config()
    config.set({"scheduler.allowed_failures": 1})
    worker = threading.Thread(target=lambda: config.set({"scheduler.allowed_failures": 999}))
    worker.start()
    worker.join()
    assert config.get("scheduler.allowed_failures") == 999


def test_manager_concurrent_sets_to_distinct_keys_all_survive() -> None:
    # `set` rebuilds the whole snapshot from `_base`; the manager locks that
    # read-modify-write so concurrent sets to distinct keys don't lose updates.
    # A tiny switch interval forces preemption inside the critical section.
    config = make_config()
    n = 32
    barrier = threading.Barrier(n)

    def worker(i: int) -> None:
        barrier.wait()
        config.set({f"codecs.k{i}": i})

    old_interval = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:
        with ThreadPoolExecutor(max_workers=n) as pool:
            list(pool.map(worker, range(n)))
    finally:
        sys.setswitchinterval(old_interval)
    codecs = config.get("codecs")
    assert all(codecs.get(f"k{i}") == i for i in range(n))


def test_manager_scoped_set_unwinds() -> None:
    config = make_config()
    with config.set({"scheduler.allowed_failures": 10}):
        assert config.scheduler.allowed_failures == 10
    assert config.scheduler.allowed_failures == 5


def test_manager_scoped_set_nests() -> None:
    config = make_config()
    with config.set(logging_level="debug"):
        with config.set(logging_level="warning"):
            assert config.logging_level == "warning"
        assert config.logging_level == "debug"
    assert config.logging_level == "info"


def test_manager_scoped_set_reverts_open_mapping_changes() -> None:
    # A scoped `set` that *adds* a new mapping key removes it again on block
    # exit, while a pre-existing key it overrode is restored to its prior value.
    def build_base() -> RootConfig:
        return RootConfig(codecs={"blosc": "pkg.Blosc"})

    config = TypedTestConfig(default_factory=RootConfig, build_base=build_base)
    with config.set({"codecs.new_codec": "pkg.New", "codecs.blosc": "pkg.Override"}):
        assert config.get("codecs.new_codec") == "pkg.New"
        assert config.get("codecs.blosc") == "pkg.Override"
    codecs = config.get("codecs")
    assert "new_codec" not in codecs
    assert codecs["blosc"] == "pkg.Blosc"


def test_manager_scoped_set_is_context_local() -> None:
    config = make_config()
    with config.set({"scheduler.allowed_failures": 10}):
        # A fresh thread has a fresh context: it sees the base, not the overlay.
        with ThreadPoolExecutor(1) as pool:
            assert pool.submit(config.get, "scheduler.allowed_failures").result() == 5


def test_manager_bare_set_inside_scope_does_not_leak_overlay() -> None:
    config = make_config()
    with config.set(logging_level="debug"):
        config.set({"scheduler.allowed_failures": 9})
        # The permanent write is masked while the scope overlay is active.
        assert config.scheduler.allowed_failures == 5
    # On exit the permanent write survives, but the scoped override does not.
    assert config.scheduler.allowed_failures == 9
    assert config.logging_level == "info"


def test_manager_update() -> None:
    config = make_config()
    config.update({"logging_level": "debug"})
    assert config.logging_level == "debug"


# --- the manager: lifecycle -----------------------------------------------
def test_manager_reset_discards_overrides() -> None:
    config = make_config()
    config.set(logging_level="debug")
    config.reset()
    assert config.logging_level == "info"


def test_manager_refresh_rebuilds_base() -> None:
    state = {"level": "info"}

    def build_base() -> RootConfig:
        return RootConfig(logging_level=state["level"])

    config = TypedTestConfig(default_factory=RootConfig, build_base=build_base)
    assert config.logging_level == "info"
    state["level"] = "warning"
    config.refresh()
    assert config.logging_level == "warning"


# --- the manager: deprecations --------------------------------------------
def test_manager_renamed_key_redirects_with_warning() -> None:
    config = make_config(deprecations={"sched.failures": "scheduler.allowed_failures"})
    with pytest.warns(DeprecationWarning, match="renamed to 'scheduler.allowed_failures'"):
        config.set({"sched.failures": 3})
    assert config.scheduler.allowed_failures == 3
    with pytest.warns(DeprecationWarning):
        assert config.get("sched.failures") == 3


def test_manager_removed_key() -> None:
    config = make_config(deprecations={"old-flag": None})
    with pytest.raises(ValueError, match="'old-flag' has been removed"):
        config.set({"old-flag": 1})
    # Reads honour an explicit default (even None), else raise KeyError.
    assert config.get("old-flag", default=2) == 2
    assert config.get("old-flag", default=None) is None
    with pytest.raises(KeyError):
        config.get("old-flag")


def test_manager_custom_deprecation_hooks() -> None:
    class MyDeprecationWarning(UserWarning):
        pass

    def removed_error(key: str) -> Exception:
        return RuntimeError(f"gone: {key}")

    config = make_config(
        deprecations={"gone": None, "old": "logging_level"},
        removed_error=removed_error,
        deprecation_warning=MyDeprecationWarning,
    )
    with pytest.raises(RuntimeError, match="gone"):
        config.set({"gone": 1})
    with pytest.warns(MyDeprecationWarning):
        config.set({"old": "debug"})
    assert config.logging_level == "debug"


def test_missing_sentinel_is_not_none() -> None:
    assert MISSING is not None
