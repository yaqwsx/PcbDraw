# -*- coding: utf-8 -*-

import setuptools
import versioneer

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="PcbDraw",
    version=versioneer.get_version(),
    cmdclass=versioneer.get_cmdclass(),
    python_requires=">=3.7",
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
        "mistune>=2.0.2",
        "pybars3",
        "pyyaml",
        "svgpathtools==1.4.1",
        "pcbnewTransition>=0.2",
        "LnkParse3; platform_system=='Windows'",
        "pyVirtualDisplay~=3.0; platform_system!='Windows'",
        "Pillow~=9.0",
        "click>=7.1"
    ],
    setup_requires=[
        "versioneer"
    ],
    extras_require={
        "dev": ["pytest", "types-pillow", "types-click", "types-PyYAML"],
    },
    zip_safe=False,
    include_package_data=True,
    entry_points = {
        "console_scripts": [
            "pcbdraw=pcbdraw.ui:run"
        ],
    }
)
