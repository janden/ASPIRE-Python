import os.path
from unittest import TestCase, skipUnless
from unittest.case import SkipTest

import numpy as np
import pytest

from aspire.nufft import Plan, backend_available
from aspire.utils.misc import complex_type

DATA_DIR = os.path.join(os.path.dirname(__file__), 'saved_test_data')


class SimTestCase(TestCase):

    def setUp(self):
        self.fourier_pts = np.array([
            [ 0.88952655922411,  0.35922344760724, -0.17107966400962, -0.70138277562649],
            [ 1.87089316522016,  1.99362869011803,  2.11636421501590,  2.23909973991377],
            [-3.93035749861843, -3.36417300942290, -2.79798852022738, -2.23180403103185]
        ])

        self.vol = np.load(os.path.join(DATA_DIR, 'nfft_volume.npy'))

        # Setup a 2D slice for testing 2d many
        self.plane = self.vol[0].T    # RCOPT
        self.vol = self.vol.T    # RCOPT

        self.recip_space = np.array([-0.05646675 + 1.503746j, 1.677600 + 0.6610926j, 0.9124417 - 0.7394574j, -0.9136836 - 0.5491410j])

        self.recip_space_plane = np.array([-0.14933796+0.00324942j,
                                           -0.29726508+0.07601329j,
                                           -0.26276074+0.12634184j,
                                           -0.09722212+0.12028122j],
                                          dtype=np.complex128)

        self.adjoint_vol = np.array([[[9.59495207e-01-1.06291322e+00j,  4.96001394e-01+1.60922425e+00j,
                               -2.78391527e+00-2.18820002e+00j,  4.53910627e+00+2.52530574e+00j,
                               -4.67770008e+00-2.29928671e+00j,  3.12346140e+00+1.42107788e+00j,
                               -8.35006613e-01-2.08392594e-01j, -8.61811880e-01-7.44775341e-01j],
                              [ 6.95609379e-01+1.21528480e+00j, -1.98693653e+00+6.99805141e-02j,
                                3.52261924e+00-1.86188461e+00j, -4.40227232e+00+3.06290826e+00j,
                                3.95080650e+00-2.99804116e+00j, -2.24070507e+00+1.82530148e+00j,
                                1.33509882e-01-3.53690847e-01j,  1.24778990e+00-5.47387355e-01j],
                              [-1.33450724e+00+3.51172971e-01j,  6.52415482e-01-2.28012935e+00j,
                               2.41584016e-01+4.38776505e+00j, -8.09711177e-01-5.38236472e+00j,
                               8.45459714e-01+4.54628775e+00j, -5.28057500e-01-2.26402471e+00j,
                               1.96011929e-01-1.93622742e-01j, -7.29420741e-02+1.50428070e+00j],
                              [-5.67875578e-02-1.41461172e+00j,  2.25953038e+00+1.66189272e+00j,
                               -4.40529657e+00-1.78799885e+00j,  5.16833043e+00+1.66557527e+00j,
                               -4.04985184e+00-1.17019140e+00j,  1.71256643e+00+3.71267910e-01j,
                               4.75782819e-01+4.08631004e-01j, -1.36051666e+00-7.80558742e-01j],
                              [ 1.52683244e+00+2.54429643e-01j, -2.77915719e+00+1.70545912e+00j,
                                3.73687261e+00-3.39672886e+00j, -3.72370373e+00+3.80423857e+00j,
                                2.54051450e+00-2.75141067e+00j, -6.99543332e-01+9.63394139e-01j,
                                -8.40657096e-01+4.72767394e-01j,  1.30811192e+00-8.36125573e-01j],
                              [-6.96113136e-01+1.64956662e+00j, -5.26556786e-01-3.67785088e+00j,
                               1.48197487e+00+5.05701967e+00j, -1.66956394e+00-4.84516408e+00j,
                               1.14523279e+00+3.01572872e+00j, -3.84547327e-01-5.39120190e-01j,
                               -1.06716909e-01-1.23019252e+00j,  1.13925960e-01+1.45913141e+00j],
                              [-1.65131058e+00-1.34345510e+00j,  3.98453418e+00+1.15295791e+00j,
                               -5.32538828e+00-9.22639650e-01j,  4.79627574e+00+6.42693834e-01j,
                               -2.66107919e+00-2.54914428e-01j,  1.57096046e-01-1.91604893e-01j,
                               1.33309475e+00+5.11125022e-01j, -1.19311268e+00-5.41755365e-01j],
                              [ 2.15238025e+00-1.33910059e+00j, -2.98313181e+00+3.42296122e+00j,
                                3.21543283e+00-4.39927175e+00j, -2.52080224e+00+3.69649112e+00j,
                                1.09283808e+00-1.79697223e+00j,  3.80379526e-01-1.31632250e-01j,
                                -1.13883648e+00+1.03630617e+00j,  9.00187963e-01-6.40239871e-01j]],
                             [[ 1.00527776e+00-5.13762619e-01j, -1.06516046e+00+9.44749860e-01j,
                                -3.74638887e-01-1.72273382e+00j,  2.55919554e+00+2.63463313e+00j,
                                -4.17049264e+00-3.19294288e+00j, 4.23169231e+00+2.93055160e+00j,
                                -2.74981604e+00-1.78183369e+00j,  6.69091601e-01+2.36886467e-01j],
                              [-4.43494995e-03+1.28361760e+00j, -5.72958286e-01-1.26784927e+00j,
                               2.08902195e+00+1.35249726e-01j, -3.86184881e+00+1.40214629e+00j,
                               4.83226894e+00-2.40070878e+00j, -4.27330560e+00+2.33513458e+00j,
                               2.34288389e+00-1.39461706e+00j, -5.45623939e-02+2.67186433e-01j],
                              [-1.24973045e+00-5.99696381e-01j,  1.36088033e+00-2.43608722e-01j,
                               -9.52580668e-01+2.30536579e+00j,  3.86913171e-01-4.48884773e+00j,
                               9.39514192e-03+5.44887089e+00j, -1.57026838e-01-4.50913493e+00j,
                               1.83309097e-01+2.14961395e+00j, -2.27116838e-01+2.90782995e-01j],
                              [ 1.08834945e+00-9.36268763e-01j, -4.64172267e-02+1.44241240e+00j,
                                -2.13412256e+00-2.01769468e+00j,  4.18583978e+00+2.44571181e+00j,
                                -4.84645323e+00-2.40092266e+00j, 3.71171852e+00+1.70306561e+00j,
                                -1.48897402e+00-5.46694434e-01j, -5.04690873e-01-5.29476600e-01j],
                              [ 4.70487024e-01+1.35942338e+00j, -1.56067010e+00-3.85532107e-01j,
                                3.09971530e+00-1.38419516e+00j, -4.24832288e+00+2.86210374e+00j,
                                4.20716570e+00-3.18144563e+00j, -2.80462870e+00+2.25309584e+00j,
                                7.03656405e-01-7.53980068e-01j,  9.76456992e-01-3.89055724e-01j],
                              [-1.41110761e+00+4.44961532e-04j,  8.84935439e-01-1.65935394e+00j,
                               2.55794780e-02+3.84488082e+00j, -7.36388646e-01-5.26702665e+00j,
                               9.18576248e-01+4.96571513e+00j, -6.55447805e-01-2.99622702e+00j,
                               2.78406473e-01+4.39557390e-01j, -7.39259240e-02+1.29735355e+00j],
                              [ 3.81671614e-01-1.32889127e+00j,  1.58058028e+00+1.58984228e+00j,
                                -3.89515019e+00-1.74369179e+00j,  5.15400777e+00+1.70039677e+00j,
                                -4.55267076e+00-1.32030127e+00j,  2.43497521e+00+5.99419596e-01j,
                                -5.31180397e-02+2.12374954e-01j, -1.27882407e+00-7.22662250e-01j],
                              [ 1.21850146e+00+6.79879859e-01j, -2.40966255e+00+1.13184483e+00j,
                                3.51667778e+00-3.03504998e+00j, -3.82515261e+00+3.87428727e+00j,
                                2.95991217e+00-3.19306165e+00j, -1.23035006e+00+1.49432506e+00j,
                                -4.85024387e-01+1.56037510e-01j,  1.29651185e+00-8.62558411e-01j]],
                             [[-6.86739810e-02-3.70300523e-01j, -1.12063667e+00+3.67172563e-01j,
                               1.15194738e+00-8.20547146e-01j,  2.30641371e-01+1.83610960e+00j,
                               -2.25827067e+00-3.06022668e+00j,  3.69690088e+00+3.80242117e+00j,
                               -3.69736000e+00-3.47632660e+00j,  2.33927662e+00+2.06262453e+00j],
                              [ 2.01642994e-01+3.70247627e-01j,  1.96353819e-01-1.30446538e+00j,
                                4.53478904e-01+1.30789388e+00j, -2.17336227e+00-3.70174142e-01j,
                                4.13698351e+00-8.78905523e-01j, -5.15569565e+00+1.67455149e+00j,
                                4.48187718e+00-1.64139406e+00j, -2.36823829e+00+9.75806650e-01j],
                              [-5.81347916e-01-2.32063891e-01j,  1.17258879e+00+7.75790302e-01j,
                               -1.38408986e+00+1.39407859e-01j,  1.27539559e+00-2.28945062e+00j,
                               -1.04103685e+00+4.49286635e+00j,  7.92773779e-01-5.38882066e+00j,
                               -5.00737218e-01+4.36485624e+00j,  1.14958382e-01-1.98652802e+00j],
                              [ 7.29282363e-01-4.52505342e-01j, -1.20273832e+00+7.93312198e-01j,
                                1.54394858e-01-1.47157901e+00j,  1.94926847e+00+2.37210665e+00j,
                                -3.86096638e+00-3.07488034e+00j,  4.41411827e+00+3.07399461e+00j,
                                -3.30379016e+00-2.15968977e+00j,  1.25586744e+00+6.65608991e-01j],
                              [ 1.90552895e-02+1.06915710e+00j, -3.09587185e-01-1.39877126e+00j,
                                1.59020799e+00+5.31672910e-01j, -3.38289188e+00+1.00170896e+00j,
                                4.67727196e+00-2.24529659e+00j, -4.58255956e+00+2.49582912e+00j,
                                2.97612347e+00-1.73789535e+00j, -6.65754916e-01+5.68583883e-01j],
                              [-1.10512212e+00-5.61257766e-01j,  1.39417670e+00+1.40277052e-01j,
                               -1.09240921e+00+1.64935310e+00j,  5.15335771e-01-3.93863575e+00j,
                               -4.05116064e-02+5.35922652e+00j, -1.68556483e-01-4.96502808e+00j,
                               1.97980361e-01+2.89906966e+00j, -2.11603565e-01-3.27366385e-01j],
                              [ 1.08436259e+00-8.19418542e-01j, -4.91742770e-01+1.28937713e+00j,
                                -1.47149005e+00-1.84499961e+00j,  3.71149228e+00+2.33217769e+00j,
                                -4.86159529e+00-2.44529713e+00j,  4.21030384e+00+1.93770771e+00j,
                                -2.16832530e+00-8.82399267e-01j, -3.38178272e-02-2.65736902e-01j],
                              [ 3.16520474e-01+1.38975107e+00j, -1.18046123e+00-7.77589784e-01j,
                                2.65147692e+00-8.75141081e-01j, -3.99619580e+00+2.55830010e+00j,
                                4.34457240e+00-3.26013709e+00j, -3.30268788e+00+2.63977923e+00j,
                                1.30455644e+00-1.19406495e+00j,  5.99181898e-01-1.46683240e-01j]],
                             [[-1.14690604e+00-6.55982045e-01j, -7.61877600e-02+3.55636826e-01j,
                               1.20901310e+00-2.00000544e-01j, -1.22094263e+00+6.93962155e-01j,
                               -6.09734088e-02-1.94494143e+00j,  1.88257130e+00+3.45125794e+00j,
                               -3.12826290e+00-4.33627181e+00j,  3.09113744e+00+3.92393143e+00j],
                              [ 9.66772110e-01-5.62132977e-01j, -8.86573691e-02-4.64356502e-01j,
                                -3.89631175e-01+1.29267510e+00j, -3.38373773e-01-1.33825087e+00j,
                                2.23291184e+00+6.34137453e-01j, -4.33589184e+00+3.01830087e-01j,
                                5.36260619e+00-9.02672832e-01j, -4.57468874e+00+9.36837573e-01j],
                              [-3.46552912e-02+8.77227736e-01j,  5.75097904e-01+3.88747592e-01j,
                               -1.06960345e+00-9.36002431e-01j,  1.40630326e+00-3.68793491e-02j,
                               -1.61490180e+00+2.22573853e+00j,  1.70466892e+00-4.39420448e+00j,
                               -1.57567238e+00+5.20339199e+00j,  1.11080277e+00-4.12233180e+00j],
                              [-4.77117802e-01-4.03353091e-01j, -8.58071418e-01+3.40926482e-01j,
                               1.29295881e+00-6.38936287e-01j, -2.70315705e-01+1.50151708e+00j,
                               -1.70246236e+00-2.71460524e+00j,  3.43475426e+00+3.65753839e+00j,
                               -3.88353239e+00-3.66740932e+00j,  2.84186794e+00+2.53121897e+00j],
                              [ 4.13935133e-01+1.91862212e-02j,  1.58938989e-01-1.11256935e+00j,
                                1.51412250e-01+1.41656053e+00j, -1.61152180e+00-6.94873844e-01j,
                                3.61678197e+00-5.62385992e-01j, -5.00981705e+00+1.56003783e+00j,
                                4.84170820e+00-1.76676213e+00j, -3.05633917e+00+1.22261111e+00j],
                              [-3.68756035e-01+9.67688559e-02j,  1.04259718e+00+7.42450956e-01j,
                               -1.36540790e+00-2.71328949e-01j,  1.31688861e+00-1.61379599e+00j,
                               -1.08460739e+00+3.95042963e+00j,  8.28904293e-01-5.32883334e+00j,
                               -5.60234996e-01+4.84644558e+00j,  2.15138284e-01-2.73403160e+00j],
                              [ 3.77708446e-01-4.04286837e-01j, -1.20978632e+00+6.72220800e-01j,
                                5.94782335e-01-1.24748100e+00j,  1.31949469e+00+2.10261059e+00j,
                                -3.43231473e+00-2.90232772e+00j,  4.45469659e+00+3.13743296e+00j,
                                -3.78238955e+00-2.48019282e+00j,  1.87472801e+00+1.10009206e+00j],
                              [ 1.01017126e-01+7.78134174e-01j, -1.33664623e-01-1.42870484e+00j,
                                1.14223139e+00+8.77057529e-01j, -2.86816696e+00+5.68988817e-01j,
                                4.40608703e+00-2.00090277e+00j, -4.76005765e+00+2.57308644e+00j,
                                3.54421407e+00-2.05479278e+00j, -1.32004566e+00+9.08083244e-01j]],
                             [[-1.19693802e+00-8.37659192e-01j,  9.82544543e-01+7.99667114e-01j,
                               2.12745665e-01-3.06952942e-01j, -1.26720324e+00+1.79372368e-02j,
                               1.27399573e+00-5.68062405e-01j, -1.36520458e-01+2.04380403e+00j,
                               -1.43610866e+00-3.79398813e+00j,  2.47754805e+00+4.77884847e+00j],
                              [ 1.37027493e+00-7.33349695e-01j, -9.85936092e-01+3.64218035e-01j,
                                -4.49749388e-02+5.30742295e-01j,  5.78226817e-01-1.24912294e+00j,
                                2.27921976e-01+1.36182410e+00j, -2.26039545e+00-9.24914566e-01j,
                                4.44803437e+00+3.17060417e-01j, -5.44633949e+00+1.04899212e-01j],
                              [ 2.11958802e-02+1.56743729e+00j,  1.84832990e-01-7.82154407e-01j,
                                -5.34383815e-01-5.44107076e-01j,  9.44784225e-01+1.07649788e+00j,
                                -1.42901784e+00-6.63403417e-02j,  1.96353752e+00-2.10851642e+00j,
                                -2.36054182e+00+4.19009950e+00j,  2.31865367e+00-4.89744616e+00j],
                              [-1.34003630e+00-6.86373228e-01j,  3.24895547e-01+4.49565576e-01j,
                               9.64714575e-01-2.02920439e-01j, -1.35862702e+00+4.77988325e-01j,
                               3.97288895e-01-1.53058694e+00j,  1.39316335e+00+3.03383419e+00j,
                               -2.91449701e+00-4.17638493e+00j,  3.26973739e+00+4.16621589e+00j],
                              [ 1.13612993e+00-7.75676715e-01j, -3.47738184e-01-1.50800701e-01j,
                                -3.44924195e-01+1.12276592e+00j,  7.98513156e-04-1.41526438e+00j,
                                1.61989135e+00+8.76240200e-01j, -3.79001165e+00+7.29661392e-02j,
                                5.23450231e+00-8.22498277e-01j, -4.98000205e+00+1.01464231e+00j],
                              [ 9.82081652e-02+1.18428473e+00j,  4.15240091e-01+4.11146167e-02j,
                                -9.49263839e-01-9.11332966e-01j,  1.32807927e+00+3.92423672e-01j,
                                -1.55529479e+00+1.54695244e+00j,  1.66884293e+00-3.87355644e+00j,
                                -1.60824204e+00+5.17457589e+00j,  1.24863649e+00-4.61678918e+00j],
                              [-8.55486958e-01-4.30877302e-01j, -5.17055458e-01+3.41054350e-01j,
                               1.30932287e+00-5.07586690e-01j, -6.93001128e-01+1.20488803e+00j,
                               -1.12116352e+00-2.35509086e+00j,  3.05927648e+00+3.43763539e+00j,
                               -3.94328058e+00-3.75824680e+00j,  3.28435866e+00+2.93580625e+00j],
                              [ 6.24453613e-01-3.27379432e-01j,  4.83087834e-02-8.50467248e-01j,
                                -4.94758327e-02+1.43962642e+00j, -1.10247505e+00-9.80946116e-01j,
                                3.04970566e+00-2.15314311e-01j, -4.73211907e+00+1.37389910e+00j,
                                5.06101686e+00-1.83155260e+00j, -3.68297927e+00+1.45651998e+00j]],
                             [[ 1.45172967e-02-2.52473566e-01j,  1.08514959e+00+1.03064337e+00j,
                                -7.98430024e-01-9.06752353e-01j, -3.33986032e-01+2.26982498e-01j,
                                1.29326203e+00+1.72901265e-01j, -1.31353744e+00+4.45166408e-01j,
                                3.62856223e-01-2.12643999e+00j,  9.25507595e-01+4.07516392e+00j],
                              [ 5.89742753e-01-7.73943338e-02j, -1.47678703e+00+5.21650586e-01j,
                                9.65729129e-01-1.72604500e-01j,  1.92903248e-01-5.65710900e-01j,
                                -7.56546708e-01+1.17585046e+00j, -1.21492852e-01-1.38134596e+00j,
                                2.24865056e+00+1.23862124e+00j, -4.46492401e+00-9.63680776e-01j],
                              [-1.90671351e-01+9.17355109e-01j,  2.18587299e-01-1.54156135e+00j,
                               -3.07006596e-01+6.61321961e-01j,  4.60215090e-01+6.91055492e-01j,
                               -8.02692856e-01-1.19446064e+00j,  1.45289056e+00+1.73099620e-01j,
                               -2.31229890e+00+1.93336247e+00j,  2.99077089e+00-3.88086799e+00j],
                              [-9.82997628e-01-7.12115983e-01j,  1.19059339e+00+8.69386113e-01j,
                               -1.70463468e-01-4.59409111e-01j, -1.04440320e+00+4.34838398e-02j,
                               1.40039579e+00-3.15062367e-01j, -5.38090846e-01+1.55611180e+00j,
                               -1.02300090e+00-3.31798821e+00j,  2.31057833e+00+4.61538081e+00j],
                              [ 1.24557384e+00-6.68927635e-01j, -1.20144702e+00+5.61758232e-01j,
                                2.53079382e-01+2.61576682e-01j,  5.32295497e-01-1.09903134e+00j,
                                -1.44642749e-01+1.39787596e+00j, -1.61000874e+00-1.07574759e+00j,
                                3.89221010e+00+4.57527557e-01j, -5.34275747e+00+5.08276913e-02j],
                              [ 4.20663810e-02+1.53251690e+00j,  9.70652325e-02-1.12048173e+00j,
                                -4.28103935e-01-1.87422129e-01j,  8.28382608e-01+1.06256744e+00j,
                                -1.28522392e+00-5.04174225e-01j,  1.80308946e+00-1.44346012e+00j,
                                -2.25320291e+00+3.70365917e+00j,  2.35790078e+00-4.89880206e+00j],
                              [-1.41689925e+00-6.80331646e-01j,  7.04097167e-01+5.36255746e-01j,
                               6.41772911e-01-2.46588248e-01j, -1.38093921e+00+3.30885169e-01j,
                               7.89014931e-01-1.16244156e+00j,  8.74482339e-01+2.59380000e+00j,
                               -2.59703728e+00-3.92172364e+00j,  3.34045318e+00+4.29113964e+00j],
                              [ 1.23049156e+00-9.14803621e-01j, -6.10242043e-01+1.63470674e-01j,
                                -2.13165068e-01+8.91996052e-01j,  2.28053402e-01-1.42408717e+00j,
                                1.05893002e+00+1.09151982e+00j, -3.18608795e+00-1.81912305e-01j,
                                4.96196127e+00-6.90929626e-01j, -5.24024691e+00+1.05551861e+00j]],
                             [[ 1.78709504e+00+1.29732516e+00j,  4.37647820e-02+3.35656379e-01j,
                                -9.36656013e-01-1.20382137e+00j,  6.02471592e-01+9.74462792e-01j,
                                4.33663009e-01-1.19831017e-01j, -1.28654231e+00-3.66252860e-01j,
                                1.34236572e+00-3.26731891e-01j, -6.17690504e-01+2.18600250e+00j],
                              [-1.43303874e+00+7.90404658e-01j, -6.99697163e-01+2.59124953e-02j,
                               1.54410214e+00-2.92114249e-01j, -9.08785605e-01-4.94808137e-03j,
                               -3.48199400e-01+5.66982267e-01j,  9.19670534e-01-1.07591940e+00j,
                               1.76178954e-02+1.39914261e+00j, -2.19099200e+00-1.56969880e+00j],
                              [-1.07463663e-01-1.07404599e+00j,  3.38631059e-01-9.67884234e-01j,
                               -4.49275418e-01+1.47309057e+00j,  3.96832361e-01-5.21434035e-01j,
                               -3.55018453e-01-8.22922554e-01j,  6.48194731e-01+1.28816502e+00j,
                               -1.47761511e+00-2.86505291e-01j,  2.65097874e+00-1.69747412e+00j],
                              [ 5.53393873e-01+1.00847165e-01j,  9.19483430e-01+8.91220923e-01j,
                                -1.01249527e+00-1.02009925e+00j,  2.15663730e-02+4.33638015e-01j,
                                1.09349255e+00+1.31574054e-01j, -1.41984431e+00+1.54276424e-01j,
                                6.94896309e-01-1.57444998e+00j,  5.95902533e-01+3.55524211e+00j],
                              [ 8.99818365e-02+1.99498021e-01j, -1.37128322e+00+4.92694114e-01j,
                                1.22485446e+00-3.44206994e-01j, -1.35245368e-01-3.46072260e-01j,
                                -7.14542694e-01+1.04199923e+00j,  2.78638644e-01-1.36768080e+00j,
                                1.57623647e+00+1.29207580e+00j, -3.91446984e+00-1.01795571e+00j],
                              [-1.99597598e-01+4.32928337e-01j,  1.91369132e-01-1.54080456e+00j,
                               -2.70751683e-01+1.02247056e+00j,  4.06411455e-01+3.34808417e-01j,
                               -6.84140048e-01-1.19169421e+00j,  1.23940913e+00+6.07994555e-01j,
                               -2.05432179e+00+1.29866291e+00j,  2.82183863e+00-3.43902791e+00j],
                              [-6.38728452e-01-5.35269372e-01j,  1.29328443e+00+8.87060798e-01j,
                               -5.39667874e-01-6.05276163e-01j, -7.45678467e-01+1.24620115e-01j,
                               1.42378307e+00-1.47616582e-01j, -8.85612133e-01+1.12005302e+00j,
                               -5.79112274e-01-2.80932039e+00j,  2.05324718e+00+4.33891167e+00j],
                              [ 1.01111712e+00-5.11400520e-01j, -1.33579061e+00+7.00509088e-01j,
                                5.61159931e-01-1.16719331e-02j,  3.86996353e-01-9.00231126e-01j,
                                -3.97853241e-01+1.38455374e+00j, -1.00851224e+00-1.21040043e+00j,
                                3.26775103e+00+6.16641265e-01j, -5.08567035e+00-3.21184000e-02j]],
                             [[ 3.00412828e+00+3.25590973e+00j, -1.46340680e+00-1.42240975e+00j,
                                -7.10549219e-02-4.36242075e-01j,  7.55877906e-01+1.34984210e+00j,
                                -4.02928826e-01-1.00171494e+00j, -5.06559002e-01-9.22344084e-03j,
                                1.24767279e+00+5.55987162e-01j, -1.36341089e+00+2.13298035e-01j],
                              [-3.83337126e+00+1.10383247e+00j,  1.37299822e+00-5.28719166e-01j,
                               7.99380664e-01+5.92153634e-02j, -1.56922672e+00+5.28361327e-02j,
                               8.19255719e-01+1.61442781e-01j,  5.03667462e-01-5.33765873e-01j,
                               -1.06353914e+00+9.53222202e-01j,  8.58820677e-02-1.41692091e+00j],
                              [ 6.35958847e-01-3.43433614e+00j, -1.54718782e-02+9.22328347e-01j,
                                -5.04320536e-01+9.86325819e-01j,  6.62655843e-01-1.36467744e+00j,
                                -4.51475205e-01+3.69893121e-01j,  2.22505710e-01+9.33733510e-01j,
                                -4.86203979e-01-1.35698918e+00j,  1.50185417e+00+4.09668465e-01j],
                              [ 2.36354603e+00+1.77374623e+00j, -4.19688560e-01-8.31064350e-02j,
                                -8.17957640e-01-1.06196592e+00j,  8.12828116e-01+1.13370454e+00j,
                                1.14433792e-01-3.74586440e-01j, -1.10962912e+00-3.15900501e-01j,
                                1.41932078e+00+9.17108271e-04j, -8.69026429e-01+1.58113060e+00j],
                              [-2.13061310e+00+1.08673060e+00j, -1.85770902e-01-1.62137261e-01j,
                               1.46484193e+00-2.90837347e-01j, -1.20690356e+00+1.31439126e-01j,
                               4.96030747e-04+4.00097339e-01j,  8.85527228e-01-9.53581085e-01j,
                               -4.02252430e-01+1.32801662e+00j, -1.51290500e+00-1.52250072e+00j],
                              [-4.93376895e-02-1.81859258e+00j,  2.75774308e-01-5.15265309e-01j,
                               -4.25576718e-01+1.50637960e+00j,  4.16692659e-01-8.95752391e-01j,
                               -3.50768710e-01-4.75946441e-01j,  5.21425192e-01+1.29528746e+00j,
                               -1.19254452e+00-7.05949858e-01j,  2.30175055e+00-1.10894167e+00j],
                              [ 1.15986178e+00+4.79957893e-01j,  6.31713873e-01+6.79893421e-01j,
                                -1.13431986e+00-1.06844775e+00j,  3.70131865e-01+6.36540729e-01j,
                                8.23535124e-01+1.99615224e-02j, -1.43815632e+00-3.68479566e-02j,
                                9.85503003e-01-1.07666914e+00j,  2.36591262e-01+2.99179398e+00j],
                              [-4.83278354e-01+5.35405301e-01j, -1.14268550e+00+3.88782017e-01j,
                               1.39982381e+00-4.72811154e-01j, -4.80945951e-01-1.21118001e-01j,
                               -5.62945787e-01+8.74090053e-01j,  5.55461782e-01-1.32420148e+00j,
                               9.47476817e-01+1.33834936e+00j, -3.28600548e+00-1.08079454e+00j]]]).T    # RCOPT

        self.adjoint_plane = np.array([
            [0.28276817+0.15660023j, -0.21264103+0.1325063j, -0.00666806-0.1822552j,
             0.10494716+0.0590003j, -0.06044544+0.02754128j,  0.01542389-0.02038304j,
             -0.02641121+0.01316627j, 0.0215158 -0.05030556j],
            [ 0.54833966+0.33850828j, -0.4958592 +0.28852081j, -0.01713981-0.49898315j,
              0.37897714+0.18819081j, -0.28442755+0.19914825j, -0.02887101-0.27192077j,
              0.18678311+0.08113525j, -0.11320052+0.08151796j],
            [ 0.69768533+0.51111915j, -0.74630965+0.36269529j,  0.0271063 -0.78358501j,
              0.63172175+0.3637445j , -0.56446735+0.35344828j, -0.04125834-0.59543717j,
              0.47733585+0.21476558j, -0.35533761+0.27220962j],
            [ 0.65654   +0.5830565j, -0.83763171+0.31681567j,  0.10977528-0.89399695j,
              0.73395449+0.50935065j, -0.77541578+0.40262967j,  0.00588976-0.84221936j,
              0.70430209+0.37900244j, -0.62136058+0.41564458j],
            [ 0.45551939+0.50553654j, -0.7169248 +0.18720528j,  0.17640627-0.77381197j,
              0.63754892+0.54242801j, -0.8065859 +0.32588577j,  0.08788936-0.88691676j,
              0.75201985+0.49518815j, -0.78544962+0.43340316j],
            [ 0.2040729 +0.31334696j, -0.4437996 +0.05144511j,  0.17955537-0.48801972j,
              0.40159172+0.4344763j,  -0.63566113+0.17655863j,  0.14807687-0.70699674j,
              0.60199882+0.49236828j, -0.75763457+0.32461718j],
            [ 0.01713837+0.10888565j, -0.15671647-0.02906575j,  0.11958363-0.1813168j,
              0.14886852+0.23912486j, -0.34893683+0.03792622j,  0.14555865-0.39746133j,
              0.33976368+0.36217065j, -0.54640878+0.15861484j],
            [-0.05256636-0.00471347j,  0.01359614-0.04566816j,  0.04580664+0.01237401j,
             -0.01350782+0.06196736j, -0.09008373-0.0351467j,   0.08978393-0.11075246j,
             0.09570568+0.1731567j,  -0.25950948+0.02134457j]
        ], dtype=np.complex128).T    # RCOPT


    def tearDown(self):
        pass

    def _testTransform(self, backend, dtype):
        if not backend_available(backend):
            raise SkipTest

        plan = Plan(self.vol.shape, self.fourier_pts.astype(dtype), backend=backend)
        result = plan.transform(self.vol.astype(dtype))
        self.assertTrue(np.allclose(result, self.recip_space))

    def _testTransformMany(self, backend, dtype, ntransforms=3):
        if not backend_available(backend):
            raise SkipTest

        plan = Plan(self.plane.shape, self.fourier_pts[0:2].astype(dtype),
                    backend=backend, ntransforms=ntransforms)

        # Note, this is how (cu)finufft transform wants it for now.
        # Can be refactored as part of row major cleanup.
        batch = np.empty((ntransforms, *self.plane.shape), dtype)
        for i in range(ntransforms):
            batch[i] = self.plane

        result = plan.transform(batch)

        for r in range(ntransforms):
            self.assertTrue(np.allclose(result[r], self.recip_space_plane))

    def _testAdjoint(self, backend, dtype):
        if not backend_available(backend):
            raise SkipTest

        complex_dtype = complex_type(dtype)

        atol = 1e-8    # Numpy default
        if dtype == np.float32:
            atol = 1e-5

        plan = Plan(self.vol.shape, self.fourier_pts.astype(dtype), backend=backend)

        # Test Adjoint
        result = plan.adjoint(self.recip_space.astype(complex_dtype))

        self.assertTrue(np.allclose(result, self.adjoint_vol, atol=atol))

    def _testAdjointMany(self, backend, dtype, ntransforms=2):
        if not backend_available(backend):
            raise SkipTest

        complex_dtype = complex_type(dtype)

        plan = Plan(self.plane.shape, self.fourier_pts[0:2].astype(dtype),
                    backend=backend, ntransforms=ntransforms)

        batch = np.empty((ntransforms, *self.recip_space_plane.shape), dtype=complex_dtype)
        for i in range(ntransforms):
            batch[i] = self.recip_space_plane

        # Test Adjoint
        result = plan.adjoint(batch)

        for r in range(ntransforms):
            self.assertTrue(np.allclose(result[r], self.adjoint_plane))

    # TODO: This list could be done better, as some sort of matrix
    #    once there are no raise exceptions, but more pressing things...

    def testTransform0_32(self):
        self._testTransform('cufinufft', np.float32)

    def testTransformMany0_32(self):
        self._testTransformMany('cufinufft', np.float32)

    def testAdjoint0_32(self):
        self._testAdjoint('cufinufft', np.float32)

    def testAdjointMany0_32(self):
        self._testAdjointMany('cufinufft', np.float32)

    def testTransformMany1_32(self):
        self._testTransformMany('finufft', np.float32)

    def testTransform1_32(self):
        self._testTransform('finufft', np.float32)

    def testAdjoint1_32(self):
        self._testAdjoint('finufft', np.float32)

    def testAdjointMany1_32(self):
        self._testAdjointMany('finufft', np.float32)

    def testTransform2_32(self):
        self._testTransform('pynfft', np.float32)

    def testAdjoint2_32(self):
        self._testAdjoint('pynfft', np.float32)

    def testTransform0_64(self):
        self._testTransform('cufinufft', np.float64)

    def testTransformMany0_64(self):
        self._testTransformMany('cufinufft', np.float64)

    def testTransformMany1_64(self):
        self._testTransformMany('finufft', np.float64)

    def testAdjoint0_64(self):
        self._testAdjoint('cufinufft', np.float64)

    def testAdjointMany0_64(self):
        self._testAdjointMany('cufinufft', np.float64)

    def testTransform1_64(self):
        self._testTransform('finufft', np.float64)

    def testAdjoint1_64(self):
        self._testAdjoint('finufft', np.float64)

    def testAdjointMany1_64(self):
        self._testAdjointMany('finufft', np.float64)

    def testTransform2_64(self):
        self._testTransform('pynfft', np.float64)

    def testAdjoint2_64(self):
        self._testAdjoint('pynfft', np.float64)
