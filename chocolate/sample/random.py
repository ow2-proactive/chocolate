
import numpy

from ..base import UpdatableMixin
from ..space import ContinuousDistribution
from .grid import ParameterGrid

class Random(UpdatableMixin):
    """Random sampler.

    Samples the search space randomly. This sampler will draw random numbers
    for each entry in the database in order to restore the random state for
    reproductibility when used concurrently with other random samplers.

    If all parameters are discrete, the sampling is made without replacement.
    Otherwise, the exploration is conducted independently of conditional
    search space, meaning that each subspace will receive approximately the
    same number of samples.

    Args:
        connection: A database connection object.
        space: The search space to explore with only discrete dimensions. The
            search space can be either a dictionary or a
            :class:`chocolate.Space` instance.
        random_state: Either a :class:`numpy.random.RandomState` instance, an
            object to initialize the random state with or
            :data:`None` in which case the global state is used.
    """
    def __init__(self, connection, space, random_state=None):
        super(Random, self).__init__(connection, space)
        if isinstance(random_state, numpy.random.RandomState):
            self.random_state = random_state
        elif random_state is None:
            self.random_state = numpy.random
        else:
            self.random_state = numpy.random.RandomState(random_state)

        # Check if all dimensions are discrete, in which case sampling
        # without replacement is possible
        self.subspace_grids = None
        if self.space.isdiscrete():
            self.subspace_grids = ParameterGrid(self.space)

        self.drawn = 0

    def next(self):
        """Retrieve the next random point to test and add it to the database
        with loss set to :data:`None`. On each call random points are burnt so
        that two random sampling running concurrently with the same random
        state don't draw the same points and produce reproductible results.

        Returns:
            A tuple containing a unique token and a vector of length equal to
            the number of parameters.

        Raises:
            StopIteration: If all dimensions are discrete and all possibilities
                have been sampled.
        """
        with self.conn.lock():
            i = self.conn.count_results()

            if self.subspace_grids is not None:
                # Sample without replacement
                l = len(self.subspace_grids)
                if i >= l:
                    raise StopIteration
                
                # Restore state by burning numbers
                for _ in range(i - self.drawn):
                    self.random_state.rand()
                
                drawn = [doc["_chocolate_id"] for doc in self.conn.all_results()]
                
                choices = sorted(set(range(l)) - set(drawn))
                sample = self.random_state.choice(choices)
                self.drawn += i - self.drawn + 1
                
                # Some dbs don't like numpy.int64
                token = {"_chocolate_id" : int(sample)}
                out = self.subspace_grids[sample]

            else:
                token = {"_chocolate_id" : i}

                # Restore state by burning numbers
                self.random_state.rand(len(self.space), (i - self.drawn))

                # Sample in [0, 1)^n
                out = self.random_state.rand(len(self.space))
                self.drawn += i - self.drawn + 1

            entry = {k : v for k, v in zip(self.space.names(), out)}
            # entry["_loss"] = None
            entry.update(token)
            self.conn.insert_result(entry)

        return token, self.space(out)