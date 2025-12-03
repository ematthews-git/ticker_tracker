from setuptools import setup, find_packages

setup(
    name="ticker-tracker",
    version="0.1.0",
    description="Reddit ticker mention tracker and analyzer",
    author="Your Name",
    author_email="your.email@example.com",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.8",
    install_requires=[
        "praw>=7.7.0",
        "python-dotenv>=1.0.0",
        "schedule>=1.2.0",
        "psycopg2-binary>=2.9.0",
        "pandas>=2.3.3",
        "vaderSentiment>=3.3.2",
        "matplotlib>=3.5.0",
        "numpy>=1.21.0",
    ],
    entry_points={
        "console_scripts": [
            "ticker-tracker=app:main",
            "ticker-statistics=statistics_collector:main",
        ],
    },
)

