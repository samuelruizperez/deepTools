#!/usr/bin/env python
#-*- coding: utf-8 -*-

# own tools
import argparse
from deeptools import writeBedGraph
from deeptools import parserCommon
from deeptools import bamHandler

debug = 0


def parseArguments(args=None):
    parentParser = parserCommon.getParentArgParse()
    bamParser = parserCommon.read_options()
    requiredArgs = getRequiredArgs()
    optionalArgs = getOptionalArgs()
    outputParser = parserCommon.output()
    parser = \
        argparse.ArgumentParser(
            parents=[requiredArgs, outputParser, optionalArgs,
                     parentParser, bamParser],
            formatter_class=argparse.ArgumentDefaultsHelpFormatter,
            description='Given a BAM file, this tool generates a bigWig or '
            'bedGraph file of fragment or read coverages. The way the method '
            'works is by first calculating all the number of reads (either '
            'extended to match the fragment length or not) that overlap each '
            'bin in the genome.\nThe resulting read counts can be '
            'normalized using either a given scaling factor, the RPKM formula '
            'or to get a 1x depth of coverage (RPGC).\n '
            'In the case of paired-end mapping each read mate is treated '
            'independently to avoid a bias when a mixture of concordant and '
            'discordant pairs is present. This means that *each end* will '
            'be extended to match the fragment length.',
            usage='An example usage is: %(prog)s -b signal.bam -o signal.bw',
            add_help=False)

    return parser


def getRequiredArgs():
    parser = argparse.ArgumentParser(add_help=False)

    required = parser.add_argument_group('Required arguments')

    # define the arguments
    required.add_argument('--bam', '-b',
                          help='Bam file to process',
                          metavar='bam file',
                          required=True)

    return parser


def getOptionalArgs():

    parser = argparse.ArgumentParser(add_help=False)
    optional = parser.add_argument_group('Optional arguments')

    optional.add_argument("--help", "-h", action="help",
                          help="show this help message and exit")

    optional.add_argument('--bamIndex', '-bai',
                          help='Index for the bam file. Default is to consider '
                          'the path of the bam file adding the .bai suffix.',
                          metavar='bam file index')

    optional.add_argument('--scaleFactor',
                          help='Indicate a number that you would like to use. It can be used in combination'
                               'with the --normalizeTo1x or --normalizeUsingRPKM. In that case the computed'
                               'scaling factor will be multiplied by the given scale factor.  The default '
                               'scale factor is one',
                          default=1.0,
                          type=float,
                          required=False)

    optional.add_argument('--normalizeTo1x',
                          help='Report read coverage normalized to 1x '
                          'sequencing depth (also known as Reads Per Genomic '
                          'Content (RPGC)). Sequencing depth is defined as: '
                          '(total number of mapped reads * fragment length) / '
                          'effective genome size.\nThe scaling factor used '
                          'is the inverse of the sequencing depth computed '
                          'for the sample to match the 1x coverage. '
                          'To use this option, the '
                          'effective genome size has to be indicated after the '
                          'command. The effective genome size is the portion '
                          'of the genome that is mappable. Large fractions of '
                          'the genome are stretches of NNNN that should be '
                          'discarded. Also, if repetitive regions were not '
                          'included in the mapping of reads, the effective '
                          'genome size needs to be adjusted accordingly. '
                          'Common values are: mm9: 2150570000, '
                          'hg19:2451960000, dm3:121400000 and ce10:93260000. '
                          'See Table 2 of http://www.plosone.org/article/info:doi/10.1371/journal.pone.0030377 ' 
                          'or http://www.nature.com/nbt/journal/v27/n1/fig_tab/nbt.1518_T1.html '
                          'for several effective genome sizes.',
                          metavar= 'EFFECTIVE GENOME SIZE LENGTH',
                          default=None,
                          type=int,
                          required=False)


    optional.add_argument('--normalizeUsingRPKM',
                          help='Use Reads Per Kilobase per Million reads to '
                          'normalize the number of reads per bin. The formula '
                          'is: RPKM (per bin) =  number of reads per bin / '
                          '( number of mapped reads ( in millions) * bin '
                          'length (kb) ). Each read is considered independently,'
                          'if you want to only count either of the mate pairs in'
                          'paired-end data use the --samFlag',
                          action='store_true',
                          required=False)


    optional.add_argument('--ignoreForNormalization', '-ignore',
                          help='A list of chromosome names '
                          'separated by comma and limited by quotes, '
                          'containing those '
                          'chromosomes that want to be excluded '
                          'for computing the normalization. For example, '
                          ' --ignoreForNormalization "chrX, chrM" ')


    optional.add_argument('--missingDataAsZero',
                          default="yes",
                          choices=["yes", "no"],
                          help='Default is "yes". This parameter determines '
                          'if missing data should be treated as zeros. '
                          'If set to "no", missing data will be ignored '
                          'and not included in the output file. Missing '
                          'data is defined as those bins for which '
                          'no overlapping reads are found.')

    optional.add_argument('--smoothLength',
                           metavar="INT bp",
                           help='The smooth length defines a window, larger than '
                           'the binSize, to average the number of reads. For '
                           'example, if the --binSize is set to 20 bp and the '
                           '--smoothLength is set to 60 bp, then, for each '
                           'binSize the average of it and its left and right '
                           'neighbors is considered. Any value smaller than the '
                           '--binSize will be ignored and no smoothing will be '
                           'applied.',
                           type=int)

    return parser


def scaleFactor(string):
    try:
        scaleFactor1, scaleFactor2 = string.split(":")
        scaleFactors = (float(scaleFactor1), float(scaleFactor2))
    except:
        raise argparse.ArgumentTypeError(
            "Format of scaleFactors is factor1:factor2. "
            "The value given ( {} ) is not valid".format(string))
    return scaleFactors


def process_args():
    args = parseArguments().parse_args()

    if args.scaleFactor != 1: args.normalizeTo1x = None
    if args.smoothLength and args.smoothLength <= args.binSize:
        print "Warning: the smooth length given ({}) is smaller than the bin "\
            "size ({}).\n\n No smoothing will "\
            "be done".format(args.smoothLength,
                             args.binSize)
        args.smoothLength = None

    if args.ignoreForNormalization:
        args.ignoreForNormalization = \
            [x.strip() for x in args.ignoreForNormalization.split(',')]
    else:
        args.ignoreForNormalization = []

    return(args)


def main():
    args = process_args()

    bamHandle = bamHandler.openBam(args.bam, args.bamIndex)

    # if a list of chromosomes to remove from normalization
    # is given, remove their counts
    if len(args.ignoreForNormalization) > 0:
        import pysam
        # get the number of mapped reads but excluding
        # some undesired chromosomes
        bam_mapped = sum([int(y[2]) for y in
                           [x.split("\t") for x in
                            pysam.idxstats(bamHandle.filename)]
                           if y[0] not in args.ignoreForNormalization])
    else:
        bam_mapped = bamHandle.mapped

    binSize = args.binSize if args.binSize > 0 else 50
    fragmentLength = \
        args.fragmentLength if args.fragmentLength > 0 else 300

    global debug
    if args.verbose:
        debug = 1
    else:
        debug = 0

    if args.normalizeTo1x:
        current_coverage = \
            float(bam_mapped * fragmentLength) / args.normalizeTo1x
        # the scaling sets the coverage to match 1x
        args.scaleFactor *= 1.0 / current_coverage
        if debug:
            print "Estimated current coverage {}".format(current_coverage)
            print "Scaling factor {}".format(args.scaleFactor)

    elif args.normalizeUsingRPKM:
        # the RPKM is the # reads per tile / \
        #    ( total reads (in millions) * tile length in Kb)
        millionReadsMapped = float(bam_mapped)  / 1e6
        tileLengthInKb = float(args.binSize) / 1000

        args.scaleFactor *= 1.0 / (millionReadsMapped * tileLengthInKb)

        if debug:
            print "scale factor using RPKM is {0}".format(args.scaleFactor)

    funcArgs = {'scaleFactor': args.scaleFactor}
    zerosToNans = True if args.missingDataAsZero == 'no' else False
    wr = writeBedGraph.WriteBedGraph([bamHandle.filename],
                                    binLength=binSize,
                                    defaultFragmentLength=fragmentLength,
                                    stepSize=binSize,
                                    region=args.region,
                                    numberOfProcessors=args.numberOfProcessors,
                                    extendPairedEnds=args.extendPairedEnds,
                                    minMappingQuality=args.minMappingQuality,
                                    ignoreDuplicates=args.ignoreDuplicates,
                                    center_read=args.centerReads,
                                    zerosToNans=zerosToNans,
                                    samFlag_include=args.samFlagInclude,
                                    samFlag_exclude=args.samFlagExclude,
                                    )

    wr.run(writeBedGraph.scaleCoverage, funcArgs,  args.outFileName,
            format=args.outFileFormat, smooth_length=args.smoothLength)
