import setuptools
import arknights_mower
from pathlib import Path

LONG_DESC = Path('README.md').read_text('utf8')
VERSION = arknights_mower.__version__

setuptools.setup(
    name='arknights_mower',
    version=VERSION,
    author='Konano',
    author_email='w@nano.ac',
    description='Arknights Helper based on ADB and Python',
    long_description=LONG_DESC,
    long_description_content_type='text/markdown',
    url='https://github.com/Konano/arknights-mower',
    packages=setuptools.find_packages(),
    install_requires=[
        'colorlog', 'opencv_python', 'matplotlib', 'numpy', 'scikit_image==0.18.3', 'scikit_learn>=1',
        'onnxruntime', 'pyclipper', 'shapely', 'tornado', 'requests', 'ruamel.yaml', 'schedule'
    ],
    include_package_data=True,
    entry_points={'console_scripts': [
        'arknights-mower=arknights_mower.__main__:main'
    ]},
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Topic :: Games/Entertainment',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
)
