""" Definition of EUROBIS-QC Flags as per specifications """
from enum import Enum


class QCFlag(Enum):
    """ The quality bitmask shall be determined by the bitmask, second element in the tuple
        includes class and object utility methods """

    REQUIRED_FIELDS_PRESENT = ("All the required fields are present", 1)  # In required_fields
    TAXONOMY_APHIAID_PRESENT = ("AphiaID found", 2)  # In taxonomy_db
    TAXONOMY_RANK_OK = ("Taxon level more detailed than Genus", 3)  # In taxonomy_db
    GEO_LAT_LON_PRESENT = ("Lat and Lon present and not equal to None", 4)  # In location
    GEO_LAT_LON_VALID = ("Lat or Lon present and valid (-90 to 90 and -180 to 180)", 5)  # In location
    GEO_LAT_LON_ON_SEA = ("Lat - Lon on sea / coastline", 6)  # In location
    DATE_TIME_OK = ("Year or Start Year or End Year complete and valid", 7)  # In time_qc
    TAXON_APHIAID_NOT_EXISTING = ("Marine Taxon not existing in APHIA", 8)  # FLAG - Not implemented
    GEO_COORD_AREA = ("Coordinates in one of the specified areas", 9)  # In location
    OBIS_DATAFORMAT_OK = ("Valid codes found in basisOfRecord", 10)  # in required_fields
    VALID_DATE_1 = ("Valid sampling date", 11)  # In time_qc
    VALID_DATE_2 = ("Start sampling date before End date - dates consistent", 12)  # In time_qc
    VALID_DATE_3 = ("Sampling time valid / timezone completed", 13)  # In time_qc
    OBSERVED_COUNT_PRESENT = ("Observed individual count found", 14)  # In measurements
    OBSERVED_WEIGHT_PRESENT = ("Observed weigth found", 15)  # In measurements
    SAMPLE_SIZE_PRESENT = ("Observed individual count > 0 sample size present", 16)  # In measurements
    SEX_PRESENT = ("Sex observation found", 17)  # In measurements
    MIN_MAX_DEPTH_VERIFIED = ("Depths consistent", 18)  # in location
    DEPTH_MAP_VERIFIED = ("Depth coherent with depth map", 19)  # In location
    DEPTH_FOR_SPECIES_OK = ("Depth coherent with species depth range", 20)  # FLAG - Not implemented

    """ [EUROBIS-420] - extra flags """
    COORDINATES_PRECISION_PRESENT = ("Coordinates uncertainty <=5000m", 21)  # In location
    SAMPLE_DEVICE_PRESENT = ("Sampling device present", 22)  # In measurements
    ABUNDANCE_PRESENT = ("Abundance", 23)  # In measurements
    ABIOTIC_MAPPED_PRESENT = ("Abiotic data is mapped to BODC terms", 24)  # In measurements
    GOODMETADATA = ("includes citation, title, license, and abstract + additionalInfo with >100 characters",
                    25)  # On dataset level - extract_metadata.py

    def __init__(self, message, qc_number):

        self.text = message
        self.qc_number = qc_number
        self.bitmask = self.encode(qc_number - 1)

    @staticmethod
    def encode(bit_number):
        """ Returns an integer corresponding to the error code.
            This can be combined to other codes using OR """

        return 1 << bit_number

    @classmethod
    def decode_message(cls, position):
        """ Returns the message of the error corresponding to the bit at position """

        # validity
        if not (0 <= position < len(QCFlag)):
            return "Invalid QC Flag code"

        # May need something more efficient
        for qc_flag in QCFlag:
            if qc_flag.bitmask == position:
                return qc_flag.text

    @classmethod
    def decode_name(cls, position):
        """ Returns the name of the error corresponding to the bit at position """

        # validity
        if not (0 <= position < len(QCFlag)):
            return "Invalid QC Flag code"

        # May need something more efficient
        for qc_flag in QCFlag:
            if qc_flag.bitmask == position:
                return QCFlag(qc_flag).name

    @classmethod
    def decode_mask(cls, mask):
        """ Finds out all flags in a bitmask and return them as a list of QC_Flags names
            adds an INVALID string at the end if the mask is too big """

        qc_flags = []
        sum_all_flags = 0
        for qc_flag in QCFlag:
            if (1 << (qc_flag.qc_number - 1)) & mask:
                qc_flags.append(QCFlag(qc_flag).name)
                sum_all_flags += 1 << qc_flag.bitmask

        # I may get a mask which I cannot fully interpret, in that case I add an INVALID to the list
        if mask > sum_all_flags:
            qc_flags.append('INVALID')

        return qc_flags

    @classmethod
    def decode_numbers(cls, mask):
        """ Finds out all flags in a bitmask and return them as a list of QC_Flags names
            adds an INVALID string at the end if the mask is too big """

        qc_flags = []
        sum_all_flags = 0
        for qc_flag in QCFlag:
            if (1 << (qc_flag.qc_number - 1)) & mask:
                qc_flags.append(qc_flag.qc_number)
                sum_all_flags += 1 << qc_flag.bitmask

        # I may get a mask which I cannot fully interpret, in that case I add an INVALID to the list
        if mask > sum_all_flags:
            qc_flags.append('INVALID')

        return qc_flags

    @classmethod
    def encode_qc(cls, record, error_mask):
        """ Record is a Python dictionary, will be augmented with the QC field
            if not present, error_mask shall be or-red to current value if
            existing """

        if isinstance(record, dict):
            if 'QC' not in record.keys():
                record['QC'] = 0

            record['QC'] |= error_mask
        else:
            return None

        return record
