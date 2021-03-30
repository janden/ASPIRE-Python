import logging

import numpy as np
from numpy import pi
from scipy.special import jv
from tqdm import tqdm

from aspire.basis import Basis
from aspire.basis.basis_utils import lgwt
from aspire.image import Image
from aspire.nufft import anufft, nufft
from aspire.numeric import fft, xp
from aspire.operators import BlkDiagMatrix
from aspire.utils import complex_type
from aspire.utils.matlab_compat import m_reshape

logger = logging.getLogger(__name__)

# This function was shamelessly copied from class_averaging.py
#   I think ASPIRE has something similar, and if not, we should...
#   Move this later....
def fix_signs(u):
    """
    makes the matrix coloumn sign be by the biggest value
    :param u: matrix
    :return: matrix
    """
    b = np.argmax(np.absolute(u), axis=0)
    b = np.array([np.linalg.norm(u[b[k], k]) / u[b[k], k] for k in range(len(b))])
    u = u * b
    return u


class FSPCABasis(Basis):
    """
    A class for Fast Steerable Principal Component Analaysis basis.

    FSPCA is an extension to Fourier Bessel representations
    (provided asFBBasis2D/FFBBasis2D), which computes combinations of basis
    coefficients coresponding to the princicpal components of image(s)
    represented in the provided basis.

    The principal components are computed from eigen decomposition of the
    covariance matrix, and when evaluated into the real domain form
    the set of `eigenimages`.

    The algorithm is described in the publication:
    Z. Zhao, Y. Shkolnisky, A. Singer, Fast Steerable Principal Component Analysis,
    IEEE Transactions on Computational Imaging, 2 (1), pp. 1-12 (2016).​

    """

    def __init__(self, source, basis):
        """ Not sure if I sure actually inherit from Basis, the __init__ doesn't correspond well... later..."""

        self.basis = basis
        self.src = source
        # check/warn dtypes
        self.dtype = self.src.dtype
        if self.basis.dtype != self.dtype:
            logger.warning(
                f"basis.dtype {self.basis.dtype} does not match"
                f" source {self.src.dtype}, using {self.dtype}."
            )

        self._build()

    def _build(self):

        # setup any common indexing arrays
        self._indices()

        # maybe call this _precompute?
        # For now, use the whole image set.
        self.coef = self.basis.evaluate_t(
            self.src.images(0, self.src.n)
        )  # basis coefficients

        # We'll use the complex representation for the calculations
        self.complex_coef = self.basis.to_complex(self.coef)

        # Create the arrays to be packed by _compute_spca
        self.eigvals = np.zeros(
            self.basis.complex_count, dtype=complex_type(self.dtype)
        )
        self.eigvecs = BlkDiagMatrix.empty(
            self.basis.ell_max + 1, dtype=complex_type(self.dtype)
        )
        self.spca_coef = np.zeros(
            (self.src.n, self.basis.complex_count), dtype=complex_type(self.dtype)
        )

        noise_var = 0  # XXX, clean img only for now

        self._compute_spca(noise_var)

    def _indices(self):
        # Map between the real coef indices and complex
        self.complex_angular_indices = self.basis._indices["ells"][
            self.basis.indices_real
        ]  # k
        self.complex_radial_indices = self.basis._indices["ks"][
            self.basis.indices_real
        ]  # q

    def _compute_spca(self, noise_var):
        """
        Algorithm 2 from paper.
        """

        # number of images
        n = self.src.n

        # Compute coefficient vector of mean image at zeroth component
        mean_coef = np.mean(
            self.complex_coef[:, self.complex_angular_indices == 0], axis=0
        )
        complex_coef = self.complex_coef.copy()

        # Foreach angular frequency (`k` in paper, `ells` in FB code)
        eigval_index = 0
        for angular_index in tqdm(range(0, self.basis.ell_max + 1)):

            ## Construct A_k, matrix of expansion coefficients a^i_k_q
            ##   for image i, angular index k, radial index q,
            ##   (around eq 31-33)
            ##   Rows radial indices, columns image i.
            ##
            ## We can extract this directly (up to transpose) from
            ##  complex_coef vector where ells == angular_index
            ##  then use the transpose so image stack becomes columns.

            indices = self.complex_angular_indices == angular_index
            A_k = complex_coef[:, indices].T

            lambda_var = self.basis.n_r / (2 * n)  # this isn't used in the clean regime

            # Zero angular freq is a special case
            if angular_index == 0:  # eq 33
                # de-mean
                # A_k = A_k - mean_coef.T[:, np.newaxis]
                A_k = (A_k.T - mean_coef).T
                # double count the zero case
                lambda_var *= 2

            ## Compute the covariance matrix representation C_k, eq 32
            ##   Note, I don't see relevance of special case 33...
            ##     C_k = np.real(A_k @ A_k.conj().T) / n
            ##   Einsum is performing the transpose, sometimes better performance.
            C_k = np.einsum("ij, kj -> ik", A_k, A_k.conj()).real / n

            ## Eigen/SVD,
            eigvals_k, eigvecs_k = np.linalg.eig(C_k)
            logger.debug(
                f"eigvals_k.shape {eigvals_k.shape} eigvecs_k.shape {eigvecs_k.shape}"
            )

            # Determistically enforce eigen vector sign convention
            eigvecs_k = fix_signs(eigvecs_k)

            # Sort eigvals_k (gbw, are they not sorted already?!)
            sorted_indices = np.argsort(-eigvals_k)
            eigvals_k, eigvecs_k = (
                eigvals_k[sorted_indices],
                eigvecs_k[:, sorted_indices],
            )

            if noise_var != 0:
                raise NotImplementedError("soon")
            else:
                # These are the complex basis indices
                basis_inds = np.arange(eigval_index, eigval_index + len(eigvals_k))

                # Store the eigvals
                self.eigvals[basis_inds] = eigvals_k

                # Store the eigvecs, note this is a BlkDiagMatrix and is assigned incrementally.
                self.eigvecs[angular_index] = eigvecs_k

                ## To compute new expansion coefficients using spca basis
                ##   we combine the basis coefs using the eigen decomposition.
                # Note image stack slow moving axis, and requires transpose from other implementation.
                self.spca_coef[:, basis_inds] = np.einsum(
                    "ji, jk -> ik", eigvecs_k, A_k
                ).T

                eigval_index += len(eigvals_k)

                ## Computing radial eigen vectors (functions) (eq 35) is not used? check

        # Sanity check we have same dimension of eigvals and (complex) basis coefs.
        if eigval_index != self.basis.complex_count:
            raise RuntimeError(
                f"eigvals dimension {eigval_index} != complex basis coef count {self.basis.complex_count}."
            )

    def expand(self, x):
        """
        Take an image in the standard coordinate basis and express as FSPCA coefs.

        :param x:  The Image instance representing a stack of images in the
        standard 2D coordinate basis to be evaluated.
        :return: Stack of (complex) coefs in the FSPCABasis.
        """

        # evaluate_t in FFB
        # then apply linear combination defined by FSPCA (eigvecs)
        pass

    def evalute(self, c):
        """
        Take FSPCA coefs and evaluate as image in the standard coordinate basis.

        :param c:  Stack of (complex) coefs in the FSPCABasis to be evaluated.
        :return: The Image instance representing a stack of images in the
        standard 2D coordinate basis..
        """

        # apply FSPCA eigenvector to coefs c, yields original coefs v in self.basis
        # return self.basis.evaluate(v)
        pass

    def rotate(self, c, radians):
        """
        Rotate a stack of coefs in the FSPCA basis.

        :param c:  Stack of (complex) coefs in the FSPCABasis.
        :param radians: Rotation to apply (positive as counter clockwise).
        :return:  Stack of (complex) coefs in the FSPCABasis after rotation.
        """
        pass

    def eigenimages(self, images):
        """
        Take stack of images in the standard coordinate basis and return the eigenimages.

        :param images:  The Image instance representing a stack of images in the
        standard 2D coordinate basis to be evaluated.
        :return: Stack of eigenimages computed by FSPCA.
        """

        # Sanity check the power captured by the eigen components
        ## Check do we expect blocks decreasing? if so i have bug...
        sorted_indices = np.argsort(-np.abs(self.eigvals))
        k = 10
        print(
            f"Top {k} Eigvals of {len(self.eigvals)} {self.eigvals[sorted_indices][:k]}"
        )
        import matplotlib.pyplot as plt

        plt.semilogy(np.abs(self.eigvals[sorted_indices]))
        plt.show()

        # What do the eigvecs look like?
        I = self.basis.evaluate(
            self.basis.to_real(
                self.eigvecs.dense()[sorted_indices].astype(np.complex128)
            )
        )
        eigenplot = np.empty((k, self.basis.nres, k, self.basis.nres))
        for i in range(k):
            for j in range(k):
                eigenplot[i, :, j, :] = I[i * k + j]
        eigenplot = eigenplot.reshape(k * self.basis.nres, k * self.basis.nres)
        plt.imshow(eigenplot)
        plt.show()

        # evaluate_t in self.basis (FFB)
        c_fb = self.basis.to_complex(self.basis.evaluate_t(images))

        # Then apply linear combination defined by FSPCA (eigvecs)
        # This yields the representation in FSPCA basis
        #  alpha =         U.T             @   X
        # c_fspca = (self.eigvecs.dense().T @ c_fb.T)  # transpose the smaller matrix
        c_fspca = (c_fb @ self.eigvecs.dense()).T

        # We then apply FSPCA eigenvector matrix again to get the reconstructed images
        #           Y            =         U            @  alpha     =     U @ U.T @ X
        reconstructed_image_coef = self.eigvecs.dense() @ c_fspca
        #  These are still coefs in self.basis (FFB)
        #  so we need to evaluate back to the image domain.
        reconstructed_image_coef = self.basis.to_real(reconstructed_image_coef.T)
        eigen_images = self.basis.evaluate(reconstructed_image_coef)

        return eigen_images
