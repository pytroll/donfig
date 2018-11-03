Donfig
======

Donfig is a python library meant to make configuration easier for other
python packages. Donfig can be configured programmatically by the user, by
environment variables, or from YAML files in standard locations. The
below examples show the basics of using donfig. For more details see the
official `documentation <https://donfig.readthedocs.io/en/latest/>`_.

Using Donfig
------------

Create the package-wide configuration object:

```python
# mypkg/__init__.py
from donfig import Config
config = Config('mypkg')
```

Use the configuration object:

```python
from mypkg import config
important_val = config.get('important_key')
if important_val:
    # do something
else:
    # something else
```

Set configuration in Python
---------------------------

```python
# mypkg/work.py
from mypkg import config
config.set(important_key=5)

# use the configuration
```

Donfig configurations can also be changed as a context manager:

```python
config.set(other_key=True)

with config.set(other_key=False):
    print(config.get('other_key'))  # False

print(config.get('other_key'))  # True
```

Configure from environment variables
------------------------------------

TODO

Configure from YAML file
------------------------

TODO

History
-------

Donfig is based on the original configuration logic of the `dask` library.
The code has been modified to use a config object instead of a global
configuration dictionary. This makes the configuration logic of dask available
to everyone.

License
-------

Original code from the dask library was distributed under the license
specified in `DASK_LICENSE.txt`. In November 2018 this code was migrated to
the Donfig project under the MIT license described in `LICENSE.txt`. The full
copyright for this project is therefore::

    Copyright (c) 2018 Donfig Developers
    Copyright (c) 2014-2018, Anaconda, Inc. and contributors
