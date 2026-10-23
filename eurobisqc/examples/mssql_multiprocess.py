import sys
import time
import logging
import multiprocessing as mp

from dbworks import mssql_db_functions as mssql
from eurobisqc.util import misc
from eurobisqc.examples.mssql_pipeline import process_dataset_list
from eurobisqc import eurobis_dataset

this = sys.modules[__name__]
this.logger = logging.getLogger(__name__)
this.logger.level = logging.DEBUG
this.logger.addHandler(logging.StreamHandler())


def do_db_multi_random_percent(percent):
    """ Example of processing multiple datasets at the same time in
        order to exploit the computing resources (cores) performs a random
        selection of 2% of available datasets having less than 4000 records """

    start_time = time.time()

    # Now set to a percent of datasets...
    # sql_random_percent_of_datasets = f"SELECT id FROM dataproviders WHERE {percent} >= CAST(CHECKSUM(NEWID(), id) " \
    #                                  "& 0x7fffffff AS float) / CAST (0x7fffffff AS int)"

    # This selects percent from SMALL datasets (less than 4000 events/occurrences)
    sql_random_percent_of_datasets = f"select a.id, a.displayname, a.rec_count from " \
                                     f"(select d.id, d.displayname, rec_count from dataproviders d " \
                                     f"inner join eurobis e on e.dataprovider_id = d.id " \
                                     f"where rec_count <= 4000 group by d.id, d.displayname, rec_count) a " \
                                     f"where {percent} >= CAST(CHECKSUM(NEWID(), id) & 0x7fffffff AS float) " \
                                     f"/ CAST (0x7fffffff AS int) order by id "

    dataset_ids = []
    dataset_names = []

    # we dedicate to the task the total number of processors - 3 or 1 if we only have 2 cores or less.
    # Knowing that mssql needs 2 cores at least.
    reserve_cpus = 1 + (0 if not mssql.server_local else 2)

    if mp.cpu_count() > reserve_cpus:
        n_cpus = mp.cpu_count() - reserve_cpus
    else:
        n_cpus = 1

    pool = mp.Pool(n_cpus)

    # Connect to the database to get dataset list
    if not mssql.conn:
        mssql.open_db()

    if mssql.conn is None:
        # Should find a way to exit and advice
        this.logger.error("No connection to DB, nothing can be done! ")
        exit(0)
    else:
        # Fetch a random set of datasets
        cur = mssql.conn.cursor()
        cur.execute(sql_random_percent_of_datasets)
        for row in cur:
            dataset_ids.append(row[0])
            # tuples names - size
            dataset_names.append((row[0], row[1], row[2]))

    mssql.close_db()

    # Retrieved list, now need to split
    dataset_id_lists = misc.split_list(dataset_ids, n_cpus)  # We are OK until here.
    dataset_names_lists = misc.split_list(dataset_names, n_cpus)

    result_pool = []
    for i, dataset_id_list in enumerate(dataset_id_lists):
        this.logger.info(f"Pool {i} will process {dataset_names_lists[i]} ")
        result_pool.append(pool.apply_async(process_dataset_list, args=(i, dataset_id_list, True, True)))

    for r in result_pool:
        res = r.get()
        if res[1] > 0:
            this.logger.warning(f"Pool {res[0]} failed to process {res[1]} datasets")

    pool.terminate()
    pool.join()

    this.logger.info(f"Started at: {start_time}. All processes have completed after {time.time() - start_time}")


def do_db_multi_selection(dataset_ids, dataset_names, dataset_numbers = 0):
    """ Performs multiprocessing of a selection of known dataset ids with corresponding names
        Using this one the entire dataset can be run partitioning it by hand on different
        computers """

    start_time = time.time()

    # we dedicate to the task the total number of processors - 3 or 1 if we only have 2 cores or less.
    # Knowing that mssql needs 2 cores at least.
    reserve_cpus = 1 + (0 if not mssql.server_local else 2)

    if mp.cpu_count() > reserve_cpus:
        n_cpus = mp.cpu_count() - reserve_cpus
    else:
        n_cpus = 1

    pool = mp.Pool(n_cpus)

    # Retrieved list, now need to split
    if dataset_numbers:
        dataset_id_lists = misc.split_list_optimized(dataset_ids, n_cpus, dataset_numbers)
        dataset_names_lists = misc.split_list_optimized(dataset_names, n_cpus, dataset_numbers)
    else:
        dataset_id_lists = misc.split_list(dataset_ids, n_cpus)
        dataset_names_lists = misc.split_list(dataset_names, n_cpus)

    # Disable the qc index...
    # eurobis_dataset.EurobisDataset.disable_qc_index()

    result_pool = []
    for i, dataset_id_list in enumerate(dataset_id_lists):
        this.logger.info(f"Pool {i} will process {dataset_names_lists[i]}")
        result_pool.append(pool.apply_async(process_dataset_list, args=(i, dataset_id_list, True, True)))

    for r in result_pool:
        res = r.get()
        if res[1] > 0:
            this.logger.warning(f"Pool {res[0]} failed to process {res[1]} datasets")

    pool.terminate()
    pool.join()

    # Rebuild the QC index
    # eurobis_dataset.EurobisDataset.rebuild_qc_index()

    this.logger.info(f"Started at: {start_time}. All processes have completed after {time.time() - start_time}")

# Parallel processing of random 2% of the (SMALL) datasets
# call do_dataset_parallel_processing(0.02)
