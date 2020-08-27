import os
import numpy as np

from unittest import TestCase

from aspire.source.simulation import Simulation
from aspire.utils.filters import RadialCTFFilter
from aspire.utils.preprocess import downsample
from aspire.orientation.commonline_sync import CLSyncVoting

import os.path
DATA_DIR = os.path.join(os.path.dirname(__file__), 'saved_test_data')


class OrientSyncTestCase(TestCase):

    # This function only run once
    @classmethod
    def setUpClass(cls):
        L = 32
        n = 64
        pixel_size = 5
        voltage = 200
        defocus_min = 1.5e4
        defocus_max = 2.5e4
        defocus_ct = 7
        Cs = 2.0
        alpha = 0.1

        np.random.seed(0)
        filters = [RadialCTFFilter(pixel_size, voltage, defocus=d, Cs=Cs, alpha=alpha) for d in
                   np.linspace(defocus_min, defocus_max, defocus_ct)]

        vols = np.load(os.path.join(DATA_DIR, 'clean70SRibosome_vol.npy'))
        vols = vols[..., np.newaxis]
        vols = downsample(vols, (L*np.ones(3, dtype=int)))

        cls.sim = Simulation(
            L=L,
            n=n,
            vols=vols,
            filters=filters
        )

        cls.orient_est = CLSyncVoting(cls.sim, L // 2, 36)
        cls.orient_est.build_clmatrix()
        cls.orient_est.syncmatrix_vote()
        np.random.seed(0)
        cls.orient_est.estimate_rotations()
        cls.est_rots = cls.orient_est.rotations
        np.random.seed(0)
        cls.est_shifts = cls.orient_est.estimate_shifts()

    def tearDown(self):
        pass

    def test01BuildCLmatrix(self):
        results = np.load(os.path.join(DATA_DIR, 'orient_est_clmatrix.npy'),
                          allow_pickle=True)
        self.assertTrue(np.allclose(results, self.orient_est.clmatrix))

    def test02SyncMatrixVote(self):
        results = np.load(os.path.join(DATA_DIR, 'orient_est_smatrix.npy'),
                          allow_pickle=True)
        self.assertTrue(np.allclose(results, self.orient_est.syncmatrix))

    def test03EstRotations(self):
        results = np.load(os.path.join(DATA_DIR, 'orient_est_rots.npy'),
                          allow_pickle=True)
        self.assertTrue(np.allclose(results, self.orient_est.rotations))

    def test04EstShifts(self):
        results = np.load(os.path.join(DATA_DIR, 'orient_est_shifts.npy'),
                          allow_pickle=True)
        self.assertTrue(np.allclose(results, self.est_shifts))
