from openfermion import QubitOperator, FermionOperator
from openfermion.transforms import jordan_wigner

from src.utils import QasmUtils, MatrixUtils

import itertools
import numpy

# We implement two different types of ansatz states
# Type "excitation_list" consists of a list of exponent Pauli terms representing single step Trotter excitations
# Type "qasm_list" consists of custom circuit elements represented explicitly by qasm instructions


class AnsatzElement:
    def __init__(self, element_type, element, n_qubits, excitation_order=None, n_var_parameters=1):
        self.element_type = element_type  # excitation or not
        self.n_qubits = n_qubits
        self.element = element

        # create a dictionary to keep count on the number of gates for each qubit
        self.gate_counter = {}
        for i in range(n_qubits):
            self.gate_counter['q{}'.format(i)] = {'cx': 0, 'u1': 0}

        if (self.element_type == 'excitation') and (excitation_order is None):
            assert type(self.element) == QubitOperator
            assert n_var_parameters == 1
            self.excitation_order = self.get_excitation_order()
        else:
            self.excitation_order = excitation_order

        self.n_var_parameters = n_var_parameters

    def get_qasm(self, var_parameters):
        if self.element_type == 'excitation':
            assert len(var_parameters) == 1
            var_parameter = var_parameters[0]
            return self.get_excitation_qasm(self.element, var_parameter)
        else:
            return self.element.format(*[var_parameters])

    def get_excitation_order(self):
        terms = list(self.element)
        n_terms = len(terms)
        return max([len(terms[i]) for i in range(n_terms)])

    # get the qasm circuit of an excitation
    def get_excitation_qasm(self, excitation, var_parameter):
        qasm = ['']
        for exponent_term in excitation.terms:
            exponent_angle = var_parameter * excitation.terms[exponent_term]
            assert exponent_angle.real == 0
            exponent_angle = exponent_angle.imag
            qasm.append(QasmUtils.get_exponent_qasm(exponent_term, exponent_angle, self.gate_counter))

        return ''.join(qasm)


# TODO change to static classes and methods?
class UCCSD:
    def __init__(self, n_orbitals, n_electrons):
        self.n_orbitals = n_orbitals
        self.n_electrons = n_electrons

    def get_single_excitation_list(self):
        single_excitations = []
        for i in range(self.n_electrons):
            for j in range(self.n_electrons, self.n_orbitals):
                excitation = jordan_wigner(FermionOperator('[{1}^ {0}] - [{0}^ {1}]'.format(j, i)))
                single_excitations.append(AnsatzElement('excitation', excitation, self.n_orbitals, excitation_order=1))
        # returns list of QubitOperators
        return single_excitations

    def get_double_excitation_list(self):
        double_excitations = []
        for i in range(self.n_electrons-1):
            for j in range(i+1, self.n_electrons):
                for k in range(self.n_electrons, self.n_orbitals-1):
                    for l in range(k+1, self.n_orbitals):
                        excitation = jordan_wigner(FermionOperator('[{2}^ {3}^ {0} {1}] - [{0}^ {1}^ {2} {3}]'
                                                                   .format(i, j, k, l)))
                        double_excitations.append(AnsatzElement('excitation', excitation, self.n_orbitals,
                                                                excitation_order=2))
        return double_excitations

    def get_ansatz_elements(self):
        return self.get_single_excitation_list() + self.get_double_excitation_list()


class UCCGSD:
    def __init__(self, n_orbitals, n_electrons):
        self.n_orbitals = n_orbitals
        self.n_electrons = n_electrons

    def get_single_excitation_list(self):
        single_excitations = []
        for indices in itertools.combinations(range(self.n_orbitals), 2):
            excitation = jordan_wigner(FermionOperator('[{1}^ {0}] - [{0}^ {1}]'.format(* indices)))
            single_excitations.append(AnsatzElement('excitation', excitation, self.n_orbitals, excitation_order=1))

        return single_excitations

    def get_double_excitation_list(self):
        double_excitations = []
        for indices in itertools.combinations(range(self.n_orbitals), 4):
            excitation = jordan_wigner(FermionOperator('[{1}^ {0}] - [{0}^ {1}]'.format(* indices)))
            double_excitations.append(AnsatzElement('excitation', excitation, self.n_orbitals, excitation_order=2))

        return double_excitations

    def get_ansatz_elements(self):
        return self.get_single_excitation_list() + self.get_double_excitation_list()


# this is ugly ansatz
# TODO
class FixedAnsatz1:
    def __init__(self, n_orbitals, n_electrons):
        self.n_orbitals = n_orbitals
        self.n_electrons = n_electrons
        self.ansatz_type = 'qasm_list'

    def get_single_block(self, index):
        qasm = ['']
        # apply single qubit general rotations to each qubit
        for qubit in range(self.n_orbitals):
            qasm.append('rx({{}}) q[{}];\n'.format(qubit))  # we want to leave first {} empty for var_parameter later
            qasm.append('ry({{}}) q[{}];\n'.format(qubit))

        # used_qubits = numpy.zeros(self.n_orbitals)

        for qubit in range(1, self.n_orbitals):

            qasm.append('cx q[{}], q[{}];\n'.format(qubit - 1, qubit))

            # used_qubits[qubit] = 1
            # used_qubits[next_qubit] = 1

        return ''.join(qasm)

    def get_ansatz_elements(self):
        # return block
        qasm_list = [self.get_single_block(index) for index in range(1, self.n_orbitals)]
        qasm = ''.join(qasm_list)
        return AnsatzElement('qasm', qasm, self.n_orbitals, n_var_parameters=2*self.n_orbitals*(self.n_orbitals-1))

