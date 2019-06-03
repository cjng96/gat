from setuptools import setup, find_packages

longdesc = """
Restart automatically when modified and deployment for golang.
Required packages:
    paramiko, watchdog, PyYAML
"""

setup(
    name             = 'god-tool',
    version          = '0.1',
    description      = 'Restart automatically when modified and deployment for golang.',
	long_description = open('README.md').read(),
    author           = 'Felix Choi',
    author_email     = 'cjng96@gmail.com',
    url              = 'https://github.com/cjng96/god',
    license          = "LGPL",
    #download_url     = 'https://github.com/cjng96/god/archive/0.1.tar.gz',
    install_requires = ["paramiko", "watchdog", "PyYAML"],
    packages         = find_packages(exclude = ['docs', 'tests*']),
    keywords         = ['auto restart', 'deployment'],
    python_requires  = '>=3',
    platforms        = "Posix; MacOS X; Windows",
	zip_safe=False,
    classifiers      = [
        "Operating System :: OS Independent",		
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.2',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
    ]
)