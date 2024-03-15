# Copyright 2024 Xanadu Quantum Technologies Inc.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
LinearCombination class
"""
# pylint: disable=too-many-arguments, protected-access

import itertools
import numbers
from copy import copy
from typing import List

import pennylane as qml
from pennylane.operation import Observable, Tensor, Operator, convert_to_opmath

from .composite import CompositeOp
from .sum import Sum


class LinearCombination(Sum):
    r"""Operator representing a linear combination of operators.

    The LinearCombination is represented as a linear combination of other operators, e.g.,
    :math:`\sum_{k=0}^{N-1} c_k O_k`, where the :math:`c_k` are trainable parameters.

    Args:
        coeffs (tensor_like): coefficients of the LinearCombination expression
        observables (Iterable[Observable]): observables in the LinearCombination expression, of same length as coeffs
        simplify (bool): Specifies whether the LinearCombination is simplified upon initialization
                         (like-terms are combined). The default value is `False`.
        grouping_type (str): If not None, compute and store information on how to group commuting
            observables upon initialization. This information may be accessed when QNodes containing this
            LinearCombination are executed on devices. The string refers to the type of binary relation between Pauli words.
            Can be ``'qwc'`` (qubit-wise commuting), ``'commuting'``, or ``'anticommuting'``.
        method (str): The graph coloring heuristic to use in solving minimum clique cover for grouping, which
            can be ``'lf'`` (Largest First) or ``'rlf'`` (Recursive Largest First). Ignored if ``grouping_type=None``.
        id (str): name to be assigned to this LinearCombination instance

    **Example:**

    A LinearCombination can be created by simply passing the list of coefficients
    as well as the list of observables:

    >>> coeffs = [0.2, -0.543]
    >>> obs = [qml.X(0) @ qml.Z(1), qml.Z(0) @ qml.Hadamard(2)]
    >>> H = qml.ops.LinearCombination(coeffs, obs)
    >>> print(H)
    0.2 * (X(0) @ Z(1)) + -0.543 * (Z(0) @ Hadamard(wires=[2]))


    The coefficients can be a trainable tensor, for example:

    >>> coeffs = tf.Variable([0.2, -0.543], dtype=tf.double)
    >>> obs = [qml.X(0) @ qml.Z(1), qml.Z(0) @ qml.Hadamard(2)]
    >>> H = qml.ops.LinearCombination(coeffs, obs)
    >>> print(H)
    0.2 * (X(0) @ Z(1)) + -0.543 * (Z(0) @ Hadamard(wires=[2]))


    A LinearCombination can store information on which commuting observables should be measured together in
    a circuit:

    >>> obs = [qml.X(0), qml.X(1), qml.Z(0)]
    >>> coeffs = np.array([1., 2., 3.])
    >>> H = qml.ops.LinearCombination(coeffs, obs, grouping_type='qwc')
    >>> H.grouping_indices
    ((0, 1), (2,))

    This attribute can be used to compute groups of coefficients and observables:

    >>> grouped_coeffs = [coeffs[list(indices)] for indices in H.grouping_indices]
    >>> grouped_obs = [[H.ops[i] for i in indices] for indices in H.grouping_indices]
    >>> grouped_coeffs
    [array([1., 2.]), array([3.])]
    >>> grouped_obs
    [[X(0), X(1)], [Z(0)]]

    Devices that evaluate a LinearCombination expectation by splitting it into its local observables can
    use this information to reduce the number of circuits evaluated.

    Note that one can compute the ``grouping_indices`` for an already initialized LinearCombination by
    using the :func:`compute_grouping <pennylane.LinearCombination.compute_grouping>` method.
    """

    num_wires = qml.operation.AnyWires
    grad_method = "A"  # supports analytic gradients
    batch_size = None
    ndim_params = None  # could be (0,) * len(coeffs), but it is not needed. Define at class-level

    def _flatten(self):
        # note that we are unable to restore grouping type or method without creating new properties
        return (self._coeffs, self._ops, self.data), (self.grouping_indices,)

    @classmethod
    def _unflatten(cls, data, metadata):
        new_op = cls(data[0], data[1])
        new_op._grouping_indices = metadata[0]  # pylint: disable=protected-access
        new_op.data = data[2]
        return new_op

    def __init__(
        self,
        coeffs,
        observables: List[Operator],
        simplify=False,
        grouping_type=None,
        method="rlf",
        _pauli_rep=None,
        id=None,
    ):
        if qml.math.shape(coeffs)[0] != len(observables):
            raise ValueError(
                "Could not create valid LinearCombination; "
                "number of coefficients and operators does not match."
            )

        self._coeffs = coeffs

        self._ops = [convert_to_opmath(op) for op in observables]

        self._hyperparameters = {"ops": self._ops}

        self._grouping_indices = None

        with qml.QueuingManager().stop_recording():
            operands = [qml.s_prod(c, op) for c, op in zip(coeffs, observables)]

        # TODO use grouping functionality of Sum once https://github.com/PennyLaneAI/pennylane/pull/5179 is merged
        super().__init__(
            *operands, grouping_type=grouping_type, method=method, id=id, _pauli_rep=_pauli_rep
        )

        if simplify:
            # TODO clean up this logic, seems unnecesssarily complicated

            simplified_coeffs, simplified_ops, pr = self._simplify_coeffs_ops()

            self._coeffs = (
                simplified_coeffs  # Losing gradient in case of torch interface at this point
            )

            self._ops = simplified_ops
            with qml.QueuingManager().stop_recording():
                operands = [qml.s_prod(c, op) for c, op in zip(self._coeffs, self._ops)]

            super().__init__(*operands, id=id, _pauli_rep=pr)

    def _check_batching(self):
        """Override for LinearCombination, batching is not yet supported."""

    def label(self, decimals=None, base_label=None, cache=None):
        decimals = None if (len(self.parameters) > 3) else decimals
        return super(CompositeOp, self).label(
            decimals=decimals, base_label=base_label or "𝓗", cache=cache
        )  # Skipping the label method of CompositeOp

    @property
    def coeffs(self):
        """Return the coefficients defining the LinearCombination.

        Returns:
            Iterable[float]): coefficients in the LinearCombination expression
        """
        return self._coeffs

    @property
    def ops(self):
        """Return the operators defining the LinearCombination.

        Returns:
            Iterable[Observable]): observables in the LinearCombination expression
        """
        return self._ops

    def terms(self):
        r"""TODO"""
        return self.coeffs, self.ops

    @property
    def wires(self):
        r"""The sorted union of wires from all operators.

        Returns:
            (Wires): Combined wires present in all terms, sorted.
        """
        return self._wires

    @property
    def name(self):
        return "LinearCombination"

    @qml.QueuingManager.stop_recording()
    def _simplify_coeffs_ops(self, cutoff=1.0e-12):
        """Simplify coeffs and ops

        Returns:
            coeffs, ops, pauli_rep"""

        if len(self.ops) == 0:
            return [], [], self.pauli_rep

        # try using pauli_rep:
        if pr := self.pauli_rep:

            wire_order = self.wires
            if len(pr) == 0:
                return [], [], pr

            # collect coefficients and ops
            coeffs = []
            ops = []

            for pw, coeff in pr.items():
                pw_op = pw.operation(wire_order=wire_order)
                ops.append(pw_op)
                coeffs.append(coeff)

            return coeffs, ops, pr

        if len(self.ops) == 1:
            return self.coeffs, [self.ops[0].simplify()], pr

        op_as_sum = qml.sum(*self.operands)
        op_as_sum = op_as_sum.simplify(cutoff)
        coeffs, ops = op_as_sum.terms()
        return coeffs, ops, None

    def simplify(self, cutoff=1.0e-12):
        coeffs, ops, pr = self._simplify_coeffs_ops(cutoff)
        return LinearCombination(coeffs, ops, _pauli_rep=pr)

    def _obs_data(self):
        r"""Extracts the data from a LinearCombination and serializes it in an order-independent fashion.

        This allows for comparison between LinearCombinations that are equivalent, but are defined with terms and tensors
        expressed in different orders. For example, `qml.X(0) @ qml.Z(1)` and
        `qml.Z(1) @ qml.X(0)` are equivalent observables with different orderings.

        .. Note::

            In order to store the data from each term of the LinearCombination in an order-independent serialization,
            we make use of sets. Note that all data contained within each term must be immutable, hence the use of
            strings and frozensets.

        **Example**

        >>> H = qml.ops.LinearCombination([1, 1], [qml.X(0) @ qml.X(1), qml.Z(0)])
        >>> print(H._obs_data())
        {(1, frozenset({('Prod', <Wires = [0, 1]>, ())})),
         (1, frozenset({('PauliZ', <Wires = [0]>, ())}))}
        """
        data = set()

        coeffs_arr = qml.math.toarray(self.coeffs)
        for co, op in zip(coeffs_arr, self.ops):
            obs = op.non_identity_obs if isinstance(op, Tensor) else [op]
            tensor = []
            for ob in obs:
                parameters = tuple(
                    str(param) for param in ob.parameters
                )  # Converts params into immutable type
                if isinstance(ob, qml.GellMann):
                    parameters += (ob.hyperparameters["index"],)
                tensor.append((ob.name, ob.wires, parameters))
            data.add((co, frozenset(tensor)))

        return data

    def compare(self, other):
        r"""Determines whether the operator is equivalent to another.

        Currently only supported for :class:`~LinearCombination`, :class:`~.Observable`, or :class:`~.Tensor`.
        LinearCombinations/observables are equivalent if they represent the same operator
        (their matrix representations are equal), and they are defined on the same wires.

        .. Warning::

            The compare method does **not** check if the matrix representation
            of a :class:`~.Hermitian` observable is equal to an equivalent
            observable expressed in terms of Pauli matrices, or as a
            linear combination of Hermitians.
            To do so would require the matrix form of LinearCombinations and Tensors
            be calculated, which would drastically increase runtime.

        Returns:
            (bool): True if equivalent.

        **Examples**

        >>> H = qml.ops.LinearCombination(
        ...     [0.5, 0.5],
        ...     [qml.PauliZ(0) @ qml.PauliY(1), qml.PauliY(1) @ qml.PauliZ(0) @ qml.Identity("a")]
        ... )
        >>> obs = qml.PauliZ(0) @ qml.PauliY(1)
        >>> print(H.compare(obs))
        True

        >>> H1 = qml.ops.LinearCombination([1, 1], [qml.PauliX(0), qml.PauliZ(1)])
        >>> H2 = qml.ops.LinearCombination([1, 1], [qml.PauliZ(0), qml.PauliX(1)])
        >>> H1.compare(H2)
        False

        >>> ob1 = qml.ops.LinearCombination([1], [qml.PauliX(0)])
        >>> ob2 = qml.Hermitian(np.array([[0, 1], [1, 0]]), 0)
        >>> ob1.compare(ob2)
        False
        """

        if (pr1 := self.pauli_rep) is not None and (pr2 := other.pauli_rep) is not None:
            pr1.simplify()
            pr2.simplify()
            return pr1 == pr2

        if isinstance(other, (LinearCombination, qml.Hamiltonian)):
            op1 = self.simplify()
            op2 = other.simplify()
            return op1._obs_data() == op2._obs_data()  # pylint: disable=protected-access

        if isinstance(other, (Tensor, Observable)):
            op1 = self.simplify()
            return op1._obs_data() == {
                (1, frozenset(other._obs_data()))  # pylint: disable=protected-access
            }

        if isinstance(other, (Operator)):
            op1 = self.simplify()
            op2 = other.simplify()
            return qml.equal(op1, op2)

        raise ValueError(
            "Can only compare a LinearCombination, and a LinearCombination/Observable/Tensor."
        )

    def __matmul__(self, other):
        """The product operation between Operator objects."""
        if isinstance(other, LinearCombination):
            coeffs1 = self.coeffs
            ops1 = self.ops
            shared_wires = qml.wires.Wires.shared_wires([self.wires, other.wires])
            if len(shared_wires) > 0:
                raise ValueError(
                    "Hamiltonians can only be multiplied together if they act on "
                    "different sets of wires"
                )

            coeffs2 = other.coeffs
            ops2 = other.ops

            coeffs = qml.math.kron(coeffs1, coeffs2)
            ops_list = itertools.product(ops1, ops2)
            terms = [qml.prod(t[0], t[1], lazy=False) for t in ops_list]
            return qml.ops.LinearCombination(coeffs, terms)

        if isinstance(other, Operator):
            if other.arithmetic_depth == 0:
                new_ops = [op @ other for op in self.ops]

                # build new pauli rep using old pauli rep
                if (pr1 := self.pauli_rep) is not None and (pr2 := other.pauli_rep) is not None:
                    new_pr = pr1 @ pr2
                else:
                    new_pr = None
                return LinearCombination(self.coeffs, new_ops, _pauli_rep=new_pr)
            return qml.prod(self, other)

        return NotImplemented

    def __add__(self, H):
        r"""The addition operation between a LinearCombination and a LinearCombination/Tensor/Observable."""
        ops = copy(self.ops)
        self_coeffs = self.coeffs

        if isinstance(H, numbers.Number) and H == 0:
            return self

        if isinstance(H, (LinearCombination, qml.Hamiltonian)):
            coeffs = qml.math.concatenate([self_coeffs, H.coeffs], axis=0)
            ops.extend(H.ops)
            if (pr1 := self.pauli_rep) is not None and (pr2 := H.pauli_rep) is not None:
                _pauli_rep = pr1 + pr2
            else:
                _pauli_rep = None
            return qml.ops.LinearCombination(coeffs, ops, _pauli_rep=_pauli_rep)

        if isinstance(H, qml.operation.Operator):
            coeffs = qml.math.concatenate(
                [self_coeffs, qml.math.cast_like([1.0], self_coeffs)], axis=0
            )
            ops.append(H)

            return qml.ops.LinearCombination(coeffs, ops)

        return NotImplemented

    __radd__ = __add__

    def __mul__(self, a):
        r"""The scalar multiplication operation between a scalar and a LinearCombination."""
        if isinstance(a, (int, float, complex)):
            self_coeffs = self.coeffs
            coeffs = qml.math.multiply(a, self_coeffs)
            return qml.ops.LinearCombination(coeffs, self.ops)

        return NotImplemented

    __rmul__ = __mul__

    def __sub__(self, H):
        r"""The subtraction operation between a LinearCombination and a LinearCombination/Tensor/Observable."""
        if isinstance(H, (LinearCombination, qml.Hamiltonian, Tensor, Observable)):
            return self + qml.s_prod(-1.0, H, lazy=False)
        return NotImplemented

    def queue(self, context=qml.QueuingManager):
        """Queues a qml.ops.LinearCombination instance"""
        if qml.QueuingManager.recording():
            for o in self.ops:
                context.remove(o)
            context.append(self)
        return self

    def eigvals(self):
        """Return the eigenvalues of the specified operator.

        This method uses pre-stored eigenvalues for standard observables where
        possible and stores the corresponding eigenvectors from the eigendecomposition.

        Returns:
            array: array containing the eigenvalues of the operator
        """
        eigvals = []
        for ops in self.overlapping_ops:
            if len(ops) == 1:
                eigvals.append(
                    qml.utils.expand_vector(ops[0].eigvals(), list(ops[0].wires), list(self.wires))
                )
            else:
                tmp_composite = Sum(*ops)  # only change compared to CompositeOp.eigvals()
                eigvals.append(
                    qml.utils.expand_vector(
                        tmp_composite.eigendecomposition["eigval"],
                        list(tmp_composite.wires),
                        list(self.wires),
                    )
                )

        return self._math_op(
            qml.math.asarray(eigvals, like=qml.math.get_deep_interface(eigvals)), axis=0
        )

    def diagonalizing_gates(self):
        r"""Sequence of gates that diagonalize the operator in the computational basis.

        Given the eigendecomposition :math:`O = U \Sigma U^{\dagger}` where
        :math:`\Sigma` is a diagonal matrix containing the eigenvalues,
        the sequence of diagonalizing gates implements the unitary :math:`U^{\dagger}`.

        The diagonalizing gates rotate the state into the eigenbasis
        of the operator.

        A ``DiagGatesUndefinedError`` is raised if no representation by decomposition is defined.

        .. seealso:: :meth:`~.Operator.compute_diagonalizing_gates`.

        Returns:
            list[.Operator] or None: a list of operators
        """
        diag_gates = []
        for ops in self.overlapping_ops:
            if len(ops) == 1:
                diag_gates.extend(ops[0].diagonalizing_gates())
            else:
                tmp_sum = Sum(*ops)  # only change compared to CompositeOp.diagonalizing_gates()
                eigvecs = tmp_sum.eigendecomposition["eigvec"]
                diag_gates.append(
                    qml.QubitUnitary(
                        qml.math.transpose(qml.math.conj(eigvecs)), wires=tmp_sum.wires
                    )
                )
        return diag_gates

    def map_wires(self, wire_map: dict):
        """Returns a copy of the current LinearCombination with its wires changed according to the given
        wire map.

        Args:
            wire_map (dict): dictionary containing the old wires as keys and the new wires as values

        Returns:
            .LinearCombination: new LinearCombination
        """
        new_ops = tuple(op.map_wires(wire_map) for op in self.ops)
        new_op = LinearCombination(self.data, new_ops)
        new_op.grouping_indices = self._grouping_indices
        return new_op