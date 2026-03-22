from setuptools import setup, find_packages

with open("requirements.txt") as f:
    install_requires = [l.strip() for l in f if l.strip() and not l.startswith("#")]

setup(
    name="dagaarsoft_hospitality",
    version="5.0.0",
    description="Enterprise Hotel & Hospitality Management for ERPNext v14/v15/v16",
    author="DagaarSoft",
    author_email="support@dagaarsoft.com",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=install_requires,
)
