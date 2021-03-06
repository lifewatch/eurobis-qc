""" Replacing the taxonomy checks with verifications performed directly on
    the lookup-db database (in SQLLite format in a first attempt)
    """
import sys
from dbworks import sqlite_db_functions

from eurobisqc import qc_flags
from eurobisqc.util import misc

this = sys.modules[__name__]

# Masks used to build the return value when the quality check fails
qc_mask_2 = qc_flags.QCFlag.TAXONOMY_APHIAID_PRESENT.bitmask  # Is the AphiaID Completed
qc_mask_3 = qc_flags.QCFlag.TAXONOMY_RANK_OK.bitmask  # Is the Taxon Level lower than the family

# error_mask_8 = qc_flags.QCFlag.TAXON_APHIAID_NOT_EXISTING. bitmask # Unclear how to do this one

this.taxon_fields = []
# this.speciesprofile_fields = []
this.taxon_fields_sought = ["genus"]


# Retrieve fields from lookup-db, call it only once, open the DB in advance
def populate_fields():
    """ Populate the taxon_fields and speciesprofile_fields - only once
        from the worms database assumes con is an active connection to
        the database """

    if sqlite_db_functions.conn is None:
        conn = sqlite_db_functions.open_db()
        if conn is None:
            return

    # Used for populating the field names
    sample_taxon = 'urn:lsid:marinespecies.org:taxname:519212'
    cur = sqlite_db_functions.conn.execute(f"SELECT * from taxon where scientificNameID='{sample_taxon}'")
    taxons = [description[0] for description in cur.description]
    this.taxon_fields.extend(taxons)
    # cur = sqlite_db_functions.conn.execute(f"SELECT * from speciesprofile where taxonID='{sample_taxon}'")
    # speciesprofiles = [description[0] for description in cur.description]
    # this.speciesprofile_fields.extend(speciesprofiles)


# Modified to Quality mask instead of error mask
def check_record(record):
    # error mask
    qc_mask = 0
    sn_id = 0  # To mark whether the scientificNameID is valid

    # Can we retrieve the aphiaID with scientificNameID?
    if "scientificNameID" in record and record["scientificNameID"] is not None:

        # Have something to query
        if len(this.taxon_fields) == 0:
            populate_fields()

        # Can query DB with sientificNameID
        aphiaid = misc.parse_lsid(record["scientificNameID"])

        if aphiaid is not None:  # Verify that the aphiaid retrieved is valid

            taxon_record = sqlite_db_functions.get_fields_of_record('taxon', 'scientificNameID',
                                                                    record['scientificNameID'],
                                                                    this.taxon_fields_sought)

            # Have we got a record
            if taxon_record is not None:
                sn_id = True
                qc_mask |= qc_mask_2
                if taxon_record['genus'] is not None:
                    qc_mask |= qc_mask_3

    if not sn_id:  # We still have a chance to verify by scientificName

        # No Aphiaid Attempt to query by scientificName
        if "scientificName" in record and record["scientificName"] is not None:

            # Have something to query
            if len(this.taxon_fields) == 0:
                populate_fields()

            # Have something to query upon
            taxon_record = sqlite_db_functions.get_fields_of_record('taxon', 'scientificName',
                                                                    record['scientificName'], this.taxon_fields_sought)

            # Have we got a record
            if taxon_record is not None:
                qc_mask |= qc_mask_2
                if taxon_record['genus'] is not None:
                    # We would not be here if scientificNameID was able to resolve
                    qc_mask |= qc_mask_3

    else:
        pass  # We have already an aphiaid from the scientificNameId

    return qc_mask


def check(records):
    """ Checks a list of records for taxonomy """

    # Ensure DB is available
    if sqlite_db_functions.conn is None:
        sqlite_db_functions.open_db()  # It shall be closed on exit

    results = [check_record(record) for record in records]
    return results
