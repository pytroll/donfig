#!/usr/bin/env python
# Copyright (c) 2022 Donfig Developers
# Copyright (c) 2014-2018, Anaconda, Inc. and contributors

import pickle

from .._lock import SerializableLock


def test_SerializableLock():
    a = SerializableLock()
    b = SerializableLock()
    with a:
        pass

    with a:
        with b:
            pass

    with a:
        assert not a.acquire(False)

    a2 = pickle.loads(pickle.dumps(a))
    a3 = pickle.loads(pickle.dumps(a))
    a4 = pickle.loads(pickle.dumps(a2))

    for x in [a, a2, a3, a4]:
        for y in [a, a2, a3, a4]:
            with x:
                assert not y.acquire(False)

    b2 = pickle.loads(pickle.dumps(b))
    b3 = pickle.loads(pickle.dumps(b2))

    for x in [a, a2, a3, a4]:
        for y in [b, b2, b3]:
            with x:
                with y:
                    pass
            with y:
                with x:
                    pass


def test_SerializableLock_name_collision():
    a = SerializableLock("a")
    b = SerializableLock("b")
    c = SerializableLock("a")
    d = SerializableLock()

    assert a.lock is not b.lock
    assert a.lock is c.lock
    assert d.lock not in (a.lock, b.lock, c.lock)


def test_SerializableLock_locked():
    a = SerializableLock("a")
    assert not a.locked()
    with a:
        assert a.locked()
    assert not a.locked()


def test_SerializableLock_acquire_blocking():
    a = SerializableLock("a")
    assert a.acquire(blocking=True)
    assert not a.acquire(blocking=False)
    a.release()
