from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _version

from .config_obj import Config, deserialize, serialize  # noqa

try:
    __version__ = _version("donfig")
except PackageNotFoundError:  # pragma: no cover - source tree without metadata
    __version__ = "0.0.0.dev0"
