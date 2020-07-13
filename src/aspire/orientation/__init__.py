import logging
import math
import numpy as np
import scipy.sparse as sparse

from aspire import config

from aspire.basis.polar_2d import PolarBasis2D
from aspire.source import ArrayImageSource
from aspire.utils.coor_trans import common_line_from_rots
from aspire.utils.matlab_compat import m_reshape

logger = logging.getLogger(__name__)


class CLOrient3D:
    """
    Define a base class for estimating 3D orientations using common lines methods
    """
    def __init__(self, src, n_rad=None, n_theta=None, n_check=None):
        """
        Initialize an object for estimating 3D orientations using common lines

        :param src: The source object of 2D denoised or class-averaged imag
        :param n_rad: The number of points in the radial direction
        :param n_theta: The number of points in the theta direction
        :param n_check: For each image/projection find its common-lines with
            n_check images. If n_check is less than the total number of images,
            a random subset of n_check images is used.
        """
        self.src = src
        self.n_img = src.n
        self.n_res = self.src.L
        self.n_rad = n_rad
        self.n_theta = n_theta
        self.n_check = n_check
        self.clmatrix = None
        self.skipmatrix = None
        self.shifts_1d = None

        self.rotations = None

        self._build()

    def _build(self):
        """
        Build the internal data structure for orientation estimation
        """
        if self.n_rad is None:
            self.n_rad = math.ceil(config.orient.r_ratio * self.n_res)
        if self.n_theta is None:
            self.n_theta = config.orient.n_theta
        if self.n_check is None:
            self.n_check = self.n_img

        self.max_shift = math.ceil(config.orient.max_shift * self.n_res)
        self.shift_step = config.orient.shift_step

        imgs = self.src.images(start=0, num=np.inf).asnumpy()
        # Switch the X, Y to be consistent with the definition of project method
        # in Volume class, it can be switch back to use the equations from paper
        imgs = np.swapaxes(imgs, 0, 1)

        # Obtain coefficients in polar Fourier basis for input 2D images
        self.basis = PolarBasis2D((self.n_res, self.n_res), self.n_rad, self.n_theta)
        self.pf = self.basis.evaluate_t(imgs)
        self.pf = m_reshape(self.pf, (self.n_rad, self.n_theta, self.n_img))

        if self.n_theta % 2 == 1:
            logger.error('n_theta must be even')
        n_theta_half = self.n_theta // 2
        # The first two dimension of pf is of size n_rad x n_theta. Convert pf into an
        # array of size (2xn_rad-1) x n_theta/2, that is, take entire ray
        # through the origin, but take the angles only up PI. In fact, the original
        # images are real, and thus each ray is conjugate symmetric. We therefore
        # gain nothing by taking longer correlations (of length 2*n_rad-1 instead of n_rad),
        # as the two halve are exactly the same. In real calculation of build_clmatrix below,
        # We only taking shorter correlation and speed the computation by a factor of two.
        self.pf = np.concatenate((np.flip(self.pf[1:, n_theta_half:], 0), self.pf[:, :n_theta_half]), 0)

    def estimate_rotations(self):
        """
        Estimate orientation matrices for all 2D images

        Subclasses should implement this function.
        """
        raise NotImplementedError('subclasses should implement this')

    def save_rotations(self):
        """
        Save the estimated rotation matrices to new ImageSource object
        """
        # Generate a new ImageSource object and save estimated rotation matrices
        # It will be simpler if it is allowed to modify the original one
        src = ArrayImageSource(self.src.images(start=0, num=np.inf))
        src.rots = self.rotations
        return src

    def build_clmatrix(self):
        """
        Build common-lines matrix from Fourier stack of 2D images
        """

        n_img = self.n_img
        n_check = self.n_check

        if self.n_theta % 2 == 1:
            logger.error('n_theta must be even')
        n_theta_half = self.n_theta // 2

        # need to do a copy to prevent modifying self.pf for other functions
        pf = self.pf.copy()

        # Allocate local variables for return
        # clstack represents the common lines matrix.
        # Namely, clstack[i,j] contains the index in image i of
        # the common line with image j. Note the common line index
        # starts from 0 instead of 1 as Matlab version. -1 means
        # there is no common line such as clstack[i,i].
        clstack = -np.ones((n_img, n_img))
        # skipstack[i, j] measures how ''common'' is the between
        # image i and j. Small value means high-similarity.
        # we will use skipstack[i, j] = 0 (including i=j) to
        # represent that there is no need to check common line
        # between i and j. Since stack is symmetric,
        # only above the diagonal entries are necessary.
        skipstack = np.zeros((n_img, n_img))

        # Allocate variables used for shift estimation

        # set maximum value of 1D shift (in pixels) to search
        # between common-lines.
        max_shift = self.max_shift
        # Set resolution of shift estimation in pixels. Note that
        # shift_step can be any positive real number.
        shift_step = self.shift_step
        # 1D shift between common-lines
        shifts_1d = np.zeros((n_img, n_img))

        # Prepare the shift phases to try and generate filter for common-line detection
        r_max = int((pf.shape[0] - 1) / 2)
        shifts, shift_phases, h = self._generate_shift_phase_and_filter(
            r_max, max_shift, shift_step)
        all_shift_phases = shift_phases.T

        # Apply bandpass filter, normalize each ray of each image
        # and only use half of each ray
        pf = self._apply_filter_and_norm('ijk, i -> ijk', pf, r_max, h)

        # change dimensions of axes to n_img × n_rad/2 × n_theta/2
        pf = pf.transpose((2, 1, 0))

        # Search for common lines between [i, j] pairs of images.
        # Creating pf and building common lines are different to the Matlab version.
        # The random selection is implemented.
        for i in range(n_img - 1):
            p1 = pf[i]
            p1_real = np.real(p1)
            p1_imag = np.imag(p1)

            # build the subset of j images if n_check < n_img
            num_j = min(n_img - i, n_check)
            subset_j = np.sort(np.random.choice(n_img - i - 1, num_j - 1,
                                                 replace=False) + i + 1)

            for j in subset_j:
                p2_flipped = np.conj(pf[j])

                for shift in range(len(shifts)):
                    shift_phases = all_shift_phases[shift]
                    p2_shifted_flipped = (shift_phases * p2_flipped).T
                    # Compute correlations in the positive r direction
                    part1 = p1_real.dot(np.real(p2_shifted_flipped))
                    # Compute correlations in the negative r direction
                    part2 = p1_imag.dot(np.imag(p2_shifted_flipped))

                    c1 = part1 - part2
                    sidx = c1.argmax()
                    cl1, cl2 = np.unravel_index(sidx, c1.shape)
                    sval = c1[cl1, cl2]

                    c2 = part1 + part2
                    sidx = c2.argmax()
                    cl1_2, cl2_2 = np.unravel_index(sidx, c2.shape)
                    sval2 = c2[cl1_2, cl2_2]

                    if sval2 > sval:
                        cl1 = cl1_2
                        cl2 = cl2_2 + n_theta_half
                        sval = sval2
                    sval = 2 * sval
                    if sval > skipstack[i, j]:
                        clstack[i, j] = cl1
                        clstack[j, i] = cl2
                        skipstack[i, j] = sval
                        shifts_1d[i, j] = shifts[shift]

        mask = (skipstack != 0)
        skipstack[mask] = 1 - skipstack[mask]

        self.clmatrix = clstack
        self.skipmatrix = skipstack
        self.shifts_1d = shifts_1d

    def estimate_shifts(self, memory_factor=10000):
        """
        Estimate 2D shifts in images

        This function computes 2D shifts in x, y of images by solving the least-squares
        equations to `Ax = b`. `A` on the left-hand side is a parse matrix representing
        precomputed coefficients of shift equations; and on the right-side, `b` is
        estimated 1D shifts along the theta direction between two Fourier rays (one in
        one in image i and one in image j).  Each row of shift equations contains four
        non-zeros (as it involves exactly four unknowns).

        :param memory_factor: If there are N images and N_check selected to check
            for common lines, then the exact system of equations solved for the shifts
            is of size 2N x N(N_check-1)/2 (2N unknowns and N(N_check-1)/2 equations).
            This may be too big if N is large. If `memory_factor` between 0 and 1, then
            it is the fraction of equation to retain. That is, the system of
            equations solved will be of size 2N x N*(N_ckeck-1)/2*`memory_factor`.
            If `memory_factor` is larger than 100, then the number of
            equations is estimated in such a way that the memory used by the equations
            is roughly `memory_factor megabytes`. Default is 10000 (use all equations).
            The code will generate an error if `memory_factor` is between 1 and 100. If
            `memory_factor` is `None`, the shift equations will be generated exactly
            from the common line matrix instead of estimated rotation matrices.
        """

        if memory_factor is None:
            # Obtain exact shift equations from common-lines matrix
            shift_equations, shift_b = self._get_shift_equations_exact()
        else:
            # Generate approximated shift equations from estimated rotations
            shift_equations, shift_b = self._get_shift_equations_approx(memory_factor)

        est_shifts = sparse.linalg.lsqr(shift_equations, shift_b)[0]
        est_shifts = est_shifts.reshape((2, self.n_img), order='F')

        return est_shifts

    def _get_shift_equations_exact(self):
        """
        Obtain exact shift equations from common-lines matrix

        Based on the estimated common-line from common-lines matrix,
        construct the equations for determining the 2D shift (in x and y)
        of each image. The shift equations are represented using a sparse matrix,
        since each row in the system contains four non-zeros (as it involves
        exactly four unknowns). Using this shift equations as the left side
        and the estimated 1D shifts ( between its two Fourier rays one in image
        i and one in image j) from all common lines as the right-hand side,
        the 2D shifts can be computed by solves the least-squares method.

        :return; The left and right-hand side of shift equations
        """

        clstack = self.clmatrix
        skipstack = self.skipmatrix
        shifts_1d = self.shifts_1d

        n_img = self.n_img
        n_check = self.n_check

        if self.n_theta % 2 == 1:
            logger.error('n_theta must be even')
        n_theta_half = self.n_theta // 2

        # Allocate variables used for shift estimation

        # Based on the estimated common-lines, construct the equations
        # for determining the 2D shift of each image. The shift equations
        # are represented using a sparse matrix, since each row in the
        # system contains four non-zeros (as it involves exactly four unknowns).
        # The variables below are used to construct this sparse system.
        # The k'th non-zero element of the equations matrix is stored as
        # index (shift_i[k],shift_j[k]).

        # Row index for sparse equations system
        shift_i = np.zeros(4 * n_img * n_check)
        #  Column index for sparse equations system
        shift_j = np.zeros(4 * n_img * n_check)
        # The coefficients of the center estimation system ordered
        # as a single vector.
        shift_eq = np.zeros(4 * n_img * n_check)
        # shift_equations_map[k1,k2] is the index of the equation for
        # the common line between images i and j.
        shift_equations_map = np.zeros((n_img, n_img))
        # The equation number we are currently processing
        shift_equation_idx = 0
        # Right hand side of the system
        shift_b = np.zeros(n_img * (n_img - 1) // 2)
        # Not 2*pi/n_theta, since we divided n_theta by 2 to take rays of length 2*n_r-1.
        dtheta = np.pi / n_theta_half

        # Go through common lines between [i, j] pairs of projections based on the
        # skipstack values created when build the common lines matrix.
        for i in range(n_img - 1):
            for j in range(i + 1, n_img):
                # skip j image without correlation
                if skipstack[i, j] == 0:
                    continue
                # Create a shift equation for the projections pair (i, j).
                idx = np.arange(4 * shift_equation_idx, 4 * shift_equation_idx + 4)
                shift_alpha = clstack[i, j] * dtheta
                shift_beta = clstack[j, i] * dtheta
                shift_i[idx] = shift_equation_idx
                shift_j[idx] = [2 * i, 2 * i + 1, 2 * j, 2 * j + 1]
                shift_b[shift_equation_idx] = shifts_1d[i, j]

                # Compute the coefficients of the current equation.
                coeffs = np.array([np.sin(shift_alpha), np.cos(shift_alpha),
                                   -np.sin(shift_beta), -np.cos(shift_beta)])
                shift_eq[idx] = coeffs if shift_beta < np.pi else -1 * coeffs

                shift_equations_map[i, j] = shift_equation_idx
                shift_equation_idx += 1

        # Only use the non-zero elements and build sparse matrix
        mask = (shift_eq != 0)
        shift_eq = shift_eq[mask]
        shift_i = shift_i[mask]
        shift_j = shift_j[mask]
        shift_equations = sparse.csr_matrix((shift_eq, (shift_i, shift_j)),
                                            shape=(shift_equation_idx, 2 * n_img))

        return shift_equations, shift_b

    def _get_shift_equations_approx(self, memory_factor=10000):
        """
        Generate approximated shift equations from estimated rotations

        The function computes the common lines from the estimated rotations,
        and then, for each common line, estimates the 1D shift between its two
        Fourier rays (one in image i and one in image j). Using the common
        lines and the 1D shifts, shift equations are generated randomly based
        on a memory factor and represented by sparse matrix.

        This function processes the (Fourier transformed) images exactly as the
        `build_clmatrix` function.

        :param memory_factor: If there are N images and N_check selected to check
            for common lines, then the exact system of equations solved for the shifts
            is of size 2N x N(N_check-1)/2 (2N unknowns and N(N_check-1)/2 equations).
            This may be too big if N is large. If `memory_factor` between 0 and 1, then
            it is the fraction of equation to retain. That is, the system of
            equations solved will be of size 2N x N*(N_ckeck-1)/2*`memory_factor`.
            If `memory_factor` is larger than 100, then the number of
            equations is estimated in such a way that the memory used by the equations
            is roughly `memory_factor megabytes`. Default is 10000 (use all equations).
            The code will generate an error if `memory_factor` is between 1 and 100.
        """

        if memory_factor < 0 or (memory_factor > 1 and memory_factor < 100):
            logger.error('Subsampling factor must be between 0 and 1 or larger than 100.')

        n_theta_half = self.n_theta // 2
        n_img = self.n_img
        rotations = self.rotations

        pf = self.pf.copy()

        # Estimate number of equations that will be used to calculate the shifts
        n_equations = self._estimate_num_shift_equations(n_img, memory_factor)
        # Allocate local variables for estimating 2D shifts based on the estimated number
        # of equations. The shift equations are represented using a sparse matrix,
        # since each row in the system contains four non-zeros (as it involves
        # exactly four unknowns). The variables below are used to construct
        # this sparse system. The k'th non-zero element of the equations matrix
        # is stored at index (shift_i(k),shift_i(k)). Note the last n_equations
        # elements are used to store the right side of Ax = b.
        shift_i = np.zeros(4 * n_equations)
        shift_j = np.zeros(4 * n_equations)
        shift_eq = np.zeros(4 * n_equations)
        shift_b = np.zeros(n_equations)

        # Prepare the shift phases to try and generate filter for common-line detection
        # The shift phases are pre-defined in a range of max_shift that can be
        # applied to maximize the common line calculation. The common-line filter
        # is also applied to the radial direction for easier detection.
        max_shift = self.max_shift
        shift_step = self.shift_step
        r_max = (pf.shape[0] - 1) // 2
        _, shift_phases, h = self._generate_shift_phase_and_filter(r_max, max_shift, shift_step)

        d_theta = np.pi / n_theta_half
        # pf = self._apply_filter_and_norm(pf, r_max, h)
        # Generate two index lists for [i, j] pairs of images
        idx_i, idx_j = self._generate_index_pairs(n_equations)

        # Go through all shift equations in the size of n_equations
        # Iterate over the common lines pairs and for each pair find the 1D
        # relative shift between the two Fourier lines in the pair.
        for shift_eq_idx in range(n_equations):
            i = idx_i[shift_eq_idx]
            j = idx_j[shift_eq_idx]
            # get the common line indices based on the rotations from i and j images
            c_ij, c_ji = self._get_cl_indices(rotations, i, j, n_theta_half)

            # Extract the Fourier rays that correspond to the common line
            pf_i = pf[:, c_ij, i]

            # Check whether need to flip or not Fourier ray of j image
            # Is the common line in image j in the positive
            # direction of the ray (is_pf_j_flipped=False) or in the
            # negative direction (is_pf_j_flipped=True).
            is_pf_j_flipped = (c_ji >= n_theta_half)
            if not is_pf_j_flipped:
                pf_j = pf[:, c_ji, j]
            else:
                pf_j = pf[:, c_ji - n_theta_half, j]

            # perform bandpass filter, normalize each ray of each image,
            # and only keep half of each ray
            pf_i = self._apply_filter_and_norm('i, i -> i', pf_i, r_max, h)
            pf_j = self._apply_filter_and_norm('i, i -> i', pf_j, r_max, h)

            # apply the shifts to images
            pf_i_flipped = np.conj(pf_i)
            pf_i_stack = np.einsum('i, ij -> ij', pf_i, shift_phases)
            pf_i_flipped_stack = np.einsum('i, ij -> ij', pf_i_flipped, shift_phases)

            c1 = 2 * np.real(np.dot(np.conj(pf_i_stack.T), pf_j))
            c2 = 2 * np.real(np.dot(np.conj(pf_i_flipped_stack.T), pf_j))

            # find the indices for the maximum values
            # and apply corresponding shifts
            sidx1 = np.argmax(c1)
            sidx2 = np.argmax(c2)
            sidx = sidx1 if c1[sidx1] > c2[sidx2] else sidx2
            dx = -max_shift + sidx * shift_step

            # Create a shift equation for the image pair [i,j]
            idx = np.arange(4 * shift_eq_idx, 4 * shift_eq_idx + 4)
            # angle of common ray in image i
            shift_alpha = c_ij * d_theta
            # Angle of common ray in image j.
            shift_beta = c_ji * d_theta
            # Row index to construct the sparse equations
            shift_i[idx] = shift_eq_idx
            # Columns of the shift variables that correspond to the current pair [i, j]
            shift_j[idx] = [2 * i, 2 * i + 1, 2 * j, 2 * j + 1]
            # Right hand side of the current equation
            shift_b[shift_eq_idx] = dx

            # Compute the coefficients of the current equation
            coeffs = np.array([np.sin(shift_alpha), np.cos(shift_alpha),
                               -np.sin(shift_beta), -np.cos(shift_beta)])
            shift_eq[idx] = -1 * coeffs if is_pf_j_flipped else coeffs

        # create sparse matrix object only containing non-zero elements
        shift_equations = sparse.csr_matrix((shift_eq, (shift_i, shift_j)),
                                            shape=(n_equations, 2 * n_img))

        return shift_equations, shift_b

    def _estimate_num_shift_equations(self, n_img, memory_factor):
        """
        Estimate total number of shift equations in images

        The function computes total number of shift equations based on
        number of images and preselected memory factor.
        :param n_img:  The total number of input images
        :param memory_factor: If there are N images and N_check selected to check
            for common lines, then the exact system of equations solved for the shifts
            is of size 2N x N(N_check-1)/2 (2N unknowns and N(N_check-1)/2 equations).
            This may be too big if N is large. If `memory_factor` between 0 and 1, then
            it is the fraction of equation to retain. That is, the system of
            equations solved will be of size 2N x N*(N_ckeck-1)/2*`memory_factor`.
            If `memory_factor` is larger than 100, then the number of
            equations is estimated in such a way that the memory used by the equations
            is roughly `memory_factor megabytes`. Default is 10000 (use all equations).
        :return: Estimated number of shift equations
        """
        # Number of equations that will be used to estimation the shifts
        n_equations_total = int(np.ceil(n_img * (self.n_check - 1) / 2))
        # Estimated memory requirements for the full system of equation.
        # This ignores the sparsity of the system, since backslash seems to
        # ignore it.
        memory_total = n_equations_total * 2 * n_img * np.dtype('float64').itemsize

        if memory_factor <= 1:
            # Number of equations that will be used to estimation the shifts
            n_equations = int(np.ceil(n_equations_total * memory_factor))
        else:
            # By how much we need to subsample the system of equations in order to
            # use roughly memory factor MB.
            subsampling_factor = (memory_factor * 10 ** 6) / memory_total
            subsampling_factor = min(1.0, subsampling_factor)
            n_equations = int(np.ceil(n_equations_total * subsampling_factor))

        if n_equations < n_img:
            logger.warning('Too few equations. Increase memory_factor. Setting n_equations to n_img.')
            n_equations = n_img

        if n_equations < 2 * n_img:
            logger.warning('Number of equations is small. Consider increase memory_factor.')

        return n_equations

    def _generate_shift_phase_and_filter(self, r_max, max_shift, shift_step):
        """
        Prepare the shift phases and generate filter for common-line detection

        The shift phases are pre-defined in a range of max_shift that can be
        applied to maximize the common line calculation. The common-line filter
        is also applied to the radial direction for easier detection.
        :param r_max: Maximum index for common line detection
        :param max_shift: Maximum value of 1D shift (in pixels) to search
        :param shift_step: Resolution of shift estimation in pixels
        :return: shift phases matrix and common lines filter
        """

        # Number of shifts to try
        n_shifts = int(np.ceil(2 * max_shift / shift_step + 1))

        rk = np.arange(-r_max, r_max + 1)
        # Only half of ray is needed
        rk2 = rk[0:r_max]
        # Generate all shift phases
        shifts = -max_shift + shift_step * np.arange(n_shifts)
        shift_phases = np.exp(
            np.outer(-2 * np.pi * 1j * rk2 / (2 * r_max + 1), shifts))
        # Set filter for common-line detection
        h = np.sqrt(np.abs(rk)) * np.exp(-np.square(rk) / (2 * (r_max / 4) ** 2))
        return shifts, shift_phases, h

    def _generate_index_pairs(self, n_equations):
        """
        Generate two index lists for [i, j] pairs of images
        """
        idx_i = []
        idx_j = []
        for i in range(self.n_img - 1):
            tmp_j = range(i + 1, self.n_img)
            idx_i.extend([i] * len(tmp_j))
            idx_j.extend(tmp_j)
        idx_i = np.array(idx_i, dtype='int')
        idx_j = np.array(idx_j, dtype='int')

        # Select random pairs based on the size of n_equations
        rp = np.random.choice(np.arange(len(idx_j)), size=n_equations, replace=False)

        return idx_i[rp], idx_j[rp]

    def _get_cl_indices(self, rotations, i, j, n_theta):
        """
        Get common line indices based on the rotations from i and j images

        :param rotations: Array of rotation matrices
        :param i: Index for i image
        :param j: Index for j image
        :param n_theta: Total number of common lines
        :return: Common line indices for i and j images
        """
        # get the common line indices based on the rotations from i and j images
        r_i = rotations[i]
        r_j = rotations[j]
        c_ij, c_ji = common_line_from_rots(r_i.T, r_j.T, 2 * n_theta)

        # To match clmatrix, c_ij is always less than PI
        # and c_ji may be be larger than PI.
        if c_ij >= n_theta:
            c_ij -= n_theta
            c_ji -= n_theta
        if c_ji < 0:
            c_ji += 2 * n_theta

        c_ij = int(c_ij)
        c_ji = int(c_ji)

        return c_ij, c_ji

    def _apply_filter_and_norm(self, subscripts, pf,  r_max, h):
        """
        Apply common line filter and normalize each ray

        :subscripts: Specifies the subscripts for summation of Numpy
            `einsum` function
        :param pf: Fourier transform of images
        :param r_max: Maximum index for common line detection
        :param h: common lines filter
        :return: filtered and normalized i images
        """
        np.einsum(subscripts, pf, h, out=pf)
        pf[r_max - 1:r_max + 2] = 0
        pf /= np.linalg.norm(pf, axis=0)
        pf = pf[0:r_max]

        return pf
