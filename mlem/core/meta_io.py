"""
Utils functions that parse and process supplied URI, serialize/derialize MLEM objects
"""
import os
from typing import Any, Dict, Tuple, Type, TypeVar

from fsspec import AbstractFileSystem, get_fs_token_paths
from fsspec.implementations.github import GithubFileSystem
from pydantic import parse_obj_as

from mlem.core.base import MlemObject
from mlem.utils.github import get_github_envs, get_github_kwargs
from mlem.utils.root import MLEM_DIR

MLEM_EXT = ".mlem.yaml"


META_FILE_NAME = "mlem.yaml"
ART_DIR = "artifacts"


def get_fs(
    uri: str, protocol: str = None, **kwargs
) -> Tuple[AbstractFileSystem, str]:
    """Parse given (uri, protocol) with fsspec and return (fs, path)"""
    storage_options = {}
    if protocol == "github" or uri.startswith("github://"):
        storage_options.update(get_github_envs())
    if protocol is None and uri.startswith("https://github.com"):
        protocol = "github"
        storage_options.update(get_github_envs())
        github_kwargs = get_github_kwargs(uri)
        uri = github_kwargs.pop("path")
        storage_options.update(github_kwargs)
    storage_options.update(kwargs)
    fs, _, (path,) = get_fs_token_paths(
        uri, protocol=protocol, storage_options=storage_options
    )
    return fs, path


def get_path_by_fs_path(fs: AbstractFileSystem, path: str):
    """Restore full uri from fs and path

    Not ideal, but alternative to this is to save uri on MlemMeta level and pass it everywhere
    Another alternative is to support this on fsspec level, but we need to contribute it ourselves"""
    if isinstance(fs, GithubFileSystem):
        # here "rev" should be already url encoded
        return f"https://github.com/{fs.org}/{fs.repo}/tree/{fs.root}/{path}"
    protocol = fs.protocol
    if isinstance(protocol, (list, tuple)):
        if any(path.startswith(p) for p in protocol):
            return path
        protocol = protocol[0]
    if path.startswith(f"{protocol}://"):
        return path
    return f"{protocol}://{path}"


def path_split_postfix(path, postfix):
    return "/".join(path.split("/")[: -len(postfix.split("/"))])


def get_path_by_repo_path_rev(
    repo: str, path: str, rev: str = None
) -> Tuple[str, Dict[str, Any]]:
    """Construct uri from repo url, relative path in repo and optional revision.
    Also returns additional kwargs for fs"""
    if repo.startswith("https://github.com"):
        if rev is None:
            # https://github.com/org/repo/path
            return os.path.join(repo, path), {}
        # https://github.com/org/repo/tree/branch/path
        fs, root_path = get_fs(repo)
        assert isinstance(fs, GithubFileSystem)
        return (
            os.path.join(
                path_split_postfix(repo, root_path),
                "tree",
                rev,
                root_path,
                path,
            ),
            {},
        )
    # TODO: do something about git protocol
    return os.path.join(repo, path), {"rev": rev}


def read(uri: str, mode: str = "r"):
    """Read file content by given path"""
    fs, path = get_fs(uri)
    with fs.open(path, mode=mode) as f:
        return f.read()


def serialize(
    obj, as_class: Type = None
):  # pylint: disable=unused-argument # todo remove later
    if not isinstance(obj, MlemObject):
        raise ValueError(f"{type(obj)} is not a subclass of MlemObject")
    return obj.dict(exclude_unset=True, exclude_defaults=True, by_alias=True)


T = TypeVar("T")


def deserialize(obj, as_class: Type[T]) -> T:
    return parse_obj_as(as_class, obj)


def get_meta_path(uri: str, fs: AbstractFileSystem) -> str:
    """Augments given path so it will point to a MLEM metafile
    if it points to a folder with dumped object
    """
    if os.path.basename(uri) == META_FILE_NAME and fs.isfile(uri):
        # .../<META_FILE_NAME>
        return uri
    if fs.isdir(uri) and fs.isfile(os.path.join(uri, META_FILE_NAME)):
        # .../path and .../path/<META_FILE_NAME> exists
        return os.path.join(uri, META_FILE_NAME)
    if fs.isfile(uri + MLEM_EXT):
        # .../name without <MLEM_EXT>
        return uri + MLEM_EXT
    if MLEM_DIR in uri and fs.isfile(uri):
        # .../<MLEM_DIR>/.../file
        return uri
    if fs.exists(uri):
        raise Exception(
            f"{uri} is not a valid MLEM metafile or a folder with a MLEM model or dataset"
        )
    raise FileNotFoundError(uri)
