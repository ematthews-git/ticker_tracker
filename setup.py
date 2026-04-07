from setuptools import setup, find_packages
from setuptools.command.install import install
import os
import shutil

# Find all packages in src/
packages = find_packages(where="src")

setup(
    name="ticker-tracker",
    version="0.1.0",
    description="Reddit ticker mention tracker and analyzer",
    author="Ethan Matthews",
    author_email="matthewsethan43@gmail.com",
    packages=packages,
    package_dir={"": "src"},
    include_package_data=True,
    package_data={
        "": ["valid_tickers.json"],
    },
    python_requires=">=3.8",
    install_requires=[
        "praw>=7.7.0",
        "python-dotenv>=1.0.0",
        "schedule>=1.2.0",
        "psycopg2-binary>=2.9.0",
        "pandas>=2.3.3",
        "vaderSentiment>=3.3.2",
        "yfinance>=0.2.0",
        "matplotlib>=3.5.0",
        "numpy>=1.21.0",
    ],
    entry_points={
        "console_scripts": [
            "ticker-tracker=app:main",
            "ticker-statistics=statistics_collector:main",
            "ticker-prices=market.price_fetcher:main",
            "ticker-visualiser=user_interaction.console_runner:main",
        ],
    },
)
