"""Separate the DWARF in a freshly collected Linux PyInstaller bundle."""

import argparse
import hashlib
import re
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path


def _elf_identity(path: Path) -> str:
    with path.open("rb") as source:
        return "ELF SHA-256 " + hashlib.file_digest(source, "sha256").hexdigest()


def _keep_matching_symbols(previous, output, binaries):
    if not previous.exists():
        return
    with tarfile.open(previous, "r|gz") as old:
        for member in old:
            binary = binaries.get(member.name)
            if (
                binary
                and member.isfile()
                and member.pax_headers.get("comment") == _elf_identity(binary)
            ):
                with old.extractfile(member) as symbol_data:
                    output.addfile(member, symbol_data)


def _elf_files(internal):
    for binary in sorted(internal.rglob("*")):
        if binary.is_symlink() or not binary.is_file():
            continue
        with binary.open("rb") as source:
            if source.read(4) == b"\x7fELF":
                yield binary


def split_linux_debug_symbols(bundle: Path):
    bundle = bundle.resolve(strict=True)
    internal = bundle / "_internal"
    if not internal.is_dir():
        raise ValueError(f"Missing PyInstaller contents directory: {internal}")

    # The two launchers outside _internal carry appended PyInstaller archives.
    # objcopy only writes ELF sections and would discard those archives.
    with tempfile.TemporaryDirectory(dir=bundle.parent) as staging:
        work = Path(staging)
        archive = work / f"{bundle.name}-linux-debug.tar.gz"
        destination = bundle.parent / archive.name
        replacements = []
        unchanged = {}
        with tarfile.open(archive, "w:gz", compresslevel=6) as symbols:
            for binary in _elf_files(internal):
                relative = binary.relative_to(bundle.parent)
                symbol_name = relative.parent / ".debug" / (binary.name + ".debug")
                sections = subprocess.check_output(["readelf", "-SW", binary])
                if not re.search(rb"\]\s+\.z?debug_info\s", sections):
                    unchanged[symbol_name.as_posix()] = binary
                    continue

                debug = work / symbol_name
                debug.parent.mkdir(parents=True, exist_ok=True)
                subprocess.run(
                    ["objcopy", "--only-keep-debug", binary, debug], check=True
                )
                stripped = work / relative
                subprocess.run(
                    [
                        "objcopy",
                        "--strip-debug",
                        "--remove-section=.gnu_debuglink",
                        f"--add-gnu-debuglink={debug}",
                        binary,
                        stripped,
                    ],
                    check=True,
                )
                shutil.copymode(binary, stripped)
                member = symbols.gettarinfo(debug, arcname=symbol_name.as_posix())
                # A retry can retain symbols only for the exact stripped ELF.
                member.pax_headers["comment"] = _elf_identity(stripped)
                with debug.open("rb") as symbol_data:
                    symbols.addfile(member, symbol_data)
                replacements.append((stripped, binary))
            _keep_matching_symbols(destination, symbols, unchanged)

        archive.replace(destination)
        for stripped, binary in replacements:
            stripped.replace(binary)
        print(f"Separated Linux debug symbols from {len(replacements)} ELF files")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path, help="fresh PyInstaller COLLECT directory")
    split_linux_debug_symbols(parser.parse_args().bundle)
