import numpy as np
import finufftpy
from aspire.nfft import Plan
from aspire.utils import ensure


class FINufftPlan(Plan):
    def __init__(self, sz, fourier_pts, epsilon=1e-15, many=0, **kwargs):
        """
        A plan for non-uniform FFT (3D)

        :param sz: A tuple indicating the geometry of the signal
        :param fourier_pts: The points in Fourier space where the Fourier transform is to be calculated,
            arranged as a 3-by-K array. These need to be in the range [-pi, pi] in each dimension.
        :param epsilon: The desired precision of the NUFFT
        :param many: Optional integer indicating if you would like to compute a batch of `many`
        transforms.  Implies vol_f.shape is (..., `many`). Defaults to 0 which disables batching.
        """

        self.many = False
        self.ntransforms = 1
        manystr = ''
        if many != 0:
            self.many = True
            self.ntransforms = many
            manystr = 'many'
        self.sz = sz
        self.dim = len(sz)

        # TODO: Currently finufftpy is hardcoded as doubles only right now
        self.dtype = fourier_pts.dtype
        assert self.dtype == np.float64, 'finufftpy is hardcoded to doubles.'

        # TODO: Replace with ASPIRE util once merged in
        if self.dtype == np.float64:
            self.complex_dtype = np.complex128
        elif self.dtype == np.float32:
            self.complex_dtype = np.complex64

        # TODO: Things get messed up unless we ensure a 'C' ordering here - investigate why
        self.fourier_pts = np.asarray(np.mod(fourier_pts + np.pi, 2 * np.pi) - np.pi,
                                      order='C', dtype=self.dtype)
        self.num_pts = fourier_pts.shape[1]
        self.epsilon = epsilon

        # Get a handle on the appropriate 1d/2d/3d forward transform function in finufftpy
        self.transform_function = getattr(finufftpy, f'nufft{self.dim}d2{manystr}')

        # Get a handle on the appropriate 1d/2d/3d adjoint function in finufftpy
        self.adjoint_function = getattr(finufftpy, f'nufft{self.dim}d1{manystr}')


    def transform(self, signal):
        sig_shape = signal.shape
        if self.many:
            sig_shape = signal.shape[:-1]         # order...
        ensure(sig_shape == self.sz, f'Signal to be transformed must have shape {self.sz}')

        epsilon = max(self.epsilon, np.finfo(signal.dtype).eps)

        # Forward transform functions in finufftpy have signatures of the form:
        # (x, y, z, c, isign, eps, f, ...)
        # (x, y     c, isign, eps, f, ...)
        # (x,       c, isign, eps, f, ...)
        # Where f is a Fortran-order ndarray of the appropriate dimensions
        # We form these function signatures here by tuple-unpacking

        res_shape = self.num_pts
        if self.many:
            res_shape = (self.ntransforms, self.num_pts)

        result = np.zeros(res_shape, dtype=self.complex_dtype)

        result_code = self.transform_function(
            *self.fourier_pts,
            result,
            -1,
            epsilon,
            signal
        )

        if result_code != 0:
            raise RuntimeError(f'FINufft transform failed. Result code {result_code}')

        return result

    def adjoint(self, signal):

        epsilon = max(self.epsilon, np.finfo(signal.dtype).eps)

        # Adjoint functions in finufftpy have signatures of the form:
        # (x, y, z, c, isign, eps, ms, mt, mu, f, ...)
        # (x, y     c, isign, eps, ms, mt      f, ...)
        # (x,       c, isign, eps, ms,         f, ...)
        # Where f is a Fortran-order ndarray of the appropriate dimensions
        # We form these function signatures here by tuple-unpacking

        res_shape = self.sz
        if self.many:
            res_shape = (*self.sz, self.ntransforms)

        result = np.zeros(res_shape, order='F', dtype=self.complex_dtype)

        result_code = self.adjoint_function(
            *self.fourier_pts,
            signal,
            1,
            epsilon,
            *self.sz,
            result
        )
        if result_code != 0:
            raise RuntimeError(f'FINufft adjoint failed. Result code {result_code}')

        return result
