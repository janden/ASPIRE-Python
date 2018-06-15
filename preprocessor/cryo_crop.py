# converted (and adjusted) from MATLAB func "cryo_crop.m"
import math
import numpy

from preprocessor.exceptions import DimensionsError


def cryo_crop(mat, n, is_stack=False, fill_value=0):
    """
        Reduce the size of the 1d array, square or cube m by cropping (or
        increase the size by padding with fill_value, by default zero) to a final
        size of [n, n] or [n, n, n]. This is the analogue of down-sample, but
        it doesn't change magnification.

        If m is 2-dimensional and n is a vector, m is cropped to n=[nx ny].

        The function handles odd and even-sized arrays correctly  The center of
        an odd array is taken to be at (n+1)/2, and an even array is n/2+1.

        If the flag isstack = 1 then a 3D array m is treated as a stack of 2D
        images, and each image is cropped to n x n.

        For 2D images, the input image doesn't have to be square.
        The result is double if fillval is double; by default the result is
        single.​
    """

    num_dimensions = len(mat.shape)
    if num_dimensions == 2 and 1 in mat.shape:
        num_dimensions = 1

    if num_dimensions == 1:  # mat is a vector
        mat = numpy.reshape(mat, [mat.size, 1])  # force a column vector
        ns = math.floor(mat.size / 2) - math.floor(n / 2)  # shift term for scaling down
        if ns >= 0:  # cropping
            result_mat = mat[ns: ns + n]

        else:  # padding
            result_mat = fill_value * numpy.ones([n, 1])
            result_mat[-ns: mat.size - ns] = mat

    elif num_dimensions == 2:  # mat is 2D image
        nx, ny = mat.shape
        nsx = math.floor(nx / 2) - math.floor(n / 2)  # shift term for scaling down
        nsy = math.floor(ny / 2) - math.floor(n / 2)

        if nsx >= 0:  # cropping
            result_mat = mat[nsx: nsx + n, nsy: nsy + n]

        else:  # padding
            result_mat = fill_value * numpy.ones([n, n])
            result_mat[-nsx: nx - nsx, -nsy: ny - nsy] = mat

    elif num_dimensions == 3:  # mat is 3D or a stack of 2D images

        if is_stack:
            # break down the stack and treat each image as an individual image
            # then return the cropped stack
            result_mat = numpy.zeros([mat.shape[0], n, n])
            for img in range(mat.shape[0]):
                result_mat[img, :, :] = cryo_crop(mat[img, :, :], n)

            return result_mat

        else:  # this is a 3D structure
            raise NotImplemented('cropping for 3D structure has not been implemented yet!')

    else:
        raise DimensionsError("cropping failed! number of dimensions is too big! "
                              f"({num_dimensions} while max is 3).")

    return result_mat
