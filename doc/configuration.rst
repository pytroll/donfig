Configuration
=============

Donfig is meant to be used by other packages or scripts that need to configure
their own environment and make it easy for their users to modify it too. A
Donfig configuration object must be named. Typically this name matches the
name of the package being configured. For all of the examples below the
package name ``mypkg`` is used, but your package name should be substituted
for your configuration.

Donfig configuration options can be used to control any aspect of a package
that may not be suited for a keyword argument or would otherwise be difficult
for a user to configure. This might be to control logging verbosity, specify
cluster configuration, provide credentials for security, or any of several
other options that arise in production.

Configuration is specified in one of the following ways:

1.  YAML files in specified paths (see below)
2.  Environment variables like ``MYPKG_DISTRIBUTED__SCHEDULER__WORK_STEALING=True``
3.  Default settings within sub-libraries

This combination makes it easy to specify configuration in a variety of
settings ranging from personal workstations, to IT-mandated configuration, to
docker images.

Configuration Object
--------------------

.. autosummary::
    donfig.Config.__init__

The main way to use a Donfig configuration object is to make your own in your
packages ``__init__.py`` module and access it through the rest of your package
by importing it. To initialize the config object:

.. code-block:: python

    from donfig import Config
    config = Config('mypkg')

This will initialize the configuration object with information found from
YAML files in the above mentioned paths and environment variables. Paths to
search for YAML files can be customized as well as default options:

.. code-block:: python

    config = Config('mypkg', defaults=[{'key1': 'default_val'}], paths=['/usr/local/etc/'])

Access Configuration
--------------------

.. autosummary::
   donfig.Config.get

Once the configuration object is created, settings can be accessed using the
``get`` method. To get a sense for what the configuration is in the current
system the ``pprint`` method can be used to print the current state
of the configuration.

.. code-block:: python

   >>> from mypkg import config
   >>> config.pprint()
   {
     'logging': {
       'distributed': 'info',
       'bokeh': 'critical',
       'tornado': 'critical',
     }
     'admin': {
       'log-format': '%(name)s - %(levelname)s - %(message)s'
     }
   }

   >>> config.get('logging')
   {'distributed': 'info',
    'bokeh': 'critical',
    'tornado': 'critical'}

   >>> config.get('logging.bokeh')  # use `.` for nested access
   'critical'

Note that the ``get`` function treats underscores and hyphens identically.
For example, ``mypkg.config.get('num_workers')`` is equivalent to
``mypkg.config.get('num-workers')``.


Specify Configuration
---------------------

YAML files
~~~~~~~~~~

You can specify configuration values in YAML files like the following:

.. code-block:: yaml

   logging:
     distributed: info
     bokeh: critical
     tornado: critical

   scheduler:
     work-stealing: True
     allowed-failures: 5

     admin:
       log-format: '%(name)s - %(levelname)s - %(message)s'

These files can live in any of the following locations:

1.  The ``~/.config/mypkg`` directory in the user's home directory
2.  The ``{sys.prefix}/etc/mypkg`` directory local to Python
3.  The ``{prefix}/etc/mypkg`` directories with ``{prefix}`` in `site.PREFIXES
    <https://docs.python.org/3/library/site.html#site.PREFIXES>`_
4.  The root directory (specified by the ``MYPKG_ROOT_CONFIG`` environment
    variable or ``/etc/mypkg/`` by default)

Donfig searches for *all* YAML files within each of these directories and merges
them together, preferring configuration files closer to the user over system
configuration files (preference follows the order in the list above).
Additionally users can specify a path with the ``MYPKG_CONFIG`` environment
variable, that takes precedence at the top of the list above.

The contents of these YAML files are merged together, allowing different
subprojects to manage configuration files separately, but have them merge
into the same global configuration (ex. ``dask``, ``dask-kubernetes``,
``dask-ml``).

Environment Variables
~~~~~~~~~~~~~~~~~~~~~

You can also specify configuration values with environment variables like
the following:

.. code-block:: bash

   export MYPKG_DISTRIBUTED__SCHEDULER__WORK_STEALING=True
   export MYPKG_DISTRIBUTED__SCHEDULER__ALLOWED_FAILURES=5

resulting in configuration values like the following:

.. code-block:: python

   {'distributed':
     {'scheduler':
       {'work-stealing': True,
        'allowed-failures': 5}
     }
   }

Donfig searches for all environment variables that start with ``MYPKG_``, then
transforms keys by converting to lower case and changing double-underscores to
nested structures.

Donfig tries to parse all values with `ast.literal_eval
<https://docs.python.org/3/library/ast.html#ast.literal_eval>`_, letting users
pass numeric and boolean values (such as ``True`` in the example above) as well
as lists, dictionaries, and so on with normal Python syntax.

Environment variables take precedence over configuration values found in YAML
files.

Defaults
~~~~~~~~

Additionally, individual subprojects may add their own default values when they
are imported.  These are always added with lower priority than the YAML files
or environment variables mentioned above.

.. code-block:: python

   >>> import mypkg.config
   >>> import mypkg.distributed
   >>> mypkg.config.pprint()  # New values have been added
   {'scheduler': ...,
    'worker': ...,
    'tls': ...}

Deprecations
~~~~~~~~~~~~

Over the life of a project configuration keys may be changed or removed. Donfig
allows specifying these changes through a ``deprecations`` dictionary. The key
of this mapping is the old deprecated key name and the value is the new name or
``None`` to declare that the old key has been removed.

.. code-block:: python

    >>> deprecations = {"old_key": "new_key", "invalid": None}
    >>> config = Config("mypkg", deprecations=deprecations)
    >>> config.set(old_key="test")
    UserWarning: Configuration key "old_key" has been deprecated. Please use "new_key" instead.
    >>> config.set(invalid="value")
    Traceback (most recent call last):
        ...
    ValueError: Configuration value "invalid" has been removed
    >>> config.set(another_key="another_value")

Directly within Python
~~~~~~~~~~~~~~~~~~~~~~

.. autosummary::
   donfig.Config.set

Additionally, you can temporarily set a configuration value using the
``mypkg.config.set`` function.  This function accepts a dictionary as an input
and interprets ``"."`` as nested access

.. code-block:: python

   >>> mypkg.config.set({'scheduler.work-stealing': True})

This function can also be used as a context manager for consistent cleanup.

.. code-block:: python

   with mypkg.config.set({'scheduler.work-stealing': True}):
       ...

Note that the ``set`` function treats underscores and hyphens identically.
For example, ``mypkg.config.set({'scheduler.work-stealing': True})`` is
equivalent to ``mypkg.config.set({'scheduler.work_stealing': True})``.

Distributing configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~

It may also be desirable to package up your whole configuration for use on
another machine. This is used in some libraries (ex. Dask Distributed) to
ensure remote components have the same configuration as your local system.

This is typically handled by the downstream libraries which use base64
encoding to pass config via the ``MYPKG_INTERNAL_INHERIT_CONFIG`` environment
variable.

.. autosummary::
   donfig.serialize
   donfig.deserialize
   donfig.Config.serialize

Conversion Utility
~~~~~~~~~~~~~~~~~~

It is possible to configure Donfig inline with dot notation, with YAML or via environment variables. You can enter
your own configuration items below to convert back and forth.

.. warning::
   This utility is designed to improve understanding of converting between different notations
   and does not claim to be a perfect implementation. Please use for reference only.

**YAML**

.. raw:: html

   <textarea id="configConvertUtilYAML" name="configConvertUtilYAML" rows="10" cols="50" class="configTextArea" wrap="off">
   distributed:
     logging:
       distributed: info
       bokeh: critical
       tornado: critical
   </textarea>

**Environment variable**

.. raw:: html

   <textarea id="configConvertUtilEnv" name="configConvertUtilEnv" rows="10" cols="50" class="configTextArea" wrap="off">
   export MYPKG_DISTRIBUTED__LOGGING__DISTRIBUTED="info"
   export MYPKG_DISTRIBUTED__LOGGING__BOKEH="critical"
   export MYPKG_DISTRIBUTED__LOGGING__TORNADO="critical"
   </textarea>

**Inline with dot notation**

.. raw:: html

   <textarea id="configConvertUtilCode" name="configConvertUtilCode" rows="10" cols="50" class="configTextArea" wrap="off">
   >>> mypkg.config.set({"distributed.logging.distributed": "info"})
   >>> mypkg.config.set({"distributed.logging.bokeh": "critical"})
   >>> mypkg.config.set({"distributed.logging.tornado": "critical"})
   </textarea>

Updating Configuration
----------------------

Manipulating configuration dictionaries
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. autosummary::
   donfig.Config.merge
   donfig.Config.update
   donfig.Config.expand_environment_variables

As described above, configuration can come from many places, including several
YAML files, environment variables, and project defaults.  Each of these
provides a configuration that is possibly nested like the following:

.. code-block:: python

   x = {'a': 0, 'c': {'d': 4}}
   y = {'a': 1, 'b': 2, 'c': {'e': 5}}

Dask will merge these configurations respecting nested data structures, and
respecting order.

.. code-block:: python

   >>> mypkg.config.pprint()
   {}
   >>> mypkg.config.merge(x, y)
   >>> mypkg.config.pprint()
   {'a': 1, 'b': 2, 'c': {'d': 4, 'e': 5}}

You can also use the ``update`` method to update the existing configuration
in place with a new configuration.  This can be done with priority being given
to either config.

.. code-block:: python

   mypkg.config.update(new, priority='new')  # Give priority to new values
   mypkg.config.update(new, priority='old')  # Give priority to old values

Sometimes it is useful to expand environment variables stored within a
configuration. This can be done with the ``expand_environment_variables``
method:

.. code-block:: python

    mypkg.config.expand_environment_variables()

Refreshing Configuration
~~~~~~~~~~~~~~~~~~~~~~~~

.. autosummary::
   donfig.Config.collect
   donfig.Config.refresh

If you change your environment variables or YAML files the configuration
object will not immediately see the changes.  Instead, you can call
``refresh`` to go through the configuration collection process and update the
default configuration.

.. code-block:: python

   >>> mypkg.config.pprint()
   {}

   >>> # make some changes to yaml files

   >>> mypkg.config.refresh()
   >>> mypkg.config.pprint()
   {...}

This function uses ``donfig.Config.collect``, which returns the configuration
without modifying the global configuration.  You might use this to determine
the configuration of particular paths not yet on the config path.

.. code-block:: python

   >>> mypkg.config.collect(paths=[...])
   {...}

Downstream Libraries
--------------------

.. autosummary::
   donfig.Config.ensure_file
   donfig.Config.update
   donfig.Config.update_defaults

One way to structure the configuration of a series of downstream packages
and one central package is to follow the model used by Dask.
Dask downstream libraries often follow a standard convention to use the
central Dask configuration.  This section provides recommendations for
integration of new downstream libraries to the ``mypkg`` example, using
another fictional project, ``mypkg-foo``, as an example.

Downstream projects can follow the following convention:

1.  Maintain default configuration in a YAML file within their source
    directory::

       setup.py
       mypkg_foo/__init__.py
       mypkg_foo/config.py
       mypkg_foo/core.py
       mypkg_foo/foo.yaml  # <---

2.  Place configuration in that file within a namespace for the project

    .. code-block:: yaml

       # mypkg_foo/foo.yaml

       foo:
         color: red
         admin:
           a: 1
           b: 2

3.  With the configuration for ``mypkg_foo`` in ``mypkg_foo/__init__.py``
    (or anywhere) load the default ``mypkg`` config and update it into the
    global configuration:

    .. code-block:: python

       # mypkg_foo/config.py
       import os
       import yaml

       import mypkg.config

       fn = os.path.join(os.path.dirname(__file__), 'foo.yaml')

       with open(fn) as f:
           defaults = yaml.load(f)

       mypkg.config.update_defaults(defaults)

4.  Within that same module, copy the ``'foo.yaml'`` file to the user's
    configuration directory if it doesn't already exist.

    We also comment the file to make it easier for us to change defaults in the
    future.

    .. code-block:: python

       # ... continued from above

       mypkg.config.ensure_file(source=fn, comment=True)

    The user can investigate ``~/.config/mypkg/*.yaml`` to see all of the
    commented out configuration files to which they have access.

5.  Ensure that this file is run on import by including it in
    ``mypkg_foo/__init__.py`` if not already there.

6.  Within ``mypkg_foo`` code, use the ``mypkg.config.get`` function to access
    configuration values:

    .. code-block:: python

       # dask_foo/core.py

       def process(fn, color=None):
           if color is None:
               color = mypkg.config.get('foo.color')
           ...

.. note::

    The config object is accessed as runtime instead of at import (in the
    function declaration) in case users customize the value later.

7.  You may also want to ensure that your yaml configuration files are included
    in your package.  This can be accomplished by including the following line
    in your ``MANIFEST.in``::

       recursive-include <PACKAGE_NAME> *.yaml

    and the following in your setup.py ``setup`` call

    .. code-block:: python

        from setuptools import setup

        setup(...,
              include_package_data=True,
              ...)

This process keeps configuration in a central place, but also keeps it safe
within namespaces.  It places config files in an easy to access location
,``~/.config/mypkg/\*.yaml`` by default so that users can easily discover what
they can change, but maintains the actual defaults within the source code, so
that they more closely track changes in the library.

However, downstream libraries may choose alternative solutions, such as
isolating their configuration within their library, rather than using the
global mypkg.config system.
