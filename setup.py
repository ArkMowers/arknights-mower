import os
from email.parser import Parser
from pathlib import Path

import setuptools

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)

LONG_DESC = (ROOT / "README.md").read_text(encoding="utf-8")
REQUIREMENTS = [
    line.strip()
    for line in (ROOT / "requirements.in").read_text(encoding="utf-8-sig").splitlines()
    if line.strip() and not line.lstrip().startswith("#")
]
PKG_INFO = ROOT / "PKG-INFO"
if PKG_INFO.is_file():
    VERSION = Parser().parsestr(PKG_INFO.read_text(encoding="utf-8"))["Version"]
else:
    import arknights_mower

    VERSION = arknights_mower.__version__
setuptools.setup(
    name="arknights_mower",
    version=VERSION,
    author="Konano",
    author_email="w@nano.ac",
    description="Arknights Helper based on ADB and Python",
    long_description=LONG_DESC,
    long_description_content_type="text/markdown",
    url="https://github.com/Konano/arknights-mower",
    packages=setuptools.find_packages(),
    install_requires=REQUIREMENTS,
    python_requires=">=3.12,<3.13",
    include_package_data=True,
    entry_points={"console_scripts": ["arknights-mower=arknights_mower.__main__:main"]},
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Programming Language :: Python :: 3.12",
        "Topic :: Games/Entertainment",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)
