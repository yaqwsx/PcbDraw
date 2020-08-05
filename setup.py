# -*- coding: utf-8 -*-

import setuptools
import versioneer

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="PcbDraw",
    version=versioneer.get_version(),
    cmdclass=versioneer.get_cmdclass(),
    author="Jan Mrázek",
    author_email="email@honzamrazek.cz",
    description="Utility to produce nice looking drawings of KiCAD boards",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yaqwsx/PcbDraw",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    install_requires=[
        "numpy",
        "lxml",
        "mistune",
        "pybars3",
        "wand",
        "pyyaml"
    ],
    setup_requires=[
        "versioneer"
    ],
    zip_safe=False,
    include_package_data=True,
    entry_points = {
        "console_scripts": [
            "pcbdraw=pcbdraw.pcbdraw:main",
            "populate=pcbdraw.populate:main"
        ],
    }
)