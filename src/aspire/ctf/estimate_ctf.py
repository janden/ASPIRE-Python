import logging
import os

import mrcfile
import numpy as np

from aspire.basis.ffb_2d import FFBBasis2D
from aspire.ctf import CtfEstimator

logger = logging.getLogger(__name__)


def estimate_ctf(
    data_folder,
    pixel_size,
    cs,
    amplitude_contrast,
    voltage,
    num_tapers,
    psd_size,
    g_min,
    g_max,
    output_dir,
    dtype=np.float32,
):
    """
    Given paramaters estimates CTF from experimental data
    and returns CTF as a mrc file.
    """

    dtype = np.dtype(dtype)
    assert dtype in (np.float32, np.float64)

    dir_content = os.scandir(data_folder)

    mrc_files = [f.name for f in dir_content if os.path.splitext(f)[1] == ".mrc"]
    mrcs_files = [f.name for f in dir_content if os.path.splitext(f)[1] == ".mrcs"]
    file_names = mrc_files + mrcs_files

    amp = amplitude_contrast
    amplitude_contrast = np.arctan(
        amplitude_contrast / np.sqrt(1 - np.square(amplitude_contrast))
    )
    lmbd = 1.22639 / np.sqrt(voltage * 1000 + 0.97845 * np.square(voltage))

    ctf_object = CtfEstimator(
        pixel_size, cs, amplitude_contrast, voltage, psd_size, num_tapers, dtype=dtype
    )

    # Note for repro debugging, suggest use of doubles,
    #   closer to original code.
    ffbbasis = FFBBasis2D((psd_size, psd_size), 2, dtype=dtype)

    results = []
    for name in file_names:
        with mrcfile.open(
            os.path.join(data_folder, name), mode="r", permissive=True
        ) as mrc:
            micrograph = mrc.data

        # Try to match dtype used in Basis instance
        micrograph = micrograph.astype(dtype, copy=False)

        micrograph_blocks = ctf_object.preprocess(micrograph, psd_size)

        tapers_1d = ctf_object.tapers(psd_size, (2 * num_tapers) / psd_size, num_tapers)

        signal_observed = ctf_object.estimate_psd(
            micrograph_blocks, tapers_1d, num_tapers
        )

        thon_rings, _ = ctf_object.elliptical_average(
            ffbbasis, signal_observed, True
        )  # absolute differenceL 10^-14. Relative error: 10^-7

        # Optionally changing to: linprog_method='simplex',
        # will more deterministically repro results in exchange for speed.
        signal_1d, background_1d = ctf_object.background_subtract_1d(
            thon_rings, linprog_method="interior-point"
        )

        low_freq_skip = 12

        avg_defocus, low_freq_skip = ctf_object.opt1d(
            signal_1d,
            pixel_size,
            cs,
            lmbd,
            amplitude_contrast,
            signal_observed.shape[-1],
        )

        signal, background_2d = ctf_object.background_subtract_2d(
            signal_observed, background_1d, low_freq_skip
        )

        ratio = ctf_object.PCA(signal_observed, pixel_size, g_min, g_max)

        signal, additional_background = ctf_object.elliptical_average(
            ffbbasis, signal.sqrt(), False
        )

        background_2d = background_2d + additional_background

        initial_df1 = (avg_defocus * 2) / (1 + ratio)
        initial_df2 = (avg_defocus * 2) - initial_df1

        center = psd_size // 2
        [X, Y] = np.meshgrid(
            np.arange(0 - center, psd_size - center) / psd_size,
            np.arange(0 - center, psd_size - center) / psd_size,
        )

        rb = np.sqrt(np.square(X) + np.square(Y))
        r_ctf = rb * (10 / pixel_size)
        theta = np.arctan2(Y, X)

        angle = -75
        cc_array = np.zeros((6, 4))
        for a in range(0, 6):
            df1, df2, angle_ast, p = ctf_object.gd(
                signal,
                initial_df1,
                initial_df2,
                angle + np.multiply(a, 30),
                r_ctf,
                theta,
                pixel_size,
                g_min,
                g_max,
                amplitude_contrast,
                lmbd,
                cs,
            )

            cc_array[a, 0] = df1
            cc_array[a, 1] = df2
            cc_array[a, 2] = angle_ast
            cc_array[a, 3] = p
        ml = np.argmax(cc_array[:, 3], -1)

        result = (
            cc_array[ml, 0],
            cc_array[ml, 1],
            cc_array[ml, 2],
            cs,
            voltage,
            pixel_size,
            amp,
            name,
        )

        ctf_object.write_star(*result)
        results.append(result)

        ctf_object.set_df1(cc_array[ml, 0])
        ctf_object.set_df2(cc_array[ml, 1])
        ctf_object.set_angle(cc_array[ml, 2])
        ctf_object.generate_ctf()

        with mrcfile.new(
            output_dir + "/" + os.path.splitext(name)[0] + "_noise.mrc", overwrite=True
        ) as mrc:
            mrc.set_data(background_2d[0].astype(np.float32))
            mrc.voxel_size = pixel_size
            mrc.close()

        df = (cc_array[ml, 0] + cc_array[ml, 1]) * np.ones(theta.shape, theta.dtype) + (
            cc_array[ml, 0] - cc_array[ml, 1]
        ) * np.cos(2 * theta - 2 * cc_array[ml, 2] * np.ones(theta.shape, theta.dtype))
        ctf_im = -np.sin(
            np.pi
            * lmbd
            * np.power(r_ctf, 2)
            / 2
            * (df - np.power(lmbd, 2) * np.power(r_ctf, 2) * (cs * np.power(10, 6)))
            + amplitude_contrast
        )
        ctf_signal = np.zeros(ctf_im.shape, ctf_im.dtype)
        ctf_signal[: ctf_im.shape[0] // 2, :] = ctf_im[: ctf_im.shape[0] // 2, :]
        ctf_signal[ctf_im.shape[0] // 2 + 1 :, :] = signal[
            :, :, ctf_im.shape[0] // 2 + 1
        ]

        with mrcfile.new(
            output_dir + "/" + os.path.splitext(name)[0] + ".ctf", overwrite=True
        ) as mrc:
            mrc.set_data(np.float32(ctf_signal))
            mrc.voxel_size = pixel_size
            mrc.close()

    return results
