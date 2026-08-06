import pprint

import xmltodict
from eurobisqc.util import misc
from xml.parsers.expat import ExpatError


# Check if there is "good metadata" available in EML file

def flag_metadata(xml_input):
    """ Skeleton file, might needs to have extra checks...

        Good metadata: includes citation, title, license, and abstract with >100 characters.
        EML Standard : https://eml.ecoinformatics.org/schema/
        :returns True when metadata requirements are matched (all) or None
    """
    # Safety measure:
    if xml_input is None:
        return None

    try:
        dict_input = xmltodict.parse(xml_input)
    except ExpatError:
        return None

    # pprint.pprint(dict_input);

    # Abstract + Additional Info
    abs_addinfo_length = 0

    dataset = dict_input['eml:eml']['dataset']

    if 'abstract' in dataset and dataset['abstract'] is not None:
        abs_addinfo_length += len(dataset['abstract']['para'])

    if 'additionalInfo' in dataset and dataset['additionalInfo'] is not None:
        abs_addinfo_length += len(dataset['additionalInfo']['para'])

    if abs_addinfo_length <= 100:
        return None

    # Citation
    if 'citation' in dict_input['eml:eml']['additionalMetadata']['metadata']['gbif']:
        if dict_input['eml:eml']['additionalMetadata']['metadata']['gbif']['citation'] is None:
            return None
    else:
        # No citation
        return None

    # Title
    if 'title' in dict_input['eml:eml']['dataset']:
        if dict_input['eml:eml']['dataset']['title'] is None:
            return None
    else:
        # No title
        return None

    # License: (intellectualRights EML - standard)
    if 'intellectualRights' in dict_input['eml:eml']['dataset']:
        # Possible options are : section, para, markdown!
        if dict_input['eml:eml']['dataset']['intellectualRights'] is None:
            return None
    else:
        # No intellectualRights / license
        return None

    return True
