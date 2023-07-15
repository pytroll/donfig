## Version 0.8.1 (2023/07/14)

### Pull Requests Merged

#### Bugs fixed

* [PR 74](https://github.com/pytroll/donfig/pull/74) - Fix subpackages not being included in sdist

In this release 1 pull request was closed.


## Version 0.8.0 (2023/07/13)

### Pull Requests Merged

#### Bugs fixed

* [PR 63](https://github.com/pytroll/donfig/pull/63) - Override old default values in `update_defaults`

#### Features added

* [PR 61](https://github.com/pytroll/donfig/pull/61) - Add key deprecation support
* [PR 60](https://github.com/pytroll/donfig/pull/60) - Add configuration serialization and deserialization
* [PR 59](https://github.com/pytroll/donfig/pull/59) - Port typing annotations and improve error messages

In this release 6 pull requests were closed.


## Version 0.7.0 (2022/02/04)

### Issues Closed

* [Issue 17](https://github.com/pytroll/donfig/issues/17) - Threadlock TypeError when trying to pickle donfig object ([PR 22](https://github.com/pytroll/donfig/pull/22) by [@djhoese](https://github.com/djhoese))
* [Issue 16](https://github.com/pytroll/donfig/issues/16) - Failure to initialize Config object ([PR 20](https://github.com/pytroll/donfig/pull/20) by [@djhoese](https://github.com/djhoese))
* [Issue 14](https://github.com/pytroll/donfig/issues/14) - 0.6.0 release?
* [Issue 13](https://github.com/pytroll/donfig/issues/13) - MNT: Stop using ci-helpers in appveyor.yml

In this release 4 issues were closed.

### Pull Requests Merged

#### Bugs fixed

* [PR 21](https://github.com/pytroll/donfig/pull/21) - Make `test__get_paths` robust to `site.PREFIXES` being set

#### Features added

* [PR 23](https://github.com/pytroll/donfig/pull/23) - Drop Python 3.6 support and add pre-commit
* [PR 22](https://github.com/pytroll/donfig/pull/22) - Add SerializableLock from Dask to use in `Config.set` ([17](https://github.com/pytroll/donfig/issues/17))
* [PR 19](https://github.com/pytroll/donfig/pull/19) - Refactor config default search path retrieval
* [PR 18](https://github.com/pytroll/donfig/pull/18) - Expand YAML config search directories

#### Documentation changes

* [PR 20](https://github.com/pytroll/donfig/pull/20) - Fix inaccurate example of Config creation with defaults ([16](https://github.com/pytroll/donfig/issues/16))

In this release 6 pull requests were closed.


## Version 0.6.0 (2021/01/17)

### Pull Requests Merged

#### Features added

* [PR 11](https://github.com/pytroll/donfig/pull/11) - Add dask config conversion javascript utility
* Drop support for Python <3.6

In this release 1 pull request was closed.


## Version 0.5.0 (2019/11/06)

### Pull Requests Merged

#### Bugs fixed

* [PR 9](https://github.com/pytroll/donfig/pull/9) - Fix environment variable loading only working with 4 characters

#### Features added

* [PR 8](https://github.com/pytroll/donfig/pull/8) - Allow nested key set by keyword argument

In this release 2 pull requests were closed.


## Version 0.4.0 (2019/04/30)

### Issues Closed

* [Issue 5](https://github.com/pytroll/donfig/issues/5) - donfig.config_obj.collect_yaml method is vulnerable

In this release 1 issue was closed.

### Pull Requests Merged

#### Bugs fixed

* [PR 6](https://github.com/pytroll/donfig/pull/6) - Avoid deprecation warning from newer versions of pyyaml
* [PR 4](https://github.com/pytroll/donfig/pull/4) - Fix handling of non-readable config files
* [PR 3](https://github.com/pytroll/donfig/pull/3) - Allow updates from arbitrary Mappings

#### Features added

* [PR 7](https://github.com/pytroll/donfig/pull/7) - Remove config key normalization

In this release 4 pull requests were closed.


## Version 0.3.0 (2018/12/24)

### Pull Requests Merged

#### Features added

* [PR 2](https://github.com/pytroll/donfig/pull/2) - Add ``__getitem__`` and ``__contains__`` method to Config object

In this release 1 pull request was closed.


## Version 0.2.0 (2018/12/23)

### Pull Requests Merged

#### Features added

* [PR 1](https://github.com/pytroll/donfig/pull/1) - Treat None as missing in config when updating

In this release 1 pull request was closed.

## Version 0.1.2 (2018/11/03)

#### Features added

* First working release of donfig migrated from dask.config.
