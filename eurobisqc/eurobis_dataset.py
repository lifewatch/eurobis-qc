import sys
import logging
import requests
import re
from pyodbc import Error
# This is to cope with possible hangs in iMIS API call
from stopit import threading_timeoutable

from datetime import datetime

from dbworks import mssql_db_functions as mssql
from eurobisqc.util import extract_area
from eurobisqc.util import extract_metadata
from eurobisqc.util import misc

this = sys.modules[__name__]
# This is not multiprocess "safe" output can be garbled...
this.logger = logging.getLogger(__name__)
# INFO keeps the per-dataset summary; DEBUG also logs every batch of 1000 records.
this.logger.level = logging.INFO
this.logger.addHandler(logging.StreamHandler())

# Allow this.imis_timeout seconds for the IMIS call to return when fetching the areas
this.imis_timeout = 25


class EurobisDataset:
    """ all the necessary to represent
        an archive as retrieved from the DB """

    OCCURRENCE = 1
    EVENT = 2
    LOOKUP_BATCH_SIZE = 1000
    INDEX_TRESHOLD = 300000

    record_batch_update_count = 0

    # Query to disable the triggers
    sql_disable_trigger = "disable TRIGGER [fill_field_sync_dataproviders] on [eurobis_dat].[dbo].[eurobis];"
    sql_enable_trigger = "enable TRIGGER [fill_field_sync_dataproviders] on [eurobis_dat].[dbo].[eurobis];"

    # FLAG: These maps could be parametric based on the Lookup DB
    # FLAG: Prerequisite is that the columns exist in the DB and that names do not change.
    # FLAG: Pipeline has been verified for the columns listed below

    field_map_eurobis = {'dataprovider_id': 'dataprovider_id',
                         'occurrenceID': 'occurrenceID',
                         'eventID': 'eventID',
                         'DarwinCoreType': 'DarwinCoreType',
                         'BasisOfRecord': 'basisOfRecord',
                         'Latitude': 'decimalLatitude',
                         'Longitude': 'decimalLongitude',
                         'CoordinatePrecision': 'coordinatePrecision',
                         'MaximumDepth': 'maximumDepthInMeters',
                         'MinimumDepth': 'minimumDepthInMeters',
                         'ScientificName': 'scientificName',
                         "'urn:lsid:marinespecies.org:taxname:' + CONVERT(VARCHAR(255), aphia_id)": 'scientificNameID',
                         'occurrenceStatus': 'occurrenceStatus',
                         'Sex': 'sex',
                         'Genus': 'genus',
                         'qc': 'qc',
                         'auto_id': 'auto_id'
                         # Disabling use of physloc: Fred conv. Bart dd 26/2
                         # '%%physloc%%': 'physloc'  # Note: Undocumented, may not work in future - use as update key
                         }  # The mapping of the interesting fields DB <--> DwCA as defined for eurobis table

    field_map_emof = {'dataprovider_id': 'dataprovider_id',
                      'occurrenceID': 'occurrenceID',
                      'eventID': 'eventID',
                      'measurementType': 'measurementType',
                      'measurementTypeID': 'measurementTypeID',
                      'measurementValue': 'measurementValue',
                      }  # Mapping of the interesting fields DB <--> DwCA as def. for eurobis_measurementoorfact table

    sql_eurobis_start = "SELECT "
    sql_eurobis_end = " FROM eurobis WHERE dataprovider_id="

    # May be we should do a SQL SP instead with parameter dataprovider_id
    sql_eurobis_eventdate = \
        """
    COALESCE(dbo.ipt_date_iso8601(StartYearCollected,
                              StartMonthCollected,
                              StartDayCollected,
                              COALESCE(StartTimeOfDay,TimeOfDay),
                              TimeZone),
                              dbo.ipt_date_iso8601(YearCollected,
                              MonthCollected,
                              DayCollected,
                              COALESCE(StartTimeOfDay,TimeOfDay),
                              TimeZone))
                              + (CASE WHEN (EndYearCollected IS NOT NULL)
                                          THEN '/'+
                                dbo.ipt_date_iso8601(EndYearCollected,
                                                     EndMonthCollected,
                                                     EndDayCollected,
                                                     COALESCE(EndTimeOfDay,TimeOfDay),TimeZone)
                                          ELSE '' END)

                               + (CASE WHEN (EndYearCollected IS NULL AND EndTimeOfDay IS NOT NULL)
                                          THEN '/'+
                                       COALESCE(dbo.ipt_date_iso8601(StartYearCollected,
                                                                     StartMonthCollected,
                                                                     StartDayCollected,
                                                                     EndTimeOfDay,
                                                                     TimeZone),
                                                dbo.ipt_date_iso8601(YearCollected,
                                                                     MonthCollected,
                                                                     DayCollected,
                                                                     EndTimeOfDay,
                                     TimeZone))
                                           ELSE '' END)
    AS eventDate """

    sql_providers = "SELECT * FROM dataproviders WHERE id="
    sql_emof_start = "SELECT "
    sql_emof_end = " FROM eurobis_measurementorfact WHERE dataprovider_id="

    # Important - query to update an event or occurrence record
    # NOTE 29/01/2021 - ADDED THE WITH ROWLOCK
    # sql_update_start = "update eurobis WITH (ROWLOCK, INDEX(IX_eurobis_lat_lon_dataproviderid)) set qc = "  # add the calculated QC
    sql_update_start = "update eur SET qc = "  # add the calculated QC
    # sql_update_middle = " FROM eurobis eur WITH (ROWLOCK,INDEX(IX_eurobis_lat_lon_dataproviderid)) WHERE dataprovider_id = "
    sql_update_middle = " FROM eurobis eur WHERE dataprovider_id = "

    # If the records contains Latitude and Longitude they are indexed, so could speed updates up
    sql_if_lat = " and Latitude = "
    sql_if_lon = " and Longitude = "
    sql_if_scientific_name = " and ScientificName = "  # This do not provide benefits
    sql_if_scientific_name_id = "and aphia_id = "  # This does not provide benefits
    sql_if_event_id = " and EventID = "

    # sql_update_end = " and %%physloc%% = "  # add at the end the record['physloc'] retrieved at the start
    sql_update_end = " and auto_id = "  # add at the end the record['auto_id'] retrieved at the start

    def __init__(self):
        """ Initialises an empty dataset """

        self.darwin_core_type = 1  # 1 = Occurrence 2 = Event
        self.event_recs = []  # The Event Records
        self.occurrence_recs = []  # The Occurrence Records
        self.emof_recs = []  # The MoF/eMof records
        self.event_indices = {}  # To push back quality of pylook-up left overs
        self.occ_indices = {}  # Key to list of occurrences for datasets where coretype = 2
        self.emof_indices = {}  # Key to list of emof
        self.dataprovider_id = None  # The dataset ID from the dataproviders table
        self.imis_das_id = None  # The IMIS dataset ID for querying the eml
        self.eml = None  # Eml as from the http://www.eurobis.org/imis?dasid=<IMIS_DasID>&show=eml API
        self.event_dates_eml = None  # Extract the dates from the EML as last resort
        self.areas = None  # Extract areas from EML (Bounding box do not have useful info - seek advice)
        self.goodmetadata = None  # [EUROBIS-420] - check if good metadata is available
        self.provider_record = None  # Provider record extracted
        self.dataset_name = ""
        self.records_for_lookup = []
        self.pyxylookup_counter = 0
        self.has_eurobis_links = False

    def get_provider_data(self, das_prov_id):
        """ Obtain the dataset info from the dataproviders table
            and stores that into the instance fields
            :param - das_prov_id - Dataset id """

        if not mssql.conn:
            mssql.open_db()

        if mssql.conn is None:
            # Should find a way to exit and advice
            pass
        else:
            # Can start querying the DB using the dataset provider ID
            sql_str = f"select * from dataproviders d where id = {das_prov_id};"

            # Fetch the provider line
            cur = mssql.conn.cursor()
            cur.execute(sql_str)
            # Get a dictionary
            provider_fields = [description[0] for description in cur.description]

            provider = cur.fetchone()

            self.provider_record = dict(zip(provider_fields, provider))
            self.imis_das_id = self.provider_record['IMIS_DasID']
            self.dataprovider_id = self.provider_record['id']  # Of course this we have already
            self.darwin_core_type = self.provider_record['core']
            self.dataset_name = self.provider_record['name']
            # Should see if more is needed
            mssql.close_db()

    def get_ev_occ_records(self, das_prov_id):
        """ retrieves event and occurrence records for the dataset in das_id from SQL Server
            also builds search indexes to easily retrieve dependant records
            :param das_prov_id """
        if not mssql.conn:
            mssql.open_db()

        if mssql.conn is None:
            # Should find a way to exit and advice
            pass
        else:
            # get records
            sql_string = self.query_builder_eve_occur(das_prov_id)
            cursor = mssql.conn.cursor()
            cursor.execute(sql_string)

            columns = [column[0] for column in cursor.description]
            records = []
            for row in cursor:
                records.append(dict(zip(columns, row)))

            # We proceed differently in accordance with the type of CORE record...
            if self.darwin_core_type == self.EVENT:
                for record in records:
                    if record['DarwinCoreType'] == self.OCCURRENCE:
                        self.occurrence_recs.append(record)
                        if record['eventID'] is not None:  # To link we need an eventID
                            # make a key - it must be lined by the eventID
                            key = f"{record['dataprovider_id']}_{record['eventID']}"
                            if key in self.occ_indices:
                                # All the records with this key shall be in a list at 'key'
                                self.occ_indices[key].append(record)
                            else:
                                self.occ_indices[key] = [record]
                    elif record['DarwinCoreType'] == self.EVENT:
                        self.event_recs.append(record)
                        # If coretype is event, then eventid is the key - only used to reverse lookup.
                        key = f"{record['dataprovider_id']}_{record['eventID']}"
                        self.event_indices[key] = [record]

            else:  # Occurrence records (Datasets with core_type = OCCURRENCE do not have events - verified)
                for record in records:
                    if record['DarwinCoreType'] == self.OCCURRENCE:
                        self.occurrence_recs.append(record)
                    else:  # Should really never happen !!
                        self.event_recs.append(record)
            mssql.close_db()

    def get_emof_records(self, das_prov_id):
        """ retrieves measurementorfact records for the dataset in das_id from SQL Server
            also building search indexes to easily retrieve dependant records
            NOTE: mof records do not exist for records that have eventID and occurrenceID NULL
            :param das_prov_id"""

        if not mssql.conn:
            mssql.open_db()

        if mssql.conn is None:
            # Should find a way to exit and advice
            pass
        else:
            # get records
            sql_string = self.query_builder_emof(das_prov_id)
            cursor = mssql.conn.cursor()
            cursor.execute(sql_string)

            columns = [column[0] for column in cursor.description]
            records = []
            for row in cursor:
                records.append(dict(zip(columns, row)))

            for record in records:
                self.emof_recs.append(record)

                if self.darwin_core_type == self.EVENT:

                    key = f"{record['dataprovider_id']}_{'NULL' if record['eventID'] is None else record['eventID']}_" \
                          f"{'NULL' if record['occurrenceID'] is None else record['occurrenceID']}"
                else:
                    # Occurrence records in datasets with core = Occurrence may have other info in EventID and NULL in
                    # eMoF record.
                    key = f"{record['dataprovider_id']}_NULL_" \
                          f"{'NULL' if record['occurrenceID'] is None else record['occurrenceID']}"

                if key in self.emof_indices:
                    # All the records with this key shall be in a list at 'key'
                    self.emof_indices[key].append(record)
                else:
                    self.emof_indices[key] = [record]
            mssql.close_db()

    def query_builder_eve_occur(self, dataprovider_id):
        """ Builds the SQL query string to retrieve all event, occur records for a dataset
            inclusive of the eventDate
            :param dataprovider_id
            :returns SQL Query string """

        sql_string = self.sql_eurobis_start

        for par in self.field_map_eurobis:
            sql_string = sql_string + f"{par} as {self.field_map_eurobis[par]}, "

        # add eventDate, end and parameter
        sql_string = sql_string + self.sql_eurobis_eventdate + self.sql_eurobis_end + f"{dataprovider_id};"

        return sql_string

    def query_builder_emof(self, dataprovider_id):
        """ Builds the SQL query string to retrieve all emof records for a dataset
            :param dataprovider_id
            :returns SQL Query string """

        sql_string = self.sql_emof_start

        for idx, par in enumerate(self.field_map_emof):

            sql_string = sql_string + f"{par} as {self.field_map_emof[par]} "

            if idx < len(self.field_map_emof) - 1:
                sql_string += ", "

        sql_string = sql_string + self.sql_emof_end + f"{dataprovider_id};"

        return sql_string

    def load_dataset(self, das_prov_id):
        """ given a dataset id from the dataprovider
            loads an entire dataset in a EurobisDataset instance (RAM) for QC processing
            :param das_prov_id
            """
        self.get_provider_data(das_prov_id)

        area_res = None

        while area_res is None:
            area_res = self.do_get_areas(self.imis_das_id, timeout=this.imis_timeout)
            this.logger.warning("Had to re-issue call to IMIS")

        if self.has_eurobis_links is True:
            self.get_ev_occ_records(das_prov_id)
            self.get_emof_records(das_prov_id)

    @threading_timeoutable()
    def do_get_areas(self, imis_das_id):
        """ This is wrapped in a timeoutable call so that if there is no return in 10 seconds
            then the call is re-issued until the list of results is returned. Average lookup of
            1000 records is around 1s, so 10 is a reasonable timeout
            :param imis_das_id - dataset IMIS identifier """

        return self.get_areas_from_eml(imis_das_id)

    def check_eurobis_links(self, eml_text):
        if not eml_text:
            return False
        patterns = [r'eurobis\.org/toolbox/en/download', r'ipt\.vliz\.be/eurobis']
        for p in patterns:
            if re.search(p, eml_text, re.I):
                return True

    def get_areas_from_eml(self, imis_das_id):
        """ Given a IMIS Dataset ID, queries the IMIS web service for
            the EML related to the dataset. Once the EML is returned, it is processed exactly
            by the same function as for the DwCA files.
            :param imis_das_id - dataset IMIS identifier"""

        eml = None
        # Where to get IMIS data from
        url = f"http://www.eurobis.org/imis?dasid={imis_das_id}&show=eml"
        eml_detect = "eml:eml"

        response = requests.get(url)

        # NOTE: This API will return 200 even if the record is not found, in that case the area extractor will fail.
        if response.status_code == 200:
            if eml_detect not in response.text:
                return None
            else:
                eml = response.text

        if eml is not None:
            self.has_eurobis_links = self.check_eurobis_links(eml)
            if self.has_eurobis_links:
                self.areas = extract_area.find_areas(eml)
                # Good metadata: includes citation, title, license, and abstract with >100 characters. [EUROBIS-420]
                self.goodmetadata = extract_metadata.flag_metadata(eml)
        else:
            self.areas = None

        # To know when I am returning from it normally or after a timeout
        return True

    @classmethod
    def disable_qc_index(cls):
        """ Disable non-clustered index on QC
            important - this depends on the index name being kept the same in the
            variable sql_disable_index below
            """

        # Check DB connection...
        if not mssql.conn:
            mssql.open_db()

        if mssql.conn is None:
            # Should find a way to exit and advice (raise an exception may be)
            return "Fail, no connection "
        else:
            try:
                sql_disable_index = "ALTER INDEX IX_eurobis_qc ON dbo.eurobis DISABLE;"
                cursor = mssql.conn.cursor()
                cursor.execute(sql_disable_index)
                mssql.conn.commit()
                this.logger.debug(f"Non clustered index on qc disabled")
                mssql.close_db()
                return "Success"
            except Error as e:
                mssql.close_db()
                return f"Failed to disable clustered index: {e}"

    @classmethod
    def rebuild_qc_index(cls):
        """ Rebuild non-clustered index on QC
            important - this depends on the index name as per disable_qc_index """

        # Check DB connection...
        if not mssql.conn:
            mssql.open_db()

        if mssql.conn is None:
            # Should find a way to exit and advice (raise an exception may be)
            return "Fail, no connection "
        else:
            try:
                sql_disable_index = "ALTER INDEX IX_eurobis_qc ON dbo.eurobis REBUILD;"
                cursor = mssql.conn.cursor()
                cursor.execute(sql_disable_index)
                mssql.conn.commit()
                this.logger.debug(f"Non clustered index on qc rebuilt")
                mssql.close_db()
                return "Success"
            except Error as e:
                mssql.close_db()
                return f"Failed to rebuild clustered index: {e}"

    @classmethod
    def update_record_qc(cls, records, batch_update_count, batch_size, ds_id, record_type):
        """ Shall update a batch of records from a dataset
            update queries shall be built record by record and sent to the DB in batches for execution
            :param records : A list of the records being updated
            :param batch_update_count: The dataset's batch number
            :param batch_size : Here only used to report the status of the update
            :param ds_id: dataset being processed
            :param record_type : For query optimization, occurrence and event records may be treated differently
            also used for printing
            NOTE: Special methods are provided to DISABLE the index on QC and REBUILD it after the updates.
            These improve vastly the query run time.
            """

        # Check DB connection...
        if not mssql.conn:
            mssql.open_db()

        if mssql.conn is None:
            # Should find a way to exit and advice (raise an exception may be)
            return "Fail, no connection "
        else:
            record_count = len(records)
            # sql_update = f"BEGIN TRAN; \n"
            sql_update = ""
            for record in records:
                # Compose update query
                # physloc = bytes.hex(record['physloc'])

                # Note The fields other than physloc and dataprovider_id are used to optimize
                # the update queries execution plans and thus to reduce browsing the records
                # and using the existing indexes on the eurobis table. Observed speed improvements
                # are between 2.5 and 5 times faster.

                # This is a temporary fix - some qc values are set to None.
                if record['qc'] is None:
                    record['qc'] = 0

                sql_update += f"{cls.sql_update_start}{record['qc']}{cls.sql_update_middle} {record['dataprovider_id']}"

                """
                Disabled - using auto_id now.
                if record['decimalLatitude'] is not None:
                    sql_update = f"{sql_update}{cls.sql_if_lat}{record['decimalLatitude']}"
                else:
                    sql_update = f"{sql_update} AND Latitude IS NULL "

                if record['decimalLongitude'] is not None:
                    sql_update = f"{sql_update} {cls.sql_if_lon}{record['decimalLongitude']}"
                else:
                    sql_update = f"{sql_update} AND Longitude IS NULL "

                if record_type == EurobisDataset.EVENT:
                    if record['eventID'] is not None and misc.is_clean_for_sql(record['eventID']):
                        sql_update = f"{sql_update} {cls.sql_if_event_id}'{record['eventID']}'"
                """

                # sql_update = f"{sql_update} {cls.sql_update_end} 0x{physloc} \n"
                sql_update = f"{sql_update} {cls.sql_update_end} {record['auto_id']} \n"

            try:
                # sql_update += f"COMMIT TRAN;\n"
                cursor = mssql.conn.cursor()
                cursor.execute(sql_update)
                mssql.conn.commit()
                rec_type = "EVENT" if record_type == EurobisDataset.EVENT else "OCCURRENCE"
                dateTimeObj = datetime.now()
                this.logger.debug(
                    f"{dateTimeObj}: {rec_type} records update count: {batch_update_count * batch_size + record_count}  "
                    f"of dataset {ds_id};")
                batch_update_count += 1
                return "Success"
            except Error as e:
                return f"Fail, batch {batch_update_count} not updated, exception {str(e)}"

            # Added close_DB to make sure that transactions are "separated".
            mssql.close_db()
