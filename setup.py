from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name='ratelink',
    version='0.1.0',
    packages=find_packages(),
    python_requires='>=3.7',
    install_requires=[],
    author='Vladlen-codes',
    author_email='your.email@example.com',  # Update with your email
    description='A flexible rate limiting library with multiple algorithms',
    long_description=long_description,
    long_description_content_type="text/markdown",
    url='https://github.com/Vladlen-codes/ratelink',  # Update with your repo URL
    project_urls={
        'Bug Tracker': 'https://github.com/Vladlen-codes/ratelink/issues',
        'Documentation': 'https://github.com/Vladlen-codes/ratelink#readme',
        'Source Code': 'https://github.com/Vladlen-codes/ratelink',
    },
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Topic :: Software Development :: Libraries',
        'Topic :: System :: Networking',
    ],
    keywords='rate-limiting, rate-limiter, token-bucket, leaky-bucket, sliding-window, gcra, throttling',
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "pytest-asyncio>=0.21.0",
            "pytest-cov>=4.1.0",
            "black>=23.0.0",
            "flake8>=6.0.0",
            "mypy>=1.4.0",
            "pre-commit>=3.3.0",
        ],
    },
)