"""Output writes protect input aliases and stage each complete file before replacement."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from .models import InputError


def same_path(first: Path, second: Path) -> bool:
    try:
        if first.resolve() == second.resolve():
            return True
        return first.exists() and second.exists() and first.samefile(second)
    except RuntimeError as exc:
        raise InputError('Cannot resolve an input/output path because it contains a symlink loop.') from exc


def validate_outputs(paths: list[Path], protected: list[Path], force: bool) -> None:
    for index, path in enumerate(paths):
        if any(same_path(path, item) for item in protected):
            raise InputError('An output path aliases an input or rerun configuration; refusing to overwrite it.')
        if any(same_path(path, item) for item in paths[:index]):
            raise InputError('Output paths must be different files.')
        if path.exists() and (not force or not path.is_file()):
            raise InputError(f'Output already exists: {path}. Choose another path or use --force.')
        if not path.parent.is_dir():
            raise InputError(f'Output directory does not exist: {path.parent}')


def write_outputs(files: list[tuple[Path, str]], protected: list[Path], force: bool) -> None:
    validate_outputs([path for path, _ in files], protected, force)
    staged: list[tuple[Path, Path]] = []
    try:
        for destination, content in files:
            fd, name = tempfile.mkstemp(prefix='.joinwitness-', dir=destination.parent)
            temporary = Path(name)
            staged.append((temporary, destination))
            with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        # Check again after analysis/staging. Concurrent hostile path replacement is out of scope.
        validate_outputs([path for path, _ in files], protected, force)
        for temporary, destination in staged:
            if force:
                os.replace(temporary, destination)
            else:
                # Same-directory hard-link publication is atomic and cannot clobber an
                # output created by another process after the existence checks.
                os.link(temporary, destination)
                temporary.unlink()
    finally:
        for temporary, _ in staged:
            temporary.unlink(missing_ok=True)
