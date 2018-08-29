import os
import numpy as np
from numpy.polynomial.legendre import leggauss
import scipy.special as sp
from abinitio.data_utils import *
import scipy.sparse as sps
import scipy.sparse.linalg as spsl
import scipy.linalg as scl
import scipy.optimize as optim
from pyfftw.interfaces import numpy_fft
import pyfftw
import mrcfile
import finufftpy
import time

np.random.seed(1137)


def run():
    algo = 2
    projs = mat_to_npy('projs')
    vol = cryo_abinitio_c1_worker(algo, projs)


def cryo_abinitio_c1_worker(alg, projs, outvol=None, outparams=None, showfigs=None, verbose=None, n_theta=360, n_r=0.5, max_shift=0.15, shift_step=1):
    num_projs = projs.shape[2]
    resolution = projs.shape[1]
    n_r *= resolution
    max_shift *= resolution
    n_r = int(np.ceil(n_r))
    max_shift = int(np.ceil(max_shift))

    if projs.shape[1] != projs.shape[0]:
        raise ValueError('input images must be squares')

    # why 0.45
    mask_radius = resolution * 0.45
    # mask_radius is ?.5
    if mask_radius * 2 == int(mask_radius * 2):
        mask_radius = int(np.ceil(mask_radius))
    # mask is not ?.5
    else:
        mask_radius = int(round(mask_radius))

    # mask projections
    m = fuzzy_mask(resolution, 2, mask_radius, 2)
    projs = projs.transpose((2, 0, 1))
    projs *= m
    projs = projs.transpose((1, 2, 0)).copy()

    # compute polar fourier transform
    pf, _ = cryo_pft(projs, n_r, n_theta)

    # find common lines from projections
    # clstack, _, _, _, _ = cryo_clmatrix_cpu(pf, num_projs, 1, max_shift, shift_step)
    clstack = np.load('clstack.npy')

    if alg == 1:
        raise NotImplementedError
    elif alg == 2:
        # s = cryo_syncmatrix_vote(clstack, n_theta)
        s = np.load('s.npy')
        rotations = cryo_sync_rotations(s)
    elif alg == 3:
        raise NotImplementedError
    else:
        raise ValueError('alg can only be 1, 2 or 3')
    return 0


def cryo_sync_rotations(s, rots_ref=None, verbose=0):
    tol = 1e-14
    ref = 0 if rots_ref is None else 1

    sz = s.shape
    if len(sz) != 2:
        raise ValueError('clmatrix must be a square matrix')
    if sz[0] != sz[1]:
        raise ValueError('clmatrix must be a square matrix')
    if sz[0] % 2 == 1:
        raise ValueError('clmatrix must be a square matrix of size 2Kx2K')

    k = sz[0] // 2

    # why 10
    d, v = sps.linalg.eigs(s, 10)
    d = np.real(d)
    sort_idx = np.argsort(-d)

    if verbose:
        print('Top eigenvalues:')
        print(d[sort_idx])

    # matlab here is weird
    v = fix_signs(np.real(v[:, sort_idx[:3]]))
    v1 = v[:2*k:2].T.copy()
    v2 = v[1:2*k:2].T.copy()


    # why not something like this
    # equations = np.zeros((3*k, 6))
    # counter = 0
    # for i in range(3):
    #     for j in range(3):
    #         if 3 * i + j in [0, 1, 2, 4, 5, 8]:
    #             equations[0::3, counter] = v1[i] * v1[j]
    #             equations[1::3, counter] = v2[i] * v2[j]
    #             equations[2::3, counter] = v1[i] * v2[j]
    #             counter += 1

    equations = np.zeros((3*k, 9))
    for i in range(3):
        for j in range(3):
            equations[0::3, 3*i+j] = v1[i] * v1[j]
            equations[1::3, 3*i+j] = v2[i] * v2[j]
            equations[2::3, 3*i+j] = v1[i] * v2[j]
    truncated_equations = equations[:, [0, 1, 2, 4, 5, 8]]

    b = np.ones(3 * k)
    b[2::3] = 0

    ata_vec = np.linalg.lstsq(truncated_equations, b)[0]
    ata = np.zeros((3, 3))
    ata[0, 0] = ata_vec[0]
    ata[0, 1] = ata_vec[1]
    ata[0, 2] = ata_vec[2]
    ata[1, 0] = ata_vec[1]
    ata[1, 1] = ata_vec[3]
    ata[1, 2] = ata_vec[4]
    ata[2, 0] = ata_vec[2]
    ata[2, 1] = ata_vec[4]
    ata[2, 2] = ata_vec[5]

    # need to check if this is upper or lower triangular matrix somehow
    a = np.linalg.cholesky(ata).T

    rotations = np.zeros((3, 3, k))
    r1 = np.dot(a, v1)
    r2 = np.dot(a, v2)
    r3 = np.cross(r1, r2)
    return 0


def cryo_syncmatrix_vote(clmatrix, l, rots_ref=0, is_perturbed=0):
    sz = clmatrix.shape
    if len(sz) != 2:
        raise ValueError('clmatrix must be a square matrix')
    if sz[0] != sz[1]:
        raise ValueError('clmatrix must be a square matrix')

    k = sz[0]
    s = np.eye(2 * k)

    for i in range(k - 1):
        stmp = np.zeros((2, 2, k))
        # why not using only one loop
        for j in range(i + 1, k):
            stmp[:, :, j] = cryo_syncmatrix_ij_vote(clmatrix, i, j, np.arange(k), l, rots_ref, is_perturbed)

        for j in range(i + 1, k):
            r22 = stmp[:, :, j]
            s[2 * i:2 * (i + 1), 2 * j:2 * (j + 1)] = r22
            s[2 * j:2 * (j + 1), 2 * i:2 * (i + 1)] = r22.T
    return s


def cryo_syncmatrix_ij_vote(clmatrix, i, j, k, l, rots_ref=None, is_perturbed=None):
    tol = 1e-12
    ref = 0 if rots_ref is None else 1

    good_k, _, _ = cryo_vote_ij(clmatrix, l, i, j, k, rots_ref, is_perturbed)

    rs, good_rotations = rotratio_eulerangle_vec(clmatrix, i, j, good_k, l)

    if ref == 1:
        reflection_mat = np.array([[1, 0, 0], [0, 1, 0], [0, 0, 1]])
        raise NotImplementedError

    if len(good_rotations) > 0:
        rk = np.mean(rs, 2)
        tmp_r = rs[:2, :2]
        diff = tmp_r - rk[:2, :2, np.newaxis]
        err = np.linalg.norm(diff) / np.linalg.norm(tmp_r)
        if err > tol:
            pass
    else:
        rk = np.zeros((3, 3))
        if ref == 1:
            raise NotImplementedError

    r22 = rk[:2, :2]
    return r22


def rotratio_eulerangle_vec(cl, i, j, good_k, n_theta):
    r = np.zeros((3, 3, len(good_k)))
    if i == j:
        return 0, 0

    tol = 1e-12

    idx1 = cl[good_k, j] - cl[good_k, i]
    idx2 = cl[j, good_k] - cl[j, i]
    idx3 = cl[i, good_k] - cl[i, j]

    a = np.cos(2 * np.pi * idx1 / n_theta)
    b = np.cos(2 * np.pi * idx2 / n_theta)
    c = np.cos(2 * np.pi * idx3 / n_theta)

    cond = 1 + 2 * a * b * c - (np.square(a) + np.square(b) + np.square(c))
    too_small_idx = np.where(cond <= 1.0e-5)[0]
    good_idx = np.where(cond > 1.0e-5)[0]

    a = a[good_idx]
    b = b[good_idx]
    c = c[good_idx]
    idx2 = idx2[good_idx]
    idx3 = idx3[good_idx]
    c_alpha = (a - b * c) / np.sqrt(1 - np.square(b)) / np.sqrt(1 - np.square(c))
    # why not c_alpha = (a - b * c) / (np.sqrt(1 - np.square(b) * 1 - np.square(c))

    ind1 = np.logical_or(idx3 > n_theta / 2 + tol, np.logical_and(idx3 < -tol, idx3 > -n_theta / 2))
    ind2 = np.logical_or(idx2 > n_theta / 2 + tol, np.logical_and(idx2 < -tol, idx2 > -n_theta / 2))
    c_alpha[np.logical_xor(ind1, ind2)] = -c_alpha[np.logical_xor(ind1, ind2)]

    aa = cl[i, j] * 2 * np.pi / n_theta
    bb = cl[j, i] * 2 * np.pi / n_theta
    alpha = np.arccos(c_alpha)

    ang1 = np.pi - bb
    ang2 = alpha
    ang3 = aa - np.pi
    sa = np.sin(ang1)
    ca = np.cos(ang1)
    sb = np.sin(ang2)
    cb = np.cos(ang2)
    sc = np.sin(ang3)
    cc = np.cos(ang3)

    r[0, 0, good_idx] = cc * ca - sc * cb * sa
    r[0, 1, good_idx] = -cc * sa - sc * cb * ca
    r[0, 2, good_idx] = sc * sb
    r[1, 0, good_idx] = sc * ca + cc * cb * sa
    r[1, 1, good_idx] = -sa * sc + cc * cb * ca
    r[1, 2, good_idx] = -cc * sb
    r[2, 0, good_idx] = sb * sa
    r[2, 1, good_idx] = sb * ca
    r[2, 2, good_idx] = cb

    if len(too_small_idx) > 0:
        r[:, :, too_small_idx] = 0

    return r, good_idx


def cryo_vote_ij(clmatrix, l, i, j, k, rots_ref, is_perturbed):
    ntics = 60
    x = np.linspace(0, 180, ntics, True)
    phis = np.zeros((len(k), 2))
    rejected = np.zeros(len(k))
    idx = 0
    rej_idx = 0
    if i != j and clmatrix[i, j] != -1:
        l_idx12 = clmatrix[i, j]
        l_idx21 = clmatrix[j, i]
        k = k[np.logical_and(np.logical_and(k != i, clmatrix[i, k] != -1), clmatrix[j, k] != -1)]

        l_idx13 = clmatrix[i, k]
        l_idx31 = clmatrix[k, i]
        l_idx23 = clmatrix[j, k]
        l_idx32 = clmatrix[k, j]

        theta1 = (l_idx13 - l_idx12) * 2 * np.pi / l
        theta2 = (l_idx21 - l_idx23) * 2 * np.pi / l
        theta3 = (l_idx32 - l_idx31) * 2 * np.pi / l

        c1 = np.cos(theta1)
        c2 = np.cos(theta2)
        c3 = np.cos(theta3)

        cond = 1 + 2 * c1 * c2 * c3 - (np.square(c1) + np.square(c2) + np.square(c3))

        good_idx = np.where(cond > 1e-5)[0]
        bad_idx = np.where(cond <= 1e-5)[0]

        cos_phi2 = (c3[good_idx] - c1[good_idx] * c2[good_idx]) / (np.sin(theta1[good_idx]) * np.sin(theta2[good_idx]))
        check_idx = np.where(np.abs(cos_phi2) > 1)[0]
        if np.any(np.abs(cos_phi2) - 1 > 1e-12):
            raise Warning('GCAR:numericalProblem')
        elif len(check_idx) == 0:
            cos_phi2[check_idx] = np.sign(cos_phi2[check_idx])

        phis[:idx + len(good_idx), 0] = cos_phi2
        phis[:idx + len(good_idx), 1] = k[good_idx]
        idx += len(good_idx)

        rejected[: rej_idx + len(bad_idx)] = k[bad_idx]
        rej_idx += len(bad_idx)

    phis = phis[:idx]
    rejected = rejected[:rej_idx]

    good_k = []
    peakh = -1
    alpha = -1  # why not alpha = []

    if idx > 0:
        angles = np.arccos(phis[:, 0]) * 180 / np.pi
        sigma = 3.0

        tmp = np.add.outer(np.square(angles), np.square(x))
        h = np.sum(np.exp((2 * np.multiply.outer(angles, x) - tmp) / (2 * sigma ** 2)), 0)
        peak_idx = h.argmax()
        peakh = h[peak_idx]
        idx = np.where(np.abs(angles - x[peak_idx]) < 360 / ntics)[0]
        good_k = phis[idx, 1]
        alpha = phis[idx, 0]

        if not np.isscalar(rots_ref):
            raise NotImplementedError
    return good_k.astype('int'), peakh, alpha


def cryo_clmatrix_cpu(pf, nk=None, verbose=1, max_shift=15, shift_step=1, map_filter_radius=0, ref_clmatrix=0, ref_shifts_2d=0):
    n_projs = pf.shape[2]
    n_shifts = int(np.ceil(2 * max_shift / shift_step + 1))
    n_theta = pf.shape[1]
    if n_theta % 2 == 1:
        raise ValueError('n_theta must be even')
    n_theta = n_theta // 2

    # why??
    pf = np.concatenate((np.flip(pf[1:, n_theta:], 0), pf[:, :n_theta]), 0).copy()

    found_ref_clmatrix = 0
    if not np.isscalar(ref_clmatrix):
        found_ref_clmatrix = 1

    found_ref_shifts = 0
    if not np.isscalar(ref_shifts_2d):
        found_ref_shifts = 1

    verbose_plot_shifts = 0
    verbose_detailed_debugging = 0
    verbose_progress = 0

    # Allocate variables
    clstack = np.zeros((n_projs, n_projs)) - 1
    corrstack = np.zeros((n_projs, n_projs))
    clstack_mask = np.zeros((n_projs, n_projs))
    refcorr = np.zeros((n_projs, n_projs))
    thetha_diff = np.zeros((n_projs, n_projs))

    # Allocate variables used for shift estimation
    shifts_1d = np.zeros((n_projs, n_projs))
    ref_shifts_1d = np.zeros((n_projs, n_projs))
    shifts_estimation_error = np.zeros((n_projs, n_projs))
    shift_i = np.zeros(4 * n_projs * nk)
    shift_j = np.zeros(4 * n_projs * nk)
    shift_eq = np.zeros(4 * n_projs * nk)
    shift_equations_map = np.zeros((n_projs, n_projs))
    shift_equation_idx = 0
    shift_b = np.zeros(n_projs * (n_projs - 1) // 2)
    dtheta = np.pi / n_theta

    # Debugging handles and variables - not implemented
    pass

    # search for common lines between pairs of projections
    r_max = int((pf.shape[0] - 1) / 2)
    rk = np.arange(-r_max, r_max + 1)
    h = np.sqrt(np.abs(rk)) * np.exp(-np.square(rk) / (2 * np.square(r_max / 4)))

    pf3 = np.zeros(pf.shape, dtype=pf.dtype)
    np.einsum('ijk, i -> ijk', pf, h, out=pf3)
    pf3[r_max - 1:r_max + 2] = 0
    pf3 /= np.linalg.norm(pf3, axis=0)

    # short for this code
    # pf3 = np.zeros(pf.shape, dtype=pf.dtype)
    # h = np.tile(h, (n_theta, 1)).T.copy()
    # for i in range(n_projs):
    #     proj = pf[:, :, i]
    #     proj *= h
    #     proj[r_max - 1:r_max + 2] = 0
    #     proj = cryo_ray_normalize(proj)
    #     pf3[:, :, i] = proj

    rk2 = rk[:r_max]
    for i in range(n_projs):
        n2 = min(n_projs - i, nk)

        # i think this is a bug, we want to sort only after we cut.
        subset_k2 = np.sort(np.random.permutation(n_projs - i - 1) + i + 1)
        subset_k2 = subset_k2[:n2]

        proj1 = pf3[:, :, i]
        p1 = proj1[:r_max].T
        p1_flipped = np.conj(p1)

        if np.linalg.norm(proj1[r_max]) > 1e-13:
            raise ValueError('DC component of projection is not zero.')

        for j in subset_k2:
            proj2 = pf3[:, :, j]
            p2 = proj2[:r_max]

            if np.linalg.norm(proj2[r_max]) > 1e-13:
                raise ValueError('DC component of projection is not zero.')

            if verbose_plot_shifts and found_ref_clmatrix:
                raise NotImplementedError

            tic = time.time()
            for shift in range(-max_shift, n_shifts, shift_step):
                shift_phases = np.exp(-2 * np.pi * 1j * rk2 * shift / (2 * r_max + 1))
                p1_shifted = shift_phases * p1
                p1_shifted_flipped = shift_phases * p1_flipped
                c1 = 2 * np.real(np.dot(p1_shifted.conj(), p2))
                c2 = 2 * np.real(np.dot(p1_shifted_flipped.conj(), p2))
                c = np.concatenate((c1, c2), 1)

                if map_filter_radius > 0:
                    raise NotImplementedError
                    # c = cryo_average_clmap(c, map_filter_radius)

                sidx = c.argmax()
                cl1, cl2 = np.unravel_index(sidx, c.shape)
                sval = c[cl1, cl2]
                improved_correlation = 0

                if sval > corrstack[i, j]:
                    clstack[i, j] = cl1
                    clstack[j, i] = cl2
                    corrstack[i, j] = sval
                    shifts_1d[i, j] = shift
                    improved_correlation = 1

                if verbose_detailed_debugging and found_ref_clmatrix and found_ref_shifts:
                    raise NotImplementedError

                if verbose_plot_shifts and improved_correlation:
                    raise NotImplementedError

                if verbose_detailed_debugging:
                    raise NotImplementedError

                if verbose_detailed_debugging:
                    raise NotImplementedError

            toc = time.time()
            # Create a shift equation for the projections pair (i, j).
            idx = np.arange(4 * shift_equation_idx, 4 * shift_equation_idx + 4)
            shift_alpha = clstack[i, j] * dtheta
            shift_beta = clstack[j, i] * dtheta
            shift_i[idx] = shift_equation_idx
            shift_j[idx] = [2 * i, 2 * i + 1, 2 * j, 2 * j + 1]
            if shift_equation_idx == 4950:
                print(1)
            shift_b[shift_equation_idx] = shifts_1d[i, j]

            # Compute the coefficients of the current equation.
            if shift_beta < np.pi:
                shift_eq[idx] = [np.sin(shift_alpha), np.cos(shift_alpha), -np.sin(shift_beta), -np.cos(shift_beta)]
            else:
                shift_beta -= np.pi
                shift_eq[idx] = [-np.sin(shift_alpha), -np.cos(shift_alpha), -np.sin(shift_beta), -np.cos(shift_beta)]

            shift_equations_map[i, j] = shift_equation_idx
            print(i, j, shift_equation_idx, toc - tic)
            shift_equation_idx += 1

            if verbose_progress:
                raise NotImplementedError

    if verbose_detailed_debugging and found_ref_clmatrix:
        raise NotImplementedError

    tmp = np.where(corrstack != 0)
    corrstack[tmp] = 1 - corrstack[tmp]
    l = 4 * shift_equation_idx
    # shift_equations = sps.csr_matrix((shift_eq[:l], (shift_i[:l], shift_j[:l])), shape=(shift_equation_idx, 2 * n_projs + 1))
    shift_eq[l: l + shift_equation_idx] = shift_b
    shift_i[l: l + shift_equation_idx] = np.arange(shift_equation_idx)
    shift_j[l: l + shift_equation_idx] = 2 * n_projs
    tmp = np.where(shift_eq != 0)[0]
    shift_eq = shift_eq[tmp]
    shift_i = shift_i[tmp]
    shift_j = shift_j[tmp]
    l += shift_equation_idx
    shift_equations = sps.csr_matrix((shift_eq, (shift_i, shift_j)), shape=(shift_equation_idx, 2 * n_projs + 1))

    if verbose_detailed_debugging:
        raise NotImplementedError

    return clstack, corrstack, shift_equations, shift_equations_map, clstack_mask


def cryo_ray_normalize(pf):
    n_theta = pf.shape[1]

    def normalize_one(p):
        for j in range(n_theta):
            nr = np.linalg.norm(p[:, j])
            if nr < 1e-3:
                raise Warning('Ray norm is close to zero.')
            p[:, j] /= nr
        return p

    if len(pf.shape) == 2:
        pf = normalize_one(pf)
    else:
        for k in range(pf.shape[2]):
            pf[:, :, k] = normalize_one(pf[:, :, k])
    return pf


def cryo_pft(p, n_r, n_theta):
    """
    Compute the polar Fourier transform of projections with resolution n_r in the radial direction
    and resolution n_theta in the angular direction.
    :param p:
    :param n_r: Number of samples along each ray (in the radial direction).
    :param n_theta: Angular resolution. Number of Fourier rays computed for each projection.
    :return:
    """
    if n_theta % 2 == 1:
        raise ValueError('n_theta must be even')

    n_projs = p.shape[2]
    omega0 = 2 * np.pi / (2 * n_r - 1)
    dtheta = 2 * np.pi / n_theta

    freqs = np.zeros((2, n_r * n_theta // 2))
    for i in range(n_theta // 2):
        freqs[0, i * n_r: (i + 1) * n_r] = np.arange(n_r) * np.sin(i * dtheta)
        freqs[1, i * n_r: (i + 1) * n_r] = np.arange(n_r) * np.cos(i * dtheta)

    freqs *= omega0
    pf = np.empty((n_r * n_theta // 2, n_projs), dtype='complex128', order='F')
    finufftpy.nufft2d2many(freqs[0], freqs[1], pf, 1, 1e-15, p)
    pf = pf.reshape((n_r, n_theta // 2, n_projs), order='F')
    pf = np.concatenate((pf, pf.conj()), axis=1).copy()
    return pf, freqs


def fuzzy_mask(n, dims, r0, rise_time, origin=None):
    if isinstance(n, int):
        n = np.array([n])

    if isinstance(r0, int):
        r0 = np.array([r0])

    center = (n + 1.0) / 2
    k = 1.782 / rise_time

    if dims == 1:
        if origin is None:
            origin = center
            origin = origin.astype('int')
        r = np.abs(np.arange(1 - origin[0], n - origin[0] + 1))

    elif dims == 2:
        if origin is None:
            origin = np.floor(n / 2) + 1
            origin = origin.astype('int')
        if len(n) == 1:
            x, y = np.mgrid[1 - origin[0]:n[0] - origin[0] + 1, 1 - origin[0]:n[0] - origin[0] + 1]
        else:
            x, y = np.mgrid[1 - origin[0]:n[0] - origin[0] + 1, 1 - origin[1]:n[1] - origin[1] + 1]

        if len(r0) < 2:
            r = np.sqrt(np.square(x) + np.square(y))
        else:
            r = np.sqrt(np.square(x) + np.square(y * r0[0] / r0[1]))

    elif dims == 3:
        if origin is None:
            origin = center
            origin = origin.astype('int')
        if len(n) == 1:
            x, y, z = np.mgrid[1 - origin[0]:n[0] - origin[0] + 1, 1 - origin[0]:n[0] - origin[0] + 1, 1 - origin[0]:n[0] - origin[0] + 1]
        else:
            x, y, z = np.mgrid[1 - origin[0]:n[0] - origin[0] + 1, 1 - origin[1]:n[1] - origin[1] + 1, 1 - origin[2]:n[2] - origin[2] + 1]

        if len(r0) < 3:
            r = np.sqrt(np.square(x) + np.square(y) + np.square(z))
        else:
            r = np.sqrt(np.square(x) + np.square(y * r0[0] / r0[1]) + np.square(z * r0[0] / r0[2]))
    else:
        return 0  # raise error

    m = 0.5 * (1 - sp.erf(k * (r - r0[0])))
    return m


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


run()
