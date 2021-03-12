from setuptools import setup, find_packages
setup(
    name="VQE",
    version="0.1",
    packages=['src', 'src/molecules'],
    #scripts=['scripts/dissociation_curves.py','scripts/iter_vqe/iqeb_vqe.py'],
    author='Jordan',
    author_email='jordanovsj@gmail.com',
    install_requires=['ray', 'openfermion', 'openfermionpsi4', 'numpy', 'scipy', 'qiskit']
)
