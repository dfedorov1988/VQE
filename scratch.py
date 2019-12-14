from openfermion.hamiltonians import MolecularData
from openfermionpsi4 import run_psi4
from openfermion.transforms import get_fermion_operator, jordan_wigner, get_sparse_operator
from scipy.linalg import eigh
from openfermion.utils import jw_hartree_fock_state


if __name__ == "__main__":

    from src.Molecules import H2

    # choose basis for the molecular orbitals
    basis = 'sto-3g'

    molecule =H2

    h2_molecule = MolecularData(molecule.geometry(0.74), basis, molecule.multiplicity, molecule.charge)

    h2_molecule_psi4 = run_psi4(h2_molecule, run_mp2=False, run_cisd=False, run_ccsd=False, run_fci=False)

    # TODO: combine the above 3 rows into a single expression
    molecular_ham = h2_molecule_psi4.get_molecular_hamiltonian()
    fermion_ham = get_fermion_operator(molecular_ham)
    jw_ham = jordan_wigner(fermion_ham)

    jw_ham_matrix = get_sparse_operator(jw_ham).todense()
    eigenvalues, eigenvectors = eigh(jw_ham_matrix)

    assert len(jw_ham_matrix) == 2**h2_molecule_psi4.n_qubits

    print(eigenvalues)

    print(eigenvectors)

    # TODO: how too implemented trotter steps (exponential)?

    print('Pizza')
