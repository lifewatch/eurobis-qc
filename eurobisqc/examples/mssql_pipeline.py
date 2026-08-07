import logging
import sys
import time
import traceback
from datetime import datetime
from _functools import reduce

from dbworks import mssql_db_functions as mssql
from eurobisqc import eurobis_dataset
from eurobisqc import location
from eurobisqc import measurements
from eurobisqc import required_fields
from eurobisqc import taxonomy
from eurobisqc import time_qc
from eurobisqc import qc_flags
from eurobisqc.util import misc

# Use "this" trick
this = sys.modules[__name__]
this.logger = logging.getLogger(__name__)
this.logger.level = logging.DEBUG
this.logger.addHandler(logging.StreamHandler())

this.PROCESS_BATCH_SIZE = 1000


def qc_event(record, data_archive):
    # None means that records have not been quality checked 0 means that QCs have been attempted
    if record["qc"] is None:
        record["qc"] = 0

    # QC for the ev. records : location basic (4, 5, 18, 21)
    record["qc"] |= location.check_basic_record(record)
    # QC for the ev. records : areas (9)
    if data_archive.areas is not None:
        record["qc"] |= location.check_record_in_areas(record, data_archive.areas)

    # Check the required fields (1) (should fail)
    record["qc"] |= required_fields.check_record_required(record, False)

    # QC for the ev. records : building batch for API call (6, 19)
    if record["qc"] & (qc_flags.QCFlag.GEO_LAT_LON_VALID.bitmask | qc_flags.QCFlag.GEO_LAT_LON_PRESENT.bitmask):
        data_archive.records_for_lookup.append(record)
        # Execute lookup if necessary
        if len(data_archive.records_for_lookup) >= data_archive.LOOKUP_BATCH_SIZE:
            location.check_xy(data_archive.records_for_lookup)
            data_archive.pyxylookup_counter += 1
            dateTimeObj = datetime.now()
            this.logger.debug(f"{dateTimeObj}: Lookups A: {data_archive.pyxylookup_counter}")
            # Empty the list
            data_archive.records_for_lookup = []

    # QC for the ev. records : time (7, 11, 12, 13)
    record["qc"] |= time_qc.check_record(record, 0)

    # Look at the event related eMoF records  (14, 15, 16, 17)
    # Disabled as per email 24/01/2021
    record["qc"] |= qc_emof(record, data_archive)

    # goodmetadata is for full dataset. (25)
    if data_archive.goodmetadata:
        record["qc"] |= qc_flags.QCFlag.GOODMETADATA.bitmask

    return record["qc"]


def qc_occurrence(record, data_archive):
    if record["qc"] is None:
        record["qc"] = 0

    # QC for the occ records: required fields: (1, 10)
    record["qc"] |= required_fields.check_record_required(record)
    record["qc"] |= required_fields.check_record_obis_format(record)

    # QC for the occ. records : location basic (4, 5, 18)
    record["qc"] |= location.check_basic_record(record)

    # QC for the ev. records : areas (9)
    if data_archive.areas is not None:
        record["qc"] |= location.check_record_in_areas(record, data_archive.areas)

    # QC for the occ. records : building batch for API call (6, 19)
    if record["qc"] & (qc_flags.QCFlag.GEO_LAT_LON_VALID.bitmask | qc_flags.QCFlag.GEO_LAT_LON_PRESENT.bitmask):
        data_archive.records_for_lookup.append(record)
        # Execute lookup if necessary
        if len(data_archive.records_for_lookup) >= data_archive.LOOKUP_BATCH_SIZE:
            location.check_xy(data_archive.records_for_lookup)
            data_archive.pyxylookup_counter += 1
            dateTimeObj = datetime.now()
            this.logger.debug(f"{dateTimeObj}: Lookups B: {data_archive.pyxylookup_counter}")
            # Empty the list
            data_archive.records_for_lookup = []

    # QC for the occ. records: taxonomy (2, 3)
    record["qc"] |= taxonomy.check_record(record)

    # QC for the occ. records : time (7, 11, 12, 13)
    record["qc"] |= time_qc.check_record(record, 0)

    # QC for occ. : sex (17)
    record["qc"] |= measurements.check_sex_record(record)

    # Do the measurement of facts QC for the event records (14, 15, 16, 17)
    # This processes all emof records belonging to this occurrence record
    record["qc"] |= qc_emof(record, data_archive)

    # Complete dataset: (25)
    if data_archive.goodmetadata:
        record["qc"] |= qc_flags.QCFlag.GOODMETADATA.bitmask

    # This is useful for when core record = event
    return record["qc"]


def qc_emof(record, data_archive):
    """ Processes all emof records for record (both event type or occurrence)
        :param record: The Occurrence or Event Record
        :param data_archive: The archive being processed
        :returns the calculated joined qc for the emof records """

    qc_em = 0

    if data_archive.darwin_core_type == data_archive.EVENT:
        key = f"{record['dataprovider_id']}_{'NULL' if record['eventID'] is None else record['eventID']}_" \
              f"{'NULL' if record['occurrenceID'] is None else record['occurrenceID']}"
    else:
        key = f"{record['dataprovider_id']}_NULL_" \
              f"{'NULL' if record['occurrenceID'] is None else record['occurrenceID']}"

    if key in data_archive.emof_indices:
        measurements_qc = measurements.check(data_archive.emof_indices[key])
        # These are per single emof record, "or" them together
        qc_em |= reduce(lambda x, y: x | y, measurements_qc)

    return qc_em


def dataset_qc_labeling(dataset_id, disable_index=True, with_logging=True, pool_no=0):
    """ Processes an eurobis dataset if it is passed as a dataset_id,
        shall popup a file chooser dialog if this is None
        :param dataset_id (The dataset identifier from the dataproviderstable)
        :param disable_index: Whether we are eventually allowed to disable the index at this level
        :param with_logging (every QC passed is printed)
        """

    if dataset_id is None:
        this.logger.warning("WARNING: Call to dataset_qc_labeling with no dataset_id ")
        return None

    data_archive = eurobis_dataset.EurobisDataset()
    data_archive.load_dataset(dataset_id)

    if not data_archive.has_eurobis_links:
        this.logger.info(f"Skipping dataset {data_archive.dataprovider_id}: no Download Toolbox or Eurobis IPT link")
        return None

    if with_logging:
        this.logger.info(f"--------------------------------------------------")
        this.logger.info(f"Loaded dataset {data_archive.dataset_name}, id = {data_archive.dataprovider_id} ")
        this.logger.info(f"Number of event records: {len(data_archive.event_recs)}")
        this.logger.info(f"Number of occurrence records: {len(data_archive.occurrence_recs)}")
        this.logger.info(f"Number of emof records: {len(data_archive.emof_recs)}")
        this.logger.info(f"Interesting areas: {data_archive.areas}")
        this.logger.info(f"Imis dataset ID: {data_archive.imis_das_id}")
        this.logger.info(f"Good metadata: {'OK' if data_archive.goodmetadata == True else 'Not OK'}")
        this.logger.info(f"Type of core records: {'Event' if data_archive.darwin_core_type == 2 else 'Occurrence'}")
        this.logger.info(f"Poolno: {pool_no}")
        this.logger.info(f"--------------------------------------------------")

    # Starting the QCs:
    # After loading, measure processing time
    time_start = time.time()

    # Proceed top-down...
    if data_archive.darwin_core_type == data_archive.EVENT:
        this.logger.info(f"1A. Event")
        # For all event records, qc event, then occurrence records
        # (which shall recurse into eMof), then own eMof and then "or" all
        for record in data_archive.event_recs:
            # qc_event shall also take care of emof for event
            # this.logger.info(f"1A. Event")
            qc_ev = qc_event(record, data_archive)
            record["qc"] |= qc_ev

            # Generate key and lookup occurrences...
            key = f"{record['dataprovider_id']}_{record['eventID']}"
            if key in data_archive.occ_indices:
                for occ_record in data_archive.occ_indices[key]:
                    # qc_occurrence sall also take care of emof for occurrence
                    qc_occ = qc_occurrence(occ_record, data_archive)
                    # Check that the combination of event and occurrence have the required fields. Assign to occurrence
                    # Consequence of email 24/01/2021
                    occ_record["qc"] |= required_fields.check_ev_occ_required(record, occ_record, False)
                    occ_record["qc"] |= qc_occ  # make sure it is assigned other than just calculated
                    occ_record["qc"] |= qc_ev  # Occurrence also inherit 'father' event qc (email 24/01/2021)
                    # qc_ev |= qc_occ  # No aggregation upwards (email 24/01/2021)

                # No longer true after email 24/01/2021
                # Needs to propagate the REQUIRED FIELDS CHECK for the event and its occurrences
                # qc_req_agg = [record]
                # qc_req_agg.extend(data_archive.occ_indices[key])
                # record["qc"] |= required_fields.check_aggregate(qc_req_agg)

    else:  # Only occurrence and emof records
        this.logger.info(f"1B. Occurence and emof")
        for occ_record in data_archive.occurrence_recs:
            # The QC is either 0 or a QC mask - emof are considered inside the occurrence
            qc_occurrence(occ_record, data_archive)

    # Are there any lookups left to do (any record type)
    if len(data_archive.records_for_lookup):
        location.check_xy(data_archive.records_for_lookup)
        data_archive.pyxylookup_counter += 1
        dateTimeObj = datetime.now()
        this.logger.debug(f"{dateTimeObj}: Lookups C: {data_archive.pyxylookup_counter}")

        # Must propagate the QC of these records (in case)
        if data_archive.darwin_core_type == data_archive.EVENT:
            for looked_up_record in data_archive.records_for_lookup:
                if looked_up_record["DarwinCoreType"] == data_archive.OCCURRENCE:
                    key = f"{looked_up_record['dataprovider_id']}_{looked_up_record['eventID']}"
                    if key in data_archive.event_indices:
                        data_archive.event_indices[key][0]["qc"] |= looked_up_record["qc"]

        # Empty the list
        data_archive.records_for_lookup = []

    # Disable QC - if necessary
    if disable_index:
        if len(data_archive.event_recs) + len(data_archive.occurrence_recs) > data_archive.INDEX_TRESHOLD:
            eurobis_dataset.EurobisDataset.disable_qc_index()

    # RECORDS UPDATE!
    this.PROCESS_BATCH_SIZE = 1000  # Shall commit at every batch

    # EVENTS
    if len(data_archive.event_recs):
        # Getting the splits
        split_events_lists = misc.split_in_chunks(data_archive.event_recs, this.PROCESS_BATCH_SIZE)

        for idx, process_batch in enumerate(split_events_lists):
            eurobis_dataset.EurobisDataset.update_record_qc(process_batch, idx, this.PROCESS_BATCH_SIZE,
                                                            data_archive.dataprovider_id, data_archive.EVENT)

    # OCCURRENCES
    if len(data_archive.occurrence_recs):
        # Getting the splits
        split_occurrences_lists = misc.split_in_chunks(data_archive.occurrence_recs, this.PROCESS_BATCH_SIZE)
        for idx, process_batch in enumerate(split_occurrences_lists):
            eurobis_dataset.EurobisDataset.update_record_qc(process_batch, idx, this.PROCESS_BATCH_SIZE,
                                                            data_archive.dataprovider_id, data_archive.OCCURRENCE)

    # REBUILD QC index
    if disable_index:
        if len(data_archive.event_recs) + len(data_archive.occurrence_recs) > data_archive.INDEX_TRESHOLD:
            eurobis_dataset.EurobisDataset.rebuild_qc_index()

    duration = time.time() - time_start
    # Dataset QC finished, taking note of the time.

    if with_logging:
        this.logger.info(
            f"Total net processing time for {data_archive.dataprovider_id} : "
            f"{data_archive.dataset_name} in: {duration} ")


def process_dataset_list(pool_no, dataset_id_list, from_pool=False, with_logging=False):
    """ Processes a list of DwCA archives, ideally to be called in parallel
        :param pool_no - Pool number to take track of the pools
        :param dataset_id_list (The list of datasets to be processed)
        :param from_pool: If it comes from a multiprocessing pool, then disabling of the QC index is taken care of
        :param with_logging (Logging enabled or not) """
    # Prints pool data
    start = time.time()
    if with_logging:
        this.logger.info(f"Pool {pool_no} started")

    # Connect to the database, each pool should have its own connection
    conn = None

    mssql.close_db()
    # Make sure db connection is ours
    if not mssql.conn:
        conn = mssql.open_db()

    if conn is None:
        # Should find a way to exit and advice
        this.logger.error("No connection to DB, nothing can be done! ")
        return pool_no

    # Disable index on QC once
    if not from_pool:
        eurobis_dataset.EurobisDataset.disable_qc_index()

    errors = 0

    for dataset_id in dataset_id_list:
        start_file = time.time()

        if with_logging:
            this.logger.info(f"Pool Number: {pool_no}, processsing dataset {dataset_id} ")

        try:
            dataset_qc_labeling(dataset_id, False, with_logging, pool_no)
        except Exception:
            errors += 1
            this.logger.error(traceback.format_exc())
            this.logger.warning(f"WARNING: Pool Number: {pool_no}, processsing dataset {dataset_id} FAILED ")

        if with_logging:
            this.logger.info(f"Processed dataset {dataset_id} in  {time.time() - start_file}")

    # REBUILD index on QC once
    if not from_pool:
        eurobis_dataset.EurobisDataset.rebuild_qc_index()

    if with_logging:
        this.logger.info(f"Pool {pool_no} completed in {time.time() - start}")

    return pool_no, errors

# To call single dataset labelling with a chooser use run_mssql_pipeline
# Single dataset  - Fixed - need eurobis.dataprovider_id (id in dataproviders table)
# dataset_qc_labeling(447, disable_index= False, with_logging=True)

# Launch individual processing of dataset list, datasets to be picked
# process_dataset_list(1, [723, 239], True, False)
