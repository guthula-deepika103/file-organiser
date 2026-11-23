from setuptools import setup, find_packages

setup(
    name="file_organizer_assistant",
    version="1.2.0",
    description="Production-grade desktop file organizer with preview mode, persistence, and analytics.",
    author="SmartCommunity Hack Team",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.8",
    entry_points={
        "console_scripts": [
            "file-organizer=file_organizer.cli:main",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)
