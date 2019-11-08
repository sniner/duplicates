from setuptools import setup, find_packages

setup(
    # Metadata
    name = "duplicates",
    version = "0.1.0",
    author = "Stefan Schönberger",
    author_email = "me@s5s9r.de",
    description = "Find identical files in subdirectories",
    long_description = open("README.md", "r").read(),
    long_description_content_type = "text/markdown",
    url = "https://github.com/sniner/duplicates",

    # Packages
    packages = find_packages(),

    # Dependencies
    install_requires = [
    ],
    extras_require = {
        'dev': [
        ],
    },

    # Services
    entry_points = {
        'console_scripts': [
            'duplicates = duplicates.__main__:main',
        ]
    },

    # Packaging information
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: BSD License",
        "Operating System :: POSIX",
    ],
    platforms = 'any',
    python_requires='>=3.6',
)

# vim: set et sw=4 ts=4:
