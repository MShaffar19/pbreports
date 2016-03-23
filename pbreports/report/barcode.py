
"""
Generate a report on SubreadSet barcoding.
"""

from collections import defaultdict
from pprint import pformat
import functools
import argparse
import logging
import time
import os
import re
import sys

from pbcommand.cli import pbparser_runner
from pbcommand.models.report import Report, Table, Column
from pbcommand.models import FileTypes, get_pbparser
from pbcommand.utils import setup_log
from pbcore.io import openDataSet, BarcodeSet


log = logging.getLogger(__name__)
__version__ = '0.6'


class Constants(object):
    TOOL_ID = "pbreports.tasks.barcode_report"
    TOOL_NAME = "barcode_report"
    DRIVER_EXE = "python -m pbreports.report.barcode --resolved-tool-contract"


def _labels_reads_iterator(reads, barcodes, subreads=True):
    with openDataSet(reads) as ds:
        movies = set()
        apply(movies.update, [rr.movieNames for rr in ds.resourceReaders()])
        if len(movies) != 1:  # FIXME
            raise NotImplementedError("Multiple-movie datasets are not " +
                                      "supported by this application.")
        assert ds.isIndexed
        zmws_by_barcode = defaultdict(set)
        reads_by_zmw = defaultdict(list)
        for rr in ds.resourceReaders():
            for i, (b, z) in enumerate(zip(rr.pbi.bcForward,
                                           rr.pbi.holeNumber)):
                zmws_by_barcode[b].add(z)
                reads_by_zmw[z].append((rr, i))
        with BarcodeSet(barcodes) as bc:
            for i_bc, barcode in enumerate(bc):
                zmws = sorted(list(zmws_by_barcode[i_bc]))
                for zmw in zmws:
                    for rr, i_read in reads_by_zmw[zmw]:
                        # FIXME(nechols)(2016-03-15) this will not work on CCS
                        qlen = rr.pbi.qEnd[i_read] - rr.pbi.qStart[i_read]
                        barcode_id = "{f}--{r}".format(
                            f=rr.pbi.bcForward[i_read]+1,
                            r=rr.pbi.bcReverse[i_read]+1)
                        yield barcode_id, barcode, ["n"] * qlen


def run_to_report(reads, barcodes, subreads=True, dataset_uuids=()):
    """ Generate a Report instance from a SubreadSet and BarcodeSet.
    :param subreads: If the ccs fofn is given this needs to be set to False
    """

    class MyRow(object):

        def __init__(self, label):
            self.label = label
            self.bases = 0
            self.reads = 0

    label2row = {}

    for label, barcode, read in _labels_reads_iterator(reads, barcodes,
                                                       subreads=subreads):
        if not label in label2row:
            label2row[label] = MyRow(label)
        label2row[label].bases += len(read)
        label2row[label].reads += 1

    columns = [Column('barcode', header="Barcode Name"),
               Column('number_of_reads', header="Reads"),
               Column('number_of_bases', header="Bases")]

    table = Table('barcode_table', title='Barcodes', columns=columns)
    labels = sorted(label2row.keys())
    for label in labels:
        row = label2row[label]
        table.add_data_by_column_id('barcode', label)
        table.add_data_by_column_id('number_of_reads', row.reads)
        table.add_data_by_column_id('number_of_bases', row.bases)

    report = Report('barcode', tables=[table],
                    dataset_uuids=dataset_uuids)
    return report


def args_runner(args):
    log.info("Starting {f} version {v} report generation".format(
        f=__file__, v=__version__))
    report = run_to_report(args.subreads, args.barcodes,
                           subreads=not args.ccs)
    log.info(pformat(report.to_dict()))
    report.write_json(args.report_json)
    return 0


def resolved_tool_contract_runner(rtc):
    log.info("Starting {f} version {v} report generation".format(
        f=__file__, v=__version__))
    dataset_uuids = [
        openDataSet(rtc.task.input_files[0]).uuid,
        BarcodeSet(rtc.task.input_files[1]).uuid
    ]
    report = run_to_report(
        reads=rtc.task.input_files[0],
        barcodes=rtc.task.input_files[1],
        subreads=True,
        dataset_uuids=dataset_uuids)
    log.info(pformat(report.to_dict()))
    report.write_json(rtc.task.output_files[0])
    return 0


def get_parser():
    p = get_pbparser(
        tool_id=Constants.TOOL_ID,
        version=__version__,
        name=Constants.TOOL_NAME,
        description=__doc__,
        driver_exe=Constants.DRIVER_EXE)
    p.add_input_file_type(FileTypes.DS_SUBREADS, "subreads",
                          name="BarcodedSubreadSet",
                          description="Barcoded Subread DataSet XML")
    p.add_input_file_type(FileTypes.DS_BARCODE, "barcodes",
                          name="BarcodeSet",
                          description="Barcode DataSet XML")
    p.add_output_file_type(FileTypes.REPORT, "report_json",
                           name="JSON report",
                           description="Path to write Report json output.",
                           default_name="barcode_report")
    # TODO(nechols)(2016-03-15) not yet supported in SA 3.x
    # this is necessary for BasH5Reader to handle the differences between the
    # .ccs.h5 files and .bas.h5 files.
    ap = p.arg_parser.parser
    ap.add_argument('--ccs', action='store_true',
                    help='Use consensus reads instead of subreads.')
    return p


def main(argv=sys.argv):
    return pbparser_runner(
        argv=argv[1:],
        parser=get_parser(),
        args_runner_func=args_runner,
        contract_runner_func=resolved_tool_contract_runner,
        alog=log,
        setup_log_func=setup_log)


if __name__ == '__main__':
    sys.exit(main())
