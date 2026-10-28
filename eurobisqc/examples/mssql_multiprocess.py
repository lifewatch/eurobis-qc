import os
import sys
import time
import logging
from concurrent.futures import ProcessPoolExecutor, as_completed
from concurrent.futures.process import BrokenProcessPool

from dbworks import mssql_db_functions as mssql
from eurobisqc.util import misc
from eurobisqc.examples.mssql_pipeline import process_dataset_list
from eurobisqc import eurobis_dataset

this = sys.modules[__name__]
this.logger = logging.getLogger(__name__)
this.logger.level = logging.DEBUG
this.logger.addHandler(logging.StreamHandler())


def available_cpus():
    """ The number of cpus this process may use. os.cpu_count() returns all cores of the host,
        also inside a container limited with 'cpus:', so the cgroup quota is read as well """

    cpus = len(os.sched_getaffinity(0))
    try:
        with open("/sys/fs/cgroup/cpu.max") as f:
            quota, period = f.read().split()
        if quota != "max":
            cpus = min(cpus, max(1, int(quota) // int(period)))
    except (OSError, ValueError):
        pass
    return cpus


def number_of_processes():
    """ The number of processes for the pool: QC_PROCESSES from the environment if set, otherwise
        the available cpus - 3 or 1 if we only have 2 cores or less.
        Knowing that mssql needs 2 cores at least. """

    if os.environ.get("QC_PROCESSES"):
        return max(1, int(os.environ["QC_PROCESSES"]))

    reserve_cpus = 1 + (0 if not mssql.server_local else 2)
    cpus = available_cpus()

    if cpus > reserve_cpus:
        return cpus - reserve_cpus
    return 1


def run_pools(dataset_id_lists, dataset_names_lists, n_cpus):
    """ Runs process_dataset_list for every list of datasets in its own process.
        If a process dies (for instance killed because the container ran out of memory)
        BrokenProcessPool is raised, where multiprocessing.Pool would wait forever
        :param dataset_id_lists: One list of dataset ids per pool
        :param dataset_names_lists: The corresponding names, for logging
        :param n_cpus: Number of processes """

    completed = set()

    with ProcessPoolExecutor(n_cpus) as executor:
        futures = {}
        for i, dataset_id_list in enumerate(dataset_id_lists):
            this.logger.info(f"Pool {i} will process {dataset_names_lists[i]}")
            futures[executor.submit(process_dataset_list, i, dataset_id_list, True, True)] = i

        try:
            for future in as_completed(futures):
                res = future.result()
                completed.add(futures[future])
                if isinstance(res, tuple) and res[1] > 0:
                    this.logger.warning(f"Pool {res[0]} failed to process {res[1]} datasets")
        except BrokenProcessPool:
            this.logger.error("A QC process died unexpectedly, probably killed for using too much memory "
                              "(check oom_kill in /sys/fs/cgroup/memory.events). Stopping all processes.")
            for i in sorted(set(futures.values()) - completed):
                this.logger.error(f"Pool {i} did not complete, its datasets: {dataset_id_lists[i]}")
            raise


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

    n_cpus = number_of_processes()
    this.logger.info(f"Using {n_cpus} processes")

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

    run_pools(dataset_id_lists, dataset_names_lists, n_cpus)

    this.logger.info(f"Started at: {start_time}. All processes have completed after {time.time() - start_time}")


def do_db_multi_selection(dataset_ids, dataset_names, dataset_numbers = 0):
    """ Performs multiprocessing of a selection of known dataset ids with corresponding names
        Using this one the entire dataset can be run partitioning it by hand on different
        computers """

    start_time = time.time()

    n_cpus = number_of_processes()
    this.logger.info(f"Using {n_cpus} processes")

    # Retrieved list, now need to split
    if dataset_numbers:
        dataset_id_lists = misc.split_list_optimized(dataset_ids, n_cpus, dataset_numbers)
        dataset_names_lists = misc.split_list_optimized(dataset_names, n_cpus, dataset_numbers)
    else:
        dataset_id_lists = misc.split_list(dataset_ids, n_cpus)
        dataset_names_lists = misc.split_list(dataset_names, n_cpus)

    # Disable the qc index...
    # eurobis_dataset.EurobisDataset.disable_qc_index()

    run_pools(dataset_id_lists, dataset_names_lists, n_cpus)

    # Rebuild the QC index
    # eurobis_dataset.EurobisDataset.rebuild_qc_index()

    this.logger.info(f"Started at: {start_time}. All processes have completed after {time.time() - start_time}")

# Parallel processing of random 2% of the (SMALL) datasets
# call do_dataset_parallel_processing(0.02)
