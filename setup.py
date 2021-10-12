import setuptools
import arknights_mower

LONG_DESC = open('README.md', 'r').read()
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
    install_requires=['colorlog', 'opencv_python', 'matplotlib', 'numpy',
                      'scikit_image', 'scikit_learn', 'onnxruntime', 'pyclipper', 'shapely', 'tornado'],
    include_package_data=True,
    entry_points={'console_scripts': [
        'arknights-mower=arknights_mower.__main__:main']},
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Programming Language :: Python :: 3 :: Only',
        'Topic :: Games/Entertainment',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
)
