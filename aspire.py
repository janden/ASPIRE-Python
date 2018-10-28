#!/usr/bin/env python3
import logging
import os
import sys
import click
import mrcfile

from aspire.common.logger import logger
from aspire.common.config import AspireConfig, PreProcessorConfig
from aspire.preprocessor import PreProcessor
from aspire.utils.compare_stacks import compare_stack_files
from aspire.utils.data_utils import load_stack_from_file
from aspire.utils.helpers import requires_finufftpy, yellow


@click.group(chain=False)
@click.option('--debug/--no-debug', default=False, help="Default is --no-debug.")
@click.option('-v', '--verbosity', default=0, help='Verbosity level (0-3).')
def simple_cli(debug, verbosity):
    """ Aspire tool accepts one command at a time, executes it and terminates\t
        \n To see usage of a command, simply type 'command --help'\t
        \n e.g. python aspire.py classify --help
    """
    AspireConfig.verbosity = verbosity
    if debug:
        logger.setLevel(logging.DEBUG)


@simple_cli.command('classify')
@click.argument('mrc_file', type=click.Path(exists=True))
@click.option('-o', '--output', default='classified.mrc', type=click.Path(exists=False),
              help='output file name')
@click.option("--avg_nn", default=50,
              help="Number of images to average into each class. (default=50)")
@click.option("--classification_nn", default=100,
              help=("Number of nearest neighbors to find for each "
                    "image during initial classification. (default=100)"))
@click.option("--k_vdm_in", default=20,
              help="Number of nearest neighbors for building VDM graph. (default=20")
@click.option("--k_vdm_out", default=200,
              help="Number of nearest neighbors to return for each image. (default=200)")
@requires_finufftpy
def classify_cmd(mrc_file, output, avg_nn, classification_nn, k_vdm_in, k_vdm_out):
    """ Classification-Averaging command """
    # TODO route optional args to the algoritm
    from aspire.class_averaging.averaging import ClassAverages
    logger.info('class-averaging..')
    ClassAverages.run(mrc_file, output, n_nbor=classification_nn, nn_avg=avg_nn)
    logger.info(f"saved to {yellow(output)}.")


@simple_cli.command('abinitio')
@click.argument('stack_file', type=click.Path(exists=True))
@click.option('-o', '--output', type=click.Path(exists=False), default='abinitio.mrc',
              help='output file name')
@requires_finufftpy
def abinitio_cmd(stack_file, output):
    """ Abinitio algorithm command. Abinitio accepts a file containig projections stack
        such as MRC/MRCS/NPY/MAT and saves the output to OUTPUT (default abinitio.mrc) """
    from aspire.abinitio import Abinitio
    logger.info(f'running abinitio on stack file {stack_file}..')

    # todo fix click.Path for "output" option
    if os.path.exists(output):
        logger.error(f"file {yellow(output)} already exsits! remove first "
                     "or use another name with '-o NAME'")
        return

    stack = load_stack_from_file(stack_file)
    output_stack = Abinitio.cryo_abinitio_c1_worker(stack)

    with mrcfile.new(output) as mrc_fh:
        mrc_fh.set_data(output_stack.astype('float32'))

    logger.info(f"saved to {yellow(output)}.")


@simple_cli.command('compare')
@click.argument('stack_file_1', type=click.Path(exists=True))
@click.argument('stack_file_2', type=click.Path(exists=True))
@click.option('--max-error', default=None, type=float,
              help='if given, raise an error once the err is bigger than given value')
def compare_cmd(stack_file_1, stack_file_2, max_error):
    """ Calculate the relative error between 2 stack files.
        Stack files can be in MRC/MRCS, NPY or MAT formats.
    """
    logger.info(f"calculating relative err between '{stack_file_1}' and '{stack_file_2}'..")
    relative_err = compare_stack_files(stack_file_1, stack_file_2,
                                       verbose=AspireConfig.verbosity, max_error=max_error)
    logger.info(f"relative err: {relative_err}")


@simple_cli.command('phaseflip')
@click.option('-o', '--output',
              help="output mrc file name (default adds '_phaseflipped' to input name)")
@click.argument('stack_file', type=click.Path(exists=True))
def phaseflip_cmd(stack_file, output):
    """ Apply global phase-flip to a stack file """
    logger.info("calculating global phaseflip..")
    PreProcessor.phaseflip_stack_file(stack_file, output_stack_file=output)


@simple_cli.command('crop')
@click.argument('stack_file', type=click.Path(exists=True))
@click.argument('size', type=int)
@click.option('--fill-value', type=float, default=PreProcessorConfig.crop_stack_fill_value)
@click.option('-o', '--output', help="output file name (default adds '_cropped' to input name)")
def crop_cmd(stack_file, size, output, fill_value):
    """ Crop projections in stack to squares of 'size x size' px.
        Then save the cropped stack into a new MRC file.
        In case size is bigger than original stack, padding will apply.
        When padding, `--fill-value=VAL` will be used for the padded values. """
    logger.info(f"resizing projections in {stack_file} to {size}x{size}..")
    PreProcessor.crop_stack_file(stack_file, size, output_stack_file=output, fill_value=fill_value)


@simple_cli.command('downsample')
@click.argument('stack_file', type=click.Path(exists=True))
@click.argument('side', type=int)
@click.option('--mask', default=None)
@click.option('-o', '--output', help="output file name (default adds '_downsampled' to input name)")
def downsample_cmd(stack_file, side, output, mask):
    """ Use Fourier methods to change the sample interval and/or aspect ratio
        of any dimensions of the input projections-stack to the output of SIZE x SIZE.
        If the optional mask argument is given, this is used as the
        zero-centered Fourier mask for the re-sampling. The size of mask should
        be the same as the output image size.
    """
    logger.info(f"downsampling stack {stack_file} to size {side}x{side} px..")
    PreProcessor.downsample_stack_file(stack_file, side, output_stack_file=output, mask_file=mask)


###################################################################
# The following is the foundation for creating a piped aspire cli
###################################################################
class PipedObj:
    """ This object will be passed between piped commands and be
        used for saving intermediate results and settings.
    """

    def __init__(self, mrc_file, debug, verbosity):
        self.stack = mrcfile.open(mrc_file).data
        self.debug = debug
        AspireConfig.verbosity = verbosity


pass_obj = click.make_pass_decorator(PipedObj, ensure=True)


@click.group(chain=True)
@click.option('--debug/--no-debug', default=False, help="Default is --no-debug.")
@click.option('-v', '--verbosity', default=0, help='Verbosity level (0-3).')
@click.argument('input_mrc')
@click.pass_context
def piped_cli(ctx, input_mrc, debug, verbosity):
    """ Piped cli accepts multiple commands, executes one by one and passes on
        the intermediate results on, between the commands. """
    logger.setLevel(debug)
    ctx.obj = PipedObj(input_mrc, debug, verbosity)  # control log/verbosity per command


@piped_cli.command("phaseflip")
@pass_obj
def phaseflip_stack(ctx_obj):
    """ Apply global phase-flip to an MRC stack """
    logger.debug("calculating global phaseflip..")
    ctx_obj.stack = PreProcessor.phaseflip_stack(ctx_obj.stack)


@piped_cli.command("save")
@click.option('-o', type=click.Path(exists=False), default='output.mrc', help='output file name')
@pass_obj
def chained_save_stack(ctx_obj, o):
    """ Save MRC stack to output file """
    if os.path.exists(o):  # TODO move this check before anything starts running
        logger.error("output file {} already exists! "
                     "please rename/delete or use flag -o with different output name")
        sys.exit(1)

    logger.info("saving stack {}..".format(o))
    mrcfile.new(o, ctx_obj.stack)


piped_cli.add_command(phaseflip_stack)
piped_cli.add_command(chained_save_stack)
...


if __name__ == "__main__":
    simple_cli()
    # piped_cli  # todo
