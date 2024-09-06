"""
https://gist.github.com/pkienzle/5e13ec07077d32985fa48ebe43486832

Get commit id from the git repo.

Drop the file rev.py into directory PACKAGE_PATH of your application. From
within that package you can then do::

    from . import rev

    rev.print_revision()  # print the repo version
    commit = rev.revision_info()  # return commit id

On "pip install" the repo root directory will not be available. In this
case the code looks for PACKAGE_NAME/git_revision, which you need to
install into site-pacakges along with your other sources.

The simplest way to create PACKAGE_NAME/git_revision is to run rev
from setup.py::

    import sys
    import os

    # Create the resource file git_revision.
    if os.system(f'"{sys.executable}" PACKAGE_NAME/rev.py') != 0:
        print("setup.py failed to build PACKAGE_NAME/git_revision", file=sys.stderr)
        sys.exit(1)

    ...

    # Include git revision in the package data, eitherj by adding
    # "include PACKAGE_NAME/git_revision" to MANIFEST.in, or by
    # adding the following to setup.py:
    #package_data = {"PACKAGE_NAME": ["git_revision"]}
    setup(
        ...
        #package_data=package_data,
        include_package_data=True,
        ...
    )

Add the following to .gitignore, substituting your package name::

    /PACKAGE_NAME/git_revision

"""

from pathlib import Path
from warnings import warn


def repo_path():
    """Return the root of the project git repo or None if not in a repo."""
    base = Path(__file__).absolute()
    for path in base.parents:
        if (path / ".git").exists():
            return path
    return None


def print_revision():
    """Print the git revision"""
    revision = revision_info()
    print("git revision", revision)


def store_revision():
    """
    Call from setup.py to save the git revision to the distribution.

    See :mod:`rev` for details.
    """
    commit = git_rev(repo_path())
    path = Path(__file__).absolute().parent / RESOURCE_NAME
    with path.open("w") as fd:
        fd.write(commit + "\n")


RESOURCE_NAME = "git_revision"
_REVISION_INFO = None  # cached value of git revision


def revision_info():
    """
    Get the git hash and mtime of the repository, or the installed files.
    """
    # TODO: test with "pip install -e ." for developer mode
    global _REVISION_INFO

    if _REVISION_INFO is None:
        _REVISION_INFO = git_rev(repo_path())

    if _REVISION_INFO is None:
        try:
            from importlib import resources
        except ImportError:  # CRUFT: pre-3.7 requires importlib_resources
            import importlib_resources as resources
        try:
            # Parse __name__ as "package.lib.rev" into "package.lib"
            package = __name__.rsplit(".", 1)[0]
            revdata = resources.read_text(package, RESOURCE_NAME)
            commit = revdata.strip()
            _REVISION_INFO = commit
        except Exception:
            _REVISION_INFO = "unknown"

    return _REVISION_INFO


def git_rev(repo):
    """
    Get the git revision for the repo in the path *repo*.

    Returns the commit id of the current head.

    Note: this function parses the files in the git repository directory
    without using the git application.  It may break if the structure of
    the git repository changes.  It only reads files, so it should not do
    any damage to the repository in the process.
    """
    # Based on stackoverflow am9417
    # https://stackoverflow.com/questions/14989858/get-the-current-git-hash-in-a-python-script/59950703#59950703
    if repo is None:
        return None

    git_root = Path(repo) / ".git"
    git_head = git_root / "HEAD"
    if not git_head.exists():
        return None

    # Read .git/HEAD file
    with git_head.open("r") as fd:
        head_ref = fd.read()

    # Find head file .git/HEAD (e.g. ref: ref/heads/master => .git/ref/heads/master)
    if not head_ref.startswith("ref: "):
        return head_ref
    head_ref = head_ref[5:].strip()

    # Read commit id from head file
    head_path = git_root.joinpath(*head_ref.split("/"))
    if not head_path.exists():
        warn(f"path {head_path} referenced from {git_head} does not exist")
        return None

    with head_path.open("r") as fd:
        commit = fd.read().strip()

    return commit


def main():
    """
    When run as a python script create git_revision in the current directory.
    """
    print_revision()
    store_revision()


if __name__ == "__main__":
    main()
