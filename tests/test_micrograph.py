from unittest import TestCase
from aspire.io.micrograph import Micrograph

import os.path
MRC_FILE = os.path.join(os.path.dirname(__file__), 'saved_test_data', 'mrc_files', 'falcon_2012_06_12-14_33_35_0.mrc')
MRCS_FILE = os.path.join(os.path.dirname(__file__), 'saved_test_data', 'mrc_files', 'stack_0500_cor_DW.mrcs')


class MicrographTestCase(TestCase):
    def setUp(self):
        pass

    def tearDown(self):
        pass

    def testShape1(self):
        # Load a single micrograph and check it's shape
        micrograph = Micrograph(MRC_FILE, margin=100, shrink_factor=2)

        # Original Image = 4096 x 4096 -> remove 100px margins -> 3896 x 3896 -> shrink by 2 -> 1948 x 1948
        self.assertEqual(micrograph.im.shape, (1948, 1948))

    def testShape2(self):
        # Load a MRCS stack and check it's shape
        micrograph = Micrograph(MRCS_FILE)

        # The first 2 dimensions are the shape of each image, the last dimension the no. of images
        self.assertEqual(micrograph.im.shape, (200, 200, 267))
