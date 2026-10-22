import argparse
from dbworks.create_lookup_tables import import_files

from eurobisqc.examples import mssql_pipeline
from eurobisqc.examples import fitness_for_use
parser = argparse.ArgumentParser(description='Calculate and save EuroBIS QC flags.')
parser.add_argument(
    '--providers', type=int, nargs='+',
    default=[1],
    help='Dataprovider IDs to process (defaults to the existing dataset list).',
)
args = parser.parse_args()
import_files()
mssql_pipeline.process_dataset_list(0, args.providers, False, True)
fitness_for_use.run(args.providers)