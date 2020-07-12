from setuptools import setup


__author__ = 'taengstagram'
__email__ = 'taengstagram@gmail.com'
__version__ = '0.3.8'

_api_version = '1.6.0'
_api_extensions_version = '0.3.9'

long_description = '''
``livestream_dl`` is a Python console script that downloads an Instagram Live stream.
It only downloads a stream that is currently ongoing, and cannot capture any part of a stream that has already passed.
'''

setup(
    name='instagram-livestream-downloader',
    version=__version__,
    author=__author__,
    author_email=__email__,
    license='MIT',
    url='https://github.com/taengstagram/instagram-livestream-downloader/',
    packages=['livestream_dl'],
    entry_points={
        'console_scripts': [
            'livestream_dl = livestream_dl.__main__:main',
            'livestream_as = livestream_dl.assemble:main [AS]',
        ]
    },
    install_requires=[
        'instagram_private_api==%(api)s' % {'api': _api_version},
        'instagram_private_api_extensions==%(ext)s' % {'ext': _api_extensions_version}
    ],
    dependency_links=[
        'https://github.com/ping/instagram_private_api/archive/%(api)s.tar.gz'
        '#egg=instagram_private_api-%(api)s' % {'api': _api_version},
        'https://github.com/ping/instagram_private_api_extensions/archive/%(ext)s.tar.gz'
        '#egg=instagram_private_api_extensions-%(ext)s' % {'ext': _api_extensions_version}
    ],
    extras_require={
        'AS': ['moviepy>=0.2.3.2'],
    },
    include_package_data=True,
    platforms='any',
    long_description=long_description,
    keywords='instagram livestream downloader',
    description='A downloader console script for Instagram Live streams.',
    classifiers=[
        'Development Status :: 4 - Beta',
        'License :: OSI Approved :: MIT License',
        'Environment :: Console',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
    ]
)
