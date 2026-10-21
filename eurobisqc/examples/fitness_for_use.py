""" Set fitness for use on all records  """

import sys
import logging
from dbworks import mssql_db_functions
from eurobisqc.qc_flags import QCFlag
import pandas as pd

this = sys.modules[__name__]
this.logger = logging.getLogger(__name__)
this.logger.setLevel(logging.DEBUG)
this.logger.addHandler(logging.StreamHandler())

this.dataset_qc = []
this.list_c = []
this.list_b = []
this.list_a1 = []
this.list_a2 = []
this.list_a3 = []
this.list_aplus1 = []
this.list_aplus2 = []
this.list_aplus3 = []

# For one provider, use "dataprovider_id = 1471".
# For a selection, use "dataprovider_id IN (1470, 1472, 1475)".
# For a range, use "dataprovider_id >= 1470 AND dataprovider_id <= 1476"
# For all providers, use "1=1" (no filter).
this.provider_filter = "dataprovider_id >= 1470 AND dataprovider_id <= 1476"
this.sql_all_qc = (
    f"SELECT DISTINCT qc FROM eurobis WHERE {this.provider_filter} ORDER BY qc ASC"
)


def grab_qcs(sql_string):
    """ Queries the database to retrieve a list of all datasets with records
        in eurobis IMPORTANT, datasets are sorted """

    if mssql_db_functions.conn is None:
        this.conn = mssql_db_functions.open_db()

    if this.conn is not None:
        cursor = this.conn.cursor()
        cursor.execute(sql_string)

        for row in cursor:
            this.dataset_qc.append(row[0])
    else:
        this.logger.error("No DB connection!")
        exit(0)


def process_qcs_db():
    """ Processes the entire DB either using multiprocessing or not """
    this.logger.debug(f"Starting fitness-for-use labeling")
    grab_qcs(this.sql_all_qc)

    # this.dataset_qc.remove(0)
    # this.dataset_qc.remove(None)
    # print(len(this.dataset_qc))
    # exit(0)

    qc_id = 0
    all_flags = {}
    c = 0
    b = 0
    a1 = 0
    a2 = 0
    a3 = 0
    aplus1 = 0
    aplus2 = 0
    aplus3 = 0

    for qc in this.dataset_qc:
        flags = QCFlag.decode_mask(qc)
        all_flags[qc] = flags
        print('--')
        print(flags)

        for fitness_id, listFlags in this.labels.items():
            # print(fitness_id)
            if set(listFlags) <= set(flags):
                qc_id = fitness_id
                if qc_id == 1:
                    this.list_aplus1.append(qc)
                    aplus1 += 1
                    break
                if qc_id == 2:
                    this.list_aplus2.append(qc)
                    aplus2 += 1
                    break
                if qc_id == 3:
                    this.list_aplus3.append(qc)
                    aplus3 += 1
                    break
                if qc_id == 4:
                    this.list_a1.append(qc)
                    a1 += 1
                    break
                if qc_id == 5:
                    this.list_a2.append(qc)
                    a2 += 1
                    break
                if qc_id == 6:
                    this.list_a3.append(qc)
                    a3 += 1
                    break
                if qc_id == 7:
                    this.list_b.append(qc)
                    b += 1
                    break
                if qc_id == 8:
                    this.list_c.append(qc)
                    c += 1
                    break

    print('Total unique QC values', len(this.dataset_qc))
    print("aplus1", aplus1)
    print("aplus2", aplus2)
    print("aplus3", aplus3)
    print("a1", a1)
    print("a2", a2)
    print("a3", a3)
    print("b", b)
    print("c", c)

    print(this.list_c)


# this.logger.info(all_flags)


def fitness_label():
    """ Define the labels - [EUROBIS-420] """
    qc_c = [
        'GOODMETADATA',
        'COORDINATES_PRECISION_PRESENT',
        'REQUIRED_FIELDS_PRESENT',
        'TAXONOMY_RANK_OK',
        'GEO_LAT_LON_PRESENT',
        'GEO_LAT_LON_VALID',
        'DATE_TIME_OK',
        'VALID_DATE_1',
        'VALID_DATE_2',
    ]
    # 'VALID_DATE_3', - Ruben 21/1/2022

    qc_b = [
        'SAMPLE_SIZE_PRESENT',
        'SAMPLE_DEVICE_PRESENT',
    ]
    qc_b.extend(qc_c)

    qc_a1 = [
        'ABUNDANCE_PRESENT',
    ]
    qc_a1.extend(qc_b)

    qc_a2 = [
        'OBSERVED_WEIGHT_PRESENT',
    ]
    qc_a2.extend(qc_b)

    qc_a3 = [
        'OBSERVED_COUNT_PRESENT',
    ]
    qc_a3.extend(qc_b)

    qc_aplus1 = [
        'ABIOTIC_MAPPED_PRESENT',
    ]
    qc_aplus1.extend(qc_a1)

    qc_aplus2 = [
        'ABIOTIC_MAPPED_PRESENT',
    ]
    qc_aplus2.extend(qc_a2)

    qc_aplus3 = [
        'ABIOTIC_MAPPED_PRESENT',
    ]
    qc_aplus3.extend(qc_a3)

    this.labels = {
        1: qc_aplus1,
        2: qc_aplus2,
        3: qc_aplus3,
        4: qc_a1,
        5: qc_a2,
        6: qc_a3,
        7: qc_b,
        8: qc_c,
    }
    print(this.labels)


""" Always on the occurence record QC label - events are nog lablled 

"""


def save_labels():
    print("START...")
    this.conn = mssql_db_functions.conn
    if this.conn is None:
        this.conn = mssql_db_functions.open_db()

    if this.conn is not None:
        cursor = this.conn.cursor()

        # Records that do not qualify for any label must use SQL NULL.
        labelled_qcs = (
            this.list_c + this.list_b + this.list_a1 + this.list_a2 + this.list_a3
            + this.list_aplus1 + this.list_aplus2 + this.list_aplus3
        )
        qry_unlabelled = (
            f"UPDATE eurobis SET fitness_label_id = NULL WHERE ({this.provider_filter})"
        )
        if labelled_qcs:
            qc_values = ",".join(map(str, labelled_qcs))
            qry_unlabelled += f" AND (qc IS NULL OR qc NOT IN ({qc_values}))"
        cursor.execute(qry_unlabelled)
        this.conn.commit()

        if len(this.list_c):
            print("Updating C")
            c_qcs = ",".join(map(str, this.list_c))
            qry_c = f"UPDATE eurobis set fitness_label_id = 4 where ({this.provider_filter}) AND qc in ({c_qcs})"
            cursor.execute(qry_c)
            this.conn.commit()
        if len(this.list_b):
            print("Updating B")
            b_qcs = ",".join(map(str, this.list_b))
            qry_b = f"UPDATE eurobis set fitness_label_id = 3 where ({this.provider_filter}) AND qc in ({b_qcs})"
            cursor.execute(qry_b)
            this.conn.commit()
        if len(this.list_a1):
            print("Updating A")
            a_qcs1 = ",".join(map(str, this.list_a1))
            qry_a = f"UPDATE eurobis set fitness_label_id = 2 where ({this.provider_filter}) AND qc in ({a_qcs1})"
            cursor.execute(qry_a)
            this.conn.commit()
        if len(this.list_a2):
            print("Updating A")
            a_qcs2 = ",".join(map(str, this.list_a2))
            qry_a = f"UPDATE eurobis set fitness_label_id = 2 where ({this.provider_filter}) AND qc in ({a_qcs2})"
            cursor.execute(qry_a)
            this.conn.commit()
        if len(this.list_a3):
            print("Updating A")
            a_qcs3 = ",".join(map(str, this.list_a3))
            qry_a = f"UPDATE eurobis set fitness_label_id = 2 where ({this.provider_filter}) AND qc in ({a_qcs3})"
            cursor.execute(qry_a)
            this.conn.commit()
        aplus_qc_values = this.list_aplus1 + this.list_aplus2 + this.list_aplus3
        if aplus_qc_values:
            print("Updating A+")
            aplus_qcs = ",".join(map(str, aplus_qc_values))
            qry_aplus = f"UPDATE eurobis set fitness_label_id = 1 where ({this.provider_filter}) AND qc in ({aplus_qcs})"
            cursor.execute(qry_aplus)
            this.conn.commit()

    print("...DONE")


def calc_datasets():
    sql_string = (
        "SELECT dataprovider_id, fitness_label_id, count(*) AS amount FROM eurobis "
        f"WHERE {this.provider_filter} "
        "GROUP BY dataprovider_id, fitness_label_id ORDER BY dataprovider_id ASC"
    )

    this.conn = mssql_db_functions.conn
    if this.conn is None:
        this.conn = mssql_db_functions.open_db()

    if this.conn is None:
        raise ConnectionError('Cannot calculate FFU labels: no DB connection.')

    df = pd.read_sql(sql_string, this.conn)
    df.to_csv('result.csv', index=False)
    if df.empty:
        this.logger.info('No records found for the selected providers.')
        return


    # print(df.groupby('dataprovider_id')['amount'].sum()[0])
    # print(df)


    # df = pd.read_csv('result.csv')
    # Zero is only a grouping value in memory; it is never saved as a label ID.
    df['fitness_label_id'] = df['fitness_label_id'].fillna(0)

    # TOTALSUM PER PROVIDER_ID
    y = df.groupby(['dataprovider_id'], as_index=False)['amount'].sum()

    # TOTALSUM PER PROVIDER_ID / FITNESS LABEL (NaN -> 0)
    x = df.groupby(['dataprovider_id', 'fitness_label_id'], as_index=False)['amount'].sum()

    df = df.merge(y, how='left', on='dataprovider_id')
    df = df.merge(x, how='left', on=['dataprovider_id', 'fitness_label_id'])
    df.drop(labels='amount_x', axis=1, inplace=True)
    df.drop_duplicates(subset=['dataprovider_id', 'fitness_label_id', 'amount_y'], keep='last', inplace=True)
    df['percentage'] = df['amount'] / df['amount_y'] * 100

    # Choose the highest label
    counts = df.pivot_table(
        index='dataprovider_id', columns='fitness_label_id',
        values='amount', aggfunc='sum', fill_value=0,
    ).reindex(columns=[1, 2, 3, 4], fill_value=0)

    totals = df.groupby('dataprovider_id')['amount'].sum()
    qualifying_a = counts[1] + counts[2]
    qualifying_b = qualifying_a + counts[3]
    qualifying_c = qualifying_b + counts[4]

    ffu = pd.Series('Unlabelled', index=totals.index)
    ffu.loc[qualifying_c > totals / 2] = 'C'
    ffu.loc[qualifying_b > totals / 2] = 'B'
    ffu.loc[qualifying_a > totals / 2] = 'A'

    df['ffu'] = df['dataprovider_id'].map(ffu)

    z = df.loc[df['percentage'] != 100]
    f = z.loc[z['fitness_label_id'] == 2]

    # print(z.head(30))
    print(f.head(30))
    print(df.head(30))


fitness_label()
process_qcs_db()
save_labels()
calc_datasets()
