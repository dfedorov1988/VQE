from src.backends import QiskitSimBackend
from src.utils import LogUtils
from src import config

from openfermion import get_sparse_operator

import scipy
import numpy
import time
from functools import partial
import logging
import ray


# TODO make this class entirely static?
class VQERunner:
    # Works for a single geometry
    def __init__(self, q_system, backend=QiskitSimBackend, optimizer=config.optimizer,
                 optimizer_options=config.optimizer_options, print_var_parameters=False, use_ansatz_gradient=False):

        self.backend = backend
        self.optimizer = optimizer
        self.optimizer_options = optimizer_options
        self.use_ansatz_gradient = use_ansatz_gradient
        self.print_var_parameters = print_var_parameters

        self.q_system = q_system

        self.previous_energy = self.q_system.hf_energy
        self.new_energy = None

        self.iteration = 0
        self.time_previous_iter = 0
        
    # TODO split this into a proper callback function!!!!!!
    def get_energy(self, var_parameters, ansatz, backend, multithread=False, multithread_iteration=None,
                   init_state_qasm=None, cache=None, excited_state=0):

        if multithread is False:
            iteration_duration = time.time() - self.time_previous_iter
            self.time_previous_iter = time.time()

        energy = backend.ham_expectation_value(var_parameters, ansatz, self.q_system, cache=cache,
                                               init_state_qasm=init_state_qasm, excited_state=excited_state)
        if multithread:
            if multithread_iteration is not None:
                try:
                    multithread_iteration[0] += 1
                except TypeError as te:
                    logging.warning(te)
        else:
            self.new_energy = energy
            delta_e = self.new_energy - self.previous_energy
            self.previous_energy = self.new_energy

            message = 'Iteration: {}. Energy {}.  Energy change {} , Iteration dutation: {}' \
                .format(self.iteration, self.new_energy, '{:.3e}'.format(delta_e), iteration_duration)
            if self.print_var_parameters:
                message += ' Params: ' + str(var_parameters)
            logging.info(message)
            # tmp_message = "Optimizer tolerance: {}".format(config.optimizer_tol)
            # logging.info(tmp_message)
            self.iteration += 1

        return energy

    def vqe_run(self, ansatz, init_guess_parameters=None, init_state_qasm=None, excited_state=0, cache=None):

        assert len(ansatz) > 0
        if init_guess_parameters is None:
            var_parameters = numpy.zeros(sum([element.n_var_parameters for element in ansatz]))
        else:
            assert len(init_guess_parameters) == sum([element.n_var_parameters for element in ansatz])
            var_parameters = init_guess_parameters

        LogUtils.vqe_info(self.q_system, self.backend, self.optimizer, ansatz)

        self.iteration = 1
        self.time_previous_iter = time.time()

        # functions to be called by the optimizer
        get_energy = partial(self.get_energy, ansatz=ansatz, backend=self.backend, init_state_qasm=init_state_qasm,
                             excited_state=excited_state, cache=cache)

        get_gradient = partial(self.backend.ansatz_gradient, ansatz=ansatz, q_system=self.q_system,
                               init_state_qasm=init_state_qasm, cache=cache, excited_state=excited_state)

        if self.use_ansatz_gradient:
            result = scipy.optimize.minimize(get_energy, var_parameters, jac=get_gradient, method=self.optimizer,
                                             options=self.optimizer_options, tol=config.optimizer_tol,
                                             bounds=config.optimizer_bounds)
        else:

            result = scipy.optimize.minimize(get_energy, var_parameters, method=self.optimizer,
                                             options=self.optimizer_options, tol=config.optimizer_tol,
                                             bounds=config.optimizer_bounds)
        result['n_iters'] = self.iteration  # cheating

        return result

    @ray.remote
    def vqe_run_multithread(self, ansatz, init_guess_parameters=None, init_state_qasm=None, excited_state=0, cache=None):

        assert len(ansatz) > 0

        if init_guess_parameters is None or init_guess_parameters == []:
            var_parameters = numpy.zeros(sum([element.n_var_parameters for element in ansatz]))
        else:
            assert len(init_guess_parameters) == sum([element.n_var_parameters for element in ansatz])
            var_parameters = init_guess_parameters

        # create it as a list so we can pass it by reference
        local_thread_iteration = [0]

        get_energy = partial(self.get_energy, ansatz=ansatz, backend=self.backend, init_state_qasm=init_state_qasm,
                             multithread=True, multithread_iteration=local_thread_iteration, cache=cache,
                             excited_state=excited_state)

        get_gradient = partial(self.backend.ansatz_gradient, ansatz=ansatz, init_state_qasm=init_state_qasm,
                               excited_state=excited_state, cache=cache, q_system=self.q_system)

        if self.use_ansatz_gradient:
            result = scipy.optimize.minimize(get_energy, var_parameters, method=self.optimizer, jac=get_gradient,
                                             options=self.optimizer_options, tol=config.optimizer_tol,
                                             bounds=config.optimizer_bounds)
        else:
            result = scipy.optimize.minimize(get_energy, var_parameters, method=self.optimizer,
                                             options=self.optimizer_options, tol=config.optimizer_tol,
                                             bounds=config.optimizer_bounds)

        # Logging does not work properly with ray multithreading. So use this printings. TODO: fix this. ..
        print('Ran VQE for last element {}. Energy {}. Iterations {}'.
              format(ansatz[-1].element, result.fun, local_thread_iteration[0]))

        # Not sure if needed
        del cache
        # if cache is not None:
        #     del cache.H_sparse_matrix_for_excited_state
        #     del cache.operator_sparse_matrix
        #     del cache.statevector
        #     del cache

        result['n_iters'] = local_thread_iteration[0]  # cheating

        return result

