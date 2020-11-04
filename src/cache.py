from src.backends import QiskitSim
from src import config

from openfermion import get_sparse_operator

import scipy
import ray
import numpy
import logging
import time


class Cache:
    def __init__(self, H_sparse_matrix, n_qubits, n_electrons, exc_gen_sparse_matrices_dict=None,
                 commutators_sparse_matrices_dict=None, sparse_statevector=None, init_sparse_statevector=None,
                 sqr_exc_gen_sparse_matrices_dict=None):
        self.n_qubits = n_qubits
        self.n_electrons = n_electrons

        self.H_sparse_matrix = H_sparse_matrix  # used in: normal vqe run/ single var. parameter vqe
        self.exc_gen_sparse_matrices_dict = exc_gen_sparse_matrices_dict  # used in:  single var. parameter vqe
        self.sqr_exc_gen_sparse_matrices_dict = sqr_exc_gen_sparse_matrices_dict
        self.commutators_sparse_matrices_dict = commutators_sparse_matrices_dict  # used in: single var. parameter vqe/ excitation gradient calculations
        self.init_sparse_statevector = init_sparse_statevector  # used in: single var. parameter vqe

        self.sparse_statevector = sparse_statevector  # used in: normal vqe run/ excitation gradient calculations
        self.var_parameters = None  # used in: normal vqe run/ single var. parameter vqe
        # NOT TO BE CONFUSED WITH EXCITATION GENERATORS. Excitation = exp(Excitation Generator)
        self.excitations_sparse_matrices_dict = {}  # used in update_statevectors/ calculating ansatz_gradient

        self.identity = scipy.sparse.identity(2 ** self.n_qubits)  # the 2^n x 26n identity matrix

    # using this function, double evaluation of the excitation matrices, to update the statevector and the
    # ansatz gradient is avoided
    def get_excitation_sparse_matrices(self, excitation, parameter):
        excitation_generators = excitation.excitation_generators
        key = str(excitation_generators)
        # if the element exists and the parameter is the same, return the excitation matrix
        if key in self.excitations_sparse_matrices_dict:
            parameter_matrix = self.excitations_sparse_matrices_dict[key]
            previous_parameter = parameter_matrix['parameter']
            if previous_parameter == parameter:
                # this can be a list of one or two elements depending on if its a spin-complement pair
                return self.excitations_sparse_matrices_dict[key]['matrix']

        # update the excitations_sparse_matrices_dict
        exc_gen_matrix_form = self.exc_gen_sparse_matrices_dict[key]
        sqr_exc_gen_matrix_form = self.sqr_exc_gen_sparse_matrices_dict[key]
        excitation_matrices = []
        for i in range(len(exc_gen_matrix_form)):
            term1 = numpy.sin(parameter) * exc_gen_matrix_form[i]
            term2 = (1 - numpy.cos(parameter)) * sqr_exc_gen_matrix_form[i]
            excitation_matrices.append(self.identity + term1 + term2)

        parameter_matrix = {'parameter': parameter, 'matrix': excitation_matrices}
        self.excitations_sparse_matrices_dict[key] = parameter_matrix
        return excitation_matrices

    def hf_statevector(self):
        statevector = numpy.zeros(2 ** self.n_qubits)
        # MAGIC
        hf_term = 0
        for i in range(self.n_electrons):
            hf_term += 2 ** (self.n_qubits - 1 - i)
        statevector[hf_term] = 1
        return statevector

    def update_statevector(self, ansatz, var_parameters, init_state_qasm=None):
        # TODO add single parameter functionnality with init_statevector
        assert len(var_parameters) == len(ansatz)
        if self.var_parameters is not None and var_parameters == self.var_parameters:  # this condition is not neccessarily sufficient
            assert self.sparse_statevector is not None
        else:

            statevector = self.hf_statevector()
            sparse_statevector = scipy.sparse.csr_matrix(statevector).transpose().conj()

            for i, excitation in enumerate(ansatz):
                parameter = var_parameters[i]
                excitation_matrices = self.get_excitation_sparse_matrices(excitation, parameter)
                excitation_matrix = self.identity
                for term in excitation_matrices:
                    excitation_matrix *= term

                sparse_statevector = excitation_matrix.dot(sparse_statevector)

            self.sparse_statevector = sparse_statevector.transpose().conj()
        ############################################
            # # if just a single ansatz element is supplied, just add its matrix to the initial statevector
            # if self.init_sparse_statevector is not None and len(ansatz) == 1:
            #     key = str(ansatz[0].excitation_generators)
            #     exc_gen_matrix = self.exc_gen_sparse_matrices_list[key]
            #     self.sparse_statevector =\
            #         scipy.sparse.linalg.expm_multiply(var_parameters[0] * exc_gen_matrix,
            #                                           self.init_sparse_statevector.transpose().conj()).transpose().conj()
            # else:
            #     self.var_parameters = var_parameters
            #     statevector = backend.statevector_from_ansatz(ansatz, var_parameters, self.n_qubits, self.n_electrons,
            #                                                   init_state_qasm=init_state_qasm)
            #     self.sparse_statevector = scipy.sparse.csr_matrix(statevector)
        # # print(self.sparse_statevector.todense())

        print(self.sparse_statevector.dot(self.sparse_statevector.transpose().conj()).todense())

        return self.sparse_statevector

    def get_exc_gen_matrix_form(self, excitation):
        key = str(excitation.excitation_generators)
        return self.exc_gen_sparse_matrices_dict[key]

    def get_sqr_exc_gen_matrix_form(self, excitation):
        key = str(excitation.excitation_generators)
        return self.sqr_exc_gen_sparse_matrices_dict[key]

    def get_commutator_sparse_matrix(self, excitation):
        key = str(excitation.excitation_generators)
        return self.commutators_sparse_matrices_dict[key]


class GlobalCache(Cache):
    def __init__(self, q_system, excited_state=0, backend=QiskitSim):
        self.q_system = q_system

        H_sparse_matrix = get_sparse_operator(q_system.jw_qubit_ham)
        if excited_state > 0:
            H_sparse_matrix = backend. ham_sparse_matrix(q_system, excited_state=excited_state)
            if H_sparse_matrix.data.nbytes > config.matrix_size_threshold:
                # decrease the size of the matrix. Typically it will have a lot of insignificant very small (~1e-19)
                # elements that do not contribute to the accuracy but inflate the size of the matrix (~200 MB for Lih)
                H_sparse_matrix = scipy.sparse.csr_matrix(H_sparse_matrix.todense().round(config.floating_point_accuracy_digits))

        super(GlobalCache, self).__init__(H_sparse_matrix=H_sparse_matrix, n_qubits=q_system.n_qubits,
                                          n_electrons=q_system.n_electrons, commutators_sparse_matrices_dict=None)

    def get_grad_thread_cache(self, ansatz_element, sparse_statevector):
        # TODO check if copy is necessary
        key = str(ansatz_element.excitation_generators)
        commutator_sparse_matrix = self.commutators_sparse_matrices_dict[key].copy()
        thread_cache = ThreadCache(commutators_sparse_matrices_dict={key: commutator_sparse_matrix},
                                   sparse_statevector=sparse_statevector.copy(), n_qubits=self.q_system.n_qubits,
                                   n_electrons=self.q_system.n_electrons)
        return thread_cache

    def get_vqe_thread_cache(self):
        # TODO check if copy is necessary
        thread_cache = ThreadCache(H_sparse_matrix=self.H_sparse_matrix.copy(),
                                   exc_gen_sparse_matrices_dict=self.get_exc_gen_sparse_matrices_list_copy(),
                                   sqr_exc_gen_sparse_matrices_dict=self.get_sqr_exc_gen_sparse_matrices_list_copy(),
                                   n_qubits=self.q_system.n_qubits, n_electrons=self.q_system.n_electrons)
        return thread_cache

    def single_par_vqe_thread_cache(self, ansatz_element, init_sparse_statevector):
        # TODO check if copy is necessary
        key = str(ansatz_element.excitation_generators)
        exc_gen_matrix_form = self.exc_gen_sparse_matrices_dict[key].copy()
        exc_gen_matrix_form_copy = self.get_sparse_matrices_list_copy(exc_gen_matrix_form)
        sqr_exc_gen_matrix_form = self.sqr_exc_gen_sparse_matrices_dict[key].copy()
        sqr_exc_gen_matrix_form_copy = self.get_sparse_matrices_list_copy(sqr_exc_gen_matrix_form)

        commutator_matrix = self.commutators_sparse_matrices_dict[key].copy()
        thread_cache = ThreadCache(H_sparse_matrix=self.H_sparse_matrix.copy(),
                                   commutators_sparse_matrices_dict={key: commutator_matrix},
                                   init_sparse_statevector=init_sparse_statevector.copy(),
                                   n_qubits=self.q_system.n_qubits, n_electrons=self.q_system.n_electrons,
                                   exc_gen_sparse_matrices_dict={key: exc_gen_matrix_form_copy},
                                   sqr_exc_gen_sparse_matrices_dict={key: sqr_exc_gen_matrix_form_copy}
                                   )
        return thread_cache

    def get_exc_gen_sparse_matrices_list_copy(self):
        exc_gen_matrices_list_copy = {}
        for exc_gen in self.exc_gen_sparse_matrices_dict.keys():
            exc_gen_matrix_form = self.exc_gen_sparse_matrices_dict[str(exc_gen)]
            assert len(exc_gen_matrix_form) == 1 or len(exc_gen_matrix_form) == 2
            exc_gen_matrices_list_copy[str(exc_gen)] = self.get_sparse_matrices_list_copy(exc_gen_matrix_form)
        return exc_gen_matrices_list_copy

    def get_sqr_exc_gen_sparse_matrices_list_copy(self):
        sqr_exc_gen_matrices_list_copy = {}
        for exc_gen in self.sqr_exc_gen_sparse_matrices_dict.keys():
            sqr_exc_gen_matrix_form = self.sqr_exc_gen_sparse_matrices_dict[str(exc_gen)]
            assert len(sqr_exc_gen_matrix_form) == 1 or len(sqr_exc_gen_matrix_form) == 2
            sqr_exc_gen_matrices_list_copy[str(exc_gen)] = self.get_sparse_matrices_list_copy(sqr_exc_gen_matrix_form)
        return sqr_exc_gen_matrices_list_copy

    @staticmethod
    def get_sparse_matrices_list_copy(sparse_matrices):
        sparse_matrices_copy = []
        for term in sparse_matrices:
            sparse_matrices_copy.append(term.copy())

        return sparse_matrices_copy

    def calculate_exc_gen_sparse_matrices_list(self, ansatz_elements):
        logging.info('Calculating excitation generators')
        exc_gen_sparse_matrices_dict = {}
        sqr_exc_gen_sparse_matrices_dict = {}
        if config.multithread:
            ray.init(num_cpus=config.ray_options['n_cpus'])
            elements_ray_ids = [
                [
                    element, GlobalCache.get_exc_generator_matrix_multithread.remote(element, n_qubits=self.q_system.n_qubits)
                ]
                for element in ansatz_elements
            ]
            for element_ray_id in elements_ray_ids:
                key = str(element_ray_id[0].excitation_generators)
                exc_gen_sparse_matrices_dict[key] = ray.get(element_ray_id[1])[0]
                sqr_exc_gen_sparse_matrices_dict[key] = ray.get(element_ray_id[1])[1]

            del elements_ray_ids
            ray.shutdown()
        else:
            for i, element in enumerate(ansatz_elements):
                excitation_generators = element.excitation_generators
                key = str(excitation_generators)
                logging.info('Calculated excitation generator matrix {}'.format(key))
                exc_gen_matrix_form = []
                sqr_exc_gen_matrix_form = []
                for term in excitation_generators:
                    exc_gen_matrix_form.append(get_sparse_operator(term, n_qubits=self.q_system.n_qubits))
                    sqr_exc_gen_matrix_form.append(exc_gen_matrix_form[-1]*exc_gen_matrix_form[-1])
                exc_gen_sparse_matrices_dict[key] = exc_gen_matrix_form
                sqr_exc_gen_sparse_matrices_dict[key] = sqr_exc_gen_matrix_form

        self.exc_gen_sparse_matrices_dict = exc_gen_sparse_matrices_dict
        self.sqr_exc_gen_sparse_matrices_dict = sqr_exc_gen_sparse_matrices_dict
        return exc_gen_sparse_matrices_dict

    def calculate_commutators_matrices(self, ansatz_elements):
        logging.info('Calculating commutators')

        if self.exc_gen_sparse_matrices_dict is None:
            self.calculate_exc_gen_sparse_matrices_list(ansatz_elements)

        commutators = {}
        if config.multithread:
            ray.init(num_cpus=config.ray_options['n_cpus'])
            elements_ray_ids = [
                [
                    element, GlobalCache.get_commutator_matrix_multithread.
                    remote(self.get_sparse_matrices_list_copy(self.exc_gen_sparse_matrices_dict[str(element.excitation_generators)]),
                           self.H_sparse_matrix.copy())
                ]
                for element in ansatz_elements
            ]
            for element_ray_id in elements_ray_ids:
                key = str(element_ray_id[0].excitation_generators)
                commutators[key] = ray.get(element_ray_id[1])

            del elements_ray_ids
            ray.shutdown()
        else:
            for i, element in enumerate(ansatz_elements):
                excitation_generator = element.excitation_generators
                key = str(excitation_generator)
                logging.info('Calculated commutator {}'.format(key))
                exc_gen_sparse_matrix = sum(self.exc_gen_sparse_matrices_dict[key])
                commutator_sparse_matrix = self.H_sparse_matrix * exc_gen_sparse_matrix - exc_gen_sparse_matrix * self.H_sparse_matrix
                commutators[key] = commutator_sparse_matrix

        self.commutators_sparse_matrices_dict = commutators
        return commutators

    @staticmethod
    @ray.remote
    def get_commutator_matrix_multithread(exc_gen_matrix_form, H_sparse_matrix):
        t0 = time.time()
        exc_gen_matrix_sum = sum(exc_gen_matrix_form)
        commutator_sparse_matrix = H_sparse_matrix * exc_gen_matrix_sum - exc_gen_matrix_sum * H_sparse_matrix
        del exc_gen_matrix_sum
        del H_sparse_matrix
        del exc_gen_matrix_form
        print('Calculated commutator time ', time.time() - t0)
        return commutator_sparse_matrix

    @staticmethod
    @ray.remote
    def get_exc_generator_matrix_multithread(excitation, n_qubits):
        t0 = time.time()
        # in the case of a spin complement pair, there are two generators for each excitation in the pair
        exc_gen_matrix_form = []
        sqr_exc_gen_matrix_form = []
        for term in excitation.excitation_generators:
            exc_gen_matrix_form.append(get_sparse_operator(term, n_qubits=n_qubits))
            sqr_exc_gen_matrix_form.append(exc_gen_matrix_form[-1]*exc_gen_matrix_form[-1])
        # exc_gen_matrix = get_sparse_operator(excitation.excitation_generators, n_qubits=n_qubits)
        # sqr_exc_gen_matrix = exc_gen_matrix*exc_gen_matrix
        print('Calculated excitation matrix time ', time.time() - t0)
        return exc_gen_matrix_form, sqr_exc_gen_matrix_form


# TODO make a subclass of global cache?
class ThreadCache(Cache):
    def __init__(self, n_qubits, n_electrons, H_sparse_matrix=None, commutators_sparse_matrices_dict=None,
                 sparse_statevector=None, init_sparse_statevector=None, exc_gen_sparse_matrices_dict=None,
                 sqr_exc_gen_sparse_matrices_dict=None):

        super(ThreadCache, self).__init__(H_sparse_matrix=H_sparse_matrix, n_qubits=n_qubits, n_electrons=n_electrons,
                                          exc_gen_sparse_matrices_dict=exc_gen_sparse_matrices_dict,
                                          sqr_exc_gen_sparse_matrices_dict=sqr_exc_gen_sparse_matrices_dict,
                                          commutators_sparse_matrices_dict=commutators_sparse_matrices_dict,
                                          sparse_statevector=sparse_statevector,
                                          init_sparse_statevector=init_sparse_statevector)


