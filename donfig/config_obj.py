#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2018 Donfig Developers
# Copyright (c) 2014-2018, Anaconda, Inc. and contributors
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
import ast
import os
import sys
import threading
import pprint
from copy import deepcopy
from collections import Mapping

try:
    import yaml
except ImportError:
    yaml = None

if sys.version_info[0] == 2:
    # python 2
    def makedirs(name, mode=0o777, exist_ok=True):
        try:
            os.makedirs(name, mode=mode)
        except OSError:
            if not exist_ok or not os.path.isdir(name):
                raise
else:
    makedirs = os.makedirs

no_default = '__no_default__'


def canonical_name(k, config):
    """Return the canonical name for a key.

    Handles user choice of '-' or '_' conventions by standardizing on whichever
    version was set first. If a key already exists in either hyphen or
    underscore form, the existing version is the canonical name. If neither
    version exists the original key is used as is.
    """
    try:
        if k in config:
            return k
    except TypeError:
        # config is not a mapping, return the same name as provided
        return k

    altk = k.replace('_', '-') if '_' in k else k.replace('-', '_')

    if altk in config:
        return altk

    return k


def update(old, new, priority='new'):
    """Update a nested dictionary with values from another

    This is like dict.update except that it smoothly merges nested values

    This operates in-place and modifies old

    Parameters
    ----------
    priority: string {'old', 'new'}
        If new (default) then the new dictionary has preference.
        Otherwise the old dictionary does.

    Examples
    --------
    >>> a = {'x': 1, 'y': {'a': 2}}
    >>> b = {'x': 2, 'y': {'b': 3}}
    >>> update(a, b)  # doctest: +SKIP
    {'x': 2, 'y': {'a': 2, 'b': 3}}

    >>> a = {'x': 1, 'y': {'a': 2}}
    >>> b = {'x': 2, 'y': {'b': 3}}
    >>> update(a, b, priority='old')  # doctest: +SKIP
    {'x': 1, 'y': {'a': 2, 'b': 3}}

    See Also
    --------
    donfig.config_obj.merge

    """
    for k, v in new.items():
        k = canonical_name(k, old)

        if isinstance(v, Mapping):
            if k not in old or old[k] is None:
                old[k] = {}
            update(old[k], v, priority=priority)
        else:
            if priority == 'new' or k not in old:
                old[k] = v

    return old


def merge(*dicts):
    """Update a sequence of nested dictionaries

    This prefers the values in the latter dictionaries to those in the former

    Examples
    --------
    >>> a = {'x': 1, 'y': {'a': 2}}
    >>> b = {'y': {'b': 3}}
    >>> merge(a, b)  # doctest: +SKIP
    {'x': 1, 'y': {'a': 2, 'b': 3}}

    See Also
    --------
    donfig.config_obj.update

    """
    result = {}
    for d in dicts:
        update(result, d)
    return result


def collect_yaml(paths):
    """Collect configuration from yaml files

    This searches through a list of paths, expands to find all yaml or json
    files, and then parses each file.

    """
    # Find all paths
    file_paths = []
    for path in paths:
        if os.path.exists(path):
            if os.path.isdir(path):
                try:
                    file_paths.extend(sorted([
                        os.path.join(path, p)
                        for p in os.listdir(path)
                        if os.path.splitext(p)[1].lower() in ('.json', '.yaml', '.yml')
                    ]))
                except OSError:
                    # Ignore permission errors
                    pass
            else:
                file_paths.append(path)

    configs = []

    # Parse yaml files
    for path in file_paths:
        try:
            with open(path) as f:
                data = yaml.safe_load(f.read()) or {}
                configs.append(data)
        except (OSError, IOError):
            # Ignore permission errors
            pass

    return configs


def collect_env(prefix, env=None):
    """Collect config from environment variables

    This grabs environment variables of the form "DASK_FOO__BAR_BAZ=123" and
    turns these into config variables of the form ``{"foo": {"bar-baz": 123}}``
    It transforms the key and value in the following way:

    -  Lower-cases the key text
    -  Treats ``__`` (double-underscore) as nested access
    -  Calls ``ast.literal_eval`` on the value

    """
    if env is None:
        env = os.environ
    d = {}
    for name, value in env.items():
        if name.startswith(prefix):
            varname = name[5:].lower().replace('__', '.')
            try:
                d[varname] = ast.literal_eval(value)
            except (SyntaxError, ValueError):
                d[varname] = value

    result = {}
    kwargs = d
    for key, value in kwargs.items():
        ConfigSet._assign(key.split('.'), value, result)

    return result


class ConfigSet(object):
    """Temporarily set configuration values within a context manager

    Note, this class should be used directly from the `Config`
    object via the :meth:`donfig.Config.set` method.

    Examples
    --------
    >>> from donfig.config_obj import ConfigSet
    >>> import mypkg
    >>> with ConfigSet(mypkg.config, {'foo': 123}):
    ...     pass

    See Also
    --------
    donfig.Config.set
    donfig.Config.get

    """
    def __init__(self, config, lock, arg=None, **kwargs):
        if arg and not kwargs:
            kwargs = arg

        with lock:
            self.config = config
            self.old = {}

            for key, value in kwargs.items():
                self._assign(key.split('.'), value, config, old=self.old)

    def __enter__(self):
        return self.config

    def __exit__(self, type, value, traceback):
        for keys, value in self.old.items():
            if value == '--delete--':
                d = self.config
                try:
                    while len(keys) > 1:
                        d = d[keys[0]]
                        keys = keys[1:]
                    del d[keys[0]]
                except KeyError:
                    pass
            else:
                self._assign(keys, value, self.config)

    @classmethod
    def _assign(cls, keys, value, d, old=None, path=[]):
        """Assign value into a nested configuration dictionary

        Optionally record the old values in old

        Parameters
        ----------
        keys: Sequence[str]
            The nested path of keys to assign the value, similar to toolz.put_in
        value: object
        d: dict
            The part of the nested dictionary into which we want to assign the
            value
        old: dict, optional
            If provided this will hold the old values
        path: List[str]
            Used internally to hold the path of old values

        """
        key = canonical_name(keys[0], d)
        if len(keys) == 1:
            if old is not None:
                path_key = tuple(path + [key])
                if key in d:
                    old[path_key] = d[key]
                else:
                    old[path_key] = '--delete--'
            d[key] = value
        else:
            if key not in d:
                d[key] = {}
                if old is not None:
                    old[tuple(path + [key])] = '--delete--'
                old = None
            cls._assign(keys[1:], value, d[key], path=path + [key], old=old)


def expand_environment_variables(config):
    """Expand environment variables in a nested config dictionary

    This function will recursively search through any nested dictionaries
    and/or lists.

    Parameters
    ----------
    config : dict, iterable, or str
        Input object to search for environment variables

    Returns
    -------
    config : same type as input

    Examples
    --------
    >>> expand_environment_variables({'x': [1, 2, '$USER']})  # doctest: +SKIP
    {'x': [1, 2, 'my-username']}

    """
    if isinstance(config, Mapping):
        return {k: expand_environment_variables(v) for k, v in config.items()}
    elif isinstance(config, str):
        return os.path.expandvars(config)
    elif isinstance(config, (list, tuple, set)):
        return type(config)([expand_environment_variables(v) for v in config])
    else:
        return config


class Config(object):
    def __init__(self, name, defaults=None, paths=None, env=None, env_var=None, root_env_var=None, env_prefix=None):
        if root_env_var is None:
            root_env_var = '{}_ROOT_CONFIG'.format(name.upper())
        if paths is None:
            paths = [
                os.getenv(root_env_var, '/etc/{}'.format(name)),
                os.path.join(sys.prefix, 'etc', name),
                os.path.join(os.path.expanduser('~'), '.config', name),
                os.path.join(os.path.expanduser('~'), '.{}'.format(name))
            ]

        if env_prefix is None:
            env_prefix = "{}_".format(name.upper())
        if env is None:
            env = os.environ
        if env_var is None:
            env_var = '{}_CONFIG'.format(name.upper())
        if env_var in os.environ:
            main_path = os.environ[env_var]
            paths.append(main_path)
        else:
            main_path = os.path.join(os.path.expanduser('~'), '.config', name)

        self.name = name
        self.env_prefix = env_prefix
        self.env = env
        self.main_path = main_path
        self.paths = paths
        self.defaults = defaults or []
        self.config = {}
        self.config_lock = threading.Lock()
        self.refresh()

    def __contains__(self, item):
        try:
            self[item]
            return True
        except (TypeError, IndexError, KeyError):
            return False

    def __getitem__(self, item):
        return self.get(item)

    def pprint(self, **kwargs):
        return pprint.pprint(self.config, **kwargs)

    def collect(self, paths=None, env=None):
        """Collect configuration from paths and environment variables

        Parameters
        ----------
        paths : List[str]
            A list of paths to search for yaml config files. Defaults to the
            paths passed when creating this object.

        env : dict
            The system environment variables to search through. Defaults to
            the environment dictionary passed when creating this object.

        Returns
        -------
        config: dict

        See Also
        --------
        donfig.Config.refresh: collect configuration and update into primary config

        """
        if paths is None:
            paths = self.paths
        if env is None:
            env = self.env
        configs = []

        if yaml:
            configs.extend(collect_yaml(paths=paths))

        configs.append(collect_env(self.env_prefix, env=env))

        return merge(*configs)

    def refresh(self, **kwargs):
        """Update configuration by re-reading yaml files and env variables.

        This goes through the following stages:

        1.  Clearing out all old configuration
        2.  Updating from the stored defaults from downstream libraries
            (see update_defaults)
        3.  Updating from yaml files and environment variables

        Note that some functionality only checks configuration once at startup and
        may not change behavior, even if configuration changes.  It is recommended
        to restart your python process if convenient to ensure that new
        configuration changes take place.

        See Also
        --------
        donfig.Config.collect: for parameters
        donfig.Config.update_defaults

        """
        self.clear()

        for d in self.defaults:
            update(self.config, d, priority='old')

        update(self.config, self.collect(**kwargs))

    def get(self, key, default=no_default):
        """Get elements from global config

        Use '.' for nested access

        Examples
        --------
        >>> from donfig import Config
        >>> config = Config('mypkg')
        >>> config.get('foo')  # doctest: +SKIP
        {'x': 1, 'y': 2}

        >>> config.get('foo.x')  # doctest: +SKIP
        1

        >>> config.get('foo.x.y', default=123)  # doctest: +SKIP
        123

        See Also
        --------
        donfig.Config.set

        """
        keys = key.split('.')
        result = self.config
        for k in keys:
            k = canonical_name(k, result)
            try:
                result = result[k]
            except (TypeError, IndexError, KeyError):
                if default is not no_default:
                    return default
                else:
                    raise
        return result

    def update_defaults(self, new):
        """Add a new set of defaults to the configuration

        It does two things:

        1.  Add the defaults to a collection to be used by refresh() later
        2.  Updates the config with the new configuration
            prioritizing older values over newer ones

        """
        self.defaults.append(new)
        update(self.config, new, priority='old')

    def to_dict(self):
        """Return dictionary copy of configuration.

        .. warning::

            This will copy all keys and values. This includes values that
            may cause unwanted side effects depending on what values exist
            in the current configuration.

        """
        return deepcopy(self.config)

    def clear(self):
        """Clear all existing configuration."""
        self.config.clear()

    def merge(self, *dicts):
        """Merge this configuration with multiple dictionaries.

        See :func:`~donfig.config_obj.merge` for more information.

        """
        self.config = merge(self.config, dicts)

    def update(self, new, priority='new'):
        """Update the internal configuration dictionary with `new`.

        See :func:`~donfig.config_obj.update` for more information.

        """
        self.config = update(self.config, new, priority=priority)

    def expand_environment_variables(self):
        """Expand any environment variables in this configuration in-place.

        See :func:`~donfig.config_obj.expand_environment_variables` for more information.

        """
        self.config = expand_environment_variables(self.config)

    def rename(self, aliases):
        """Rename old keys to new keys

        This helps migrate older configuration versions over time

        """
        old = []
        new = {}
        for o, n in aliases.items():
            value = self.get(o, None)
            if value is not None:
                old.append(o)
                new[n] = value

        for k in old:
            del self.config[k]  # TODO: support nested keys

        self.set(new)

    def set(self, arg=None, **kwargs):
        """Set configuration values within a context manager.

        Examples
        --------
        >>> from donfig import Config
        >>> config = Config('mypkg')
        >>> with config.set({'foo': 123}):
        ...     pass

        See Also
        --------
        donfig.Config.get

        """
        return ConfigSet(self.config, self.config_lock, arg=arg, **kwargs)

    def ensure_file(self, source, destination=None, comment=True):
        """Copy file to default location if it does not already exist

        This tries to move a default configuration file to a default location if
        if does not already exist.  It also comments out that file by default.

        This is to be used by downstream modules that may
        have default configuration files that they wish to include in the default
        configuration path.

        Parameters
        ----------
        source : string, filename
            Source configuration file, typically within a source directory.
        destination : string, directory
            Destination directory. Configurable by ``<CONFIG NAME>_CONFIG``
            environment variable, falling back to ~/.config/<config name>.
        comment : bool, True by default
            Whether or not to comment out the config file when copying.

        """
        if destination is None:
            destination = self.main_path

        # destination is a file and already exists, never overwrite
        if os.path.isfile(destination):
            return

        # If destination is not an existing file, interpret as a directory,
        # use the source basename as the filename
        directory = destination
        destination = os.path.join(directory, os.path.basename(source))

        try:
            if not os.path.exists(destination):
                makedirs(directory, exist_ok=True)

                # Atomically create destination.  Parallel testing discovered
                # a race condition where a process can be busy creating the
                # destination while another process reads an empty config file.
                tmp = '%s.tmp.%d' % (destination, os.getpid())
                with open(source) as f:
                    lines = list(f)

                if comment:
                    lines = ['# ' + line
                             if line.strip() and not line.startswith('#')
                             else line
                             for line in lines]

                with open(tmp, 'w') as f:
                    f.write(''.join(lines))

                try:
                    os.rename(tmp, destination)
                except OSError:
                    os.remove(tmp)
        except OSError:
            pass
