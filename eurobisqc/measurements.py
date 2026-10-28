""" To check for missing fields in eMoF records as per error masks  """

import sys
from eurobisqc import qc_flags
from eurobisqc.util import misc
from dbworks import sqlite_db_functions

qc_mask_14 = qc_flags.QCFlag.OBSERVED_COUNT_PRESENT.bitmask
qc_mask_15 = qc_flags.QCFlag.OBSERVED_WEIGHT_PRESENT.bitmask
qc_mask_16 = qc_flags.QCFlag.SAMPLE_SIZE_PRESENT.bitmask
qc_mask_17 = qc_flags.QCFlag.SEX_PRESENT.bitmask
qc_mask_22 = qc_flags.QCFlag.SAMPLE_DEVICE_PRESENT.bitmask
qc_mask_23 = qc_flags.QCFlag.ABUNDANCE_PRESENT.bitmask
qc_mask_24 = qc_flags.QCFlag.ABIOTIC_MAPPED_PRESENT.bitmask

# Introduce parameters for aggregation of measurements (or | and | percentage)

this = sys.modules[__name__]

# For measurement:The measurement type must contain for weight verification (lowercase check)
this.weight_measure_types = {}
# And the measurement type ID must be :
this.weight_measure_type_ids = {}

this.weight_measures = {}

# For count :The measurement type must contain for weight verification (lowercase check)
this.count_measure_types = {}
# And the measurement type ID must match one of
this.count_measure_type_ids = {}

this.count_measures = {}

# For sample size
this.sample_size_measure_types = {}
this.sample_size_measure_type_ids = {}

this.sample_size_measures = {}

# Same question for sex / gender (vocabulary) - no need for database lookup for this
# Sets are faster than lists for lookups
this.sex_field = "sex"
# Read it from DB
this.sex_field_measure_types = {}
this.sex_field_measure_type_ids = {}
this.sex_field_values = {}

this.lookups_loaded = False


# Improved QC for sex
def initialize_lookups():
    """ Only needed at the first call to initialize the lookup tables """

    if this.lookups_loaded:
        return

    # row factory - BEWARE - do not use con.row_factory as !
    # db_functions.conn.row_factory = lambda cursor, row: row[0] # important, this has side effects
    # Fill the lookups:

    # Get a connection to the DB
    if sqlite_db_functions.conn is None:
        conn = sqlite_db_functions.open_db()
        if conn is None:
            return

    # COUNT IDs and words
    c = sqlite_db_functions.conn.cursor()
    data = c.execute('SELECT Value FROM countMeasurementTypeID').fetchall()
    this.count_measure_type_ids = {val[0] for val in data}

    c = sqlite_db_functions.conn.cursor()
    data = c.execute('SELECT Value FROM countMeasurementType').fetchall()
    this.count_measure_types = {val[0] for val in data}

    # SAMPLE SIZE IDs and words
    c = sqlite_db_functions.conn.cursor()
    data = c.execute('SELECT Value FROM sampleSizeMeasurementTypeID').fetchall()
    this.sample_size_measure_type_ids = {val[0] for val in data}

    c = sqlite_db_functions.conn.cursor()
    data = c.execute('SELECT Value FROM sampleSizeMeasurementType').fetchall()
    this.sample_size_measure_types = {val[0] for val in data}

    # WEIGHT IDs and words
    c = sqlite_db_functions.conn.cursor()
    data = c.execute('SELECT Value FROM weightMeasurementTypeID').fetchall()
    this.weight_measure_type_ids = {val[0] for val in data}

    c = sqlite_db_functions.conn.cursor()
    data = c.execute('SELECT Value FROM weightMeasurementType').fetchall()
    this.weight_measure_types = {val[0] for val in data}

    # SAMPLING DEVICE PRESENT
    c = sqlite_db_functions.conn.cursor()
    data = c.execute('SELECT Value FROM deviceMeasurementTypeID').fetchall()
    this.device_measure_type_ids = {val[0] for val in data}

    c = sqlite_db_functions.conn.cursor()
    data = c.execute('SELECT Value FROM deviceMeasurementType').fetchall()
    this.device_measure_types = {val[0] for val in data}

    # ABUNDANCE PRESENT
    c = sqlite_db_functions.conn.cursor()
    data = c.execute('SELECT Value FROM abundanceMeasurementTypeID').fetchall()
    this.abundance_measure_type_ids = {val[0] for val in data}

    c = sqlite_db_functions.conn.cursor()
    data = c.execute('SELECT Value FROM abundanceMeasurementType').fetchall()
    this.abundance_measure_types = {val[0] for val in data}

    # ABIOTIC PRESENT
    c = sqlite_db_functions.conn.cursor()
    data = c.execute('SELECT Value FROM abioticMeasurementTypeID').fetchall()
    this.abiotic_measure_type_ids = {val[0] for val in data}

    c = sqlite_db_functions.conn.cursor()
    data = c.execute('SELECT Value FROM abioticMeasurementType').fetchall()
    this.abiotic_measure_types = {val[0] for val in data}

    # SEX type IDs, types and values
    c = sqlite_db_functions.conn.cursor()
    data = c.execute('SELECT Value FROM sexMeasurementTypeID').fetchall()
    this.sex_field_measure_type_ids = {val[0] for val in data}

    c = sqlite_db_functions.conn.cursor()
    data = c.execute('SELECT Value FROM sexMeasurementType').fetchall()
    this.sex_field_measure_types = {val[0] for val in data}

    c = sqlite_db_functions.conn.cursor()
    data = c.execute('SELECT Value FROM sexValues').fetchall()
    this.sex_field_values = {val[0] for val in data}

    this.lookups_loaded = True

    # These will function as lookups for the dynamicProperty field on Occurrence when found
    this.weight_measures = this.weight_measure_type_ids.union(this.weight_measure_types)
    this.sample_size_measures = this.sample_size_measure_type_ids.union(this.sample_size_measure_types)
    this.count_measures = this.count_measure_type_ids.union(this.count_measure_types)
    this.device_measures = this.device_measure_type_ids.union(this.device_measure_types)
    this.abundance_measures = this.abundance_measure_type_ids.union(this.abundance_measure_types)
    this.abiotic_measures = this.abiotic_measure_type_ids.union(this.abiotic_measure_types)


def check_mtid(measurement_type_id, measurement_value):
    """ FOR eMoF records.
        Verifies that the measurement value is not none,
        if one of the sought measurement
        types IDS is present, then the QC is passed
        :param measurement_type_id - as in the record
        :param measurement_value - as in the record
        purpose: attempt optimization
        returns: 0 or one or more of the bitmasks 14, 15, 16 or 17 """

    qc_mask = 0
    found = False

    if measurement_value is None:
        return qc_mask

    # Is the measurement type id of a biomass weight
    for wmtid in this.weight_measure_type_ids:
        if wmtid in measurement_type_id:
            found = True
            qc_mask |= qc_mask_15

    # Is the measurement type id of a sampling device
    #print(this.device_measure_type_ids)
    for dmtid in this.device_measure_type_ids:
        if dmtid in measurement_type_id:
            qc_mask |= qc_mask_22

    # Is the measurement type id of abundance
    for abundanceid in this.abundance_measure_type_ids:
        if abundanceid in measurement_type_id:
            qc_mask |= qc_mask_23

    # Is the measurement type id of abiotic

    for abioticid in this.abiotic_measure_type_ids:
        if abioticid in measurement_type_id:
            qc_mask |= qc_mask_24


    # Is it the measurement of a sample size - do not check if found
    if not found:
        for smtid in this.sample_size_measure_type_ids:
            if smtid in measurement_type_id:
                found = True
                qc_mask |= qc_mask_16

    # Is it a head count - do not check if found
    if not found:
        for cmtid in this.count_measure_type_ids:
            if cmtid in measurement_type_id:
                found = True
                qc_mask |= qc_mask_14

    # Does the measurement contain the gender - and check validity of value
    if not found:
        if isinstance(measurement_value, str):
            for smtid in this.sex_field_measure_type_ids:
                if smtid in measurement_type_id:
                    for m_v in this.sex_field_values:
                        # Always use lowercase
                        if m_v in measurement_value.lower():
                            qc_mask |= qc_mask_17

    return qc_mask


def check_mt(measurement_type, measurement_value):
    """ FOR eMoF records.
        Verifies that the measurement value is not none,
        if one of the sought measurement
        types is present, then the QC is passed
        :param measurement_type - as in the record
        :param measurement_value - as in the record
        purpose: attempt optimization
        returns: 0 or one or more of the bitmasks 14, 15, 16, 17 or 22 """

    qc_mask = 0
    found = False

    if measurement_value is None:
        return qc_mask

    # Is the measurement type id of a biomass weight
    for wmt in this.weight_measure_types:
        if wmt in measurement_type:
            found = True
            qc_mask |= qc_mask_15

    # Is the measurement type id of a sampling device
    for dmtid in this.device_measure_types:
        if dmtid in measurement_type:
            qc_mask |= qc_mask_22

    # Is the measurement type id of abundance
    for abundanceid in this.abundance_measure_types:
        if abundanceid in measurement_type:
            qc_mask |= qc_mask_23

    # Is the measurement type id of abiotic
    for abioticid in this.abiotic_measure_types:
        if abioticid in measurement_type:
            qc_mask |= qc_mask_24


    # Is it the measurement of a sample size
    if not found:
        for smt in this.sample_size_measure_types:
            if smt in measurement_type:
                found = True
                qc_mask |= qc_mask_16

    # Is it a head count
    if not found:
        for cmt in this.count_measure_types:
            if cmt in measurement_type:
                found = True
                qc_mask |= qc_mask_14

    # Does it concern the gender/sex - and check the values
    if not found:
        for sex_mt in this.sex_field_measure_types:
            if sex_mt in measurement_type:
                for m_v in this.sex_field_values:
                    if m_v in measurement_value:
                        qc_mask |= qc_mask_17

    return qc_mask


def check_record(record):
    """ Applies the sampling verifications, input should be a
        eMoF record or one containing the requested fields
        if the a measure is found but the measurementValue is null
        then QC is not passed
        :param - record
        returns: 0 or one of the bitmasks 14, 15, 16 or 17 """

    qc_mask = 0

    # It shall be done only once on the first entry
    if not this.lookups_loaded:
        initialize_lookups()

    # Starting with IDs
    #print(record)
    if "measurementTypeID" in record and record["measurementTypeID"] is not None:
        measurement_value = None if "measurementValue" not in record else record["measurementValue"]
        if isinstance(measurement_value, str):
            measurement_value = None if not measurement_value.strip() else measurement_value
        if measurement_value is not None:
            qc_mask |= check_mtid(record["measurementTypeID"].lower(), measurement_value)

    # ID measurement did not give any result, if we have a measurement type - we try.
    if not qc_mask:
        if "measurementType" in record and record["measurementType"] is not None:
            measurement_value = None if "measurementValue" not in record else record["measurementValue"]
            if isinstance(measurement_value, str):
                measurement_value = None if not measurement_value.strip() else measurement_value
            if measurement_value is not None:
                qc_mask |= check_mt(record["measurementType"].lower(), measurement_value)

    return qc_mask


def check_sex_record(record):
    """ The sex field is only present in the occurrence records,
        so use on occurrence only. It makes sense to separate
        :param record (type should be occurrence)
        :returns  or QC 17 bitmask """

    qc_mask = 0

    # It shall be done only once on the first entry
    if not this.lookups_loaded:
        initialize_lookups()

    # We still have to look at sex (for occurrence records)
    if "sex" in record:
        if record["sex"] is not None:
            value = record['sex']
            if isinstance(value, str):
                if value.lower() in this.sex_field_values:
                    qc_mask |= qc_mask_17

    return qc_mask


# Modified to Quality mask instead of error mask
def check_dyn_prop_record(record):
    """ runs the checks for dynamic property on the occurrence records
        :param record

        """
    # This is a check on the properties field - to be done on the occurrence records
    qc_mask = 0

    # It shall be done only once on the first entry
    if not this.lookups_loaded:
        initialize_lookups()

    if "dynamicProperties" in record and record["dynamicProperties"] is not None:

        # split up the value and make a dict
        properties = misc.string_to_dict(record["dynamicProperties"].strip())
        # If malformed, then skip
        if "conversion_fail" not in properties:

            for k in properties.keys():
                # We test each key againsts all possibilities
                key = k.lower()

                for cmt in this.count_measures:
                    if cmt in key:
                        if properties[k] is not None:
                            if isinstance(properties[k], str):
                                if properties[k].strip():
                                    qc_mask |= qc_mask_14  # It is a non empty string
                            else:
                                qc_mask |= qc_mask_14  # It is another value type

                for wmt in this.weight_measures:
                    if wmt in key:
                        if properties[k] is not None:
                            if isinstance(properties[k], str):
                                if properties[k].strip():
                                    qc_mask |= qc_mask_15  # It is a non empty string
                            else:
                                qc_mask |= qc_mask_15  # It is another value type

                for smt in this.sample_size_measures:
                    if smt in key:
                        if properties[k] is not None:
                            if isinstance(properties[k], str):
                                if properties[k].strip():
                                    qc_mask |= qc_mask_16  # It is a non empty string
                            else:
                                qc_mask |= qc_mask_16  # It is another value type

                for dmt in this.device_measures:
                    if dmt in key:
                        if properties[k] is not None:
                            if isinstance(properties[k], str):
                                if properties[k].strip():
                                    qc_mask |= qc_mask_22  # It is a non empty string
                            else:
                                qc_mask |= qc_mask_22  # It is another value type

                for abundancemt in this.abundance_measures:
                    if abundancemt in key:
                        if properties[k] is not None:
                            if isinstance(properties[k], str):
                                if properties[k].strip():
                                    qc_mask |= qc_mask_23  # It is a non empty string
                            else:
                                qc_mask |= qc_mask_23  # It is another value type

                for abioticmt in this.abiotic_measures:
                    if abioticmt in key:
                        if properties[k] is not None:
                            if isinstance(properties[k], str):
                                if properties[k].strip():
                                    qc_mask |= qc_mask_24  # It is a non empty string
                            else:
                                qc_mask |= qc_mask_24  # It is another value type

                # Can they contain sex? Can they contain the typeIDs?

    return qc_mask


def check_sex(records):
    """ runs the sex check on a list of occurrence records """
    return [check_sex_record(record) for record in records]


def check_dyn_prop(records):
    """ runs the checks for dynamic property on the occurrence records """
    return [check_dyn_prop_record(record) for record in records]


def check(records):
    """ runs the checks for multiple records (of type eMoF) """
    return [check_record(record) for record in records]
