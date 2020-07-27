"""Command line interface for pysradb
"""
import argparse
import os
import re
import sys
import warnings
from io import StringIO
from textwrap import dedent

import pandas as pd

from . import __version__
from .exceptions import IncorrectFieldException
from .exceptions import MissingQueryException
from .search import EnaSearch
from .search import GeoSearch
from .search import SraSearch
from .sradb import SRAdb
from .sradb import download_sradb_file
from .sraweb import SRAweb
from .utils import confirm

warnings.simplefilter(action="ignore", category=FutureWarning)


class CustomFormatterArgP(
    argparse.ArgumentDefaultsHelpFormatter, argparse.RawDescriptionHelpFormatter
):
    pass


class ArgParser(argparse.ArgumentParser):
    def error(self, message):
        sys.stderr.write("error: %s\n" % message)
        self.print_help()
        sys.exit(2)


def _print_save_df(df, saveto=None):
    if saveto:
        if saveto.lower().endswith(".csv"):
            #  if the save file format is csv
            df.to_csv(saveto, index=False, header=True)
        else:
            df.to_csv(saveto, index=False, header=True, sep="\t")
    else:
        if len(df.index):
            pd.set_option("display.max_colwidth", None)
            # Bug in pandas 0.25.3: https://github.com/pandas-dev/pandas/issues/24980
            # causes extra leading spaces
            to_print = df.to_string(
                index=False, justify="left", header=False, col_space=0
            ).lstrip()
            to_print_split = to_print.split(os.linesep)
            # Header formatting seems off when it is added via to_string()
            # method. Hence it is added to to_print separately
            to_print = ["\t".join(df.columns)]
            for line in to_print_split:
                to_print.append(line.lstrip())
            print(("{}".format(os.linesep)).join(to_print))


def _check_sradb_file(db):
    if db is None:
        db = os.path.join(os.getcwd(), "SRAmetadb.sqlite")
        if os.path.isfile(db):
            return db
        """
        if confirm(
            "SRAmetadb.sqlite file was not found in the current directory. Please quit and specify the path using `--db <DB_PATH>`"
            + os.linesep
            + "Otherwise, should I download SRAmetadb.sqlite in the current directory?"
        ):
            download_sradb_file()
        else:
            sys.exit(1)
        """
        # Use the web version
        return "web"

    if not os.path.isfile(db):
        raise RuntimeError("{} does not exist".format(db))
    return db


def get_sra_object(db="web"):
    if db == "web":
        return SRAweb()
    return SRAdb(db)


################### metadb #########################
def metadb(out_dir, overwrite, keep_gz):
    if out_dir is None:
        out_dir = os.getcwd()
    download_sradb_file(out_dir, overwrite, keep_gz)


#####################################################


###################### metadata ##############################
def metadata(srp_id, db, assay, desc, detailed, expand, saveto):
    db = _check_sradb_file(db)
    sradb = get_sra_object(db)
    df = sradb.sra_metadata(
        srp_id,
        assay=assay,
        detailed=detailed,
        sample_attribute=desc,
        expand_sample_attributes=expand,
    )
    _print_save_df(df, saveto)
    sradb.close()


################################################################


################# download ##########################
def download(out_dir, db, srx, srp, skip_confirmation, col="sra_url", use_wget=True):
    if use_wget:
        protocol = "ftp"
    else:
        protocol = "fasp"
    db = _check_sradb_file(db)
    if out_dir is None:
        out_dir = os.path.join(os.getcwd(), "pysradb_downloads")
    sradb = get_sra_object(db)
    if not srp:
        text = ""
        for index, line in enumerate(sys.stdin):
            line = line.strip()
            line = line.lstrip(" ")
            # pandas has different paddings to indent,
            # we cannot replace all sapces at once since the description column
            # can have text with space
            line = re.sub("\s\s\s", "\t", line)
            line = re.sub("\s\s", "\t", line)
            line = re.sub("\t+", "\t", line)
            line = re.sub("\s\t", "\t", line)
            line = re.sub("\t\s", "\t", line)

            if index == 0:
                # For first line which is the header, allow substituting spaces with tab at once
                line = re.sub("\s+", "\t", line)

            text += "{}\n".format(line)
        df = pd.read_csv(StringIO(text), sep="\t")
        sradb.download(
            df=df,
            out_dir=out_dir,
            filter_by_srx=srx,
            skip_confirmation=True,
            protocol=protocol,
            url_col=col,
        )
    else:
        for srp_x in srp:
            metadata = sradb.sra_metadata(srp_x, detailed=True)
            sradb.download(
                df=metadata,
                out_dir=out_dir,
                filter_by_srx=srx,
                skip_confirmation=skip_confirmation,
            )
    sradb.close()


#########################################################


######################### search #################################
def search(saveto, db, verbosity, return_max, fields):
    try:
        if db == "ena":
            instance = EnaSearch(
                verbosity,
                return_max,
                fields["query"],
                fields["accession"],
                fields["organism"],
                fields["layout"],
                fields["mbases"],
                fields["publication_date"],
                fields["platform"],
                fields["selection"],
                fields["source"],
                fields["strategy"],
                fields["title"],
            )
            instance.search()
        elif db == "geo":
            instance = GeoSearch(
                verbosity,
                return_max,
                fields["query"],
                fields["accession"],
                fields["organism"],
                fields["layout"],
                fields["mbases"],
                fields["publication_date"],
                fields["platform"],
                fields["selection"],
                fields["source"],
                fields["strategy"],
                fields["title"],
                fields["geo_query"],
                fields["geo_dataset_type"],
                fields["geo_entry_type"],
            )
            instance.search()
        else:
            instance = SraSearch(
                verbosity,
                return_max,
                fields["query"],
                fields["accession"],
                fields["organism"],
                fields["layout"],
                fields["mbases"],
                fields["publication_date"],
                fields["platform"],
                fields["selection"],
                fields["source"],
                fields["strategy"],
                fields["title"],
            )
            instance.search()
    except (MissingQueryException, IncorrectFieldException) as e:
        print(e)
        return

    _print_save_df(instance.get_df(), saveto)


####################################################################


######################### gse-to-gsm ###############################
def gse_to_gsm(gse_ids, db, saveto, detailed, desc, expand):
    db = _check_sradb_file(db)
    sradb = get_sra_object(db)
    df = sradb.gse_to_gsm(
        gse_ids,
        detailed=detailed,
        sample_attribute=desc,
        expand_sample_attributes=expand,
    )
    _print_save_df(df, saveto)
    sradb.close()


####################################################################


######################## gse-to-srp ################################
def gse_to_srp(gse_ids, db, saveto, detailed, desc, expand):
    db = _check_sradb_file(db)
    sradb = get_sra_object(db)
    df = sradb.gse_to_srp(
        gse_ids,
        detailed=detailed,
        sample_attribute=desc,
        expand_sample_attributes=expand,
    )
    _print_save_df(df, saveto)
    sradb.close()


######################################################################


######################### gsm-to-gse #################################
def gsm_to_gse(gsm_ids, db, saveto, detailed, desc, expand):
    db = _check_sradb_file(db)
    sradb = get_sra_object(db)
    df = sradb.gsm_to_gse(
        gsm_ids,
        detailed=detailed,
        sample_attribute=desc,
        expand_sample_attributes=expand,
    )
    _print_save_df(df, saveto)
    sradb.close()


########################################################################


############################ gsm-to-srp ################################
def gsm_to_srp(gsm_ids, db, saveto, detailed, desc, expand):
    db = _check_sradb_file(db)
    sradb = get_sra_object(db)
    df = sradb.gsm_to_srp(
        gsm_ids,
        detailed=detailed,
        sample_attribute=desc,
        expand_sample_attributes=expand,
    )
    _print_save_df(df, saveto)
    sradb.close()


########################################################################


############################ gsm-to-srr ################################
def gsm_to_srr(gsm_ids, db, saveto, detailed, desc, expand):
    db = _check_sradb_file(db)
    sradb = get_sra_object(db)
    df = sradb.gsm_to_srr(
        gsm_ids,
        detailed=detailed,
        sample_attribute=desc,
        expand_sample_attributes=expand,
    )
    _print_save_df(df, saveto)
    sradb.close()


########################################################################


############################ gsm-to-srs ################################
def gsm_to_srs(gsm_ids, db, saveto, detailed, desc, expand):
    db = _check_sradb_file(db)
    sradb = get_sra_object(db)
    df = sradb.gsm_to_srs(
        gsm_ids,
        detailed=detailed,
        sample_attribute=desc,
        expand_sample_attributes=expand,
    )
    _print_save_df(df, saveto)
    sradb.close()


########################################################################


############################# gsm-to-srx ###############################
def gsm_to_srx(gsm_ids, db, saveto, detailed, desc, expand):
    db = _check_sradb_file(db)
    sradb = get_sra_object(db)
    df = sradb.gsm_to_srx(
        gsm_ids,
        detailed=detailed,
        sample_attribute=desc,
        expand_sample_attributes=expand,
    )
    _print_save_df(df, saveto)
    sradb.close()


#########################################################################


########################### srp-to-gse ##################################
def srp_to_gse(srp_id, db, saveto, detailed, desc, expand):
    db = _check_sradb_file(db)
    sradb = get_sra_object(db)
    df = sradb.srp_to_gse(
        srp_id,
        detailed=detailed,
        sample_attribute=desc,
        expand_sample_attributes=expand,
    )
    _print_save_df(df, saveto)
    sradb.close()


#########################################################################


########################### srp-to-srr ##################################
def srp_to_srr(srp_id, db, saveto, detailed, desc, expand):
    db = _check_sradb_file(db)
    sradb = get_sra_object(db)
    df = sradb.srp_to_srr(
        srp_id,
        detailed=detailed,
        sample_attribute=desc,
        expand_sample_attributes=expand,
    )
    _print_save_df(df, saveto)
    sradb.close()


#########################################################################


########################### srp-to-srs ##################################
def srp_to_srs(srp_id, db, saveto, detailed, desc, expand):
    db = _check_sradb_file(db)
    sradb = get_sra_object(db)
    df = sradb.srp_to_srs(
        srp_id,
        detailed=detailed,
        sample_attribute=desc,
        expand_sample_attributes=expand,
    )
    _print_save_df(df, saveto)
    sradb.close()


#########################################################################


########################### srp-to-srx ##################################
def srp_to_srx(srp_id, db, saveto, detailed, desc, expand):
    db = _check_sradb_file(db)
    sradb = get_sra_object(db)
    df = sradb.srp_to_srx(
        srp_id,
        detailed=detailed,
        sample_attribute=desc,
        expand_sample_attributes=expand,
    )
    _print_save_df(df, saveto)
    sradb.close()


#########################################################################


########################### srr-to-gsm ##################################
def srr_to_gsm(srr_ids, db, saveto, detailed, desc, expand):
    db = _check_sradb_file(db)
    sradb = get_sra_object(db)
    df = sradb.srr_to_gsm(
        srr_ids,
        detailed=detailed,
        sample_attribute=desc,
        expand_sample_attributes=expand,
    )
    _print_save_df(df, saveto)
    sradb.close()


########################################################################


########################### srr-to-srp ##################################
def srr_to_srp(srr_ids, db, saveto, detailed, desc, expand):
    db = _check_sradb_file(db)
    sradb = get_sra_object(db)
    df = sradb.srr_to_srp(
        srr_ids,
        detailed=detailed,
        sample_attribute=desc,
        expand_sample_attributes=expand,
    )
    _print_save_df(df, saveto)
    sradb.close()


#########################################################################


########################### srr-to-srs ##################################
def srr_to_srs(srr_ids, db, saveto, detailed, desc, expand):
    db = _check_sradb_file(db)
    sradb = get_sra_object(db)
    df = sradb.srr_to_srs(
        srr_ids,
        detailed=detailed,
        sample_attribute=desc,
        expand_sample_attributes=expand,
    )
    _print_save_df(df, saveto)
    sradb.close()


#########################################################################


########################### srr-to-srx ##################################
def srr_to_srx(srr_ids, db, saveto, detailed, desc, expand):
    db = _check_sradb_file(db)
    sradb = get_sra_object(db)
    df = sradb.srr_to_srx(
        srr_ids,
        detailed=detailed,
        sample_attribute=desc,
        expand_sample_attributes=expand,
    )
    _print_save_df(df, saveto)
    sradb.close()


#########################################################################


########################### srs-to-gsm ##################################
def srs_to_gsm(srs_ids, db, saveto, detailed, desc, expand):
    db = _check_sradb_file(db)
    sradb = get_sra_object(db)
    df = sradb.srs_to_gsm(
        srs_ids,
        detailed=detailed,
        sample_attribute=desc,
        expand_sample_attributes=expand,
    )
    _print_save_df(df, saveto)
    sradb.close()


#########################################################################


########################### srs-to-srx ##################################
def srs_to_srx(srs_ids, db, saveto, detailed, desc, expand):
    db = _check_sradb_file(db)
    sradb = get_sra_object(db)
    df = sradb.srs_to_srx(
        srs_ids,
        detailed=detailed,
        sample_attribute=desc,
        expand_sample_attributes=expand,
    )
    _print_save_df(df, saveto)
    sradb.close()


#########################################################################


########################### srx-to-srp ##################################
def srx_to_srp(srx_ids, db, saveto, detailed, desc, expand):
    db = _check_sradb_file(db)
    sradb = get_sra_object(db)
    df = sradb.srx_to_srp(
        srx_ids,
        detailed=detailed,
        sample_attribute=desc,
        expand_sample_attributes=expand,
    )
    _print_save_df(df, saveto)
    sradb.close()


#########################################################################


########################### srx-to-srr ##################################
def srx_to_srr(srx_ids, db, saveto, detailed, desc, expand):
    db = _check_sradb_file(db)
    sradb = get_sra_object(db)
    df = sradb.srx_to_srr(
        srx_ids,
        detailed=detailed,
        sample_attribute=desc,
        expand_sample_attributes=expand,
    )
    _print_save_df(df, saveto)
    sradb.close()


#########################################################################


########################### srx-to-srs ##################################
def srx_to_srs(srx_ids, db, saveto, detailed, desc, expand):
    db = _check_sradb_file(db)
    sradb = get_sra_object(db)
    df = sradb.srx_to_srs(
        srx_ids,
        detailed=detailed,
        sample_attribute=desc,
        expand_sample_attributes=expand,
    )
    _print_save_df(df, saveto)
    sradb.close()


#########################################################################


def parse_args(args=None):
    """Argument parser"""
    parser = ArgParser(
        description=dedent(
            """\
    pysradb: Query NGS metadata and data from NCBI Sequence Read Archive.
    version: {}.
    Citation: 10.12688/f1000research.18676.1""".format(
                __version__
            )
        ),
        formatter_class=CustomFormatterArgP,
    )

    # pysradb subcommands
    subparsers = parser.add_subparsers(title="subcommands", dest="command")

    # pysradb --version
    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s {version}".format(version=__version__),
    )

    # pysradb --citation
    parser.add_argument(
        "--citation",
        action="version",
        version=dedent(
            """
        Choudhary, Saket. "pysradb: A Python Package to Query next-Generation Sequencing Metadata and Data from NCBI Sequence Read Archive." F1000Research, vol. 8, F1000 (Faculty of 1000 Ltd), Apr. 2019, p. 532 (https://f1000research.com/articles/8-532/v1)

        @article{Choudhary2019,
        doi = {10.12688/f1000research.18676.1},
        url = {https://doi.org/10.12688/f1000research.18676.1},
        year = {2019},
        month = apr,
        publisher = {F1000 (Faculty of 1000 Ltd)},
        volume = {8},
        pages = {532},
        author = {Saket Choudhary},
        title = {pysradb: A {P}ython package to query next-generation sequencing metadata and data from {NCBI} {S}equence {R}ead {A}rchive},
        journal = {F1000Research}
        }
        """
        ),
        help="how to cite",
    )

    # pysradb metadb
    subparser = subparsers.add_parser("metadb", help="Download SRAmetadb.sqlite")
    subparser.add_argument("--out-dir", type=str, help="Output directory location")
    subparser.add_argument(
        "--overwrite", action="store_true", help="Overwrite existing file"
    )
    subparser.add_argument(
        "--keep-gz",
        action="store_true",
        help="Should keep SRAmetadb.sqlite.gz post decompression",
    )
    subparser.set_defaults(func=metadb)

    # pysradb metadata
    subparser = subparsers.add_parser(
        "metadata", help="Fetch metadata for SRA project (SRPnnnn)"
    )
    subparser.add_argument("--saveto", help="Save metadata dataframe to file")
    subparser.add_argument("--db", help="Path to SRAmetadb.sqlite file", type=str)
    subparser.add_argument(
        "--assay", action="store_true", help="Include assay type in output"
    )
    subparser.add_argument(
        "--desc", action="store_true", help="Should sample_attribute be included"
    )
    subparser.add_argument(
        "--detailed", action="store_true", help="Display detailed metadata table"
    )
    subparser.add_argument(
        "--expand", action="store_true", help="Should sample_attribute be expanded"
    )
    subparser.add_argument("srp_id", nargs="+")
    subparser.set_defaults(func=metadata)

    # pysradb download
    subparser = subparsers.add_parser("download", help="Download SRA project (SRPnnnn)")
    subparser.add_argument("--out-dir", help="Output directory root")
    subparser.add_argument("--db", help="Path to SRAmetadb.sqlite file", type=str)
    subparser.add_argument("--srx", "-x", help="Download only these SRX(s)", nargs="+")
    subparser.add_argument("--srp", "-p", help="SRP ID", nargs="+")
    subparser.add_argument(
        "--skip-confirmation", "-y", action="store_true", help="Skip confirmation"
    )
    subparser.add_argument(
        "--use-wget", "-w", action="store_true", help="Use wget instead of aspera"
    )
    subparser.add_argument(
        "--col", help="Specify column to download", default="sra_url"
    )
    subparser.set_defaults(func=download)

    # pysradb search
    subparser = subparsers.add_parser("search", help="Search SRA/ENA for matching text")
    subparser.add_argument("--saveto", help="Save search result dataframe to file")
    subparser.add_argument(
        "--db",
        choices=["ena", "geo", "sra"],
        default="sra",
        help="Select the db API (sra, ena, or geo) to query, default = sra",
    )
    subparser.add_argument(
        "-v",
        "--verbosity",
        choices=[0, 1, 2, 3],
        default=2,
        help="Level of search result details (0, 1, 2 or 3), default = 2",
        type=int,
    )
    subparser.add_argument(
        "-m",
        "--max",
        default=20,
        help="Maximum number of entries to return, default = 20",
        type=int,
    )
    subparser.add_argument(
        "-q",
        "--query",
        nargs="+",
        help="Main query string. Note that if no query is supplied, at least one of the "
        "following flags must be present:",
    )
    subparser.add_argument("--accession", help="Accession number")
    subparser.add_argument(
        "--organism", nargs="+", help="Scientific name of the sample organism"
    )
    subparser.add_argument(
        "--layout", choices=["SINGLE", "PAIRED"], help="Library layout", type=str.upper
    )
    subparser.add_argument(
        "--mbases", help="Size of the sample rounded to the nearest megabase", type=int
    )
    subparser.add_argument(
        "--publication-date",
        help="Publication date of the run in the format dd-mm-yyyy. If a date range is desired, "
        "enter the start date, followed by end date, separated by a colon ':'.\n "
        "Example: 01-01-2010:31-12-2010",
    )
    subparser.add_argument("--platform", nargs="+", help="Sequencing platform")
    subparser.add_argument("--selection", nargs="+", help="Library selection")
    subparser.add_argument("--source", nargs="+", help="Library source")
    subparser.add_argument("--strategy", nargs="+", help="Library preparation strategy")
    subparser.add_argument("--title", nargs="+", help="Experiment title")

    # The following arguments are for GEO DataSets only
    subparser.add_argument(
        "--geo-query",
        nargs="+",
        help="Main query string for GEO DataSet. This flag is only used when db is set to be geo.",
    )
    subparser.add_argument(
        "--geo-dataset-type",
        nargs="+",
        help="GEO DataSet Type. This flag is only used when --db is set to be geo.",
    )
    subparser.add_argument(
        "--geo-entry-type",
        nargs="+",
        help="GEO Entry Type. This flag is only used when --db is set to be geo.",
    )

    subparser.set_defaults(func=search)

    # pysradb gse-to-gsm
    subparser = subparsers.add_parser("gse-to-gsm", help="Get GSM for a GSE")
    subparser.add_argument("--db", help="Path to SRAmetadb.sqlite file", type=str)
    subparser.add_argument("--saveto", help="Save output to file")
    subparser.add_argument(
        "--detailed",
        action="store_true",
        help="""Output additional columns: [sample_accession (SRS),
                                         run_accession (SRR),
                                         sample_alias (GSM),
                                         run_alias (GSM_r)]""",
    )
    subparser.add_argument(
        "--desc", action="store_true", help="Should sample_attribute be included"
    )
    subparser.add_argument(
        "--expand", action="store_true", help="Should sample_attribute be expanded"
    )
    subparser.add_argument("gse_ids", nargs="+")
    subparser.set_defaults(func=gse_to_gsm)

    # pysradb gse-to-srp
    subparser = subparsers.add_parser("gse-to-srp", help="Get SRP for a GSE")
    subparser.add_argument("--db", help="Path to SRAmetadb.sqlite file", type=str)
    subparser.add_argument("--saveto", help="Save output to file")
    subparser.add_argument(
        "--detailed",
        action="store_true",
        help="""Output additional columns: [experiment_accession (SRX),
                                           run_accession (SRR),
                                           sample_accession (SRS),
                                           experiment_alias (GSM_),
                                           run_alias (GSM_r),
                                           sample_alias (GSM)]
                                           """,
    )
    subparser.add_argument(
        "--desc", action="store_true", help="Should sample_attribute be included"
    )
    subparser.add_argument(
        "--expand", action="store_true", help="Should sample_attribute be expanded"
    )
    subparser.add_argument("gse_ids", nargs="+")
    subparser.set_defaults(func=gse_to_gsm)

    # pysradb gsm-to-gse
    subparser = subparsers.add_parser("gsm-to-gse", help="Get GSE for a GSM")
    subparser.add_argument("--db", help="Path to SRAmetadb.sqlite file", type=str)
    subparser.add_argument("--saveto", help="Save output to file")
    subparser.add_argument(
        "--detailed",
        action="store_true",
        help="""Output additional columns: [sample_accession (SRS),
                                            run_accession (SRR),
                                            sample_alias (GSM),
                                            run_alias (GSM_r)]""",
    )
    subparser.add_argument(
        "--desc", action="store_true", help="Should sample_attribute be included"
    )
    subparser.add_argument(
        "--expand", action="store_true", help="Should sample_attribute be expanded"
    )
    subparser.add_argument("gsm_ids", nargs="+")
    subparser.set_defaults(func=gsm_to_gse)

    # pysradb gsm-to-srp
    subparser = subparsers.add_parser("gsm-to-srp", help="Get SRP for a GSM")
    subparser.add_argument("--db", help="Path to SRAmetadb.sqlite file", type=str)
    subparser.add_argument(
        "--desc", action="store_true", help="Should sample_attribute be included"
    )
    subparser.add_argument(
        "--detailed",
        action="store_true",
        help="""Output additional columns: [experiment_accession (SRX),
                                            sample_accession (SRS),
                                            run_accession (SRR),
                                            experiment_alias (GSM),
                                            sample_alias (GSM),
                                            run_alias (GSM_r),
                                            study_alias (GSE)]""",
    )
    subparser.add_argument(
        "--expand", action="store_true", help="Should sample_attribute be expanded"
    )
    subparser.add_argument("--saveto", help="Save output to file")
    subparser.add_argument("gsm_ids", nargs="+")
    subparser.set_defaults(func=gsm_to_srp)

    # pysradb gsm-to-srr
    subparser = subparsers.add_parser("gsm-to-srr", help="Get SRR for a GSM")
    subparser.add_argument("--db", help="Path to SRAmetadb.sqlite file", type=str)
    subparser.add_argument(
        "--desc", action="store_true", help="Should sample_attribute be included"
    )
    subparser.add_argument(
        "--detailed",
        action="store_true",
        help="""Output additional columns: [experiment_accession (SRX),
                                            sample_accession (SRS),
                                            study_accession (SRS),
                                            run_alias (GSM_r),
                                            sample_alias (GSM),
                                            study_alias (GSE)]""",
    )
    subparser.add_argument(
        "--expand", action="store_true", help="Should sample_attribute be expanded"
    )
    subparser.add_argument("--saveto", help="Save output to file")
    subparser.add_argument("gsm_ids", nargs="+")
    subparser.set_defaults(func=gsm_to_srr)

    # pysradb gsm-to-srs
    subparser = subparsers.add_parser("gsm-to-srs", help="Get SRS for a GSM")
    subparser.add_argument("--db", help="Path to SRAmetadb.sqlite file", type=str)
    subparser.add_argument(
        "--desc", action="store_true", help="Should sample_attribute be included"
    )
    subparser.add_argument(
        "--detailed",
        action="store_true",
        help="""Output additional columns: [experiment_accession (SRX),
                                            run_accession (SRR),
                                            study_accession (SRP),
                                            run_alias (GSM_r),
                                            experiment_alias (GSM),
                                            study_alias (GSE)]""",
    )
    subparser.add_argument(
        "--expand", action="store_true", help="Should sample_attribute be expanded"
    )
    subparser.add_argument("--saveto", help="Save output to file")
    subparser.add_argument("gsm_ids", nargs="+")
    subparser.set_defaults(func=gsm_to_srs)

    # pysradb gsm-to-srx
    subparser = subparsers.add_parser("gsm-to-srx", help="Get SRX for a GSM")
    subparser.add_argument("--db", help="Path to SRAmetadb.sqlite file", type=str)
    subparser.add_argument(
        "--desc", action="store_true", help="Should sample_attribute be included"
    )
    subparser.add_argument(
        "--detailed",
        action="store_true",
        help="""Output additional columns: [experiment_accession (SRX),
                                            sample_accession (SRS),
                                            run_accession (SRR),
                                            experiment_alias (GSM),
                                            sample_alias (GSM),
                                            run_alias (GSM_r),
                                            study_alias (GSE)]""",
    )
    subparser.add_argument(
        "--expand", action="store_true", help="Should sample_attribute be expanded"
    )
    subparser.add_argument("--saveto", help="Save output to file")
    subparser.add_argument("gsm_ids", nargs="+")
    subparser.set_defaults(func=gsm_to_srx)

    # pysradb srp-to-gse
    subparser = subparsers.add_parser("srp-to-gse", help="Get GSE for a SRP")
    subparser.add_argument("--db", help="Path to SRAmetadb.sqlite file", type=str)
    subparser.add_argument("--saveto", help="Save output to file")
    subparser.add_argument(
        "--detailed",
        action="store_true",
        help="Output additional columns: [sample_accession, run_accession]",
    )
    subparser.add_argument(
        "--desc", action="store_true", help="Should sample_attribute be included"
    )
    subparser.add_argument(
        "--expand", action="store_true", help="Should sample_attribute be expanded"
    )
    subparser.add_argument("srp_id")
    subparser.set_defaults(func=srp_to_gse)

    # pysradb srp-to-srr
    subparser = subparsers.add_parser("srp-to-srr", help="Get SRR for a SRP")
    subparser.add_argument("--db", help="Path to SRAmetadb.sqlite file", type=str)
    subparser.add_argument("--saveto", help="Save output to file")
    subparser.add_argument(
        "--detailed",
        action="store_true",
        help="""Output additional columns: [experiment_accession (SRX),
                                            sample_accession (SRS),
                                            study_alias (GSE),
                                            experiment_alias (GSM),
                                            sample_alias (GSM_),
                                            run_alias (GSM_r)]""",
    )
    subparser.add_argument(
        "--desc", action="store_true", help="Should sample_attribute be included"
    )
    subparser.add_argument(
        "--expand", action="store_true", help="Should sample_attribute be expanded"
    )
    subparser.add_argument("srp_id")
    subparser.set_defaults(func=srp_to_srr)

    # pysradb srp-to-srs
    subparser = subparsers.add_parser("srp-to-srs", help="Get SRS for a SRP")
    subparser.add_argument("--db", help="Path to SRAmetadb.sqlite file", type=str)
    subparser.add_argument("--saveto", help="Save output to file")
    subparser.add_argument(
        "--detailed",
        action="store_true",
        help="""Output additional columns: [run_accession (SRR),
                                            study_accession (SRP),
                                            experiment_alias (GSM),
                                            sample_alias (GSM_),
                                            run_alias (GSM_r),
                                            study_alias (GSE)]""",
    )
    subparser.add_argument(
        "--desc", action="store_true", help="Should sample_attribute be included"
    )
    subparser.add_argument(
        "--expand", action="store_true", help="Should sample_attribute be expanded"
    )
    subparser.add_argument("srp_id")
    subparser.set_defaults(func=srp_to_srs)

    # pysradb srp-to-srx
    subparser = subparsers.add_parser("srp-to-srx", help="Get SRX for a SRP")
    subparser.add_argument("--db", help="Path to SRAmetadb.sqlite file", type=str)
    subparser.add_argument("--saveto", help="Save output to file")
    subparser.add_argument(
        "--detailed",
        action="store_true",
        help="""Output additional columns: [sample_accession (SRS),
                                            run_accession (SRR),
                                            experiment_alias (GSM),
                                            sample_alias (GSM_),
                                            run_alias (GSM_r)',
                                            study_alias (GSE)]""",
    )
    subparser.add_argument(
        "--desc", action="store_true", help="Should sample_attribute be included"
    )
    subparser.add_argument(
        "--expand", action="store_true", help="Should sample_attribute be expanded"
    )
    subparser.add_argument("srp_id")
    subparser.set_defaults(func=srp_to_srx)

    # pysradb srr-to-gsm
    subparser = subparsers.add_parser("srr-to-gsm", help="Get GSM for a SRR")
    subparser.add_argument("--db", help="Path to SRAmetadb.sqlite file", type=str)
    subparser.add_argument(
        "--detailed",
        action="store_true",
        help="""'Output additional columns: [experiment_accession (SRX),
                                             study_accession (SRP),
                                             run_alias (GSM_r),
                                             sample_alias (GSM_),
                                             experiment_alias (GSM),
                                             study_alias (GSE)]""",
    )
    subparser.add_argument(
        "--desc", action="store_true", help="Should sample_attribute be included"
    )
    subparser.add_argument(
        "--expand", action="store_true", help="Should sample_attribute be expanded"
    )
    subparser.add_argument("--saveto", help="Save output to file")
    subparser.add_argument("srr_ids", nargs="+")
    subparser.set_defaults(func=srr_to_gsm)

    # pysradb srr-to-srp
    subparser = subparsers.add_parser("srr-to-srp", help="Get SRP for a SRR")
    subparser.add_argument("--db", help="Path to SRAmetadb.sqlite file", type=str)
    subparser.add_argument(
        "--detailed",
        action="store_true",
        help="""'Output additional columns: [experiment_accession (SRX),
                                             sample_accession (SRS),
                                             run_alias (GSM_r),
                                             experiment_alias (GSM),
                                             sample_alias (GSM_),
                                             study_alias (GSE)]""",
    )
    subparser.add_argument(
        "--desc", action="store_true", help="Should sample_attribute be included"
    )
    subparser.add_argument(
        "--expand", action="store_true", help="Should sample_attribute be expanded"
    )
    subparser.add_argument("--saveto", help="Save output to file")
    subparser.add_argument("srr_ids", nargs="+")
    subparser.set_defaults(func=srr_to_srp)

    # pysradb srr-to-srs
    subparser = subparsers.add_parser("srr-to-srs", help="Get SRS for a SRR")
    subparser.add_argument("--db", help="Path to SRAmetadb.sqlite file", type=str)
    subparser.add_argument(
        "--detailed",
        action="store_true",
        help="""'Output additional columns: [experiment_accession (SRX),
                                             study_accession (SRP),
                                             run_alias (GSM_r),
                                             sample_alias (GSM_),
                                             experiment_alias (GSM),
                                             study_alias (GSE)]""",
    )
    subparser.add_argument(
        "--desc", action="store_true", help="Should sample_attribute be included"
    )
    subparser.add_argument(
        "--expand", action="store_true", help="Should sample_attribute be expanded"
    )
    subparser.add_argument("--saveto", help="Save output to file")
    subparser.add_argument("srr_ids", nargs="+")
    subparser.set_defaults(func=srr_to_srs)

    # pysradb srr-to-srx
    subparser = subparsers.add_parser("srr-to-srx", help="Get SRX for a SRR")
    subparser.add_argument("--db", help="Path to SRAmetadb.sqlite file", type=str)
    subparser.add_argument(
        "--detailed",
        action="store_true",
        help="""Output additional columns: [sample_accession (SRS),
                                            study_accession (SRP),
                                            run_alias (GSM_r),
                                            experiment_alias (GSM),
                                            sample_alias (GSM_),
                                            study_alias (GSE)]""",
    )
    subparser.add_argument(
        "--desc", action="store_true", help="Should sample_attribute be included"
    )
    subparser.add_argument(
        "--expand", action="store_true", help="Should sample_attribute be expanded"
    )
    subparser.add_argument("--saveto", help="Save output to file")
    subparser.add_argument("srr_ids", nargs="+")
    subparser.set_defaults(func=srr_to_srx)

    # pysradb srs-to-gsm
    subparser = subparsers.add_parser("srs-to-gsm", help="Get GSM for a SRS")
    subparser.add_argument("--db", help="Path to SRAmetadb.sqlite file", type=str)
    subparser.add_argument("--saveto", help="Save output to file")
    subparser.add_argument(
        "--detailed",
        action="store_true",
        help="Output additional columns: [run_accession, study_accession]",
    )
    subparser.add_argument(
        "--desc", action="store_true", help="Should sample_attribute be included"
    )
    subparser.add_argument(
        "--expand", action="store_true", help="Should sample_attribute be expanded"
    )
    subparser.add_argument("srs_ids", nargs="+")
    subparser.set_defaults(func=srs_to_gsm)

    # pysradb srs-to-srx
    subparser = subparsers.add_parser("srs-to-srx", help="Get SRX for a SRS")
    subparser.add_argument("--db", help="Path to SRAmetadb.sqlite file", type=str)
    subparser.add_argument("--saveto", help="Save output to file")
    subparser.add_argument(
        "--detailed",
        action="store_true",
        help="Output additional columns: [run_accession, study_accession]",
    )
    subparser.add_argument(
        "--desc", action="store_true", help="Should sample_attribute be included"
    )
    subparser.add_argument(
        "--expand", action="store_true", help="Should sample_attribute be expanded"
    )
    subparser.add_argument("srs_ids", nargs="+")
    subparser.set_defaults(func=srs_to_srx)

    # pysradb srx-to-srp
    subparser = subparsers.add_parser("srx-to-srp", help="Get SRP for a SRX")
    subparser.add_argument("--db", help="Path to SRAmetadb.sqlite file", type=str)
    subparser.add_argument(
        "--desc", action="store_true", help="Should sample_attribute be included"
    )
    subparser.add_argument(
        "--detailed",
        action="store_true",
        help="""Output additional columns: [run_accession (SRR),
                                            sample_accession (SRS),
                                            experiment_alias (GSM),
                                            run_alias (GSM_r),
                                            sample_alias (GSM),
                                            study_alias (GSE)]""",
    )
    subparser.add_argument(
        "--expand", action="store_true", help="Should sample_attribute be expanded"
    )
    subparser.add_argument("--saveto", help="Save output to file")
    subparser.add_argument("srx_ids", nargs="+")
    subparser.set_defaults(func=srx_to_srp)

    # pysradb srx-to-srr
    subparser = subparsers.add_parser("srx-to-srr", help="Get SRR for a SRX")
    subparser.add_argument("--db", help="Path to SRAmetadb.sqlite file", type=str)
    subparser.add_argument(
        "--desc", action="store_true", help="Should sample_attribute be included"
    )
    subparser.add_argument(
        "--detailed",
        action="store_true",
        help="Output additional columns: [sample_accession, study_accession]",
    )
    subparser.add_argument(
        "--expand", action="store_true", help="Should sample_attribute be expanded"
    )
    subparser.add_argument("--saveto", help="Save output to file")
    subparser.add_argument("srx_ids", nargs="+")
    subparser.set_defaults(func=srx_to_srr)

    # pysradb srx-to-srs
    subparser = subparsers.add_parser("srx-to-srs", help="Get SRS for a SRX")
    subparser.add_argument("--db", help="Path to SRAmetadb.sqlite file", type=str)
    subparser.add_argument("--saveto", help="Save output to file")
    subparser.add_argument(
        "--detailed",
        action="store_true",
        help="Output additional columns: [run_accession, study_accession]",
    )
    subparser.add_argument(
        "--desc", action="store_true", help="Should sample_attribute be included"
    )
    subparser.add_argument(
        "--expand", action="store_true", help="Should sample_attribute be expanded"
    )
    subparser.add_argument("srx_ids", nargs="+")
    subparser.set_defaults(func=srx_to_srs)

    args = parser.parse_args(args=None if sys.argv[1:] else ["--help"])
    if args.command == "metadb":
        metadb(args.out_dir, args.overwrite, args.keep_gz)
    elif args.command == "metadata":
        metadata(
            args.srp_id,
            args.db,
            args.assay,
            args.desc,
            args.detailed,
            args.expand,
            args.saveto,
        )
    elif args.command == "download":
        download(
            args.out_dir, args.db, args.srx, args.srp, args.skip_confirmation, args.col
        )
    elif args.command == "search":
        flags = vars(args)
        search(
            flags.pop("saveto"),
            flags.pop("db"),
            flags.pop("verbosity"),
            flags.pop("max"),
            flags,
        )
    elif args.command == "gse-to-gsm":
        gse_to_gsm(
            args.gse_ids, args.db, args.saveto, args.detailed, args.desc, args.expand
        )
    elif args.command == "gse-to-srp":
        gse_to_srp(
            args.gse_ids, args.db, args.saveto, args.detailed, args.desc, args.expand
        )
    elif args.command == "gsm-to-gse":
        gsm_to_gse(
            args.gsm_ids, args.db, args.saveto, args.detailed, args.desc, args.expand
        )
    elif args.command == "gsm-to-srp":
        gsm_to_srp(
            args.gsm_ids, args.db, args.saveto, args.detailed, args.desc, args.expand
        )
    elif args.command == "gsm-to-srr":
        gsm_to_srr(
            args.gsm_ids, args.db, args.saveto, args.detailed, args.desc, args.expand
        )
    elif args.command == "gsm-to-srs":
        gsm_to_srs(
            args.gsm_ids, args.db, args.saveto, args.detailed, args.desc, args.expand
        )
    elif args.command == "gsm-to-srx":
        gsm_to_srx(
            args.gsm_ids, args.db, args.saveto, args.detailed, args.desc, args.expand
        )
    elif args.command == "srp-to-gse":
        srp_to_gse(
            args.srp_id, args.db, args.saveto, args.detailed, args.desc, args.expand
        )
    elif args.command == "srp-to-srr":
        srp_to_srr(
            args.srp_id, args.db, args.saveto, args.detailed, args.desc, args.expand
        )
    elif args.command == "srp-to-srs":
        srp_to_srs(
            args.srp_id, args.db, args.saveto, args.detailed, args.desc, args.expand
        )
    elif args.command == "srp-to-srx":
        srp_to_srx(
            args.srp_id, args.db, args.saveto, args.detailed, args.desc, args.expand
        )
    elif args.command == "srr-to-gsm":
        srr_to_gsm(
            args.srr_ids, args.db, args.saveto, args.detailed, args.desc, args.expand
        )
    elif args.command == "srr-to-srp":
        srr_to_srp(
            args.srr_ids, args.db, args.saveto, args.detailed, args.desc, args.expand
        )
    elif args.command == "srr-to-srs":
        srr_to_srs(
            args.srr_ids, args.db, args.saveto, args.detailed, args.desc, args.expand
        )
    elif args.command == "srr-to-srx":
        srr_to_srx(
            args.srr_ids, args.db, args.saveto, args.detailed, args.desc, args.expand
        )
    elif args.command == "srs-to-gsm":
        srs_to_gsm(
            args.srs_ids, args.db, args.saveto, args.detailed, args.desc, args.expand
        )
    elif args.command == "srs-to-srx":
        srs_to_srx(
            args.srs_ids, args.db, args.saveto, args.detailed, args.desc, args.expand
        )
    elif args.command == "srx-to-srp":
        srx_to_srp(
            args.srx_ids, args.db, args.saveto, args.detailed, args.desc, args.expand
        )
    elif args.command == "srx-to-srr":
        srx_to_srr(
            args.srx_ids, args.db, args.saveto, args.detailed, args.desc, args.expand
        )
    elif args.command == "srx-to-srs":
        srx_to_srs(
            args.srx_ids, args.db, args.saveto, args.detailed, args.desc, args.expand
        )


if __name__ == "__main__":
    parse_args(sys.argv[1:])
