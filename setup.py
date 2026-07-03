import os

from setuptools import find_packages, setup


def get_version():
    version_file = os.path.join(
        os.path.dirname(__file__), "openedx_certifyme", "__init__.py"
    )
    with open(version_file, encoding="utf-8") as f:
        for line in f:
            if line.startswith("__version__"):
                return line.split("=")[1].strip().strip('"').strip("'")
    raise RuntimeError("Unable to find __version__ in openedx_certifyme/__init__.py")


setup(
    name="openedx-certifyme",
    version=get_version(),
    description="CertifyMe certificate issuance plugin for Open edX",
    long_description=open(  # noqa: SIM115
        os.path.join(os.path.dirname(__file__), "README.md"), encoding="utf-8"
    ).read(),
    long_description_content_type="text/markdown",
    author="CertifyMe",
    license="Apache-2.0",
    python_requires=">=3.8",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Framework :: Django",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3",
        "Topic :: Education",
    ],
    packages=find_packages(
        include=["openedx_certifyme", "openedx_certifyme.*"],
    ),
    include_package_data=True,
    install_requires=[
        "requests>=2.28",
        "django-config-models>=2.4",
        "edx-opaque-keys>=2.5",
        "celery>=5.2",
        "openedx-events>=9.0",
    ],
    entry_points={
        "lms.djangoapp": [
            "openedx_certifyme = openedx_certifyme.apps:CertifyMeConfig",
        ],
        "cms.djangoapp": [
            "openedx_certifyme = openedx_certifyme.apps:CertifyMeConfig",
        ],
    },
    zip_safe=False,
)